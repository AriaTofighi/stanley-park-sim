#include "SPBicyclePawn.h"
#include "SPBicycleRider.h"
#include "SPWorldDirector.h"
#include "SPHud.h"
#include "SPGameMode.h"
#include "SPWalkingBikeGeometry.h"
#include "SPWaterSafety.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/InputComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Sound/SoundBase.h"
#include "UObject/ConstructorHelpers.h"

ASPBicyclePawn::ASPBicyclePawn()
{
    PrimaryActorTick.bCanEverTick = true;
    AutoPossessPlayer = EAutoReceiveInput::Player0;
    Collision = CreateDefaultSubobject<UCapsuleComponent>(TEXT("RiderContact"));
    Collision->InitCapsuleSize(32, 70);
    Collision->SetCollisionProfileName(TEXT("Pawn"));
    RootComponent = Collision;
    Bicycle = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("BicycleFrame"));
    Bicycle->SetupAttachment(RootComponent);
    Bicycle->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Bicycle->SetRelativeLocation(FVector(0, 0, -70));
    FrontWheel = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("FrontWheel"));
    RearWheel = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("RearWheel"));
    FrontWheel->SetupAttachment(Bicycle);
    RearWheel->SetupAttachment(Bicycle);
    for (UStaticMeshComponent* Wheel : { FrontWheel.Get(), RearWheel.Get() })
        Wheel->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    FrontWheel->SetRelativeLocation(FVector(55, 0, 34));
    RearWheel->SetRelativeLocation(FVector(-55, 0, 34));
    Rider = CreateDefaultSubobject<USPBicycleRider>(TEXT("ExplorerRider"));
    Rider->SetupAttachment(Bicycle);
    CameraArm = CreateDefaultSubobject<USpringArmComponent>(TEXT("ComfortCameraArm"));
    CameraArm->SetupAttachment(RootComponent);
    CameraArm->SetRelativeLocation(FVector(0, 0, 78));
    CameraArm->TargetArmLength = 0;
    CameraArm->bEnableCameraLag = false;
    CameraArm->bDoCollisionTest = true;
    Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("RideCamera"));
    Camera->SetupAttachment(CameraArm);
    Camera->SetFieldOfView(85);
    // Optional assets can be imported after the native module has compiled.
    static ConstructorHelpers::FObjectFinderOptional<UStaticMesh> FrameAsset(TEXT("/Game/StanleyPark/Kit/SM_Bicycle.SM_Bicycle"));
    static ConstructorHelpers::FObjectFinderOptional<UStaticMesh> WheelAsset(TEXT("/Game/StanleyPark/Kit/SM_Wheel.SM_Wheel"));
    static ConstructorHelpers::FObjectFinderOptional<USoundBase> BellAsset(TEXT("/Game/StanleyPark/Audio/S_Bell.S_Bell"));
    if (FrameAsset.Succeeded()) Bicycle->SetStaticMesh(FrameAsset.Get());
    if (WheelAsset.Succeeded())
    {
        FrontWheel->SetStaticMesh(WheelAsset.Get());
        RearWheel->SetStaticMesh(WheelAsset.Get());
    }
    if (BellAsset.Succeeded()) BellSound = BellAsset.Get();
}

void ASPBicyclePawn::BeginPlay()
{
    Super::BeginPlay();
    RideTuning.Load();
    Camera->SetFieldOfView(RideTuning.Get(ESPRideSetting::FieldOfView));
    Rider->SetWalkingPose(bWalking);
    UpdateCamera();
}

void ASPBicyclePawn::SetupPlayerInputComponent(UInputComponent* Input)
{
    Super::SetupPlayerInputComponent(Input);
    Input->BindAxis(TEXT("Pedal"), this, &ASPBicyclePawn::SetPedal);
    Input->BindAxis(TEXT("Brake"), this, &ASPBicyclePawn::SetBrake);
    Input->BindAxis(TEXT("Steer"), this, &ASPBicyclePawn::SetSteer);
    Input->BindAxis(TEXT("LookX"), this, &ASPBicyclePawn::LookHorizontal);
    Input->BindAxis(TEXT("LookY"), this, &ASPBicyclePawn::LookVertical);
    Input->BindAction(TEXT("Camera"), IE_Pressed, this, &ASPBicyclePawn::ToggleCamera);
    Input->BindAction(TEXT("Dismount"), IE_Pressed, this, &ASPBicyclePawn::ToggleDismount);
    Input->BindKey(EKeys::Tab, IE_Pressed, this, &ASPBicyclePawn::ToggleExplorer);
    Input->BindAction(TEXT("Recover"), IE_Pressed, this, &ASPBicyclePawn::Recover);
    Input->BindAction(TEXT("Bell"), IE_Pressed, this, &ASPBicyclePawn::RingBell);
    Input->BindAction(TEXT("PauseRide"), IE_Pressed, this, &ASPBicyclePawn::PauseRide).bExecuteWhenPaused = true;
    Input->BindKey(EKeys::F1, IE_Pressed, this, &ASPBicyclePawn::ToggleSettings).bExecuteWhenPaused = true;
    Input->BindKey(EKeys::H, IE_Pressed, this, &ASPBicyclePawn::ToggleControls);
#if !UE_BUILD_SHIPPING
    Input->BindAction(TEXT("RideCheck"), IE_Pressed, this, &ASPBicyclePawn::ToggleRideCheck);
    Input->BindKey(EKeys::F10, IE_Pressed, this, &ASPBicyclePawn::ToggleCircuitCheck);
#endif
}

bool ASPBicyclePawn::GroundAt(const FVector& Position, FHitResult& Hit) const
{
    FCollisionQueryParams Query(SCENE_QUERY_STAT(BicycleGround), true, this);
    // Start below overhead decks. A valid step is below the capsule centre;
    // tracing from above the player can select a bridge roof as the floor.
    return GetWorld()->LineTraceSingleByChannel(Hit, Position,
        Position - FVector(0, 0, 300), ECC_WorldStatic, Query) && Hit.ImpactNormal.Z > 0.55;
}

void ASPBicyclePawn::MoveOverGround(const FVector& Movement, bool bCanStep, FHitResult& Hit)
{
    const FVector Start = GetActorLocation();
    AddActorWorldOffset(Movement, true, &Hit);
    if (!Hit.IsValidBlockingHit() || !bCanStep || Hit.ImpactNormal.Z > .55) return;
    // Small curbs and terrain seams must not behave like route boundaries.
    // Sweep all three parts of the step to retain wall and ceiling collision.
    const FVector BlockedPosition = GetActorLocation();
    const FHitResult OriginalHit = Hit;
    SetActorLocation(Start);
    FHitResult Up, Across, Down;
    AddActorWorldOffset(FVector(0, 0, 40), true, &Up);
    if (!Up.bBlockingHit)
    {
        AddActorWorldOffset(FVector(Movement.X, Movement.Y, 0), true, &Across);
        FHitResult Floor;
        if (!Across.bBlockingHit && GroundAt(GetActorLocation(), Floor))
        {
            const double Radius = Collision->GetScaledCapsuleRadius();
            const double Height = Collision->GetScaledCapsuleHalfHeight() - Radius + Radius / Floor.ImpactNormal.Z + 2;
            const double LandingZ = Floor.ImpactPoint.Z + Height;
            if (LandingZ <= Start.Z + 40 && LandingZ >= Start.Z - 40)
            {
                AddActorWorldOffset(FVector(0, 0, LandingZ - GetActorLocation().Z), true, &Down);
                if (!Down.bStartPenetrating && (!Down.bBlockingHit || Down.ImpactNormal.Z > .55))
                {
                    Hit = FHitResult();
                    return;
                }
            }
        }
    }
    SetActorLocation(BlockedPosition);
    Hit = OriginalHit;
}

void ASPBicyclePawn::ToggleExplorer()
{
    if (!bSettingsOpen)
        if (ASPGameMode* Mode = GetWorld()->GetAuthGameMode<ASPGameMode>()) Mode->ToggleExplorer();
}

bool ASPBicyclePawn::WalkingBikePoseBlocked(const FTransform& From, const FTransform& To) const
{
    if (From.Equals(To, 1e-6)) return false;
    FCollisionQueryParams Query(SCENE_QUERY_STAT(WalkingBicycleContact), true, this);
    Query.bFindInitialOverlaps = true;
    const double Degrees = FMath::RadiansToDegrees(From.GetRotation().AngularDistance(To.GetRotation()));
    const int32 Steps = FMath::Max(1, FMath::CeilToInt(Degrees / SPWalkingBikeMaximumRotationStep));
    const double Scale = FMath::Max(From.GetScale3D().GetAbsMax(), To.GetScale3D().GetAbsMax());
    const double ArcFactor = 1. - FMath::Cos(FMath::DegreesToRadians(Degrees / Steps) * .5);
    FTransform Previous = From;
    for (int32 StepIndex = 1; StepIndex <= Steps; ++StepIndex)
    {
        const double Alpha = double(StepIndex) / Steps;
        const FTransform Next(FQuat::Slerp(From.GetRotation(), To.GetRotation(), Alpha),
            FMath::Lerp(From.GetLocation(), To.GetLocation(), Alpha), To.GetScale3D());
        for (const FSPWalkingBikeProbe& Probe : SPWalkingBikeProbes)
        {
            const FVector Local(Probe.Forward, Probe.Right, Probe.Up);
            const FVector Start = Previous.TransformPosition(Local), End = Next.TransformPosition(Local);
            // A sphere follows an arc during rotation. Inflate its chord
            // sweep by the sagitta so that the outside of that arc is covered.
            const FCollisionShape Shape = FCollisionShape::MakeSphere((Probe.Radius + Local.Size() * ArcFactor) * Scale);
            FHitResult Hit;
            const bool bBlocked = Start.Equals(End, 1e-6)
                ? GetWorld()->OverlapBlockingTestByChannel(End, FQuat::Identity, ECC_WorldStatic, Shape, Query)
                : GetWorld()->SweepSingleByChannel(Hit, Start, End, FQuat::Identity, ECC_WorldStatic, Shape, Query);
            if (bBlocked)
            {
                if (BlockingContactCount == 0)
                    UE_LOG(LogTemp, Warning, TEXT("SP_WALK_BIKE_CONTACT: probe=%d start=%s end=%s"),
                        int32(&Probe - SPWalkingBikeProbes), *Start.ToString(), *End.ToString());
                return true;
            }
        }
        Previous = Next;
    }
    return false;
}

void ASPBicyclePawn::Simulate(double Step)
{
    const FVector Forward = FRotator(0, GetActorRotation().Yaw, 0).Vector();
    FHitResult Front, Back;
    const FVector Position = GetActorLocation();
    const bool bFront = GroundAt(Position + Forward * 50, Front);
    const bool bBack = GroundAt(Position - Forward * 50, Back);
    // Wheel probes determine pitch, not permission to leave the path. A wheel
    // can cross an edge while the bike still has support beneath its centre.
    const double Grade = bFront && bBack
        ? FMath::Clamp((Front.ImpactPoint.Z - Back.ImpactPoint.Z) / 100.0, -0.65, 0.65) : 0.0;
    const double MaximumSpeed = bWalking ? 150 : RideTuning.Get(ESPRideSetting::TopSpeed) / .036;
    const double PedalForce = bWalking ? 300 : RideTuning.Get(ESPRideSetting::Acceleration) * 100
        * FMath::Max(.6, 1.0 - .4 * Speed / MaximumSpeed);
    const double Acceleration = Pedal * PedalForce - Brake * RideTuning.Get(ESPRideSetting::Braking) * 100
        - (bWalking ? 0 : 980 * Grade)
        - (Speed > 1 ? 7 + Speed * Speed * 0.000075 : 0);
    Speed = FMath::Clamp(Speed + Acceleration * Step, 0.0, MaximumSpeed);
    if (Brake > 0.1f && Speed < 5) Speed = 0;
    SteeringAngle = FMath::FInterpTo(SteeringAngle,
        Steer * (bWalking ? 50.f : RideTuning.Get(ESPRideSetting::Steering)), Step, 7.f);
    const double YawStep = bWalking ? Steer * 95 * Step
        : FMath::RadiansToDegrees(Speed / 110 * FMath::Tan(FMath::DegreesToRadians(SteeringAngle))) * Step;
    const FRotator ProposedRotation(0, GetActorRotation().Yaw + YawStep, 0);
    // Riding retains its existing turn model. Walking checks the visible bike
    // before committing either an in-place turn or forward movement.
    if (!bWalking) AddActorWorldRotation(FRotator(0, YawStep, 0));
    FVector Movement = (bWalking ? ProposedRotation.Vector() : GetActorForwardVector()) * Speed * Step;
    FHitResult Support;
    // The lower capsule hemisphere needs more vertical clearance on a slope.
    // A constant half-height embeds it in cross-slopes and causes false walls.
    const double Radius = Collision->GetScaledCapsuleRadius();
    const double CylinderHalf = Collision->GetScaledCapsuleHalfHeight() - Radius;
    const bool bGroundAhead = GroundAt(Position + Movement, Support);
    const double Clearance = CylinderHalf + Radius / (bGroundAhead ? Support.ImpactNormal.Z : 1.0) + 2;
    const double DesiredHeight = bGroundAhead ? Support.ImpactPoint.Z + Clearance : Position.Z;
    VerticalSpeed = FMath::Max(VerticalSpeed - 980 * Step, -2500.0);
    const double FallDistance = VerticalSpeed * Step;
    bHasSurface = bGroundAhead && DesiredHeight <= Position.Z + 40
        && DesiredHeight >= Position.Z + FMath::Min(-40.0, FallDistance);
    if (bHasSurface)
    {
        Movement.Z = DesiredHeight - Position.Z;
        VerticalSpeed = 0;
    }
    else
    {
        ++SurfaceMissCount;
        Movement.Z = FallDistance;
    }
    if (bWalking)
    {
        const FTransform CurrentBike = Bicycle->GetComponentTransform();
        FTransform TurnedBike = CurrentBike;
        TurnedBike.SetRotation(ProposedRotation.Quaternion()
            * FRotator(FMath::RadiansToDegrees(FMath::Atan(Grade)), 0, 0).Quaternion());
        FTransform MovedBike = TurnedBike;
        MovedBike.AddToTranslation(Movement);
        // Check the same two operations that will be committed below. A
        // combined start/end chord alone can miss the outer arc of a turn.
        if (WalkingBikePoseBlocked(CurrentBike, TurnedBike) || WalkingBikePoseBlocked(TurnedBike, MovedBike))
        {
            ++BlockingContactCount;
            Speed = 0;
            Notice = TEXT("Bicycle touches an obstacle. Steer clear or press R.");
            return;
        }
        SetActorRotation(ProposedRotation);
    }
    FHitResult CollisionHit;
    MoveOverGround(Movement, bHasSurface, CollisionHit);
    if (CollisionHit.IsValidBlockingHit())
    {
        ++BlockingContactCount;
        Speed *= 0.3;
        Notice = TEXT("Obstacle. Brake and steer clear, or press R.");
    }
    else if (!bHasSurface) Notice = TEXT("Airborne. Press R to return to solid ground.");
    else Notice.Empty();
    Distance += FVector::Dist2D(Position, GetActorLocation());
    double WaterZ = 0;
    const bool bOverWater = SPWaterSafety::GetSurfaceHeight(GetActorLocation(), WaterZ);
    const double FeetZ = GetActorLocation().Z - Collision->GetScaledCapsuleHalfHeight();
    if (bOverWater && FeetZ < WaterZ - 20) { Recover(); return; }
    if (bHasSurface && (!bOverWater || FeetZ >= WaterZ + 5)
        && FMath::Abs(Grade) < 0.18 && !CollisionHit.IsValidBlockingHit())
    {
        LastSafe = GetActorLocation();
        LastSafeYaw = GetActorRotation().Yaw;
        bHasSafePosition = true;
    }
    const float Lean = bWalking ? 0 : -SteeringAngle * FMath::Min(Speed / 1000.0, 0.35);
    // Keep the wheels on the surface when the capsule needs extra clearance
    // on a cross-slope. Rider and wheels share this frame transform.
    Bicycle->SetRelativeLocation(FVector(0, 0,
        bHasSurface ? Support.ImpactPoint.Z - GetActorLocation().Z + 2 : -70));
    Bicycle->SetRelativeRotation(FRotator(FMath::RadiansToDegrees(FMath::Atan(Grade)), 0, Lean));
    WheelAngle += FMath::RadiansToDegrees(Speed * Step / 34);
    // The M1 pushed bicycle stays aligned with its frame. The walking probes
    // describe that pose; normal riding still steers the front wheel.
    FrontWheel->SetRelativeRotation(FRotator(WheelAngle, bWalking ? 0.f : SteeringAngle, 0));
    RearWheel->SetRelativeRotation(FRotator(WheelAngle, 0, 0));
    if (bHasSafePosition && GetActorLocation().Z < LastSafe.Z - 1500) Recover();
}

void ASPBicyclePawn::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    Diagnostics.Inputs(*this, Pedal, Brake, Steer);
    constexpr double Step = 1.0 / 60.0;
    const double Allowed = FMath::Min(double(DeltaSeconds), Step * 8);
    DroppedSimulationTime += DeltaSeconds - Allowed;
    Accumulator += Allowed;
    int32 Count = 0;
    while (Accumulator >= Step && Count++ < 8)
    {
        Diagnostics.RefreshCircuitRidingSpeedInputs(*this, Pedal, Brake);
        Simulate(Step);
        Accumulator -= Step;
    }
    UpdateCamera();
    Diagnostics.Record(*this, DeltaSeconds);
}

void ASPBicyclePawn::ToggleRideCheck()
{
    if (Diagnostics.IsActive()) { Diagnostics.Stop(*this, false); return; }
    Speed = Accumulator = 0;
    BlockingContactCount = 0;
    LookYaw = 0;
    bWalking = false;
    Rider->SetWalkingPose(false);
    Bicycle->SetRelativeLocation(FVector(0, 0, -70));
    Diagnostics.Start(*this);
}

void ASPBicyclePawn::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    Diagnostics.Stop(*this, false);
    RideTuning.Save();
    Super::EndPlay(EndPlayReason);
}

void ASPBicyclePawn::ToggleCircuitCheck()
{
    if (Diagnostics.IsActive()) { Diagnostics.Stop(*this, false); return; }
    // Let the diagnostic report its supported profile before changing the
    // player's speed or travel mode.
    if (!RideTuning.HasRoamMovementDefaults()) { Diagnostics.Start(*this, true); return; }
    Speed = Accumulator = 0;
    BlockingContactCount = 0;
    // Reset pushed-bike mode before the scenario places the pawn at its start.
    bWalking = false;
    Rider->SetWalkingPose(false);
    Bicycle->SetRelativeLocation(FVector(0, 0, -70));
    Diagnostics.Start(*this, true);
}

void ASPBicyclePawn::Recover()
{
    Diagnostics.Stop(*this, false);
    if (bHasSafePosition)
    {
        SetActorLocationAndRotation(LastSafe, FRotator(0, LastSafeYaw, 0));
        Speed = VerticalSpeed = Accumulator = 0;
        Pedal = Brake = Steer = SteeringAngle = 0;
        Notice = TEXT("Returned to the last safe ground position.");
        return;
    }
    for (TActorIterator<ASPWorldDirector> It(GetWorld()); It; ++It)
    {
        FVector Place;
        double Yaw;
        if (It->GetRecoveryLocation(GetActorLocation(), Place, Yaw))
        {
            PlaceOnRoute(Place, Yaw);
            Notice = TEXT("Returned to the route.");
            return;
        }
    }
    Speed = VerticalSpeed = 0;
}

void ASPBicyclePawn::PlaceOnRoute(const FVector& Contact, double Yaw)
{
    SetActorLocationAndRotation(Contact + FVector(0, 0, 75), FRotator(0, Yaw, 0));
    Speed = VerticalSpeed = Accumulator = 0;
    Pedal = Brake = Steer = SteeringAngle = 0;
    LookYaw = 0;
    LookPitch = -4;
    LastSafe = GetActorLocation();
    LastSafeYaw = Yaw;
    bHasSafePosition = true;
    Notice.Empty();
}

void ASPBicyclePawn::LookHorizontal(float Value)
{
    if (!bSettingsOpen) LookYaw = FMath::Clamp(LookYaw + Value * 1.2f * RideTuning.Get(ESPRideSetting::LookSensitivity), -85.f, 85.f);
}
void ASPBicyclePawn::LookVertical(float Value)
{
    if (!bSettingsOpen) LookPitch = FMath::Clamp(LookPitch + Value * RideTuning.Get(ESPRideSetting::LookSensitivity), -50.f, 35.f);
}
void ASPBicyclePawn::ToggleCamera() { bChaseCamera = !bChaseCamera; LookYaw = 0; }
void ASPBicyclePawn::UpdateCamera()
{
    CameraArm->TargetArmLength = bChaseCamera ? 420 : 0;
    CameraArm->SetRelativeLocation(FVector(bChaseCamera ? 0 : 12, 0, bChaseCamera ? 130 : 78));
    CameraArm->SetRelativeRotation(FRotator(bChaseCamera ? LookPitch - 10 : LookPitch, LookYaw, 0));
    Rider->SetVisibility(bChaseCamera);
}

void ASPBicyclePawn::ToggleDismount()
{
    SetWalking(!bWalking);
}

bool ASPBicyclePawn::SetWalking(bool bRequested)
{
    if (bWalking == bRequested) return true;
    if (Speed > 5) { Notice = TEXT("Stop before changing between walking and cycling."); return false; }
    bWalking = bRequested;
    Rider->SetWalkingPose(bWalking);
    Bicycle->SetRelativeLocation(FVector(0, 0, -70));
    if (bWalking) FrontWheel->SetRelativeRotation(FRotator(WheelAngle, 0, 0));
    Notice = bWalking ? TEXT("Walking the bicycle.") : TEXT("Ready to ride.");
    return true;
}

void ASPBicyclePawn::RingBell()
{
    const double Now = GetWorld()->GetTimeSeconds();
    if (Now - LastBellTime < 0.6) return;
    LastBellTime = Now;
    if (BellSound) UGameplayStatics::PlaySoundAtLocation(this, BellSound, GetActorLocation());
    for (TActorIterator<ASPWorldDirector> It(GetWorld()); It; ++It) It->OnBell(GetActorLocation());
}

void ASPBicyclePawn::PauseRide()
{
    UGameplayStatics::SetGamePaused(this, !UGameplayStatics::IsGamePaused(this));
}

void ASPBicyclePawn::ToggleSettings()
{
    if (APlayerController* Player = Cast<APlayerController>(GetController()))
        if (ASPHud* Hud = Cast<ASPHud>(Player->GetHUD())) Hud->ToggleRideSettings();
}

void ASPBicyclePawn::ToggleControls()
{
    if (APlayerController* Player = Cast<APlayerController>(GetController()))
        if (ASPHud* Hud = Cast<ASPHud>(Player->GetHUD())) Hud->ToggleControls();
}

void ASPBicyclePawn::SetSettingsOpen(bool bOpen)
{
    if (bOpen) Diagnostics.Stop(*this, false);
    bSettingsOpen = bOpen;
    Pedal = Brake = Steer = SteeringAngle = 0;
}

void ASPBicyclePawn::SetRideSetting(ESPRideSetting Setting, float Value)
{
    RideTuning.Set(Setting, Value);
    Speed = FMath::Min(Speed, bWalking ? 150. : RideTuning.Get(ESPRideSetting::TopSpeed) / .036);
    Camera->SetFieldOfView(RideTuning.Get(ESPRideSetting::FieldOfView));
}

void ASPBicyclePawn::ResetRideTuning(bool bOriginalPace)
{
    RideTuning.Reset(bOriginalPace);
    SetRideSetting(ESPRideSetting::TopSpeed, RideTuning.Get(ESPRideSetting::TopSpeed));
}
