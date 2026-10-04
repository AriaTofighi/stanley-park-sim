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

void ASPHud::DrawHUD()
{
    Super::DrawHUD();
    if (!GEngine || !GEngine->GameViewport) return;
    if (!Display.IsValid())
    {
        DisplayState = MakeShared<FSPHudState>();
        SAssignNew(Display, SPParkHUDWidget).State(DisplayState);
        GEngine->GameViewport->AddViewportWidgetContent(Display.ToSharedRef(), 10);
    }
    const ASPBicyclePawn* Bicycle = Cast<ASPBicyclePawn>(GetOwningPawn());
    DisplayState->bBicycle = Bicycle != nullptr;
    DisplayState->bWalking = Bicycle && Bicycle->IsWalking();
    DisplayState->bPaused = UGameplayStatics::IsGamePaused(this);
    DisplayState->bSettingsOpen = RideSettings.IsValid();
    const auto UpdateText = [](FText& Text, const FString& Value)
    {
        // Preserve the text identity when unchanged, avoiding a fresh text
        // layout each frame for a stationary speed, distance or notice.
        if (Text.ToString() != Value) Text = FText::FromString(Value);
    };
    UpdateText(DisplayState->Speed, FString::Printf(TEXT("%02.0f"), Bicycle ? Bicycle->GetSpeedKmh() : 0));
    UpdateText(DisplayState->Distance, FString::Printf(TEXT("%.2f km"), Bicycle ? Bicycle->GetDistanceMetres() / 1000 : 0));
    UpdateText(DisplayState->Notice, Bicycle ? Bicycle->Notice : FString());
    UpdateText(DisplayState->Diagnostic, Bicycle ? Bicycle->GetDiagnosticStatus() : FString());
    FString Error;
    for (TActorIterator<ASPWorldDirector> It(GetWorld()); It; ++It)
        if (!It->Error.IsEmpty()) { Error = It->Error; break; }
    UpdateText(DisplayState->Error, Error);
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
