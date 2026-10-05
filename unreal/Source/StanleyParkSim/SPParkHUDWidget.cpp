#include "SPParkHUDWidget.h"
#include "SPUITheme.h"
#include "SPParkMinimap.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SDPIScaler.h"
#include "Widgets/Layout/SWrapBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

namespace
{
    struct FControl { const TCHAR* Key; const TCHAR* Action; };
    const FControl ExplorerControls[] = {
        { TEXT("WASD"), TEXT("Move") }, { TEXT("Shift"), TEXT("Run") },
        { TEXT("Space"), TEXT("Jump") }, { TEXT("Mouse"), TEXT("Look") },
        { TEXT("Tab"), TEXT("Ride bicycle") }, { TEXT("R"), TEXT("Recover") },
        { TEXT("N"), TEXT("Nature sounds") }, { TEXT("Esc"), TEXT("Pause") }, { TEXT("H"), TEXT("Close controls") }
    };
    const FControl BicycleControls[] = {
        { TEXT("W"), TEXT("Pedal") }, { TEXT("S"), TEXT("Brake") },
        { TEXT("Shift"), TEXT("Boost to 80 km/h") }, { TEXT("Space"), TEXT("Jump bicycle") },
        { TEXT("P"), TEXT("Toggle Seawall autopilot") },
        { TEXT("Q"), TEXT("Back up when stopped") },
        { TEXT("A / D"), TEXT("Steer") }, { TEXT("Mouse"), TEXT("Look") },
        { TEXT("C"), TEXT("Change camera") }, { TEXT("B"), TEXT("Bell") },
        { TEXT("E"), TEXT("Walk bicycle") }, { TEXT("Tab"), TEXT("Explore on foot") },
        { TEXT("R"), TEXT("Recover") }, { TEXT("F1"), TEXT("Ride settings") },
        { TEXT("N"), TEXT("Nature sounds") }, { TEXT("Esc"), TEXT("Pause") }, { TEXT("H"), TEXT("Close controls") }
    };

    TSharedRef<SWidget> Key(const TCHAR* Label, float Height = SPUI::RowHeight)
    {
        return SNew(SBox).MinDesiredWidth(32).HeightOverride(Height)
        [
            SNew(SBorder).BorderImage(SPUI::KeyBrush()).Padding(FMargin(SPUI::Unit, 0))
            .HAlign(HAlign_Center).VAlign(VAlign_Center)
            [SNew(STextBlock).Text(FText::FromString(Label)).Font(SPUI::Font(11, true)).ColorAndOpacity(SPUI::Text)]
        ];
    }

    TSharedRef<SWidget> Hint(const TCHAR* KeyName, const TCHAR* Action)
    {
        return SNew(SHorizontalBox)
            + SHorizontalBox::Slot().AutoWidth()[Key(KeyName)]
            + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(SPUI::Unit, 0, 0, 0)
            [SNew(STextBlock).Text(FText::FromString(Action)).Font(SPUI::Font(12)).ColorAndOpacity(SPUI::Text)
                .ShadowOffset(FVector2D(0, 1)).ShadowColorAndOpacity(FLinearColor(0, 0, 0, .8f))];
    }
}

void SPParkHUDWidget::Construct(const FArguments& Arguments)
{
    State = Arguments._State;
    // This display never takes mouse or keyboard focus from the game.
    SetVisibility(EVisibility::HitTestInvisible);
    ChildSlot
    [
        SNew(SDPIScaler).DPIScale_Static(&SPUI::ViewportScale)
        [
            SNew(SOverlay)
            + SOverlay::Slot().Padding(SPUI::Margin)
            [
                SNew(SOverlay).Visibility(this, &SPParkHUDWidget::GameplayVisibility)
                + SOverlay::Slot().HAlign(HAlign_Left).VAlign(VAlign_Top)
                [
                    SNew(SVerticalBox)
                    + SVerticalBox::Slot().AutoHeight()
                    [SNew(STextBlock).Text(FText::FromString(TEXT("Stanley Park"))).Font(SPUI::Font(14, true))
                        .ColorAndOpacity(SPUI::Text).ShadowOffset(FVector2D(0, 2)).ShadowColorAndOpacity(FLinearColor(0, 0, 0, .8f))]
                    + SVerticalBox::Slot().AutoHeight().Padding(0, SPUI::Unit, 0, 0)
                    [TravelReadout()]
                ]
                + SOverlay::Slot().HAlign(HAlign_Right).VAlign(VAlign_Top)[Hint(TEXT("Esc"), TEXT("Pause"))]
                + SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Top).Padding(0, 80, 0, 0)
                [
                    SNew(SBox).WidthOverride(512)
                    [
                        SNew(SVerticalBox)
                        + SVerticalBox::Slot().AutoHeight()
                        [
                            SNew(SBorder).BorderImage(SPUI::PanelBrush()).Padding(SPUI::Padding)
                            .Visibility_Lambda([this]() { return State->Notice.IsEmpty() ? EVisibility::Collapsed : EVisibility::Visible; })
                            [SNew(STextBlock).Text_Lambda([this]() { return State->Notice; }).AutoWrapText(true)
                                .Justification(ETextJustify::Center).Font(SPUI::Font(12)).ColorAndOpacity(SPUI::Warning)]
                        ]
                        + SVerticalBox::Slot().AutoHeight().Padding(0, SPUI::Unit)
                        [
                            SNew(SBorder).BorderImage(SPUI::PanelBrush()).Padding(SPUI::Padding)
                            .Visibility_Lambda([this]() { return State->Error.IsEmpty() ? EVisibility::Collapsed : EVisibility::Visible; })
                            [SNew(STextBlock).Text_Lambda([this]() { return State->Error; }).AutoWrapText(true)
                                .Font(SPUI::Font(12)).ColorAndOpacity(SPUI::Error)]
                        ]
                        + SVerticalBox::Slot().AutoHeight()
                        [
                            SNew(STextBlock).Text_Lambda([this]() { return State->Diagnostic; }).AutoWrapText(true)
                            .Font(SPUI::Font(11)).ColorAndOpacity(SPUI::Warning).ShadowOffset(FVector2D(0, 1))
                        ]
                    ]
                ]
                + SOverlay::Slot().HAlign(HAlign_Left).VAlign(VAlign_Bottom)[Minimap()]
                + SOverlay::Slot().HAlign(HAlign_Right).VAlign(VAlign_Bottom)
                [
                    SNew(SVerticalBox)
                    + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Right).Padding(0, 0, 0, SPUI::Padding)
                    [ControlsPanel(false)]
                    + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Right).Padding(0, 0, 0, SPUI::Padding)
                    [ControlsPanel(true)]
                    + SVerticalBox::Slot().AutoHeight()[QuickControls(false)]
                    + SVerticalBox::Slot().AutoHeight()[QuickControls(true)]
                ]
            ]
            + SOverlay::Slot()[PausePanel()]
        ]
    ];
}

EVisibility SPParkHUDWidget::GameplayVisibility() const
{
    return State->bPaused || State->bSettingsOpen ? EVisibility::Collapsed : EVisibility::Visible;
}
TSharedRef<SWidget> SPParkHUDWidget::TravelReadout()
{
    return SNew(SHorizontalBox)
        + SHorizontalBox::Slot().AutoWidth()
        [SNew(STextBlock).Text_Lambda([this]() { return State->Speed; })
            .Font(SPUI::Font(23,true)).ColorAndOpacity(SPUI::Text)
            .ShadowOffset(FVector2D(0,1)).ShadowColorAndOpacity(FLinearColor::Black)]
        + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Bottom).Padding(6,0,0,3)
        [SNew(STextBlock).Text(FText::FromString(TEXT("km/h"))).Font(SPUI::Font(10))
            .ColorAndOpacity(SPUI::Text).ShadowOffset(FVector2D(0,1)).ShadowColorAndOpacity(FLinearColor::Black)];
}

TSharedRef<SWidget> SPParkHUDWidget::Minimap()
{
    return SNew(SBorder).BorderImage(SPUI::PanelBrush()).Padding(8)
        [SNew(SVerticalBox)
            + SVerticalBox::Slot().AutoHeight()[SNew(SPParkMinimap).State(State)]
            + SVerticalBox::Slot().AutoHeight().Padding(2,6)
            [SNew(SHorizontalBox)
                + SHorizontalBox::Slot().FillWidth(1)
                [SNew(STextBlock).Text_Lambda([this]() { return FText::FromString(State->bAutopilot
                    ? TEXT("Autopilot · P to stop") : TEXT("Seawall ride")); }).Font(SPUI::Font(10))
                    .ColorAndOpacity(FLinearColor(.88f,.78f,.49f,1))]
                + SHorizontalBox::Slot().AutoWidth()
                [SNew(STextBlock).Text_Lambda([this]() { return State->RouteLength; }).Font(SPUI::Font(10))
                    .ColorAndOpacity(SPUI::Muted)]]];
}

TSharedRef<SWidget> SPParkHUDWidget::QuickControls(bool bBicycle)
{
    auto Items = SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(SPUI::Padding, SPUI::Unit));
    if (bBicycle)
    {
        Items->AddSlot()[Hint(TEXT("W"), TEXT("Pedal"))];
        Items->AddSlot()[Hint(TEXT("S"), TEXT("Brake"))];
        Items->AddSlot()[Hint(TEXT("A / D"), TEXT("Steer"))];
        Items->AddSlot()[Hint(TEXT("Shift"), TEXT("Boost"))];
        Items->AddSlot()[Hint(TEXT("Space"), TEXT("Jump"))];
        Items->AddSlot()[Hint(TEXT("P"), TEXT("Autopilot"))];
    }
    else
    {
        Items->AddSlot()[Hint(TEXT("WASD"), TEXT("Move"))];
        Items->AddSlot()[Hint(TEXT("Shift"), TEXT("Run"))];
        Items->AddSlot()[Hint(TEXT("Space"), TEXT("Jump"))];
    }
    Items->AddSlot()[Hint(TEXT("Tab"), bBicycle ? TEXT("On foot") : TEXT("Bicycle"))];
    Items->AddSlot()[Hint(TEXT("H"), TEXT("Controls"))];
    return SNew(SBorder).BorderImage(SPUI::PanelBrush()).Padding(SPUI::Padding)
        .Visibility_Lambda([this, bBicycle]() { return State->bBicycle == bBicycle ? EVisibility::Visible : EVisibility::Collapsed; })
        [SNew(SBox).WidthOverride(568)[Items]];
}

TSharedRef<SWidget> SPParkHUDWidget::ControlsPanel(bool bBicycle)
{
    auto Rows = SNew(SVerticalBox);
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, SPUI::Padding)
        [SNew(STextBlock).Text(FText::FromString(TEXT("Controls"))).Font(SPUI::Font(18, true)).ColorAndOpacity(SPUI::Text)];
    TArrayView<const FControl> Controls = bBicycle ? MakeArrayView(BicycleControls) : MakeArrayView(ExplorerControls);
    for (const FControl& Control : Controls)
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, SPUI::Unit)
        [
            SNew(SHorizontalBox)
            + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)
            [SNew(STextBlock).Text(FText::FromString(Control.Action)).Font(SPUI::Font(12)).ColorAndOpacity(SPUI::Text)]
            + SHorizontalBox::Slot().AutoWidth()[Key(Control.Key, 24)]
        ];
    return SNew(SBorder).BorderImage(SPUI::PanelBrush()).Padding(SPUI::Padding)
        .Visibility_Lambda([this, bBicycle]() { return State->bControlsOpen && State->bBicycle == bBicycle ? EVisibility::Visible : EVisibility::Collapsed; })
        [SNew(SBox).WidthOverride(288)[Rows]];
}

TSharedRef<SWidget> SPParkHUDWidget::PausePanel()
{
    return SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush"))
        .BorderBackgroundColor(FLinearColor(0, 0, 0, .62f)).Padding(SPUI::Margin)
        .HAlign(HAlign_Center).VAlign(VAlign_Center)
        .Visibility_Lambda([this]() { return State->bPaused && !State->bSettingsOpen ? EVisibility::Visible : EVisibility::Collapsed; })
        [
            SNew(SBox).WidthOverride(352)
            [
                SNew(SBorder).BorderImage(SPUI::PanelBrush()).Padding(SPUI::Margin)
                [
                    SNew(SVerticalBox)
                    + SVerticalBox::Slot().AutoHeight()
                    [SNew(STextBlock).Text(FText::FromString(TEXT("Paused"))).Font(SPUI::Font(28, true)).ColorAndOpacity(SPUI::Text)]
                    + SVerticalBox::Slot().AutoHeight().Padding(0, SPUI::Unit, 0, SPUI::Margin)
                    [SNew(STextBlock).Text(FText::FromString(TEXT("Stanley Park"))).Font(SPUI::Font(12)).ColorAndOpacity(SPUI::Muted)]
                    + SVerticalBox::Slot().AutoHeight()[Hint(TEXT("Esc"), TEXT("Return to game"))]
                    + SVerticalBox::Slot().AutoHeight().Padding(0, SPUI::Padding, 0, 0)
                    [
                        SNew(SBox).Visibility_Lambda([this]() { return State->bBicycle ? EVisibility::Visible : EVisibility::Collapsed; })
                        [Hint(TEXT("F1"), TEXT("Ride settings"))]
                    ]
                ]
            ]
        ];
}
