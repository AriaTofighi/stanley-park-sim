#pragma once

#include "CoreMinimal.h"

enum class ESPRideSetting : uint8
{
    TopSpeed, Acceleration, Braking, Steering, FieldOfView, LookSensitivity, Count
};

struct FSPRideSettingDefinition
{
    const TCHAR* Key;
    const TCHAR* Label;
    const TCHAR* Unit;
    float Minimum, Maximum, Step, RoamDefault, OriginalPace;
    int32 Decimals;
};

const FSPRideSettingDefinition& GetRideSettingDefinition(ESPRideSetting Setting);

// Per-player development controls. Source geometry and access rules are separate.
class FSPRideTuning
{
public:
    FSPRideTuning() { Reset(); }
    float Get(ESPRideSetting Setting) const { return Values[static_cast<uint8>(Setting)]; }
    void Set(ESPRideSetting Setting, float Value);
    void Reset(bool bOriginalPace = false);
    void Load();
    void Save() const;
    bool HasRoamMovementDefaults() const;

private:
    float Values[static_cast<uint8>(ESPRideSetting::Count)]{};
};
