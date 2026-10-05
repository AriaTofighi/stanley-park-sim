#pragma once

#include "CoreMinimal.h"

class ASPBicyclePawn;
class ASPWorldDirector;

struct FSPAutopilotInputs
{
    float Pedal = 0;
    float Brake = 0;
    float Steer = 0;
    bool bWalking = false;
};

// A player-facing route follower, separate from development diagnostics.
// It supplies normal movement inputs; it never teleports or skips collision.
class FSPBicycleAutopilot
{
public:
    bool Start(const ASPBicyclePawn& Bicycle, ASPWorldDirector* World);
    void Stop();
    void StopWithReason(const FString& Reason);
    bool IsActive() const { return bActive; }
    const FString& GetFailure() const { return Failure; }
    FSPAutopilotInputs Update(const ASPBicyclePawn& Bicycle, double Step, bool bBoost);
    static double SteeringRange(double SpeedCm) { return 35.0/(1.0+SpeedCm/700.0); }

private:
    TWeakObjectPtr<ASPWorldDirector> Director;
    bool bActive = false;
    double MainAlong = 0;
    double GuideAlong = 0;
    double StoppedTime = 0;
    int32 GuideIndex = INDEX_NONE;
    int32 CompletedGuide = INDEX_NONE;
    FString Failure;
};
