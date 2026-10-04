#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "SPHud.generated.h"

class SPRideSettingsWidget;
class SPParkHUDWidget;
struct FSPHudState;

UCLASS()
class STANLEYPARKSIM_API ASPHud : public AHUD
{
    GENERATED_BODY()
public:
    virtual void DrawHUD() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    void ToggleRideSettings();
    void ToggleControls();

private:
    TSharedPtr<SPRideSettingsWidget> RideSettings;
    TSharedPtr<SPParkHUDWidget> Display;
    TSharedPtr<FSPHudState> DisplayState;
    bool bPausedBeforeSettings = false;
};
