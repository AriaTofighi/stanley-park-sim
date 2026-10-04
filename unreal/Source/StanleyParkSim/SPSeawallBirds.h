#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "SPSeawallBirds.generated.h"

class UStaticMeshComponent;

struct FSPSeawallBird
{
    FString ZoneId;
    FVector Centre = FVector::ZeroVector;
    FVector2D Radius = FVector2D::ZeroVector;
    TArray<double> ArcLengths;
    double Phase = 0;
    double Speed = 0;
    double FlapPhase = 0;
    double ClearanceAt = 0;
    double LastClearanceTime = -1;
    double LastFloorClearance = 0;
    double MinFloorClearance = TNumericLimits<double>::Max();
    double FlapDegrees = 0;
    double MinShownFlapDegrees = TNumericLimits<double>::Max();
    double MaxShownFlapDegrees = TNumericLimits<double>::Lowest();
    double BankDegrees = 0;
    int32 TransformSamples = 0;
    int32 ClearanceSamples = 0;
    int32 SweepSamples = 0;
    int32 BlockedSamples = 0;
    int32 CulledSamples = 0;
    int32 GlideSamples = 0;
    int32 FlapSamples = 0;
    bool bFloorHit = false;
    FString LastBlockingActor;
    bool bClear = false;
    bool bVisible = false;
};

// A small visual layer. It has no navigation, perception, physics, or audio.
UCLASS(ClassGroup=(StanleyPark))
class STANLEYPARKSIM_API USPSeawallBirds : public UActorComponent
{
    GENERATED_BODY()
public:
    USPSeawallBirds();
    virtual void BeginPlay() override;
    virtual void TickComponent(float DeltaTime, ELevelTick TickType,
        FActorComponentTickFunction* ThisTickFunction) override;
    // Read-only capture support. Returns actual component transforms and query
    // counters; it does not move birds or declare visual/collision acceptance.
    UFUNCTION(BlueprintCallable, Category="Stanley Park|Birds")
    FString GetReviewSnapshot() const;

private:
    UPROPERTY(Transient) TArray<TObjectPtr<UStaticMeshComponent>> Parts;
    TArray<FSPSeawallBird> Birds;
    bool bReady = false;
    bool bUnavailable = false;
    bool bSeawallMap = false;
    double WaterHeight = 20.452;
    bool InitializeBirds();
    void HideBird(int32 Index);
    bool CheckClearance(FSPSeawallBird& Bird, const FVector& Position, const FVector& LookAhead);
    FVector SampleFlight(const FSPSeawallBird& Bird, double Time, double* OutAngle = nullptr) const;
};
