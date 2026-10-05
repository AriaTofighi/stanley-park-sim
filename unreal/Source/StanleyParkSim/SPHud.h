#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "SPHud.generated.h"

class SPRideSettingsWidget;
class SPParkHUDWidget;
struct FSPHudState;
class UTexture2D;

UCLASS()
class STANLEYPARKSIM_API ASPHud : public AHUD
{
    GENERATED_BODY()
public:
    ASPHud();
    virtual void DrawHUD() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    void ToggleRideSettings();
    void ToggleControls();

private:
    TSharedPtr<SPRideSettingsWidget> RideSettings;
    TSharedPtr<SPParkHUDWidget> Display;
    TSharedPtr<FSPHudState> DisplayState;
    bool bPausedBeforeSettings = false;
    UPROPERTY() TObjectPtr<UTexture2D> MinimapTexture;
    FVector2D MapMinimum = FVector2D::ZeroVector;
    FVector2D MapMaximum = FVector2D::ZeroVector;
    bool bMapBoundsValid = false;
    void LoadMinimap();
};
