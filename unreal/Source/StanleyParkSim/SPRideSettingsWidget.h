#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"
#include "SPRideTuning.h"
#include "SPGraphicsSettings.h"
#include "Styling/SlateTypes.h"

class ASPBicyclePawn;

class SPRideSettingsWidget : public SCompoundWidget
{
public:
    SLATE_BEGIN_ARGS(SPRideSettingsWidget) {}
        SLATE_ARGUMENT(TWeakObjectPtr<ASPBicyclePawn>, Bicycle)
        SLATE_EVENT(FSimpleDelegate, OnClose)
    SLATE_END_ARGS()

    void Construct(const FArguments& Arguments);
    virtual bool SupportsKeyboardFocus() const override { return true; }
    virtual FReply OnPreviewKeyDown(const FGeometry& Geometry, const FKeyEvent& Event) override;

private:
    TWeakObjectPtr<ASPBicyclePawn> Bicycle;
    FSimpleDelegate OnClose;
    FSliderStyle SliderStyle;
    FButtonStyle SecondaryButton;
    FButtonStyle PrimaryButton;
    TArray<TSharedPtr<ESPGraphicsPreset>> GraphicsOptions;
    ESPGraphicsPreset GraphicsPreset = ESPGraphicsPreset::Balanced;
    TSharedRef<SWidget> MakeSlider(ESPRideSetting Setting);
    TSharedRef<SWidget> MakeGraphicsControl();
    FReply Close();
};
