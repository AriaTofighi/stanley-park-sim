#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"

struct FSPHudState
{
    bool bBicycle = false;
    bool bWalking = false;
    bool bPaused = false;
    bool bSettingsOpen = false;
    bool bControlsOpen = false;
    FText Speed;
    FText Distance;
    FText Notice;
    FText Diagnostic;
    FText Error;
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
    FText TravelMode() const;
    TSharedRef<SWidget> TravelReadout();
    TSharedRef<SWidget> QuickControls(bool bBicycle);
    TSharedRef<SWidget> ControlsPanel(bool bBicycle);
    TSharedRef<SWidget> PausePanel();
};
