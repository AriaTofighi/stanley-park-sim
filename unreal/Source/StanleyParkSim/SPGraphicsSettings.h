#pragma once

#include "CoreMinimal.h"

enum class ESPGraphicsPreset : uint8
{
    Performance, Balanced, Quality, Count
};

// Presets change rendering cost, not world geometry or collision. Output
// resolution and window mode remain under the engine's user settings.
namespace SPGraphics
{
    const TCHAR* Name(ESPGraphicsPreset Preset);
    const TCHAR* Description(ESPGraphicsPreset Preset);
    ESPGraphicsPreset SavedPreset();
    void ApplySavedPreset();
    void ApplyAndSavePreset(ESPGraphicsPreset Preset);
}
