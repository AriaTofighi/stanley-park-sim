#pragma once

#include "CoreMinimal.h"
#include "Styling/SlateBrush.h"
#include "Styling/SlateTypes.h"

// All measurements are logical Slate units. Exactly one scale is applied at
// each viewport root; descendants use these unscaled values.
namespace SPUI
{
    constexpr float Unit = 8;
    constexpr float Margin = 4 * Unit;
    constexpr float Padding = 2 * Unit;
    constexpr float RowHeight = 4 * Unit;
    constexpr float ButtonHeight = 6 * Unit;
    inline const FLinearColor Text(.94f, .95f, .91f, 1);
    inline const FLinearColor Muted(.64f, .71f, .68f, 1);
    inline const FLinearColor Accent(.68f, .82f, .63f, 1);
    inline const FLinearColor Warning(.96f, .76f, .43f, 1);
    inline const FLinearColor Error(1, .58f, .49f, 1);
    inline const FLinearColor Panel(.018f, .027f, .024f, .94f);

    float ViewportScale();
    FVector2D LogicalViewport();
    FSlateFontInfo Font(int32 Size, bool bBold = false);
    const FSlateBrush* PanelBrush();
    const FSlateBrush* KeyBrush();
    const FSlateBrush* DividerBrush();
    FButtonStyle ButtonStyle(bool bPrimary);
}
