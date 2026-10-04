#include "SPGraphicsSettings.h"
#include "GameFramework/GameUserSettings.h"
#include "Misc/ConfigCacheIni.h"

namespace
{
    constexpr const TCHAR* SettingsSection = TEXT("StanleyPark.Graphics");
    struct FGraphicsPreset
    {
        const TCHAR* Name;
        const TCHAR* Description;
        float ResolutionScale;
        int32 Detail;
    };
    constexpr FGraphicsPreset Presets[] = {
        { TEXT("Performance"), TEXT("Lower shadows and foliage detail. 50% render scale; 60 fps limit."), 50, 1 },
        { TEXT("Balanced"), TEXT("High detail. 67% render scale; 60 fps limit."), 67, 2 },
        { TEXT("Quality"), TEXT("Higher detail at full render resolution. 60 fps limit."), 100, 3 }
    };
    static_assert(UE_ARRAY_COUNT(Presets) == static_cast<uint8>(ESPGraphicsPreset::Count));

    const FGraphicsPreset& Definition(ESPGraphicsPreset Preset)
    {
        const uint8 Index = static_cast<uint8>(Preset);
        return Presets[Index < UE_ARRAY_COUNT(Presets) ? Index : static_cast<uint8>(ESPGraphicsPreset::Balanced)];
    }

    void Apply(ESPGraphicsPreset Preset, bool bSave)
    {
        UGameUserSettings* Settings = UGameUserSettings::GetGameUserSettings();
        if (!Settings) return;
        const FGraphicsPreset& Value = Definition(Preset);
        Settings->SetResolutionScaleValueEx(Value.ResolutionScale);
        Settings->SetViewDistanceQuality(Value.Detail);
        Settings->SetAntiAliasingQuality(FMath::Max(2, Value.Detail));
        Settings->SetShadowQuality(Value.Detail);
        Settings->SetGlobalIlluminationQuality(0);
        Settings->SetReflectionQuality(0);
        Settings->SetPostProcessingQuality(Value.Detail);
        Settings->SetTextureQuality(2);
        Settings->SetVisualEffectQuality(Value.Detail);
        Settings->SetFoliageQuality(Value.Detail);
        Settings->SetShadingQuality(Value.Detail);
        Settings->SetFrameRateLimit(60);
        // Apply quality without changing the output resolution, window mode,
        // or the user's display confirmation state. Console overrides retain
        // their engine-defined priority for explicit profiling sessions.
        Settings->ApplyNonResolutionSettings();
        if (bSave)
        {
            Settings->SaveSettings();
            if (GConfig)
            {
                GConfig->SetString(SettingsSection, TEXT("Preset"), Value.Name, GGameUserSettingsIni);
                GConfig->Flush(false, GGameUserSettingsIni);
            }
        }
        UE_LOG(LogTemp, Display, TEXT("SP_GRAPHICS_PRESET: %s (requested scale %.0f%%, detail %d, cap 60)"),
            Value.Name, Value.ResolutionScale, Value.Detail);
    }
}

const TCHAR* SPGraphics::Name(ESPGraphicsPreset Preset) { return Definition(Preset).Name; }
const TCHAR* SPGraphics::Description(ESPGraphicsPreset Preset) { return Definition(Preset).Description; }

ESPGraphicsPreset SPGraphics::SavedPreset()
{
    FString Saved;
    if (GConfig && GConfig->GetString(SettingsSection, TEXT("Preset"), Saved, GGameUserSettingsIni))
        for (uint8 Index = 0; Index < static_cast<uint8>(ESPGraphicsPreset::Count); ++Index)
            if (Saved.Equals(Presets[Index].Name, ESearchCase::IgnoreCase))
                return static_cast<ESPGraphicsPreset>(Index);
    return ESPGraphicsPreset::Balanced;
}

void SPGraphics::ApplySavedPreset() { Apply(SavedPreset(), false); }
void SPGraphics::ApplyAndSavePreset(ESPGraphicsPreset Preset) { Apply(Preset, true); }
