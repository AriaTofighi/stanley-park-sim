#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"
#include "Styling/SlateBrush.h"

struct FSPHudState
{
    bool bBicycle = false;
    bool bPaused = false;
    bool bSettingsOpen = false;
    bool bControlsOpen = false;
    bool bAutopilot = false;
    FText Speed;
    FText RouteLength;
    FText Notice;
    FText Diagnostic;
    FText Error;
    FSlateBrush MinimapBrush;
    FVector2D MapPosition = FVector2D::ZeroVector;
    double MapYaw = 0;
    bool bMapPositionValid = false;
};

class SPParkHUDWidget : public SCompoundWidget
{
public:
    SLATE_BEGIN_ARGS(SPParkHUDWidget) {}
        SLATE_ARGUMENT(TSharedPtr<FSPHudState>, State)
    SLATE_END_ARGS()
    void Construct(const FArguments& Arguments);

private:
    TSharedPtr<FSPHudState> State;
    EVisibility GameplayVisibility() const;
    TSharedRef<SWidget> TravelReadout();
    TSharedRef<SWidget> Minimap();
    TSharedRef<SWidget> QuickControls(bool bBicycle);
    TSharedRef<SWidget> ControlsPanel(bool bBicycle);
    TSharedRef<SWidget> PausePanel();
};
