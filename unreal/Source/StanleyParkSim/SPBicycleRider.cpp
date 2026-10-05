#include "SPBicycleRider.h"
#include "SPBicyclePawn.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
    constexpr double CrankRadius = 17.0;
    const FVector CrankCentre(-8, 0, 30);
    FVector PedalPosition(double Phase, double Side)
    {
        return CrankCentre + FVector(CrankRadius * FMath::Sin(Phase), Side * 20, CrankRadius * FMath::Cos(Phase));
    }
}

USPBicycleRider::USPBicycleRider()
{
    PrimaryComponentTick.bCanEverTick = true;
    PrimaryComponentTick.bStartWithTickEnabled = true;
    SetCollisionEnabled(ECollisionEnabled::NoCollision);
    static ConstructorHelpers::FObjectFinder<USkeletalMesh> Model(TEXT("/Game/StanleyPark/Explorer/SK_Explorer.SK_Explorer"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Frame(TEXT("/Game/StanleyPark/Kit/SM_Bicycle_Animated.SM_Bicycle_Animated"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Pedal(TEXT("/Game/StanleyPark/Kit/SM_Pedal.SM_Pedal"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Crank(TEXT("/Game/StanleyPark/Kit/SM_CrankArm.SM_CrankArm"));
    if (Model.Succeeded()) SetSkinnedAssetAndUpdate(Model.Object);
    AnimatedFrame = Frame.Object; PedalMesh = Pedal.Object; CrankMesh = Crank.Object;
    SetBoundsScale(1.5f);
}

void USPBicycleRider::BeginPlay()
{
    Super::BeginPlay();
    AddTickPrerequisiteActor(GetOwner());
    CacheReferencePose();
    // Preserve the original M1 frame. Only Seawall uses the separated pedals.
    UStaticMeshComponent* Frame = Cast<UStaticMeshComponent>(GetAttachParent());
    if (Frame && AnimatedFrame && PedalMesh && CrankMesh && GetWorld()->GetMapName().Contains(TEXT("StanleyParkSeawall")))
    {
        Frame->SetStaticMesh(AnimatedFrame);
        for (int32 Side = 0; Side < 2; ++Side)
        {
            const auto MakePart = [&](UStaticMesh* Mesh)
            {
                UStaticMeshComponent* Part = NewObject<UStaticMeshComponent>(GetOwner());
                Part->SetMobility(EComponentMobility::Movable);
                Part->SetStaticMesh(Mesh);
                Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
                Part->SetupAttachment(Frame);
                Part->RegisterComponent();
                return Part;
            };
            Pedals.Add(MakePart(PedalMesh));
            Cranks.Add(MakePart(CrankMesh));
        }
    }
    UpdatePose();
    UpdatePedalMeshes();
}

void USPBicycleRider::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
    Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
    const ASPBicyclePawn* Bicycle = Cast<ASPBicyclePawn>(GetOwner());
    if (Bicycle) bWalkingPose = Bicycle->IsWalking();
    const double Speed = Bicycle ? FMath::Abs(Bicycle->GetSpeedKmh()) / 3.6 : AmbientSpeed;
    // A freewheel stops the feet during coasting/braking. Smooth cadence avoids
    // snapping the knees when the pedal key changes state.
    const double TargetCadence = !Pedals.IsEmpty() && (Bicycle ? Bicycle->IsPedalling() : Speed > .03) && Speed > .03
        ? FMath::Clamp(Speed / 4.0, .35, 1.6) : 0.0;
    Cadence = FMath::Lerp(Cadence, TargetCadence, 1.0 - FMath::Exp(-double(DeltaTime) / .15));
    if (Cadence < .001 && TargetCadence == 0.0) Cadence = 0.0;
    PedalPhase = FMath::Fmod(PedalPhase + double(DeltaTime) * Cadence * 2.0 * PI, 2.0 * PI);
    if (bWalkingPose && Speed > .03)
        WalkPhase = FMath::Fmod(WalkPhase + double(DeltaTime) * Speed / 1.4 * 2.0 * PI, 2.0 * PI);
    UpdatePose();
    UpdatePedalMeshes();
}

void USPBicycleRider::CacheReferencePose()
{
    const USkeletalMesh* Mesh = Cast<USkeletalMesh>(GetSkinnedAsset());
    bReferenceValid = false;
    if (!Mesh) return;
    const FReferenceSkeleton& Skeleton = Mesh->GetRefSkeleton();
    ReferencePose = Skeleton.GetRefBonePose();
    for (int32 Index = 0; Index < ReferencePose.Num(); ++Index)
    {
        const int32 Parent = Skeleton.GetParentIndex(Index);
        if (Parent != INDEX_NONE) ReferencePose[Index] *= ReferencePose[Parent];
    }
    for (const TCHAR* Name : { TEXT("pelvis"), TEXT("spine"), TEXT("head"),
        TEXT("upperarm_l"), TEXT("forearm_l"), TEXT("hand_l"),
        TEXT("upperarm_r"), TEXT("forearm_r"), TEXT("hand_r"),
        TEXT("thigh_l"), TEXT("calf_l"), TEXT("foot_l"),
        TEXT("thigh_r"), TEXT("calf_r"), TEXT("foot_r") })
        if (Skeleton.FindBoneIndex(FName(Name)) == INDEX_NONE) return;
    bReferenceValid = true;
}

void USPBicycleRider::SetWalkingPose(bool bWalking)
{
    bWalkingPose = bWalking;
    if (bWalking) Cadence = 0.0;
    if (!bReferenceValid) CacheReferencePose();
    UpdatePose();
}

void USPBicycleRider::UpdatePose()
{
    if (!bReferenceValid) return;
    const USkeletalMesh* Mesh = Cast<USkeletalMesh>(GetSkinnedAsset());
    if (!Mesh || Mesh->GetRefSkeleton().GetNum() != ReferencePose.Num()) return;
    const FReferenceSkeleton& Skeleton = Mesh->GetRefSkeleton();
    Pose = ReferencePose;
    const auto RefPosition = [&](FName Name) { return ReferencePose[Skeleton.FindBoneIndex(Name)].GetLocation(); };
    const auto Set = [&](FName Name, const FVector& Position, const FQuat& Delta)
    {
        const int32 Index = Skeleton.FindBoneIndex(Name);
        Pose[Index] = FTransform(Delta * ReferencePose[Index].GetRotation(), Position, ReferencePose[Index].GetScale3D());
    };
    // Solve in mesh space and retain authored bone lengths across the crank cycle.
    const auto Limb = [&](FName Upper, FName Lower, FName End, const FVector& Start,
                          const FVector& Target, const FVector& Bend, const FQuat& EndRotation)
    {
        const FVector A = RefPosition(Upper), B = RefPosition(Lower), C = RefPosition(End);
        const double L1 = FVector::Distance(A, B), L2 = FVector::Distance(B, C);
        const FVector Direction = (Target - Start).GetSafeNormal();
        const double Distance = FMath::Clamp(FVector::Distance(Start, Target), FMath::Abs(L1 - L2) + .01, L1 + L2 - .01);
        const double Along = (L1 * L1 - L2 * L2 + Distance * Distance) / (2 * Distance);
        FVector BendAxis = (Bend - Direction * FVector::DotProduct(Bend, Direction)).GetSafeNormal();
        if (BendAxis.IsNearlyZero()) BendAxis = FVector::CrossProduct(Direction, FVector::YAxisVector).GetSafeNormal();
        const FVector Joint = Start + Direction * Along + BendAxis * FMath::Sqrt(FMath::Max(0.0, L1 * L1 - Along * Along));
        const FVector Reached = Start + Direction * Distance;
        Set(Upper, Start, FQuat::FindBetweenNormals((B - A).GetSafeNormal(), (Joint - Start).GetSafeNormal()));
        Set(Lower, Joint, FQuat::FindBetweenNormals((C - B).GetSafeNormal(), (Reached - Joint).GetSafeNormal()));
        Set(End, Reached, EndRotation);
    };

    if (bWalkingPose)
    {
        // Keep the near shoulder within the authored arm reach of the grip.
        const FVector Offset(-5, -52, 0);
        for (FTransform& Bone : Pose) Bone.AddToTranslation(Offset);
        const ASPBicyclePawn* Bicycle = Cast<ASPBicyclePawn>(GetOwner());
        const double Weight = Bicycle ? FMath::Clamp(FMath::Abs(Bicycle->GetSpeedKmh()) / 3.6 / .4, 0.0, 1.0) : 0.0;
        for (const TCHAR* Side : { TEXT("l"), TEXT("r") })
        {
            const auto Name = [&](const TCHAR* Part) { return FName(*FString::Printf(TEXT("%s_%s"), Part, Side)); };
            const double PelvisY = RefPosition(TEXT("pelvis")).Y;
            const bool bNegativeLegSide = RefPosition(Name(TEXT("thigh"))).Y < PelvisY;
            const bool bNearHand = RefPosition(Name(TEXT("upperarm"))).Y > PelvisY;
            const double Wave = FMath::Sin(WalkPhase + (bNegativeLegSide ? 0.0 : PI)) * Weight;
            Limb(Name(TEXT("thigh")), Name(TEXT("calf")), Name(TEXT("foot")),
                RefPosition(Name(TEXT("thigh"))) + Offset,
                RefPosition(Name(TEXT("foot"))) + Offset + FVector(Wave * 18, 0, FMath::Max(0.0, Wave) * 8),
                FVector::XAxisVector, FQuat::Identity);
            // Select the near shoulder from the imported reference positions.
            // Bone-name suffixes do not define Unreal's Y side after FBX import.
            Limb(Name(TEXT("upperarm")), Name(TEXT("forearm")), Name(TEXT("hand")),
                RefPosition(Name(TEXT("upperarm"))) + Offset,
                bNearHand ? FVector(33, -25, 106) : RefPosition(Name(TEXT("hand"))) + Offset + FVector(-Wave * 12, 0, 0),
                FVector(-1, 0, -1), bNearHand ? FQuat(FVector::YAxisVector, -PI / 2) : FQuat::Identity);
        }
    }
    else
    {
        // The lower seated hip keeps the bottom pedal within the 79 cm leg.
        const FVector Hip(-24, 0, Pedals.IsEmpty() ? 100 : 96);
        const FVector ReferenceHip = RefPosition(TEXT("pelvis"));
        const FQuat Lean(FVector::YAxisVector, FMath::DegreesToRadians(35.0));
        const auto TorsoPoint = [&](const FVector& Point) { return Hip + Lean.RotateVector(Point - ReferenceHip); };
        Set(TEXT("pelvis"), Hip, FQuat::Identity);
        Set(TEXT("spine"), TorsoPoint(RefPosition(TEXT("spine"))), Lean);
        Set(TEXT("head"), TorsoPoint(RefPosition(TEXT("head"))), FQuat::Identity);
        for (const TCHAR* Side : { TEXT("l"), TEXT("r") })
        {
            const auto Name = [&](const TCHAR* Part) { return FName(*FString::Printf(TEXT("%s_%s"), Part, Side)); };
            const double LegSide = RefPosition(Name(TEXT("thigh"))).Y < ReferenceHip.Y ? -1.0 : 1.0;
            const double ArmSide = RefPosition(Name(TEXT("upperarm"))).Y < ReferenceHip.Y ? -1.0 : 1.0;
            Limb(Name(TEXT("upperarm")), Name(TEXT("forearm")), Name(TEXT("hand")),
                TorsoPoint(RefPosition(Name(TEXT("upperarm")))), FVector(33, ArmSide * 25, 106),
                FVector(-1, 0, -1), FQuat(FVector::YAxisVector, -PI / 2));
            // Reference ankle: 6 cm behind boot centre, 10 cm above its sole.
            const FVector Ankle = Pedals.IsEmpty() ? FVector(-14, LegSide * 20, 38)
                : PedalPosition(PedalPhase + (LegSide < 0.0 ? 0.0 : PI), LegSide) + FVector(-6, 0, 11.25);
            Limb(Name(TEXT("thigh")), Name(TEXT("calf")), Name(TEXT("foot")),
                Hip + RefPosition(Name(TEXT("thigh"))) - ReferenceHip,
                Ankle, FVector::XAxisVector, FQuat::Identity);
        }
    }
    BoneSpaceTransforms.SetNum(Pose.Num());
    for (int32 Index = 0; Index < Pose.Num(); ++Index)
    {
        const int32 Parent = Skeleton.GetParentIndex(Index);
        BoneSpaceTransforms[Index] = Parent == INDEX_NONE ? Pose[Index] : Pose[Index].GetRelativeTransform(Pose[Parent]);
    }
    MarkRefreshTransformDirty();
    RefreshBoneTransforms();
}

void USPBicycleRider::UpdatePedalMeshes()
{
    for (int32 Side = 0; Side < Pedals.Num(); ++Side)
    {
        const double Sign = Side == 0 ? -1.0 : 1.0;
        const double Phase = PedalPhase + (Side == 0 ? 0.0 : PI);
        Pedals[Side]->SetRelativeLocation(PedalPosition(Phase, Sign));
        // Authored crank mesh runs from the origin 17 cm along +Z.
        Cranks[Side]->SetRelativeLocation(CrankCentre + FVector(0, Sign * 16, 0));
        Cranks[Side]->SetRelativeRotation(FQuat(FVector::YAxisVector, Phase));
    }
}

