#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "InputCoreTypes.h"
#include "SPReleaseCheck.generated.h"

class FJsonObject;

// Opt-in Development-build check. It drives mapped inputs for one short local
// sequence. It never starts a full circuit or runs during a normal launch.
UCLASS()
class ASPReleaseCheck : public AActor
{
    GENERATED_BODY()
public:
    ASPReleaseCheck();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
private:
    void Key(const FKey& Key, bool Down);
    void Tap(const FKey& Key);
    void Check(const FString& Name, bool Passed);
    void Shot(const FString& Name);
    void Finish();
    bool PrepareOffRoadFixture(class ASPExplorerCharacter& Explorer);
    double Started = 0;
    int32 Stage = 0;
    bool bFinished = false, bProfileOnly = false, bShortRideOnly = false;
    bool bWaterOnly = false;
    double FinishedAt = 0;
    FString Output;
    FVector StartPosition = FVector::ZeroVector;
    double WalkDistance = 0, RunDistance = 0, JumpHeight = 0;
    bool bSawAir = false;
    TArray<FKey> ReleaseNextTick;
    TSharedPtr<FJsonObject> Result;
    TArray<TSharedPtr<class FJsonValue>> Checks;
    TArray<double> Frames, Games, Renders, Gpus;
    uint64 PeakMemory = 0;
};
