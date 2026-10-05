#include "SPParkMinimap.h"
#include "SPParkHUDWidget.h"
#include "SPUITheme.h"
#include "Rendering/DrawElements.h"
#include "Styling/CoreStyle.h"

void SPParkMinimap::Construct(const FArguments& Arguments)
{
    State = Arguments._State;
    ForceVolatile(true); // Position and heading change without a text attribute.
}

int32 SPParkMinimap::OnPaint(const FPaintArgs&, const FGeometry& Geometry,
    const FSlateRect&, FSlateWindowElementList& Elements, int32 Layer,
    const FWidgetStyle& Style, bool) const
{
    FSlateDrawElement::MakeBox(Elements, Layer, Geometry.ToPaintGeometry(), &State->MinimapBrush,
        ESlateDrawEffect::None, Style.GetColorAndOpacityTint());
    FSlateDrawElement::MakeText(Elements, Layer+1,
        Geometry.ToPaintGeometry(FVector2D(20,20), FSlateLayoutTransform(FVector2D(10,8))),
        FText::FromString(TEXT("N")), SPUI::Font(10,true), ESlateDrawEffect::None, SPUI::Text);
    if (!State->bMapPositionValid) return Layer+1;
    const FVector2D Size = Geometry.GetLocalSize();
    // Keep the marker inside the map if the player leaves its coverage.
    const FVector2D P(FMath::Clamp(State->MapPosition.X*Size.X, 9., Size.X-9),
        FMath::Clamp(State->MapPosition.Y*Size.Y, 9., Size.Y-9));
    const double Yaw = FMath::DegreesToRadians(State->MapYaw);
    const FVector2D Forward(FMath::Sin(Yaw), -FMath::Cos(Yaw));
    const FVector2D Right(-Forward.Y, Forward.X);
    TArray<FVector2D> Arrow = { P+Forward*9, P-Forward*5+Right*5,
        P-Forward*2, P-Forward*5-Right*5, P+Forward*9 };
    FSlateDrawElement::MakeLines(Elements, Layer+2, Geometry.ToPaintGeometry(), Arrow,
        ESlateDrawEffect::None, FLinearColor(.025f,.04f,.035f,1), true, 5);
    FSlateDrawElement::MakeLines(Elements, Layer+3, Geometry.ToPaintGeometry(), Arrow,
        ESlateDrawEffect::None, FLinearColor(.98f,.99f,.94f,1), true, 2.5);
    return Layer+3;
}
