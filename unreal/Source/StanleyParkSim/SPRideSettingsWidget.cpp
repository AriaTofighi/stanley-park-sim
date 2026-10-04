#include "SPRideSettingsWidget.h"
#include "SPBicyclePawn.h"
#include "SPUITheme.h"
#include "InputCoreTypes.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SComboBox.h"
#include "Widgets/Input/SSlider.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SDPIScaler.h"
#include "Widgets/Layout/SExpandableArea.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

namespace
{
    TSharedRef<SWidget> Divider()
    {
        return SNew(SBox).HeightOverride(1)
            [SNew(SBorder).Padding(0).BorderImage(SPUI::DividerBrush())];
    }
}

void SPRideSettingsWidget::Construct(const FArguments& Arguments)
{
    Bicycle = Arguments._Bicycle;
    OnClose = Arguments._OnClose;
    PrimaryButton = SPUI::ButtonStyle(true);
    SecondaryButton = SPUI::ButtonStyle(false);
    SliderStyle = FCoreStyle::Get().GetWidgetStyle<FSliderStyle>("Slider");
    SliderStyle.NormalThumbImage.ImageSize = FVector2D(16, 24);
    SliderStyle.HoveredThumbImage.ImageSize = FVector2D(16, 24);
    SliderStyle.DisabledThumbImage.ImageSize = FVector2D(16, 24);
    SliderStyle.BarThickness = 4;
    GraphicsPreset = SPGraphics::SavedPreset();
    for (uint8 Index = 0; Index < static_cast<uint8>(ESPGraphicsPreset::Count); ++Index)
        GraphicsOptions.Add(MakeShared<ESPGraphicsPreset>(static_cast<ESPGraphicsPreset>(Index)));

    auto Rows = SNew(SVerticalBox);
    for (uint8 Index = 0; Index < static_cast<uint8>(ESPRideSetting::Count); ++Index)
    {
        const ESPRideSetting Setting = static_cast<ESPRideSetting>(Index);
        if (Setting == ESPRideSetting::TopSpeed || Setting == ESPRideSetting::FieldOfView)
            Rows->AddSlot().AutoHeight().Padding(0, Index == 0 ? 0 : SPUI::Padding, 0, SPUI::Padding)
            [
                SNew(STextBlock).Text(FText::FromString(Index == 0 ? TEXT("Bicycle") : TEXT("Camera")))
                .Font(SPUI::Font(14, true)).ColorAndOpacity(SPUI::Text)
            ];
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, SPUI::Padding)[MakeSlider(Setting)];
    }
    Rows->AddSlot().AutoHeight().Padding(0, SPUI::Padding, 0, SPUI::Padding)[MakeGraphicsControl()];
    Rows->AddSlot().AutoHeight().Padding(0, SPUI::Unit, 0, SPUI::Padding)
    [
        SNew(SExpandableArea).InitiallyCollapsed(true).AllowAnimatedTransition(false)
        .BorderImage(FCoreStyle::Get().GetBrush("NoBorder")).HeaderPadding(FMargin(0, SPUI::Unit))
        .Padding(FMargin(0, SPUI::Unit, 0, 0))
        .HeaderContent()
        [SNew(STextBlock).Text(FText::FromString(TEXT("Data credits"))).Font(SPUI::Font(11)).ColorAndOpacity(SPUI::Muted)]
        .BodyContent()
        [
            SNew(STextBlock).AutoWrapText(true)
            .Text(FText::FromString(TEXT("City of Vancouver, Province of British Columbia, Natural Resources Canada and Fisheries and Oceans Canada.\n\nWalking paths: © OpenStreetMap contributors, ODbL 1.0. openstreetmap.org/copyright\n\nFull credits and source data: DATA-ATTRIBUTION.txt, SEAWALL-CREDITS.txt and SourceData beside the game.")))
            .Font(SPUI::Font(11)).ColorAndOpacity(SPUI::Muted)
        ]
    ];

    ChildSlot
    [
        SNew(SDPIScaler).DPIScale_Static(&SPUI::ViewportScale)
        [
            SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush"))
            .BorderBackgroundColor(FLinearColor(0, 0, 0, .62f)).Padding(SPUI::Margin)
            .HAlign(HAlign_Center).VAlign(VAlign_Center)
            [
                SNew(SBox)
                .WidthOverride_Lambda([]() { return FMath::Min(640.f, float(SPUI::LogicalViewport().X) - 2 * SPUI::Margin); })
                .HeightOverride_Lambda([]() { return FMath::Min(720.f, float(SPUI::LogicalViewport().Y) - 2 * SPUI::Margin); })
                [
                    SNew(SBorder).BorderImage(SPUI::PanelBrush()).Padding(3 * SPUI::Unit)
                    [
                        SNew(SVerticalBox)
                        + SVerticalBox::Slot().AutoHeight()
                        [SNew(STextBlock).Text(FText::FromString(TEXT("Ride settings"))).Font(SPUI::Font(24, true)).ColorAndOpacity(SPUI::Text)]
                        + SVerticalBox::Slot().AutoHeight().Padding(0, SPUI::Unit, 0, 0)
                        [SNew(STextBlock).Text(FText::FromString(TEXT("F1 or Esc to close"))).Font(SPUI::Font(12)).ColorAndOpacity(SPUI::Muted)]
                        + SVerticalBox::Slot().AutoHeight().Padding(0, SPUI::Padding)[Divider()]
                        + SVerticalBox::Slot().FillHeight(1)
                        [
                            SNew(SScrollBox).ScrollBarPadding(FMargin(SPUI::Padding, 0, 0, 0))
                            + SScrollBox::Slot()[Rows]
                        ]
                        + SVerticalBox::Slot().AutoHeight().Padding(0, SPUI::Padding)[Divider()]
                        + SVerticalBox::Slot().AutoHeight()
                        [
                            SNew(SBox).HeightOverride(SPUI::ButtonHeight)
                            [
                                SNew(SHorizontalBox)
                                + SHorizontalBox::Slot().FillWidth(1).Padding(0, 0, SPUI::Unit, 0)
                                [
                                    SNew(SButton).ButtonStyle(&SecondaryButton).HAlign(HAlign_Center).VAlign(VAlign_Center)
                                    .OnClicked_Lambda([this]() {
                                        if (Bicycle.IsValid()) Bicycle->ResetRideTuning();
                                        return FReply::Handled();
                                    })
                                    [SNew(STextBlock).Text(FText::FromString(TEXT("Roam defaults"))).Font(SPUI::Font(12))]
                                ]
                                + SHorizontalBox::Slot().FillWidth(1).Padding(0, 0, SPUI::Unit, 0)
                                [
                                    SNew(SButton).ButtonStyle(&SecondaryButton).HAlign(HAlign_Center).VAlign(VAlign_Center)
                                    .OnClicked_Lambda([this]() {
                                        if (Bicycle.IsValid()) Bicycle->ResetRideTuning(true);
                                        return FReply::Handled();
                                    })
                                    [SNew(STextBlock).Text(FText::FromString(TEXT("Relaxed pace"))).Font(SPUI::Font(12))]
                                ]
                                + SHorizontalBox::Slot().FillWidth(1)
                                [
                                    SNew(SButton).ButtonStyle(&PrimaryButton).HAlign(HAlign_Center).VAlign(VAlign_Center)
                                    .OnClicked(this, &SPRideSettingsWidget::Close)
                                    [SNew(STextBlock).Text(FText::FromString(TEXT("Done"))).Font(SPUI::Font(12, true))]
                                ]
                            ]
                        ]
                        + SVerticalBox::Slot().AutoHeight().Padding(0, SPUI::Padding, 0, 0)
                        [SNew(STextBlock).Text(FText::FromString(TEXT("Changes are saved automatically."))).Font(SPUI::Font(11)).ColorAndOpacity(SPUI::Muted)]
                    ]
                ]
            ]
        ]
    ];
}

TSharedRef<SWidget> SPRideSettingsWidget::MakeGraphicsControl()
{
    return SNew(SVerticalBox)
        + SVerticalBox::Slot().AutoHeight()
        [
            SNew(SHorizontalBox)
            + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)
            [SNew(STextBlock).Text(FText::FromString(TEXT("Graphics"))).Font(SPUI::Font(14, true)).ColorAndOpacity(SPUI::Text)]
            + SHorizontalBox::Slot().AutoWidth()
            [
                SNew(SBox).WidthOverride(208).HeightOverride(SPUI::ButtonHeight)
                [
                    SNew(SComboBox<TSharedPtr<ESPGraphicsPreset>>)
                    .OptionsSource(&GraphicsOptions)
                    .InitiallySelectedItem(GraphicsOptions[static_cast<uint8>(GraphicsPreset)])
                    .ButtonStyle(&SecondaryButton).ForegroundColor(SPUI::Text)
                    .ContentPadding(FMargin(SPUI::Padding, SPUI::Unit))
                    .OnGenerateWidget_Lambda([](TSharedPtr<ESPGraphicsPreset> Option) -> TSharedRef<SWidget> {
                        return SNew(STextBlock).Text(FText::FromString(SPGraphics::Name(*Option))).Font(SPUI::Font(12));
                    })
                    .OnSelectionChanged_Lambda([this](TSharedPtr<ESPGraphicsPreset> Option, ESelectInfo::Type) {
                        if (!Option.IsValid()) return;
                        GraphicsPreset = *Option;
                        SPGraphics::ApplyAndSavePreset(GraphicsPreset);
                    })
                    [SNew(STextBlock).Text_Lambda([this]() { return FText::FromString(SPGraphics::Name(GraphicsPreset)); }).Font(SPUI::Font(12))]
                ]
            ]
        ]
        + SVerticalBox::Slot().AutoHeight().Padding(0, SPUI::Unit, 0, 0)
        [
            SNew(STextBlock).AutoWrapText(true).Font(SPUI::Font(11)).ColorAndOpacity(SPUI::Muted)
            .Text_Lambda([this]() { return FText::FromString(SPGraphics::Description(GraphicsPreset)); })
        ];
}

TSharedRef<SWidget> SPRideSettingsWidget::MakeSlider(ESPRideSetting Setting)
{
    const auto Definition = GetRideSettingDefinition(Setting);
    return SNew(SVerticalBox)
        + SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, SPUI::Unit)
        [
            SNew(SHorizontalBox)
            + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)
            [SNew(STextBlock).Text(FText::FromString(Definition.Label)).Font(SPUI::Font(12)).ColorAndOpacity(SPUI::Text)]
            + SHorizontalBox::Slot().AutoWidth()
            [
                SNew(SBox).WidthOverride(112).HAlign(HAlign_Right)
                [
                    SNew(STextBlock).Font(SPUI::Font(12, true)).ColorAndOpacity(SPUI::Accent)
                    .Text_Lambda([this, Setting, Definition]() {
                        const float Value = Bicycle.IsValid() ? Bicycle->GetRideTuning().Get(Setting) : Definition.RoamDefault;
                        return FText::FromString(FString::Printf(TEXT("%.*f %s"), Definition.Decimals, Value, Definition.Unit));
                    })
                ]
            ]
        ]
        + SVerticalBox::Slot().AutoHeight()
        [
            SNew(SBox).HeightOverride(SPUI::RowHeight)
            [
                SNew(SSlider).Style(&SliderStyle).IsFocusable(true).MouseUsesStep(true).RequiresControllerLock(false)
                .ToolTipText(FText::FromString(TEXT("Drag to adjust. Use arrow keys for small changes.")))
                .StepSize(Definition.Step / (Definition.Maximum - Definition.Minimum))
                .SliderBarColor(FLinearColor(.22f, .29f, .24f)).SliderHandleColor(SPUI::Accent)
                .Value_Lambda([this, Setting, Definition]() {
                    const float Value = Bicycle.IsValid() ? Bicycle->GetRideTuning().Get(Setting) : Definition.RoamDefault;
                    return (Value - Definition.Minimum) / (Definition.Maximum - Definition.Minimum);
                })
                .OnValueChanged_Lambda([this, Setting, Definition](float Normalized) {
                    if (Bicycle.IsValid()) Bicycle->SetRideSetting(Setting, FMath::GridSnap(
                        FMath::Lerp(Definition.Minimum, Definition.Maximum, Normalized), Definition.Step));
                })
            ]
        ];
}

FReply SPRideSettingsWidget::Close()
{
    OnClose.ExecuteIfBound();
    return FReply::Handled();
}

FReply SPRideSettingsWidget::OnPreviewKeyDown(const FGeometry& Geometry, const FKeyEvent& Event)
{
    if (Event.GetKey() == EKeys::F1 || Event.GetKey() == EKeys::Escape) return Close();
    return SCompoundWidget::OnPreviewKeyDown(Geometry, Event);
}
