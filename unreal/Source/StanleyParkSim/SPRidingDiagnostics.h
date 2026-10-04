#pragma once

#include "CoreMinimal.h"
#include "SPRouteData.h"
#include "SPRideCapture.h"
#include "SPJoinCheck.h"

class ASPBicyclePawn;
class FJsonValue;
class FJsonObject;

struct FSPFrameTiming
{
    float Frame = 0, Game = 0, Render = 0, Rhi = 0, Gpu = -1;
};

struct FSPGateTraversal
{
    bool bEntered = false, bPassed = false;
    double FirstDistance = 0, LastDistance = 0, MaximumPlanarOffset = 0;
    int32 ObservedFrames = 0;
};

// An explicit development scenario. It supplies normal controller inputs;
// it never moves the bicycle directly after the initial fixture placement.
class FSPRidingDiagnostics
{
public:
    ~FSPRidingDiagnostics();
    bool Start(ASPBicyclePawn& Pawn, bool bFullCircuit = false);
    void Inputs(ASPBicyclePawn& Pawn, float& Pedal, float& Brake, float& Steer);
    void RefreshCircuitRidingSpeedInputs(const ASPBicyclePawn& Pawn, float& Pedal, float& Brake) const;
    void Record(ASPBicyclePawn& Pawn, float DeltaSeconds);
    void Stop(const ASPBicyclePawn& Pawn, bool bCompleted);
    bool IsActive() const { return bActive || PendingResult.IsValid(); }
    const FString& Status() const { return Label; }

private:
    void SavePendingResult();
    TSharedPtr<FJsonObject> PendingResult;
    FString PendingFilename;
    FSPWorldData Data;
    TArray<FSPGateTraversal> GateTraversals;
    void RecordGateTraversals(const ASPBicyclePawn& Pawn, const FVector& Contact, double MainChainage);
    TArray<float> FrameTimes;
    TArray<FSPFrameTiming> EngineTimings;
    TArray<TSharedPtr<FJsonValue>> Samples;
    FString Label;
    double Elapsed = 0, NextSample = 0, StartDistance = 0, StartDropped = 0;
    double MaximumSpeed = 0, MaximumRouteError = 0, BrakeEndSpeed = 0;
    double SetupMilliseconds = 0;
    double Progress = 0, PreviousChainage = 0, LastAdvanceTime = 0, NextProgressReport = 0;
    double LastAdvanceProgress = 0;
    int32 PassedGates = 0, WalkingTransitions = 0;
    bool bCircuit = false, bFinishing = false;
    bool bCircuitRidingFeedback = false;
    double CircuitRidingTarget = 0, CircuitRidingBrakeThreshold = 0;
    FString Failure;
    FSPRideCapture Capture;
    bool bCaptureRequested = false;
    bool bFastRoamCheck = false;
    bool bGateCheck = false;
    bool bJoinCheck = false;
    FSPJoinCheck JoinCheck;
    int32 JoinCheckpoints = 0;
    int32 GateCheckIndex = INDEX_NONE;
    double GateCheckEnd = 0;
    int32 FramesWithoutSurface = 0;
    uint64 StartSurfaceMisses = 0;
    bool bActive = false;
};
