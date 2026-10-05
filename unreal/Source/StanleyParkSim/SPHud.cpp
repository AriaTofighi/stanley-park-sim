#include "SPHud.h"
#include "SPParkHUDWidget.h"
#include "SPBicyclePawn.h"
#include "SPWorldDirector.h"
#include "SPRideSettingsWidget.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Engine/Texture2D.h"
#include "Dom/JsonObject.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/ConstructorHelpers.h"

ASPHud::ASPHud()
{
    static ConstructorHelpers::FObjectFinderOptional<UTexture2D> Map(TEXT("/Game/StanleyPark/UI/T_ParkMinimap.T_ParkMinimap"));
    if (Map.Succeeded()) MinimapTexture = Map.Get();
}

void ASPHud::LoadMinimap()
{
    if (!MinimapTexture || !DisplayState) return;
    FString Text, Coordinates;
    TSharedPtr<FJsonObject> Root;
    double Schema = 0;
    if (!FFileHelper::LoadFileToString(Text, *(FPaths::ProjectContentDir()/TEXT("WorldData/minimap.json")))
        || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Root) || !Root
        || !Root->TryGetNumberField(TEXT("schema_version"),Schema) || Schema != 1
        || !Root->TryGetStringField(TEXT("coordinate_contract"),Coordinates)
        || Coordinates != TEXT("unreal_north_east_up_cm")
        || !Root->TryGetNumberField(TEXT("east_min"),MapMinimum.X)
        || !Root->TryGetNumberField(TEXT("north_min"),MapMinimum.Y)
        || !Root->TryGetNumberField(TEXT("east_max"),MapMaximum.X)
        || !Root->TryGetNumberField(TEXT("north_max"),MapMaximum.Y)
        || MapMinimum.ContainsNaN() || MapMaximum.ContainsNaN()
        || MapMaximum.X <= MapMinimum.X || MapMaximum.Y <= MapMinimum.Y) return;
    DisplayState->MinimapBrush.SetResourceObject(MinimapTexture);
    DisplayState->MinimapBrush.ImageSize = FVector2D(768,768);
    DisplayState->MinimapBrush.DrawAs = ESlateBrushDrawType::Image;
    bMapBoundsValid = true;
}

void ASPHud::DrawHUD()
{
    Super::DrawHUD();
    if (!GEngine || !GEngine->GameViewport) return;
    if (!Display.IsValid())
    {
        DisplayState = MakeShared<FSPHudState>();
        LoadMinimap();
        SAssignNew(Display, SPParkHUDWidget).State(DisplayState);
        GEngine->GameViewport->AddViewportWidgetContent(Display.ToSharedRef(), 10);
    }
    const ASPBicyclePawn* Bicycle = Cast<ASPBicyclePawn>(GetOwningPawn());
    DisplayState->bBicycle = Bicycle != nullptr;
    DisplayState->bAutopilot = Bicycle && Bicycle->IsAutopilotActive();
    DisplayState->bPaused = UGameplayStatics::IsGamePaused(this);
    DisplayState->bSettingsOpen = RideSettings.IsValid();
    const auto UpdateText = [](FText& Text, const FString& Value)
    {
        // Preserve the text identity when unchanged, avoiding a fresh text
        // layout each frame for a stationary speed, distance or notice.
        if (Text.ToString() != Value) Text = FText::FromString(Value);
    };
    const APawn* PlayerPawn = GetOwningPawn();
    const double Speed = Bicycle ? Bicycle->GetSpeedKmh() : PlayerPawn ? PlayerPawn->GetVelocity().Size2D()*.036 : 0;
    UpdateText(DisplayState->Speed, FString::Printf(TEXT("%.0f"), Speed));
    UpdateText(DisplayState->Notice, Bicycle ? Bicycle->Notice : FString());
    UpdateText(DisplayState->Diagnostic, Bicycle ? Bicycle->GetDiagnosticStatus() : FString());
    FString Error;
    for (TActorIterator<ASPWorldDirector> It(GetWorld()); It; ++It)
    {
        if (const FSPRoute* Route = It->GetData().FindRoute(TEXT("main_circuit")))
            UpdateText(DisplayState->RouteLength,FString::Printf(TEXT("%.2f km"),Route->Length/100000.));
        if (!It->Error.IsEmpty()) { Error = It->Error; break; }
    }
    UpdateText(DisplayState->Error, Error);
    DisplayState->bMapPositionValid = bMapBoundsValid && PlayerPawn;
    if (DisplayState->bMapPositionValid)
    {
        const FVector P = PlayerPawn->GetActorLocation();
        DisplayState->MapPosition = FVector2D((P.Y-MapMinimum.X)/(MapMaximum.X-MapMinimum.X),
            (MapMaximum.Y-P.X)/(MapMaximum.Y-MapMinimum.Y));
        DisplayState->MapYaw = PlayerPawn->GetActorRotation().Yaw;
    }
}

void ASPHud::ToggleControls()
{
    if (DisplayState.IsValid() && !RideSettings.IsValid())
        DisplayState->bControlsOpen = !DisplayState->bControlsOpen;
}

void ASPHud::ToggleRideSettings()
{
    APlayerController* Player = GetOwningPlayerController();
    ASPBicyclePawn* Bicycle = Cast<ASPBicyclePawn>(GetOwningPawn());
    if (!Player || !Bicycle || !GEngine || !GEngine->GameViewport) return;
    if (RideSettings.IsValid())
    {
        Bicycle->SaveRideTuning();
        GEngine->GameViewport->RemoveViewportWidgetContent(RideSettings.ToSharedRef());
        RideSettings.Reset();
        Bicycle->SetSettingsOpen(false);
        Player->bShowMouseCursor = false;
        Player->SetInputMode(FInputModeGameOnly());
        Player->FlushPressedKeys();
        UGameplayStatics::SetGamePaused(this, bPausedBeforeSettings);
        return;
    }
    bPausedBeforeSettings = UGameplayStatics::IsGamePaused(this);
    Bicycle->SetSettingsOpen(true);
    UGameplayStatics::SetGamePaused(this, true);
    SAssignNew(RideSettings, SPRideSettingsWidget)
        .Bicycle(Bicycle)
        .OnClose(FSimpleDelegate::CreateUObject(this, &ASPHud::ToggleRideSettings));
    GEngine->GameViewport->AddViewportWidgetContent(RideSettings.ToSharedRef(), 100);
    FInputModeUIOnly Mode;
    Mode.SetWidgetToFocus(RideSettings);
    Mode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
    Player->SetInputMode(Mode);
    Player->bShowMouseCursor = true;
    Player->FlushPressedKeys();
}

void ASPHud::EndPlay(const EEndPlayReason::Type Reason)
{
    if (Display.IsValid() && GEngine && GEngine->GameViewport)
        GEngine->GameViewport->RemoveViewportWidgetContent(Display.ToSharedRef());
    Display.Reset();
    DisplayState.Reset();
    if (RideSettings.IsValid() && GEngine && GEngine->GameViewport)
        GEngine->GameViewport->RemoveViewportWidgetContent(RideSettings.ToSharedRef());
    RideSettings.Reset();
    Super::EndPlay(Reason);
}
