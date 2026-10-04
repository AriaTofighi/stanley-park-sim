#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "SPRidingDiagnostics.h"
#include "SPRideTuning.h"
#include "SPBicyclePawn.generated.h"

class UCapsuleComponent;
class UStaticMeshComponent;
class USpringArmComponent;
class UCameraComponent;
class USoundBase;
class USPBicycleRider;

UCLASS()
class STANLEYPARKSIM_API ASPBicyclePawn : public APawn
{
    GENERATED_BODY()
public:
    ASPBicyclePawn();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
    void Recover();
    void PlaceOnRoute(const FVector& Contact, double Yaw);
    bool SetWalking(bool bRequested);
    double GetSpeedKmh() const { return Speed * 0.036; }
    double GetDistanceMetres() const { return Distance / 100.0; }
    bool IsWalking() const { return bWalking; }
    bool IsPedalling() const { return !bWalking && Pedal > .05f && Brake < .05f && !bSettingsOpen; }
    bool HasSurface() const { return bHasSurface; }
    double GetDroppedSimulationTime() const { return DroppedSimulationTime; }
    const FString& GetDiagnosticStatus() const { return Diagnostics.Status(); }
    int32 GetBlockingContactCount() const { return BlockingContactCount; }
    uint64 GetSurfaceMissCount() const { return SurfaceMissCount; }
    const FSPRideTuning& GetRideTuning() const { return RideTuning; }
    void SetRideSetting(ESPRideSetting Setting, float Value);
    void ResetRideTuning(bool bOriginalPace = false);
    void SaveRideTuning() const { RideTuning.Save(); }
    void SetSettingsOpen(bool bOpen);
    FString Notice;

private:
    UPROPERTY(VisibleAnywhere) TObjectPtr<UCapsuleComponent> Collision;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> Bicycle;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> FrontWheel;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> RearWheel;
    UPROPERTY(VisibleAnywhere) TObjectPtr<USPBicycleRider> Rider;
    UPROPERTY(VisibleAnywhere) TObjectPtr<USpringArmComponent> CameraArm;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UCameraComponent> Camera;
    UPROPERTY() TObjectPtr<USoundBase> BellSound;
    double Speed = 0, Distance = 0, Accumulator = 0, DroppedSimulationTime = 0;
    float Pedal = 0, Brake = 0, Steer = 0, SteeringAngle = 0;
    float LookYaw = 0, LookPitch = -4, WheelAngle = 0;
    bool bWalking = false, bChaseCamera = true, bHasSurface = false;
    double VerticalSpeed = 0;
    bool bHasSafePosition = false;
    FVector LastSafe = FVector::ZeroVector;
    double LastSafeYaw = 0;
    double LastBellTime = -10;
    FSPRidingDiagnostics Diagnostics;
    int32 BlockingContactCount = 0;
    uint64 SurfaceMissCount = 0; // Latched across all fixed steps, including within one frame.
    FSPRideTuning RideTuning;
    bool bSettingsOpen = false;

    void Simulate(double Step);
    bool GroundAt(const FVector& Position, FHitResult& Hit) const;
    void MoveOverGround(const FVector& Movement, bool bCanStep, FHitResult& Hit);
    bool WalkingBikePoseBlocked(const FTransform& From, const FTransform& To) const;
    void SetPedal(float Value) { Pedal = bSettingsOpen ? 0.f : FMath::Clamp(Value, 0.f, 1.f); }
    void SetBrake(float Value) { Brake = bSettingsOpen ? 0.f : FMath::Clamp(Value, 0.f, 1.f); }
    void SetSteer(float Value) { Steer = bSettingsOpen || FMath::Abs(Value) < 0.12f ? 0.f : Value; }
    void LookHorizontal(float Value);
    void LookVertical(float Value);
    void ToggleCamera();
    void ToggleDismount();
    void ToggleExplorer();
    void RingBell();
    void PauseRide();
    void ToggleSettings();
    void ToggleControls();
    void UpdateCamera();
    void ToggleRideCheck();
    void ToggleCircuitCheck();
};
