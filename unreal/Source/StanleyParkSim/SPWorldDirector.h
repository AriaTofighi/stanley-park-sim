#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SPRouteData.h"
#include "SPWorldDirector.generated.h"

class USPSeawallBirds;
class UAudioComponent;
class ASPParkVisitor;

UCLASS()
class STANLEYPARKSIM_API ASPWorldDirector : public AActor
{
    GENERATED_BODY()
public:
    ASPWorldDirector();
    virtual void BeginPlay() override;
    bool GetRecoveryLocation(const FVector& Position, FVector& Place, double& Yaw) const;
    void OnBell(const FVector& Position);
    bool IsBellNear(const FVector& Position) const;
    void ToggleAmbience();
    const FSPWorldData& GetData() const { return Data; }
    FString Error;

private:
    UPROPERTY(VisibleAnywhere) TObjectPtr<USPSeawallBirds> SeawallBirds;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UAudioComponent> Ambience;
    UPROPERTY() TArray<TObjectPtr<ASPParkVisitor>> Visitors;
    FSPWorldData Data;
    double BellUntil = 0;
    FVector BellPosition = FVector::ZeroVector;
};
