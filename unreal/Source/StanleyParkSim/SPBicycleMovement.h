#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PawnMovementComponent.h"
#include "SPBicycleMovement.generated.h"

// Collision movement is separate from the pawn's steering/acceleration model.
// Engine safe moves resolve multiple overlaps and engine slides handle corners.
UCLASS()
class STANLEYPARKSIM_API USPBicycleMovement : public UPawnMovementComponent
{
    GENERATED_BODY()
public:
    USPBicycleMovement();
    bool GroundAt(const FVector& Position, FHitResult& Hit) const;
    double FloorClearance(const FHitResult& Floor) const;
    void MoveOverGround(const FVector& Delta, bool bGrounded, FHitResult& Obstacle,
        FHitResult* SurfaceContact = nullptr);

private:
    bool TryStep(const FVector& Remaining, double StartZ);
};
