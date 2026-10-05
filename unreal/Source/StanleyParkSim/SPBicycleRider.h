#pragma once

#include "CoreMinimal.h"
#include "Components/PoseableMeshComponent.h"
#include "SPBicycleRider.generated.h"

class UStaticMesh;
class UStaticMeshComponent;

// Uses the same Blender-authored mesh and materials as the explorer.
UCLASS()
class STANLEYPARKSIM_API USPBicycleRider : public UPoseableMeshComponent
{
    GENERATED_BODY()
public:
    USPBicycleRider();
    virtual void BeginPlay() override;
    virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
    void SetWalkingPose(bool bWalking);
    void SetAmbientMotion(double MetresPerSecond) { AmbientSpeed = MetresPerSecond; }

private:
    UPROPERTY() TObjectPtr<UStaticMesh> AnimatedFrame;
    UPROPERTY() TObjectPtr<UStaticMesh> PedalMesh;
    UPROPERTY() TObjectPtr<UStaticMesh> CrankMesh;
    UPROPERTY(Transient) TArray<TObjectPtr<UStaticMeshComponent>> Pedals;
    UPROPERTY(Transient) TArray<TObjectPtr<UStaticMeshComponent>> Cranks;
    TArray<FTransform> ReferencePose;
    TArray<FTransform> Pose;
    double PedalPhase = 0.0;
    double Cadence = 0.0;
    double WalkPhase = 0.0;
    double AmbientSpeed = 0.0;
    bool bWalkingPose = false;
    bool bReferenceValid = false;
    void CacheReferencePose();
    void UpdatePose();
    void UpdatePedalMeshes();
};
