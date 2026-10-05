#include "SPBicyclePawn.h"
#include "SPBicycleRider.h"
#include "SPBicycleMovement.h"
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
    GroundMovement = CreateDefaultSubobject<USPBicycleMovement>(TEXT("GroundMovement"));
    GroundMovement->SetUpdatedComponent(Collision);
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
    Input->BindKey(EKeys::N, IE_Pressed, this, &ASPBicyclePawn::ToggleNatureSounds);
    Input->BindKey(EKeys::Q, IE_Pressed, this, &ASPBicyclePawn::StartBacking);
    Input->BindKey(EKeys::Q, IE_Released, this, &ASPBicyclePawn::StopBacking).bExecuteWhenPaused = true;
    Input->BindAction(TEXT("BicycleBoost"), IE_Pressed, this, &ASPBicyclePawn::StartBoost);
    Input->BindAction(TEXT("BicycleBoost"), IE_Released, this, &ASPBicyclePawn::StopBoost).bExecuteWhenPaused = true;
    Input->BindKey(EKeys::SpaceBar, IE_Pressed, this, &ASPBicyclePawn::JumpBicycle);
    Input->BindKey(EKeys::P, IE_Pressed, this, &ASPBicyclePawn::ToggleAutopilot);
#if !UE_BUILD_SHIPPING
    Input->BindAction(TEXT("RideCheck"), IE_Pressed, this, &ASPBicyclePawn::ToggleRideCheck);
    Input->BindKey(EKeys::F10, IE_Pressed, this, &ASPBicyclePawn::ToggleCircuitCheck);
#endif
}

bool ASPBicyclePawn::GroundAt(const FVector& Position, FHitResult& Hit) const
{
    return GroundMovement->GroundAt(Position, Hit);
}

bool ASPBicyclePawn::FindSafePlacement(const FVector& Near, double Yaw, FVector& Out, bool bCheckpoint) const
{
    FHitResult Ground;
    if (!GroundAt(Near + FVector(0,0,40), Ground) || Ground.ImpactNormal.Z < .78) return false;
    double WaterZ = 0;
    if (SPWaterSafety::GetSurfaceHeight(Ground.ImpactPoint, WaterZ) && Ground.ImpactPoint.Z < WaterZ + 5) return false;
    const double Radius = Collision->GetScaledCapsuleRadius();
    Out = Ground.ImpactPoint + FVector(0,0,Collision->GetScaledCapsuleHalfHeight() - Radius + Radius / Ground.ImpactNormal.Z + 4);
    FCollisionQueryParams Query(SCENE_QUERY_STAT(BicycleSafePlacement), false, this);
    const FCollisionShape Shape = FCollisionShape::MakeCapsule(Radius + (bCheckpoint ? 8 : 2),
        Collision->GetScaledCapsuleHalfHeight() + (bCheckpoint ? 8 : 2));
    // Lift the clearance shape so its extra margin does not overlap the floor.
    const FVector Lift(0,0,bCheckpoint ? 10 : 3);
    if (GetWorld()->OverlapBlockingTestByChannel(Out + Lift, FQuat::Identity, ECC_Pawn, Shape, Query)) return false;
    const FVector Forward = FRotator(0,Yaw,0).Vector();
    for (double Along : {-110.0, 110.0})
    {
        FHitResult WheelFloor;
        if (!GroundAt(Out + Forward * Along, WheelFloor)
            || FMath::Abs(WheelFloor.ImpactPoint.Z - Ground.ImpactPoint.Z) > 35) return false;
    }
    FHitResult Clear;
    if (GetWorld()->SweepSingleByChannel(Clear, Out + Lift - Forward * 90,
        Out + Lift + Forward * 150, FQuat::Identity, ECC_Pawn, Shape, Query)) return false;
    return true;
}

void ASPBicyclePawn::ToggleExplorer()
{
    StopAutopilot();
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
    if (Autopilot.IsActive())
    {
        const FSPAutopilotInputs Inputs = Autopilot.Update(*this,Step,bBoostHeld);
        Pedal = Inputs.Pedal; Brake = Inputs.Brake; Steer = Inputs.Steer;
        if (Autopilot.IsActive() && Inputs.bWalking != bWalking && Speed < 5)
            SetWalking(Inputs.bWalking);
    }
    const FVector Forward = FRotator(0, GetActorRotation().Yaw, 0).Vector();
    FHitResult Front, Back;
    const FVector Position = GetActorLocation();
    const bool bFront = GroundAt(Position + Forward * 50, Front);
    const bool bBack = GroundAt(Position - Forward * 50, Back);
    // Wheel probes determine pitch, not permission to leave the path. A wheel
    // can cross an edge while the bike still has support beneath its centre.
    const double Grade = !bJumpInFlight && bFront && bBack
        ? FMath::Clamp((Front.ImpactPoint.Z - Back.ImpactPoint.Z) / 100.0, -0.65, 0.65) : 0.0;
    const bool bBoosting = bBoostHeld && !bWalking && !bSettingsOpen;
    BoostBlend = FMath::FInterpConstantTo(BoostBlend,bBoosting ? 1.f : 0.f,Step,1.5f);
    const double MaximumSpeed = bWalking ? 150 : (bBoosting ? 80.0 : RideTuning.Get(ESPRideSetting::TopSpeed)) / .036;
    const double NormalAcceleration = RideTuning.Get(ESPRideSetting::Acceleration);
    const double AccelerationSetting = FMath::Lerp(NormalAcceleration,FMath::Max(NormalAcceleration,5.4),double(BoostBlend));
    const double Taper = FMath::Lerp(.4,.15,double(BoostBlend));
    const double PedalForce = bWalking ? 300 : AccelerationSetting * 100
        * FMath::Max(1.0-Taper,1.0-Taper*Speed/MaximumSpeed);
    double Acceleration = (Speed < MaximumSpeed ? Pedal * PedalForce : 0)
        - Brake * RideTuning.Get(ESPRideSetting::Braking) * 100
        - (bWalking ? 0 : 980 * Grade)
        - (Speed > 1 ? 7 + Speed * Speed * 0.000075 : 0);
    // Releasing boost coasts down to the ordinary limit, rather than jumping
    // instantly from 80 to 50 km/h. Braking still has its full normal effect.
    if (Speed > MaximumSpeed) Acceleration = FMath::Min(Acceleration,-180.0);
    Speed = FMath::Clamp(Speed + Acceleration * Step, 0.0, FMath::Max(Speed,MaximumSpeed));
    if (Brake > 0.1f && Speed < 5) Speed = 0;
    bBackingActive = bBackupRequested && !bWalking && Speed < 5 && Pedal < .05f && Brake < .05f && !bSettingsOpen;
    const double TravelSpeed = bBackingActive ? -150.0 : Speed;
    const double SteeringRange = Autopilot.IsActive() ? FSPBicycleAutopilot::SteeringRange(Speed)
        : RideTuning.Get(ESPRideSetting::Steering)/(1.0+Speed/700.0);
    SteeringAngle = FMath::FInterpTo(SteeringAngle,Steer * (bWalking ? 50.f : float(SteeringRange)),Step,4.f);
    const double YawStep = bWalking ? Steer * 95 * Step
        : FMath::Clamp(FMath::RadiansToDegrees(TravelSpeed / 110 * FMath::Tan(FMath::DegreesToRadians(SteeringAngle))), -65.0, 65.0) * Step;
    const FRotator ProposedRotation(0, GetActorRotation().Yaw + YawStep, 0);
    // Riding retains its existing turn model. Walking checks the visible bike
    // before committing either an in-place turn or forward movement.
    if (!bWalking) AddActorWorldRotation(FRotator(0, YawStep, 0));
    FVector Movement = (bWalking ? ProposedRotation.Vector() : GetActorForwardVector()) * TravelSpeed * Step;
    FHitResult Support;
    // The lower capsule hemisphere needs more vertical clearance on a slope.
    // A constant half-height embeds it in cross-slopes and causes false walls.
    const bool bGroundAhead = GroundAt(Position + Movement, Support);
    const double Clearance = bGroundAhead ? GroundMovement->FloorClearance(Support) : Collision->GetScaledCapsuleHalfHeight() + 6;
    const double DesiredHeight = bGroundAhead ? Support.ImpactPoint.Z + Clearance : Position.Z;
    VerticalSpeed = FMath::Max(VerticalSpeed - 980 * Step, -2500.0);
    const double FallDistance = VerticalSpeed * Step;
    bHasSurface = bGroundAhead && VerticalSpeed <= 0 && DesiredHeight <= Position.Z + 40
        && DesiredHeight >= Position.Z + FMath::Min(-40.0, FallDistance)
        && (!bJumpInFlight || (DesiredHeight >= Position.Z + FallDistance && DesiredHeight <= Position.Z + 6));
    if (bHasSurface)
    {
        Movement.Z = DesiredHeight - Position.Z;
        VerticalSpeed = 0;
        bJumpInFlight = false;
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
    FHitResult CollisionHit, SurfaceContact;
    GroundMovement->MoveOverGround(Movement,bHasSurface,CollisionHit,&SurfaceContact);
    if (VerticalSpeed > 0 && SurfaceContact.bBlockingHit && SurfaceContact.ImpactNormal.Z < -.1)
        VerticalSpeed = 0; // A ceiling ends ascent; collision remains enabled.
    if (CollisionHit.bBlockingHit || CollisionHit.bStartPenetrating)
    {
        ++BlockingContactCount;
        Speed = 0;
        Notice = TEXT("Obstacle. Hold Q to back away, or press R to reset.");
    }
    else
    {
        FHitResult ActualFloor;
        if (GroundAt(GetActorLocation(), ActualFloor))
        {
            const double FloorZ = ActualFloor.ImpactPoint.Z + GroundMovement->FloorClearance(ActualFloor);
            const bool bCanSettle = !bJumpInFlight || (VerticalSpeed <= 0 && FloorZ >= GetActorLocation().Z-1);
            if (bCanSettle && FMath::Abs(FloorZ - GetActorLocation().Z) <= 40)
            {
                FHitResult Settle;
                GroundMovement->SafeMoveUpdatedComponent(FVector(0,0,FloorZ-GetActorLocation().Z),
                    GetActorQuat(), true, Settle);
                if (!Settle.bStartPenetrating)
                {
                    Support = ActualFloor;
                    bHasSurface = true;
                    VerticalSpeed = 0;
                    bJumpInFlight = false;
                }
            }
        }
        Notice.Empty();
    }
    Distance += FVector::Dist2D(Position, GetActorLocation());
    double WaterZ = 0;
    const bool bOverWater = SPWaterSafety::GetSurfaceHeight(GetActorLocation(), WaterZ);
    const double FeetZ = GetActorLocation().Z - Collision->GetScaledCapsuleHalfHeight();
    if (bOverWater && FeetZ < WaterZ - 20) { Recover(); return; }
    if (bHasSurface && (!bOverWater || FeetZ >= WaterZ + 5)
        && FMath::Abs(Grade) < 0.18 && !CollisionHit.IsValidBlockingHit())
    {
        // Keep spaced checkpoints, well away from a grazing contact.
        FVector Safe;
        if ((SafeHistory.IsEmpty() || FVector::Dist2D(SafeHistory.Last().GetLocation(), GetActorLocation()) > 250)
            && FindSafePlacement(GetActorLocation(), GetActorRotation().Yaw, Safe, true))
        {
            LastSafe = Safe;
            LastSafeYaw = GetActorRotation().Yaw;
            bHasSafePosition = true;
            SafeHistory.Add(FTransform(FRotator(0,LastSafeYaw,0), Safe));
            if (SafeHistory.Num() > 24) SafeHistory.RemoveAt(0);
        }
    }
    const float Lean = bWalking ? 0 : -SteeringAngle * FMath::Min(Speed / 1000.0, 0.35);
    // Keep the wheels on the surface when the capsule needs extra clearance
    // on a cross-slope. Rider and wheels share this frame transform.
    Bicycle->SetRelativeLocation(FVector(0, 0,
        bHasSurface ? Support.ImpactPoint.Z - GetActorLocation().Z + 2 : -70));
    Bicycle->SetRelativeRotation(FRotator(FMath::RadiansToDegrees(FMath::Atan(Grade)), 0, Lean));
    WheelAngle += FMath::RadiansToDegrees(TravelSpeed * Step / 34);
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
    if (Notice.IsEmpty() && !Autopilot.GetFailure().IsEmpty()) Notice = Autopilot.GetFailure();
    UpdateCamera();
    Diagnostics.Record(*this, DeltaSeconds);
}

void ASPBicyclePawn::ToggleRideCheck()
{
    StopAutopilot();
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
    StopAutopilot();
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
    StopAutopilot();
    Diagnostics.Stop(*this, false);
    FVector Place = FVector::ZeroVector;
    double Yaw = LastSafeYaw;
    bool bFound = false;
    // Prefer a checkpoint at least two metres behind the obstruction.
    for (int32 Index = SafeHistory.Num() - 1; Index >= 0; --Index)
    {
        const FTransform& Candidate = SafeHistory[Index];
        if (FVector::Dist2D(Candidate.GetLocation(), GetActorLocation()) < 200) continue;
        Yaw = Candidate.Rotator().Yaw;
        if (FindSafePlacement(Candidate.GetLocation(), Yaw, Place)) { bFound = true; break; }
    }
    if (!bFound)
        for (TActorIterator<ASPWorldDirector> It(GetWorld()); It && !bFound; ++It)
        {
            const FSPRoute* Route = It->GetData().FindRoute(TEXT("main_circuit"));
            double Squared = 0;
            const double Along = Route ? Route->FindNearest(GetActorLocation(), Squared) : 0;
            for (double Offset : {0.0, -300.0, 300.0, -700.0, 700.0, -1500.0, 1500.0, -3000.0, 3000.0})
            {
                FVector Direction;
                FVector Ground = Route ? Route->Sample(Along + Offset, &Direction) : It->GetData().Spawn;
                Yaw = Route ? Direction.Rotation().Yaw : It->GetData().SpawnYaw;
                if (FindSafePlacement(Ground + FVector(0,0,75), Yaw, Place)) { bFound = true; break; }
            }
            if (!bFound)
            {
                Yaw = It->GetData().SpawnYaw;
                bFound = FindSafePlacement(It->GetData().Spawn + FVector(0,0,75), Yaw, Place);
            }
        }
    if (bFound)
    {
        bWalking = false;
        Rider->SetWalkingPose(false);
        SetActorLocationAndRotation(Place, FRotator(0,Yaw,0));
        LastSafe = Place; LastSafeYaw = Yaw; bHasSafePosition = true;
        Bicycle->SetRelativeLocation(FVector(0,0,-70));
        Bicycle->SetRelativeRotation(FRotator::ZeroRotator);
        Notice = TEXT("Returned to clear ground. Ready to ride.");
    }
    else Notice = TEXT("No clear reset position found. Move clear and press R again.");
    Speed = VerticalSpeed = Accumulator = 0;
    Pedal = Brake = Steer = SteeringAngle = 0;
    bBackupRequested = bBackingActive = false;
    bBoostHeld = bJumpInFlight = false;
    BoostBlend = 0;
}

void ASPBicyclePawn::PlaceOnRoute(const FVector& Contact, double Yaw)
{
    StopAutopilot();
    FVector Place;
    const FVector Near = Contact + FVector(0,0,75);
    if (!FindSafePlacement(Near, Yaw, Place)) Place = Near;
    SetActorLocationAndRotation(Place, FRotator(0,Yaw,0));
    Speed = VerticalSpeed = Accumulator = 0;
    Pedal = Brake = Steer = SteeringAngle = 0;
    bBackupRequested = bBackingActive = false;
    bBoostHeld = bJumpInFlight = false;
    BoostBlend = 0;
    LookYaw = 0; LookPitch = -4;
    LastSafe = GetActorLocation(); LastSafeYaw = Yaw; bHasSafePosition = true;
    SafeHistory.Reset();
    if (FindSafePlacement(Place, Yaw, Place, true)) SafeHistory.Add(FTransform(FRotator(0,Yaw,0),Place));
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
    StopAutopilot();
    SetWalking(!bWalking);
}

bool ASPBicyclePawn::SetWalking(bool bRequested)
{
    if (bWalking == bRequested) return true;
    if (bJumpInFlight) { Notice = TEXT("Land before walking the bicycle."); return false; }
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
    if (bOpen) StopAutopilot();
    if (bOpen) Diagnostics.Stop(*this, false);
    bSettingsOpen = bOpen;
    Pedal = Brake = Steer = SteeringAngle = 0;
    bBackupRequested = bBackingActive = false;
    bBoostHeld = false;
    BoostBlend = 0;
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

void ASPBicyclePawn::ToggleNatureSounds()
{
    for (TActorIterator<ASPWorldDirector> It(GetWorld()); It; ++It) It->ToggleAmbience();
}

void ASPBicyclePawn::SetPedal(float Value)
{
    if (Value > .1f && !Autopilot.IsActive()) Autopilot.Stop();
    Pedal = bSettingsOpen ? 0.f : FMath::Clamp(Value,0.f,1.f);
}

void ASPBicyclePawn::SetBrake(float Value)
{
    if (Value > .1f) StopAutopilot();
    Brake = bSettingsOpen ? 0.f : FMath::Clamp(Value,0.f,1.f);
}

void ASPBicyclePawn::SetSteer(float Value)
{
    if (FMath::Abs(Value) >= .12f) StopAutopilot();
    Steer = bSettingsOpen || FMath::Abs(Value) < .12f ? 0.f : Value;
}

void ASPBicyclePawn::StartBacking()
{
    if (bSettingsOpen) return;
    StopAutopilot();
    bBackupRequested = true;
}

void ASPBicyclePawn::JumpBicycle()
{
    if (bSettingsOpen || bWalking || !bHasSurface || bJumpInFlight) return;
    StopAutopilot();
    bJumpInFlight = true;
    bHasSurface = false;
    VerticalSpeed = 520; // About 1.4 m of height and one second in the air.
}

void ASPBicyclePawn::StopAutopilot()
{
    const bool bWasActive = Autopilot.IsActive();
    Autopilot.Stop();
    if (bWasActive) Pedal = Brake = Steer = SteeringAngle = 0;
}

void ASPBicyclePawn::ToggleAutopilot()
{
    if (Autopilot.IsActive()) { StopAutopilot(); return; }
    if (bSettingsOpen || bJumpInFlight || !bHasSurface) return;
    for (TActorIterator<ASPWorldDirector> It(GetWorld()); It; ++It)
    {
        if (!Autopilot.Start(*this,*It)) { Notice = Autopilot.GetFailure(); return; }
        Diagnostics.Stop(*this,false);
        Pedal = Brake = Steer = SteeringAngle = 0;
        bBackupRequested = bBackingActive = bBoostHeld = false;
        BoostBlend = 0;
        if (APlayerController* Player = Cast<APlayerController>(GetController())) Player->FlushPressedKeys();
        // The upright capsule is rotationally symmetric. Align heading only;
        // joining the route still uses ordinary swept movement from here.
        const FSPRoute* Route = It->GetData().FindRoute(TEXT("main_circuit"));
        double Squared;
        const double Along = Route->FindNearest(GetActorLocation()-FVector(0,0,76),Squared);
        FVector Direction;
        Route->Sample(Along,&Direction);
        if (!bWalking) SetActorRotation(FRotator(0,Direction.Rotation().Yaw,0));
        Notice.Empty();
        return;
    }
    Notice = TEXT("Autopilot needs the Seawall ride route.");
}
