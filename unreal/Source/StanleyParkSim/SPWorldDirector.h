#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SPRouteData.h"
#include "SPWorldDirector.generated.h"

class UInstancedStaticMeshComponent;
class USPSeawallBirds;

struct FSPAmbientAgent
{
    int32 RouteIndex = 0;
    int32 Instance = 0;
    double Distance = 0;
    double Speed = 0;
    double TargetSpeed = 0;
    double Phase = 0;
    bool bCyclist = false;
};

UCLASS()
class STANLEYPARKSIM_API ASPWorldDirector : public AActor
{
    GENERATED_BODY()
public:
    ASPWorldDirector();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    bool GetRecoveryLocation(const FVector& Position, FVector& Place, double& Yaw) const;
    void OnBell(const FVector& Position);
    const FSPWorldData& GetData() const { return Data; }
    FString Error;

private:
    UPROPERTY(VisibleAnywhere) TObjectPtr<USPSeawallBirds> SeawallBirds;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> Walkers;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> Riders;
    FSPWorldData Data;
    TArray<FSPAmbientAgent> Agents;
    double AmbientAccumulator = 0;
    double BellUntil = 0;
    FVector BellPosition = FVector::ZeroVector;
    void UpdateAgents(double DeltaSeconds);
};
