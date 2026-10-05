#include "SPUITheme.h"
#include "Brushes/SlateColorBrush.h"
#include "Brushes/SlateRoundedBoxBrush.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Styling/CoreStyle.h"
#include "Widgets/SViewport.h"

namespace
{
    FVector2D ViewportSize()
    {
        FVector2D Size(1280, 720);
        if (GEngine && GEngine->GameViewport)
        {
            // The overlay inherits desktop DPI. Use its parent's local size,
            // not physical pixels, so Windows scaling is not applied twice.
            const TSharedPtr<SViewport> Viewport = GEngine->GameViewport->GetGameViewportWidget();
            if (Viewport.IsValid() && Viewport->GetCachedGeometry().GetLocalSize().GetMin() > 0)
                Size = Viewport->GetCachedGeometry().GetLocalSize();
            else GEngine->GameViewport->GetViewportSize(Size);
        }
        return Size.ComponentMax(FVector2D(1, 1));
    }
}

float SPUI::ViewportScale()
{
    const FVector2D Size = ViewportSize();
    // A 1600x900 design canvas keeps the HUD 20% smaller at the same output
    // size. Desktop DPI is already supplied by the viewport parent.
    return FMath::Clamp(FMath::Min(Size.X / 1600., Size.Y / 900.), .25, 1.5);
}

FVector2D SPUI::LogicalViewport() { return ViewportSize() / ViewportScale(); }
FSlateFontInfo SPUI::Font(int32 Size, bool bBold)
{
    return FCoreStyle::GetDefaultFontStyle(bBold ? "Bold" : "Regular", Size);
}
const FSlateBrush* SPUI::PanelBrush()
{
    static const FSlateRoundedBoxBrush Brush(Panel, 4.f);
    return &Brush;
}
const FSlateBrush* SPUI::KeyBrush()
{
    static const FSlateRoundedBoxBrush Brush(FLinearColor(.10f, .13f, .11f, 1), 4.f,
        FLinearColor(.29f, .34f, .30f, 1), 1.f);
    return &Brush;
}
const FSlateBrush* SPUI::DividerBrush()
{
    static const FSlateColorBrush Brush(FLinearColor(.16f, .20f, .17f, 1));
    return &Brush;
}
FButtonStyle SPUI::ButtonStyle(bool bPrimary)
{
    const FLinearColor Fill = bPrimary ? Accent : FLinearColor(.09f, .13f, .10f, 1);
    const FLinearColor Foreground = bPrimary ? FLinearColor(.025f, .04f, .028f, 1) : Text;
    FButtonStyle Style = FCoreStyle::Get().GetWidgetStyle<FButtonStyle>("Button");
    Style.SetNormal(FSlateRoundedBoxBrush(Fill, 4.f));
    Style.SetHovered(FSlateRoundedBoxBrush(Fill * FLinearColor(1.18f, 1.18f, 1.18f, 1), 4.f));
    Style.SetPressed(FSlateRoundedBoxBrush(Fill * FLinearColor(.8f, .8f, .8f, 1), 4.f));
    Style.SetNormalForeground(Foreground).SetHoveredForeground(Foreground).SetPressedForeground(Foreground);
    Style.SetNormalPadding(FMargin(0)).SetPressedPadding(FMargin(0));
    return Style;
}
