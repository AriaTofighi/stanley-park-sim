#include "SPExplorerCharacter.h"
#include "SPExplorerAnimInstance.h"
#include "SPGameMode.h"
#include "SPHud.h"
#include "SPWaterSafety.h"
#include "Camera/CameraComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Engine/World.h"
#include "Components/CapsuleComponent.h"
#include "Components/InputComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "Kismet/GameplayStatics.h"
#include "UObject/ConstructorHelpers.h"

ASPExplorerCharacter::ASPExplorerCharacter()
{
    PrimaryActorTick.bCanEverTick = true;
    GetCapsuleComponent()->InitCapsuleSize(34.f, 90.f);
    GetMesh()->SetRelativeLocation(FVector(0, 0, -90));
    GetMesh()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    bUseControllerRotationYaw = false;
    UCharacterMovementComponent* Movement = GetCharacterMovement();
    Movement->bOrientRotationToMovement = true;
    Movement->RotationRate = FRotator(0, 540, 0);
    Movement->MaxWalkSpeed = 260;
    Movement->JumpZVelocity = 520;
    Movement->AirControl = .35f;
    Movement->BrakingDecelerationWalking = 1800;
    Movement->MaxStepHeight = 40;
    Movement->SetWalkableFloorAngle(45);
    CameraArm = CreateDefaultSubobject<USpringArmComponent>(TEXT("ExplorerCameraArm"));
    CameraArm->SetupAttachment(RootComponent);
    CameraArm->TargetArmLength = 380;
    CameraArm->SocketOffset = FVector(0, 45, 70);
    CameraArm->bUsePawnControlRotation = true;
    CameraArm->bDoCollisionTest = true;
    CameraArm->bEnableCameraLag = true;
    CameraArm->CameraLagSpeed = 12;
    Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("ExplorerCamera"));
    Camera->SetupAttachment(CameraArm);
    Camera->SetFieldOfView(80);
    static ConstructorHelpers::FObjectFinder<USkeletalMesh> Model(TEXT("/Game/StanleyPark/Explorer/SK_Explorer.SK_Explorer"));
    if (Model.Succeeded()) GetMesh()->SetSkeletalMesh(Model.Object);
    GetMesh()->SetAnimInstanceClass(USPExplorerAnimInstance::StaticClass());
}

void ASPExplorerCharacter::BeginPlay()
{
    Super::BeginPlay();
    SafeLocation = GetActorLocation();
    SafeRotation = GetActorRotation();
    bHasSafeLocation = true;
    if (APlayerController* Player = Cast<APlayerController>(GetController()))
    {
        Player->PlayerCameraManager->ViewPitchMin = -65;
        Player->PlayerCameraManager->ViewPitchMax = 35;
        Player->SetControlRotation(FRotator(-12, GetActorRotation().Yaw, 0));
    }
}

void ASPExplorerCharacter::SetupPlayerInputComponent(UInputComponent* Input)
{
    Super::SetupPlayerInputComponent(Input);
    Input->BindAxis(TEXT("ExploreForward"), this, &ASPExplorerCharacter::MoveForward);
    Input->BindAxis(TEXT("ExploreRight"), this, &ASPExplorerCharacter::MoveRight);
    Input->BindAxis(TEXT("LookX"), this, &ASPExplorerCharacter::LookYaw);
    Input->BindAxis(TEXT("LookY"), this, &ASPExplorerCharacter::LookPitch);
    Input->BindAction(TEXT("ExploreJump"), IE_Pressed, this, &ACharacter::Jump);
    Input->BindAction(TEXT("ExploreJump"), IE_Released, this, &ACharacter::StopJumping);
    Input->BindAction(TEXT("ExploreRun"), IE_Pressed, this, &ASPExplorerCharacter::StartRunning);
    Input->BindAction(TEXT("ExploreRun"), IE_Released, this, &ASPExplorerCharacter::StopRunning);
    Input->BindAction(TEXT("Recover"), IE_Pressed, this, &ASPExplorerCharacter::Recover);
    Input->BindAction(TEXT("PauseRide"), IE_Pressed, this, &ASPExplorerCharacter::Pause).bExecuteWhenPaused = true;
    Input->BindKey(EKeys::Tab, IE_Pressed, this, &ASPExplorerCharacter::SwitchTravelMode);
    Input->BindKey(EKeys::H, IE_Pressed, this, &ASPExplorerCharacter::ToggleControls);
}

void ASPExplorerCharacter::ToggleControls()
{
    if (APlayerController* Player = Cast<APlayerController>(GetController()))
        if (ASPHud* Hud = Cast<ASPHud>(Player->GetHUD())) Hud->ToggleControls();
}

void ASPExplorerCharacter::MoveForward(float Value)
{
    if (Controller) AddMovementInput(FRotationMatrix(FRotator(0, Controller->GetControlRotation().Yaw, 0)).GetUnitAxis(EAxis::X), Value);
}
void ASPExplorerCharacter::MoveRight(float Value)
{
    if (Controller) AddMovementInput(FRotationMatrix(FRotator(0, Controller->GetControlRotation().Yaw, 0)).GetUnitAxis(EAxis::Y), Value);
}
void ASPExplorerCharacter::LookYaw(float Value) { AddControllerYawInput(Value); }
void ASPExplorerCharacter::LookPitch(float Value) { AddControllerPitchInput(Value); }
void ASPExplorerCharacter::StartRunning() { GetCharacterMovement()->MaxWalkSpeed = 600; }
void ASPExplorerCharacter::StopRunning() { GetCharacterMovement()->MaxWalkSpeed = 260; }
void ASPExplorerCharacter::Pause()
{
    StopRunning();
    UGameplayStatics::SetGamePaused(this, !UGameplayStatics::IsGamePaused(this));
}
void ASPExplorerCharacter::SwitchTravelMode()
{
    if (ASPGameMode* Mode = GetWorld()->GetAuthGameMode<ASPGameMode>()) Mode->ToggleExplorer();
}

void ASPExplorerCharacter::PlaceOnGround(const FVector& Contact, double Yaw)
{
    const FVector Location = Contact + FVector(0, 0, GetCapsuleComponent()->GetScaledCapsuleHalfHeight() + 3);
    if (TeleportTo(Location, FRotator(0, Yaw, 0)))
    {
        GetCharacterMovement()->StopMovementImmediately();
        SafeLocation = GetActorLocation(); SafeRotation = GetActorRotation(); bHasSafeLocation = true;
        if (Controller) Controller->SetControlRotation(FRotator(-12, Yaw, 0));
    }
}

void ASPExplorerCharacter::Recover()
{
    if (bHasSafeLocation && TeleportTo(SafeLocation, SafeRotation))
    {
        GetCharacterMovement()->StopMovementImmediately();
        StopJumping();
    }
}

void ASPExplorerCharacter::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    double WaterZ = 0;
    const bool bOverWater = SPWaterSafety::GetSurfaceHeight(GetActorLocation(), WaterZ);
    const double FeetZ = GetActorLocation().Z - GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
    if (bOverWater && FeetZ < WaterZ - 20) { Recover(); return; }
    if (GetCharacterMovement()->IsMovingOnGround() && (!bOverWater || FeetZ >= WaterZ + 5))
    {
        SafeLocation = GetActorLocation(); SafeRotation = GetActorRotation(); bHasSafeLocation = true;
    }
    else if (bHasSafeLocation && GetActorLocation().Z < SafeLocation.Z - 1500) Recover();
}
