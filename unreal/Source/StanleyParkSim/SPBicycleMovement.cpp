#include "SPBicycleMovement.h"
#include "Components/CapsuleComponent.h"
#include "Engine/World.h"
#include "Engine/ScopedMovementUpdate.h"

namespace
{
    constexpr double WalkableZ = .55;
    constexpr double StepHeight = 40;
    constexpr double FloorGap = 6;
}

USPBicycleMovement::USPBicycleMovement()
{
    // The pawn supplies fixed simulation steps. No second movement tick.
    PrimaryComponentTick.bCanEverTick = false;
}

bool USPBicycleMovement::GroundAt(const FVector& Position, FHitResult& Hit) const
{
    FCollisionQueryParams Query(SCENE_QUERY_STAT(BicycleGround), true, GetOwner());
    return GetWorld()->LineTraceSingleByChannel(Hit, Position, Position-FVector(0,0,300),
        ECC_WorldStatic, Query) && Hit.ImpactNormal.Z > WalkableZ;
}

double USPBicycleMovement::FloorClearance(const FHitResult& Floor) const
{
    const UCapsuleComponent* Capsule = CastChecked<UCapsuleComponent>(UpdatedComponent);
    const double Radius = Capsule->GetScaledCapsuleRadius();
    return Capsule->GetScaledCapsuleHalfHeight()-Radius
        + Radius/FMath::Max(Floor.ImpactNormal.Z,WalkableZ) + FloorGap;
}

bool USPBicycleMovement::TryStep(const FVector& Remaining, double StartZ)
{
    // A failed trial restores location and deferred overlap events together.
    FScopedMovementUpdate Trial(UpdatedComponent, EScopedUpdate::DeferredUpdates);
    const FQuat Rotation = UpdatedComponent->GetComponentQuat();
    FHitResult Up, Across, Down;
    SafeMoveUpdatedComponent(FVector(0,0,StepHeight),Rotation,true,Up);
    if (Up.bBlockingHit || Up.bStartPenetrating) { Trial.RevertMove(); return false; }
    SafeMoveUpdatedComponent(FVector(Remaining.X,Remaining.Y,0),Rotation,true,Across);
    if (Across.bBlockingHit || Across.bStartPenetrating) { Trial.RevertMove(); return false; }
    FHitResult Floor;
    if (!GroundAt(UpdatedComponent->GetComponentLocation(),Floor)) { Trial.RevertMove(); return false; }
    const double Landing = Floor.ImpactPoint.Z+FloorClearance(Floor);
    if (Landing > StartZ+StepHeight || Landing < StartZ-StepHeight)
    { Trial.RevertMove(); return false; }
    SafeMoveUpdatedComponent(FVector(0,0,Landing-UpdatedComponent->GetComponentLocation().Z),Rotation,true,Down);
    if (Down.bStartPenetrating || (Down.bBlockingHit && Down.ImpactNormal.Z <= WalkableZ))
    { Trial.RevertMove(); return false; }
    return true;
}

void USPBicycleMovement::MoveOverGround(const FVector& Delta, bool bGrounded, FHitResult& Obstacle,
    FHitResult* SurfaceContact)
{
    Obstacle = FHitResult();
    const FVector Start = UpdatedComponent->GetComponentLocation();
    FHitResult Hit;
    SafeMoveUpdatedComponent(Delta,UpdatedComponent->GetComponentQuat(),true,Hit);
    if (SurfaceContact) *SurfaceContact = Hit;
    if (!Hit.bBlockingHit && !Hit.bStartPenetrating) return;
    if (Hit.bStartPenetrating) { Obstacle = Hit; return; }

    // Ground triangle edges and curb faces both use the swept step. The old
    // code excluded sloping floor hits and repeatedly slowed on those seams.
    const FHitResult FirstHit = Hit;
    const FVector Remaining = Delta*(1-Hit.Time);
    if (bGrounded && !Remaining.IsNearlyZero() && TryStep(Remaining,Start.Z)) return;
    FVector SlideNormal = Hit.Normal;
    if (Hit.ImpactNormal.Z <= WalkableZ)
        SlideNormal = FVector(SlideNormal.X,SlideNormal.Y,0).GetSafeNormal();
    SlideAlongSurface(Delta,1-Hit.Time,SlideNormal,Hit,false);
    if (SurfaceContact && Hit.bBlockingHit) *SurfaceContact = Hit;

    // Floor impacts are support, never a braking obstacle. Grazing walls
    // constrain displacement but do not repeatedly multiply scalar speed.
    const FVector Travel = UpdatedComponent->GetComponentLocation()-Start;
    const FVector Direction = FVector(Delta.X,Delta.Y,0).GetSafeNormal();
    const auto PreventsTravel = [&](const FHitResult& Contact)
    {
        return Contact.bStartPenetrating || (Contact.IsValidBlockingHit()
            && Contact.ImpactNormal.Z <= WalkableZ
            && -FVector::DotProduct(Direction,Contact.ImpactNormal) > .45);
    };
    if (Delta.Size2D() > .01 && Travel.Size2D() < Delta.Size2D()*.15)
    {
        if (PreventsTravel(Hit)) Obstacle = Hit;
        else if (PreventsTravel(FirstHit)) Obstacle = FirstHit;
    }
}
