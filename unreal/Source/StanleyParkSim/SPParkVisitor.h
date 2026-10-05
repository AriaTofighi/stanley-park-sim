#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SPParkVisitor.generated.h"

class USkeletalMeshComponent;
class UStaticMeshComponent;
class USPBicycleRider;
class UAnimSequence;

// Decorative visitors use the measured route and grounded side offsets.
// They yield to the player and never add blocking collision to the path.
UCLASS()
class STANLEYPARKSIM_API ASPParkVisitor : public AActor
{
    GENERATED_BODY()
public:
    ASPParkVisitor();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    void Configure(int32 InRoute, double Along, bool bRide, double Pace, double Offset);
private:
    UPROPERTY() TObjectPtr<USkeletalMeshComponent> Walker;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Frame;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> FrontWheel;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> RearWheel;
    UPROPERTY() TObjectPtr<USPBicycleRider> Rider;
    UPROPERTY() TObjectPtr<UAnimSequence> WalkClip;
    UPROPERTY() TObjectPtr<UAnimSequence> IdleClip;
    int32 RouteIndex = 0;
    double Distance = 0, TargetSpeed = 120, Speed = 0, SideOffset = 90, WheelAngle = 0;
    bool bCyclist = false, bMoving = false;
};
