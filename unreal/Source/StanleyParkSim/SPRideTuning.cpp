#include "SPRideTuning.h"
#include "Misc/ConfigCacheIni.h"

namespace
{
constexpr const TCHAR* SettingsSection = TEXT("StanleyPark.RideTuning");
constexpr FSPRideSettingDefinition Definitions[] = {
    { TEXT("TopSpeedKmh"), TEXT("Top speed"), TEXT("km/h"), 10, 80, 1, 50, 15, 0 },
    { TEXT("AccelerationMps2"), TEXT("Pedal acceleration"), TEXT("m/s²"), .5f, 8, .05f, 4.2f, 1.45f, 2 },
    { TEXT("BrakingMps2"), TEXT("Braking strength"), TEXT("m/s²"), 2, 12, .1f, 6, 4.5f, 1 },
    { TEXT("SteeringDegrees"), TEXT("Steering range"), TEXT("degrees"), 10, 40, 1, 18, 28, 0 },
    { TEXT("FieldOfView"), TEXT("Camera field of view"), TEXT("degrees"), 60, 110, 1, 85, 85, 0 },
    { TEXT("LookSensitivity"), TEXT("Mouse look sensitivity"), TEXT("×"), .25f, 2.5f, .05f, 1, 1, 2 }
};
static_assert(UE_ARRAY_COUNT(Definitions) == static_cast<uint8>(ESPRideSetting::Count));
}

const FSPRideSettingDefinition& GetRideSettingDefinition(ESPRideSetting Setting)
{
    return Definitions[static_cast<uint8>(Setting)];
}

void FSPRideTuning::Set(ESPRideSetting Setting, float Value)
{
    const auto& Definition = GetRideSettingDefinition(Setting);
    if (FMath::IsFinite(Value))
        Values[static_cast<uint8>(Setting)] = FMath::Clamp(Value, Definition.Minimum, Definition.Maximum);
}

void FSPRideTuning::Reset(bool bOriginalPace)
{
    for (uint8 Index = 0; Index < static_cast<uint8>(ESPRideSetting::Count); ++Index)
        Values[Index] = bOriginalPace ? Definitions[Index].OriginalPace : Definitions[Index].RoamDefault;
}

void FSPRideTuning::Load()
{
    if (!GConfig) return;
    for (uint8 Index = 0; Index < static_cast<uint8>(ESPRideSetting::Count); ++Index)
    {
        float Value;
        if (GConfig->GetFloat(SettingsSection, Definitions[Index].Key, Value, GGameUserSettingsIni))
            Set(static_cast<ESPRideSetting>(Index), Value);
    }
    int32 Version = 0;
    GConfig->GetInt(SettingsSection, TEXT("DefaultsVersion"), Version, GGameUserSettingsIni);
    if (Version < 2)
    {
        // Upgrade values left at v0.4 defaults. Deliberate custom values stay.
        if (FMath::IsNearlyEqual(Get(ESPRideSetting::TopSpeed), 40.f)) Set(ESPRideSetting::TopSpeed, 50);
        if (FMath::IsNearlyEqual(Get(ESPRideSetting::Acceleration), 3.5f)) Set(ESPRideSetting::Acceleration, 4.2f);
        if (FMath::IsNearlyEqual(Get(ESPRideSetting::Steering), 28.f)
            && !FMath::IsNearlyEqual(Get(ESPRideSetting::TopSpeed), 15.f)) Set(ESPRideSetting::Steering, 18);
        Save();
    }
}

void FSPRideTuning::Save() const
{
    if (!GConfig) return;
    GConfig->SetInt(SettingsSection, TEXT("DefaultsVersion"), 2, GGameUserSettingsIni);
    for (uint8 Index = 0; Index < static_cast<uint8>(ESPRideSetting::Count); ++Index)
        GConfig->SetFloat(SettingsSection, Definitions[Index].Key, Values[Index], GGameUserSettingsIni);
    GConfig->Flush(false, GGameUserSettingsIni);
}

bool FSPRideTuning::HasRoamMovementDefaults() const
{
    // Camera preferences do not affect the diagnostic's steering or speed.
    for (uint8 Index = 0; Index <= static_cast<uint8>(ESPRideSetting::Steering); ++Index)
        if (!FMath::IsNearlyEqual(Values[Index], Definitions[Index].RoamDefault, .001f)) return false;
    return true;
}
