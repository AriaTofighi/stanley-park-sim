#pragma once

#include "CoreMinimal.h"
#include "Widgets/SLeafWidget.h"

struct FSPHudState;

// A fixed park overview with one live position/heading marker. No scene capture.
class SPParkMinimap : public SLeafWidget
{
public:
    SLATE_BEGIN_ARGS(SPParkMinimap) {}
        SLATE_ARGUMENT(TSharedPtr<FSPHudState>, State)
    SLATE_END_ARGS()
    void Construct(const FArguments& Arguments);
    virtual FVector2D ComputeDesiredSize(float) const override { return FVector2D(240, 240); }
    virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& Geometry,
        const FSlateRect& CullingRect, FSlateWindowElementList& Elements, int32 Layer,
        const FWidgetStyle& Style, bool bParentEnabled) const override;

private:
    TSharedPtr<FSPHudState> State;
};
