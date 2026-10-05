#include "SPReleaseCheck.h"
#include "SPBicyclePawn.h"
#include "SPExplorerCharacter.h"
#include "SPHud.h"
#include "SPWorldDirector.h"
#include "SPWaterSafety.h"
#include "Components/CapsuleComponent.h"
#include "EngineUtils.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "InputKeyEventArgs.h"
#include "Kismet/GameplayStatics.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Engine/GameViewportClient.h"
#include "UnrealClient.h"
#include "DynamicRHI.h"
#include "RenderTimer.h"
#include "HAL/PlatformMemory.h"
#include "HAL/PlatformProcess.h"
#include "HAL/IConsoleManager.h"
#include "HAL/FileManager.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "Misc/DateTime.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"

ASPReleaseCheck::ASPReleaseCheck()
{
    PrimaryActorTick.bCanEverTick = true;
    PrimaryActorTick.bTickEvenWhenPaused = true;
}

void ASPReleaseCheck::BeginPlay()
{
    Super::BeginPlay();
    Started = FPlatformTime::Seconds();
    Output = FPaths::ProjectSavedDir() / TEXT("ReleaseCheck/result.json");
    FParse::Value(FCommandLine::Get(), TEXT("SPReleaseCheckOutput="), Output);
    Output = FPaths::ConvertRelativePathToFull(Output);
    IFileManager::Get().MakeDirectory(*FPaths::GetPath(Output), true);
    bProfileOnly = FParse::Param(FCommandLine::Get(), TEXT("SPProfileOnly"));
    bShortRideOnly = FParse::Param(FCommandLine::Get(), TEXT("SPShortRideOnly"));
    bWaterOnly = FParse::Param(FCommandLine::Get(), TEXT("SPWaterOnly"));
    Result = MakeShared<FJsonObject>();
    Result->SetStringField(TEXT("started_utc"), FDateTime::UtcNow().ToIso8601());
    Result->SetStringField(TEXT("scope"), bProfileOnly ? TEXT("30-second stationary standalone sample after 10-second warm-up")
        : bShortRideOnly ? TEXT("Local F9 diagnostic through mapped inputs; no full-route acceptance")
        : bWaterOnly ? TEXT("Explicit submerged explorer and bicycle fixtures; verify return to last dry ground")
        : TEXT("Mapped-input local explorer/bicycle smoke check; no full-route acceptance"));
    Result->SetStringField(TEXT("map"), GetWorld()->GetMapName());
    Result->SetNumberField(TEXT("process_id"), FPlatformProcess::GetCurrentProcessId());
}

void ASPReleaseCheck::Key(const FKey& Button, bool Down)
{
    if (APlayerController* Player = GetWorld()->GetFirstPlayerController())
        Player->InputKey(FInputKeyEventArgs::CreateSimulated(Button, Down ? IE_Pressed : IE_Released, Down ? 1.f : 0.f));
}
void ASPReleaseCheck::Tap(const FKey& Button) { Key(Button, true); ReleaseNextTick.Add(Button); }
void ASPReleaseCheck::Check(const FString& Name, bool Passed)
{
    TSharedPtr<FJsonObject> Item = MakeShared<FJsonObject>();
    Item->SetStringField(TEXT("check"), Name); Item->SetBoolField(TEXT("passed"), Passed);
    Checks.Add(MakeShared<FJsonValueObject>(Item));
    UE_LOG(LogTemp, Display, TEXT("SP_RELEASE_CHECK: %s %s"), *Name, Passed ? TEXT("PASS") : TEXT("FAIL"));
}
void ASPReleaseCheck::Shot(const FString& Name)
{
    const bool bShowUI = Name == TEXT("settings") || Name == TEXT("controls") || Name == TEXT("pause") || Name == TEXT("ride-end") || Name == TEXT("profile");
    FScreenshotRequest::RequestScreenshot(FPaths::GetPath(Output) / (FPaths::GetBaseFilename(Output) + TEXT("-") + Name + TEXT(".png")), bShowUI, false);
}

bool ASPReleaseCheck::PrepareOffRoadFixture(ASPExplorerCharacter& Explorer)
{
    // Select a short, unobstructed terrain strip using actual collision. Only
    // initial fixture placement is direct; all tested travel uses mapped keys.
    for (TActorIterator<ASPWorldDirector> It(GetWorld()); It; ++It)
    {
        const FSPWorldData& Data = It->GetData();
        const FSPRoute* Route = Data.FindRoute(TEXT("main_circuit"));
        if (!Route) continue;
        for (double Along = 0; Along <= 40000; Along += 2500)
        {
            FVector Tangent;
            const FVector Centre = Route->Sample(FMath::Min(Route->Length - 2500., Data.ReviewStartMetres * 100 + Along), &Tangent);
            Tangent.Z = 0; Tangent.Normalize();
            const FVector Side(-Tangent.Y, Tangent.X, 0);
            for (const double Offset : {600., -600., 1000., -1000., 1600., -1600.})
            {
                FHitResult First; bool Suitable = true;
                for (double Forward = 0; Forward <= 4000; Forward += 250)
                {
                    const FVector Probe = Centre + Side * Offset + Tangent * Forward;
                    FHitResult Hit;
                    FCollisionQueryParams Query(SCENE_QUERY_STAT(ReleaseOffRoadFixture), true, &Explorer);
                    if (!GetWorld()->LineTraceSingleByChannel(Hit, Probe + FVector(0,0,500), Probe - FVector(0,0,500), ECC_WorldStatic, Query)) { Suitable = false; break; }
                    const UStaticMeshComponent* Mesh = Cast<UStaticMeshComponent>(Hit.GetComponent());
                    if (!Mesh || !Mesh->GetStaticMesh() || !Mesh->GetStaticMesh()->GetName().StartsWith(TEXT("SM_Terrain_")) || Hit.ImpactNormal.Z < .96) { Suitable = false; break; }
                    double WaterZ = 0;
                    if (SPWaterSafety::GetSurfaceHeight(Hit.ImpactPoint, WaterZ) && Hit.ImpactPoint.Z < WaterZ + 5) { Suitable = false; break; }
                    if (Forward == 0) First = Hit;
                    else if (FMath::Abs(Hit.ImpactPoint.Z - First.ImpactPoint.Z) > 35) { Suitable = false; break; }
                }
                if (!Suitable) continue;
                Explorer.PlaceOnGround(First.ImpactPoint, Tangent.Rotation().Yaw);
                if (FVector::Dist2D(Explorer.GetActorLocation(), First.ImpactPoint) > 50) continue;
                Result->SetStringField(TEXT("off_road_surface"), First.GetComponent()->GetPathName());
                Result->SetStringField(TEXT("off_road_start_cm"), First.ImpactPoint.ToString());
                Result->SetNumberField(TEXT("off_road_route_offset_cm"), Offset);
                Result->SetStringField(TEXT("fixture_limit"), TEXT("Selected flat terrain strip; does not validate all off-road surfaces or drops."));
                return true;
            }
        }
    }
    return false;
}

void ASPReleaseCheck::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (bFinished)
    {
        if (FParse::Param(FCommandLine::Get(), TEXT("SPExitAfterCheck")) && FPlatformTime::Seconds() - FinishedAt > 2)
            FPlatformMisc::RequestExit(false);
        return;
    }
    for (const FKey& Button : ReleaseNextTick) Key(Button, false);
    ReleaseNextTick.Reset();
    const double Time = FPlatformTime::Seconds() - Started;
    APlayerController* Player = GetWorld()->GetFirstPlayerController();
    if (!Player || !Player->GetPawn()) { if (Time > 15) { Check(TEXT("player_spawn"), false); Finish(); } return; }
    ASPExplorerCharacter* Explorer = Cast<ASPExplorerCharacter>(Player->GetPawn());
    ASPBicyclePawn* Bike = Cast<ASPBicyclePawn>(Player->GetPawn());
    PeakMemory = FMath::Max(PeakMemory, FPlatformMemory::GetStats().UsedPhysical);
    if (bWaterOnly)
    {
        // The generator audit records this ocean-mask fixture near spawn.
        const FVector WetFoot(-78670.803813, 54012.548394, -29.548);
        if (Stage == 0 && Time >= 8 && Explorer)
        {
            double WaterZ = 0;
            Check(TEXT("known_ocean_fixture"), SPWaterSafety::GetSurfaceHeight(WetFoot, WaterZ) && FMath::Abs(WaterZ - 20.452) < .1);
            StartPosition = Explorer->GetActorLocation();
            Explorer->SetActorLocation(WetFoot + FVector(0,0,Explorer->GetCapsuleComponent()->GetScaledCapsuleHalfHeight()));
            ++Stage;
        }
        else if (Stage == 1 && Time >= 10 && Explorer)
        {
            Check(TEXT("explorer_returns_to_dry_ground"), FVector::Distance(StartPosition, Explorer->GetActorLocation()) < 10);
            Shot(TEXT("water-explorer-recovered")); Tap(EKeys::Tab); ++Stage;
        }
        else if (Stage == 2 && Time >= 12 && Bike)
        {
            StartPosition = Bike->GetActorLocation();
            Bike->SetActorLocation(WetFoot + FVector(0,0,70)); ++Stage;
        }
        else if (Stage == 3 && Time >= 14 && Bike)
        {
            Check(TEXT("bike_returns_to_dry_ground"), FVector::Distance(StartPosition, Bike->GetActorLocation()) < 10 && Bike->HasSurface());
            Shot(TEXT("water-bike-recovered")); Finish();
        }
        if (!bFinished && Time > 20) { Check(TEXT("water_recovery_timeout"), false); Finish(); }
        return;
    }
    if (bShortRideOnly)
    {
        if (Stage == 0 && Time >= 8) { if (Explorer) Tap(EKeys::Tab); ++Stage; }
        else if (Stage == 1 && Time >= 10 && Bike) { Tap(EKeys::F9); ++Stage; }
        else if (Stage == 2 && Bike)
        {
            const FString& Status = Bike->GetDiagnosticStatus();
            if (Status.Contains(TEXT("trace saved")) || Status.Contains(TEXT("save failed")))
            {
                Result->SetStringField(TEXT("diagnostic_status"), Status);
                Check(TEXT("local_F9"), Status == TEXT("Ride check passed; trace saved."));
                Shot(TEXT("ride-end")); Finish();
            }
        }
        const double Limit = FParse::Param(FCommandLine::Get(), TEXT("SPGateCheck")) ? 180. :
            FParse::Param(FCommandLine::Get(), TEXT("SPFastRideCheck")) ? 65. : 150.;
        if (!bFinished && Time > Limit) { Check(TEXT("local_F9_timeout"), false); Finish(); }
        return;
    }
    if (bProfileOnly)
    {
        if (Time >= 10 && Time < 40)
        {
            Frames.Add(DeltaSeconds * 1000.);
            Games.Add(FPlatformTime::ToMilliseconds(GGameThreadTime));
            Renders.Add(FPlatformTime::ToMilliseconds(GRenderThreadTime));
            const uint32 Cycles = RHIGetGPUFrameCycles();
            if (Cycles > 0) Gpus.Add(FPlatformTime::ToMilliseconds(Cycles));
        }
        if (Time >= 40) { Shot(TEXT("profile")); Finish(); }
        return;
    }
    if (Explorer && Stage >= 4 && Stage <= 5)
    {
        bSawAir |= Explorer->GetCharacterMovement()->IsFalling();
        JumpHeight = FMath::Max(JumpHeight, Explorer->GetActorLocation().Z - StartPosition.Z);
    }
    // Each state executes once. Measurements use real elapsed time so a paused
    // UI cannot stall the check. Only the explicit launch option enables it.
    switch (Stage)
    {
    case 0: if (Time >= 8) {
        Check(TEXT("explorer_spawn_mesh_animation"), Explorer && Explorer->GetMesh()->GetSkeletalMeshAsset() && Explorer->GetMesh()->GetAnimInstance());
        if (!Explorer) { Finish(); break; }
        if (FParse::Param(FCommandLine::Get(), TEXT("SPOffRoadOnly")))
        {
            const bool Prepared = PrepareOffRoadFixture(*Explorer); Check(TEXT("off_road_terrain_fixture"), Prepared);
            if (!Prepared) { Finish(); break; }
        }
        Shot(TEXT("explorer-idle")); StartPosition = Explorer->GetActorLocation(); Key(EKeys::W, true); ++Stage;
    } break;
    case 1: if (Time >= 10) {
        WalkDistance = FVector::Dist2D(StartPosition, Player->GetPawn()->GetActorLocation());
        Check(TEXT("walk_moves"), WalkDistance > 200); Shot(TEXT("walk"));
        StartPosition = Player->GetPawn()->GetActorLocation(); Key(EKeys::LeftShift, true); ++Stage;
    } break;
    case 2: if (Time >= 12) {
        RunDistance = FVector::Dist2D(StartPosition, Player->GetPawn()->GetActorLocation());
        Check(TEXT("run_faster_than_walk"), RunDistance > WalkDistance * 1.4);
        Shot(TEXT("run")); Key(EKeys::W, false); Key(EKeys::LeftShift, false); ++Stage;
    } break;
    case 3: if (Time >= 13) { StartPosition = Player->GetPawn()->GetActorLocation(); Key(EKeys::SpaceBar, true); ++Stage; } break;
    case 4: if (Time >= 13.3) { Shot(TEXT("jump")); Key(EKeys::SpaceBar, false); ++Stage; } break;
    case 5: if (Time >= 15) {
        Check(TEXT("jump_and_land"), Explorer && bSawAir && JumpHeight > 50 && Explorer->GetCharacterMovement()->IsMovingOnGround());
        Tap(EKeys::Tab); ++Stage;
    } break;
    case 6: if (Time >= 17) {
        Check(TEXT("switch_to_bike"), Bike != nullptr); if (!Bike) { Finish(); break; }
        StartPosition = Bike->GetActorLocation(); Shot(TEXT("bike-idle")); Key(EKeys::W, true); ++Stage;
    } break;
    case 7: if (Time >= 19) {
        Check(TEXT("bike_accelerates"), Bike && Bike->GetSpeedKmh() > 5 && FVector::Dist2D(StartPosition, Bike->GetActorLocation()) > 150);
        Shot(TEXT("pedal")); Key(EKeys::W, false); Key(EKeys::S, true); ++Stage;
    } break;
    case 8: if (Time >= 22) {
        Check(TEXT("bike_brakes"), Bike && Bike->GetSpeedKmh() < .1); Key(EKeys::S, false); Tap(EKeys::E); ++Stage;
    } break;
    case 9: if (Time >= 23) { Check(TEXT("push_bike"), Bike && Bike->IsWalking()); Shot(TEXT("push")); Tap(EKeys::E); ++Stage; } break;
    case 10: if (Time >= 24) { Check(TEXT("remount"), Bike && !Bike->IsWalking()); Tap(EKeys::C); ++Stage; } break;
    case 11: if (Time >= 25) { Shot(TEXT("first-person")); Tap(EKeys::C); Tap(EKeys::F1); ++Stage; } break;
    case 12: if (Time >= 26) {
        Check(TEXT("settings_pause"), UGameplayStatics::IsGamePaused(this)); Shot(TEXT("settings"));
        ++Stage;
    } break;
    case 13: if (Time >= 27) { if (ASPHud* Hud = Cast<ASPHud>(Player->GetHUD())) Hud->ToggleRideSettings(); ++Stage; } break;
    case 14: if (Time >= 28) {
        Check(TEXT("settings_resume"), !UGameplayStatics::IsGamePaused(this));
        StartPosition = Player->GetPawn()->GetActorLocation();
        // An explicit recovery fixture, separate from movement evidence. This
        // must return to the last safe point rather than pass while stationary.
        if (Bike) Bike->AddActorWorldOffset(FVector(0,0,1000), false);
        Tap(EKeys::R); ++Stage;
    } break;
    case 15: if (Time >= 29) { Check(TEXT("bike_recovery"), Bike && Bike->HasSurface() && Bike->GetSpeedKmh() < .1 && FVector::Distance(StartPosition, Bike->GetActorLocation()) < 10); Tap(EKeys::Tab); ++Stage; } break;
    case 16: if (Time >= 31) { Check(TEXT("switch_back_to_explorer"), Explorer != nullptr); Tap(EKeys::H); ++Stage; } break;
    case 17: if (Time >= 32) { Shot(TEXT("controls")); ++Stage; } break;
    case 18: if (Time >= 33) { Tap(EKeys::H); Tap(EKeys::Escape); ++Stage; } break;
    case 19: if (Time >= 34) { Check(TEXT("pause"), UGameplayStatics::IsGamePaused(this)); Shot(TEXT("pause")); ++Stage; } break;
    case 20: if (Time >= 35) { Tap(EKeys::Escape); ++Stage; } break;
    case 21: if (Time >= 36) { Check(TEXT("resume"), !UGameplayStatics::IsGamePaused(this)); Tap(EKeys::Tab); ++Stage; } break;
    case 22: if (Time >= 37 && Bike) { Bike->SetRideSetting(ESPRideSetting::Steering, 10); Tap(EKeys::F10); ++Stage; } break;
    case 23: if (Time >= 38) {
        Check(TEXT("F10_rejects_unsupported_steering"), Bike && Bike->GetDiagnosticStatus().StartsWith(TEXT("F10 needs Roam defaults"))
            && FMath::Abs(Bike->GetRideTuning().Get(ESPRideSetting::Steering) - 10) < .01);
        if (Bike) Bike->SetRideSetting(ESPRideSetting::Steering, GetRideSettingDefinition(ESPRideSetting::Steering).RoamDefault);
        Finish();
    } break;
    }
}

void ASPReleaseCheck::Finish()
{
    bFinished = true;
    FinishedAt = FPlatformTime::Seconds();
    for (const FKey& Button : {EKeys::W, EKeys::S, EKeys::LeftShift, EKeys::SpaceBar}) Key(Button, false);
    Result->SetArrayField(TEXT("checks"), Checks);
    bool Passed = !Checks.IsEmpty();
    for (const auto& Item : Checks) Passed &= Item->AsObject()->GetBoolField(TEXT("passed"));
    if (!bProfileOnly) Result->SetBoolField(TEXT("functional_checks_passed"), Passed);
    Result->SetNumberField(TEXT("walk_cm"), WalkDistance); Result->SetNumberField(TEXT("run_cm"), RunDistance);
    Result->SetNumberField(TEXT("jump_height_cm"), JumpHeight);
    Result->SetNumberField(TEXT("peak_sampled_process_memory_bytes"), double(PeakMemory));
    Result->SetStringField(TEXT("ended_utc"), FDateTime::UtcNow().ToIso8601());
    Result->SetBoolField(TEXT("full_route_run"), false);
    TSharedPtr<FJsonObject> Settings = MakeShared<FJsonObject>();
    for (const TCHAR* Name : {TEXT("r.ScreenPercentage"), TEXT("t.MaxFPS"), TEXT("sg.ShadowQuality"), TEXT("sg.FoliageQuality"), TEXT("sg.ViewDistanceQuality")})
        if (const IConsoleVariable* Value = IConsoleManager::Get().FindConsoleVariable(Name)) Settings->SetNumberField(Name, Value->GetFloat());
    Result->SetObjectField(TEXT("render_settings"), Settings);
    if (GEngine && GEngine->GameViewport && GEngine->GameViewport->Viewport)
    {
        FIntPoint Size = GEngine->GameViewport->Viewport->GetSizeXY();
        Result->SetNumberField(TEXT("width"), Size.X); Result->SetNumberField(TEXT("height"), Size.Y);
    }
    const auto Stats = [](TArray<double> Values) {
        TSharedPtr<FJsonObject> Summary = MakeShared<FJsonObject>(); Values.Sort();
        Summary->SetNumberField(TEXT("samples"), Values.Num());
        if (!Values.IsEmpty()) {
            for (const auto& Percent : {TPair<const TCHAR*, double>(TEXT("p50_ms"), .5), {TEXT("p95_ms"), .95}, {TEXT("p99_ms"), .99}})
                Summary->SetNumberField(Percent.Key, Values[FMath::Clamp(FMath::CeilToInt(Values.Num() * Percent.Value) - 1, 0, Values.Num() - 1)]);
            Summary->SetNumberField(TEXT("max_ms"), Values.Last());
            Summary->SetNumberField(TEXT("frames_above_50_ms"), Values.FilterByPredicate([](double V) { return V > 50; }).Num());
        } return Summary;
    };
    Result->SetObjectField(TEXT("frame"), Stats(Frames)); Result->SetObjectField(TEXT("game"), Stats(Games));
    Result->SetObjectField(TEXT("render"), Stats(Renders)); Result->SetObjectField(TEXT("gpu"), Stats(Gpus));
    Result->SetStringField(TEXT("timing_limit"), TEXT("Stationary engine timing only; near-zero render counters are invalid; no external display or full-route performance claim."));
    FString Json; FJsonSerializer::Serialize(Result.ToSharedRef(), TJsonWriterFactory<>::Create(&Json));
    if (FFileHelper::SaveStringToFile(Json, *Output))
    {
        UE_LOG(LogTemp, Display, TEXT("SP_RELEASE_CHECK_SAVED: %s"), *Output);
    }
    else
    {
        UE_LOG(LogTemp, Error, TEXT("SP_RELEASE_CHECK_SAVE_FAILED: %s"), *Output);
    }
}
