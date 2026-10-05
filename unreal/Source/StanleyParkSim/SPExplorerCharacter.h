#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "SPExplorerCharacter.generated.h"

class USpringArmComponent;
class UCameraComponent;

UCLASS()
class STANLEYPARKSIM_API ASPExplorerCharacter : public ACharacter
{
    GENERATED_BODY()
public:
    ASPExplorerCharacter();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void SetupPlayerInputComponent(UInputComponent* Input) override;
    void PlaceOnGround(const FVector& Contact, double Yaw);
    void Recover();

private:
    UPROPERTY(VisibleAnywhere) TObjectPtr<USpringArmComponent> CameraArm;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UCameraComponent> Camera;
    FVector SafeLocation = FVector::ZeroVector;
    FRotator SafeRotation = FRotator::ZeroRotator;
    bool bHasSafeLocation = false;
    void MoveForward(float Value);
    void MoveRight(float Value);
    void LookYaw(float Value);
    void LookPitch(float Value);
    void StartRunning();
    void StopRunning();
    void Pause();
    void SwitchTravelMode();
    void ToggleControls();
    void ToggleNatureSounds();
};
