#include "SPRideCapture.h"
#include "FrameGrabber.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "ImageWriteQueue.h"
#include "ImageWriteTask.h"
#include "ImageUtils.h"
#include "Framework/Application/SlateApplication.h"
#include "Layout/ArrangedChildren.h"
#include "Layout/WidgetPath.h"
#include "Widgets/SViewport.h"
#include "Widgets/SWindow.h"
#include "HAL/FileManager.h"
#include "Misc/DateTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "HAL/IConsoleManager.h"

namespace
{
    TAutoConsoleVariable<float> CVarRideCaptureRate(TEXT("sp.RideCapture.FPS"), 8.f,
        TEXT("Requested diagnostic viewport capture rate (1 to 30). The manifest reports actual frames."));
    constexpr double StopTimeoutSeconds = 5.0;
    const FIntPoint OutputSize(960, 540);

    // Match FFrameGrabber's window-relative capture rectangle, including DPI
    // and an embedded PIE viewport. GetSize() alone can differ from this rect.
    bool CaptureGeometry(const TSharedRef<FSceneViewport>& Viewport, FIntRect& Rect,
        FIntPoint& ViewportSize, FIntPoint& WindowSize)
    {
        ViewportSize = Viewport->GetSize();
        auto Widget = Viewport->GetViewportWidget().Pin();
        if (!FSlateApplication::IsInitialized() || !Widget.IsValid()) return false;
        auto Window = FSlateApplication::Get().FindWidgetWindow(Widget.ToSharedRef());
        if (!Window.IsValid()) return false;
        const FGeometry WindowGeometry = Window->GetWindowGeometryInWindow();
        FArrangedChildren Children(EVisibility::Visible);
        Children.AddWidget(FArrangedWidget(Window.ToSharedRef(), WindowGeometry));
        FWidgetPath Path(Window.ToSharedRef(), Children);
        if (!Path.ExtendPathTo(FWidgetMatcher(Widget.ToSharedRef()), EVisibility::Visible)) return false;
        const auto Arranged = Path.FindArrangedWidget(Widget.ToSharedRef());
        if (!Arranged.IsSet()) return false;
        const FVector2D Position = Arranged.GetValue().Geometry.GetAbsolutePosition();
        const FVector2D Size = Arranged.GetValue().Geometry.GetAbsoluteSize();
        Rect = FIntRect(int32(Position.X), int32(Position.Y),
            int32(Position.X + Size.X), int32(Position.Y + Size.Y));
        const FVector2D WindowPixels = WindowGeometry.GetAbsoluteSize();
        WindowSize = FIntPoint(int32(WindowPixels.X), int32(WindowPixels.Y));
        return Rect.Width() > 0 && Rect.Height() > 0 && ViewportSize.X > 0 && ViewportSize.Y > 0;
    }

    FIntRect OutputContentRect(FIntPoint SourceSize)
    {
        const double Scale = FMath::Min(double(OutputSize.X) / SourceSize.X, double(OutputSize.Y) / SourceSize.Y);
        const FIntPoint Fitted(FMath::Clamp(FMath::RoundToInt(SourceSize.X * Scale), 1, OutputSize.X),
            FMath::Clamp(FMath::RoundToInt(SourceSize.Y * Scale), 1, OutputSize.Y));
        const FIntPoint Offset((OutputSize.X - Fitted.X) / 2, (OutputSize.Y - Fitted.Y) / 2);
        return FIntRect(Offset, Offset + Fitted);
    }
    struct FSPCapturePayload : IFramePayload
    {
        int32 Index;
        double Seconds;
        FSPCapturePayload(int32 InIndex, double InSeconds) : Index(InIndex), Seconds(InSeconds) {}
    };
}

FSPRideCapture::FSPRideCapture() = default;
FSPRideCapture::~FSPRideCapture() { Stop(); }

bool FSPRideCapture::Start()
{
    Stop();
    Writes.Reset(); Error.Empty(); Directory.Empty();
    Requested = Skipped = 0;
    NextFrame = Duration = 0;
    StopStarted = 0;
    bPassed = false;
    bStopping = bStopTimedOut = false;
    CaptureInterval = 1.0 / FMath::Clamp(double(CVarRideCaptureRate.GetValueOnGameThread()), 1., 30.);
    if (!GEngine || !GEngine->GameViewport) { Error = TEXT("No game viewport."); return false; }
    auto Widget = GEngine->GameViewport->GetGameViewportWidget();
    auto Viewport = Widget.IsValid() ? Widget->GetViewportInterface().Pin() : nullptr;
    if (!Viewport.IsValid() || Viewport.Get() != static_cast<ISlateViewport*>(GEngine->GameViewport->GetGameViewport()))
    { Error = TEXT("The game viewport cannot be captured."); return false; }
    const auto SceneViewport = StaticCastSharedRef<FSceneViewport>(Viewport.ToSharedRef());
    if (!CaptureGeometry(SceneViewport, NativeCaptureRect, NativeViewportSize, NativeWindowSize))
    { Error = TEXT("The viewport capture rectangle is unavailable."); return false; }
    Queue = &FModuleManager::LoadModuleChecked<IImageWriteQueueModule>(TEXT("ImageWriteQueue")).GetWriteQueue();
    Directory = FPaths::ProjectSavedDir() / TEXT("Diagnostics") /
        (TEXT("video-") + FDateTime::UtcNow().ToString(TEXT("%Y%m%d-%H%M%S")) + TEXT("-") + FGuid::NewGuid().ToString(EGuidFormats::Short));
    IFileManager::Get().MakeDirectory(*Directory, true);
    // UE 5.8 normalizes DrawRectangle by CaptureRect.Size(), not the requested
    // target size. A smaller target renders only a fraction of that target.
    // Read at the exact capture size, then resize on the image writer worker.
    Grabber = MakeUnique<FFrameGrabber>(SceneViewport, NativeCaptureRect.Size());
    Grabber->StartCapturingFrames();
    return true;
}

void FSPRideCapture::Tick(double Seconds)
{
    if (!Grabber || bStopping) return;
    Duration = Seconds;
    auto Widget = GEngine && GEngine->GameViewport ? GEngine->GameViewport->GetGameViewportWidget() : nullptr;
    auto Viewport = Widget.IsValid() ? Widget->GetViewportInterface().Pin() : nullptr;
    FIntRect CurrentRect;
    FIntPoint CurrentViewport, CurrentWindow;
    if (!Viewport.IsValid() || Viewport.Get() != static_cast<ISlateViewport*>(GEngine->GameViewport->GetGameViewport()) ||
        !CaptureGeometry(StaticCastSharedRef<FSceneViewport>(Viewport.ToSharedRef()), CurrentRect, CurrentViewport, CurrentWindow) ||
        CurrentRect != NativeCaptureRect || CurrentViewport != NativeViewportSize || CurrentWindow != NativeWindowSize)
    {
        Error = TEXT("The viewport geometry changed during capture. Start a new diagnostic after resizing.");
        Stop();
        return;
    }
    Drain();
    if (Seconds >= NextFrame)
    {
        // Record missing capture slots instead of slowing the simulation or
        // fabricating repeated frames. The manifest retains real capture times.
        Skipped += FMath::Max(0, FMath::FloorToInt((Seconds - NextFrame) / CaptureInterval));
        NextFrame = Seconds + CaptureInterval;
        if (Queue->GetNumPendingTasks() >= 16) { ++Skipped; return; }
        Grabber->CaptureThisFrame(MakeShared<FSPCapturePayload, ESPMode::ThreadSafe>(Requested++, Seconds));
    }
}

void FSPRideCapture::Drain()
{
    for (FCapturedFrameData& Frame : Grabber->GetCapturedFrames())
    {
        auto* Payload = Frame.GetPayload<FSPCapturePayload>();
        if (!Payload || Frame.BufferSize != NativeCaptureRect.Size() ||
            int64(Frame.ColorBuffer.Num()) != int64(Frame.BufferSize.X) * Frame.BufferSize.Y)
        {
            Error = TEXT("The captured pixel buffer does not match the native viewport rectangle.");
            continue;
        }
        FWrite Write;
        Write.Index = Payload->Index;
        Write.Seconds = Payload->Seconds;
        Write.Filename = FString::Printf(TEXT("frame-%06d.jpg"), Write.Index);
        auto Task = MakeUnique<FImageWriteTask>();
        Task->Filename = Directory / Write.Filename;
        Task->Format = EImageFormat::JPEG;
        Task->CompressionQuality = 85;
        Task->bOverwriteFile = false;
        TArray64<FColor> Pixels;
        Pixels.Init(FColor::Black, int64(OutputSize.X) * OutputSize.Y);
        Task->PixelData = MakeUnique<TImagePixelData<FColor>>(OutputSize, MoveTemp(Pixels));
        const FIntPoint SourceSize = Frame.BufferSize;
        const FIntRect ContentRect = OutputContentRect(SourceSize);
        Task->PixelPreProcessors.Emplace(
            [SourcePixels = MoveTemp(Frame.ColorBuffer), SourceSize, ContentRect](FImagePixelData* Data)
            {
                TArray<FColor> Resized;
                FImageUtils::ImageResize(SourceSize.X, SourceSize.Y, SourcePixels,
                    ContentRect.Width(), ContentRect.Height(), Resized, true, true);
                auto& Destination = static_cast<TImagePixelData<FColor>*>(Data)->Pixels;
                for (int32 Row = 0; Row < ContentRect.Height(); ++Row)
                {
                    FMemory::Memcpy(Destination.GetData() + (Row + ContentRect.Min.Y) * OutputSize.X + ContentRect.Min.X,
                        Resized.GetData() + Row * ContentRect.Width(), ContentRect.Width() * sizeof(FColor));
                }
            });
        Write.Result = Queue->Enqueue(MoveTemp(Task), false);
        Writes.Add(MoveTemp(Write));
    }
}

void FSPRideCapture::BeginStop()
{
    if (!Grabber || bStopping) return;
    bStopping = true;
    StopStarted = FPlatformTime::Seconds();
    // PendingShutdown keeps the viewport-present delegate alive. Shutdown()
    // here would drop a payload requested in this world's final tick.
    Grabber->StopCapturingFrames();
}

bool FSPRideCapture::PollStop()
{
    if (!Grabber) return true;
    BeginStop();
    Drain();
    const bool bWritesPending = Writes.ContainsByPredicate([](const FWrite& Write)
        { return Write.Result.IsValid() && !Write.Result.IsReady(); });
    if (Grabber->HasOutstandingFrames() || bWritesPending)
    {
        if (FPlatformTime::Seconds() - StopStarted < StopTimeoutSeconds) return false;
        bStopTimedOut = true;
        if (Error.IsEmpty()) Error = TEXT("Capture finalization exceeded its 5-second deadline. Pending frames or writes are incomplete.");
    }
    Stop();
    return true;
}

void FSPRideCapture::Stop()
{
    if (!Grabber) return;
    BeginStop();
    Drain();
    if (Grabber->HasOutstandingFrames() && Error.IsEmpty())
        Error = TEXT("Capture teardown occurred before all requested viewport frames arrived.");
    Grabber->Shutdown();
    Drain();
    Grabber.Reset();
    bStopping = false;
    auto Root = MakeShared<FJsonObject>();
    TArray<TSharedPtr<FJsonValue>> Frames;
    int32 Failed = 0, PendingWrites = 0;
    Writes.Sort([](const FWrite& A, const FWrite& B) { return A.Index < B.Index; });
    for (FWrite& Write : Writes)
    {
        const bool bPending = Write.Result.IsValid() && !Write.Result.IsReady();
        PendingWrites += bPending;
        // Never block the game thread on an image-write future. A write that
        // finishes after the deadline does not make this frozen result pass.
        const bool bSaved = Write.Result.IsValid() && !bPending && Write.Result.Get();
        Failed += !bSaved;
        auto Row = MakeShared<FJsonObject>();
        Row->SetNumberField(TEXT("index"), Write.Index);
        Row->SetNumberField(TEXT("seconds"), Write.Seconds);
        Row->SetStringField(TEXT("file"), Write.Filename);
        Row->SetBoolField(TEXT("saved"), bSaved);
        Row->SetBoolField(TEXT("pending_at_finalization"), bPending);
        Frames.Add(MakeShared<FJsonValueObject>(Row));
    }
    if (PendingWrites > 0 && Error.IsEmpty()) Error = TEXT("Capture teardown occurred before all image writes finished.");
    bPassed = Error.IsEmpty() && Requested > 0 && Writes.Num() == Requested && Failed == 0 && Skipped == 0;
    Root->SetBoolField(TEXT("capture_complete"), bPassed);
    Root->SetStringField(TEXT("scope"), TEXT("Application viewport only; native-size readback resized on the image writer worker to 960x540 JPEG. The full viewport fits without cropping; non-16:9 views have centred black margins. This is a visual record, not a clean performance benchmark or proof of route completion."));
    Root->SetNumberField(TEXT("requested_capture_fps"), 1.0 / CaptureInterval);
    Root->SetStringField(TEXT("error"), Error);
    Root->SetNumberField(TEXT("source_width"), NativeCaptureRect.Width());
    Root->SetNumberField(TEXT("source_height"), NativeCaptureRect.Height());
    Root->SetNumberField(TEXT("scene_viewport_width"), NativeViewportSize.X);
    Root->SetNumberField(TEXT("scene_viewport_height"), NativeViewportSize.Y);
    Root->SetNumberField(TEXT("output_width"), OutputSize.X);
    Root->SetNumberField(TEXT("output_height"), OutputSize.Y);
    const FIntRect ContentRect = OutputContentRect(NativeCaptureRect.Size());
    Root->SetNumberField(TEXT("content_x"), ContentRect.Min.X);
    Root->SetNumberField(TEXT("content_y"), ContentRect.Min.Y);
    Root->SetNumberField(TEXT("content_width"), ContentRect.Width());
    Root->SetNumberField(TEXT("content_height"), ContentRect.Height());
    Root->SetNumberField(TEXT("duration_seconds"), Duration);
    Root->SetNumberField(TEXT("requested_frames"), Requested);
    Root->SetNumberField(TEXT("missing_frames"), Requested - Writes.Num());
    Root->SetNumberField(TEXT("failed_writes"), Failed);
    Root->SetNumberField(TEXT("skipped_slots"), Skipped);
    Root->SetNumberField(TEXT("pending_writes_at_finalization"), PendingWrites);
    Root->SetNumberField(TEXT("finalization_wall_seconds"), FPlatformTime::Seconds() - StopStarted);
    Root->SetNumberField(TEXT("finalization_timeout_seconds"), StopTimeoutSeconds);
    Root->SetBoolField(TEXT("finalization_timed_out"), bStopTimedOut);
    Root->SetArrayField(TEXT("frames"), Frames);
    FString Json;
    FJsonSerializer::Serialize(Root, TJsonWriterFactory<>::Create(&Json));
    if (!FFileHelper::SaveStringToFile(Json, *(Directory / TEXT("capture.json"))))
    { bPassed = false; Error = TEXT("Capture manifest could not be saved."); }
}
