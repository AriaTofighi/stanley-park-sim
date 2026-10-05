#include "SPParkVisitor.h"
#include "SPWorldDirector.h"
#include "SPBicycleRider.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimSingleNodeInstance.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/Pawn.h"
#include "Materials/MaterialInterface.h"
#include "UObject/ConstructorHelpers.h"

ASPParkVisitor::ASPParkVisitor()
{
    PrimaryActorTick.bCanEverTick = true;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    Walker = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("Walker"));
    Walker->SetupAttachment(RootComponent);
    Frame = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Bicycle"));
    Frame->SetupAttachment(RootComponent);
    FrontWheel = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("FrontWheel"));
    RearWheel = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("RearWheel"));
    FrontWheel->SetupAttachment(Frame); RearWheel->SetupAttachment(Frame);
    FrontWheel->SetRelativeLocation(FVector(55,0,34));
    RearWheel->SetRelativeLocation(FVector(-55,0,34));
    Rider = CreateDefaultSubobject<USPBicycleRider>(TEXT("Rider"));
    Rider->SetupAttachment(Frame);
    static ConstructorHelpers::FObjectFinder<USkeletalMesh> Person(TEXT("/Game/StanleyPark/Explorer/SK_Explorer.SK_Explorer"));
    static ConstructorHelpers::FObjectFinder<UAnimSequence> Walk(TEXT("/Game/StanleyPark/Explorer/A_Explorer_Walk.A_Explorer_Walk"));
    static ConstructorHelpers::FObjectFinder<UAnimSequence> Idle(TEXT("/Game/StanleyPark/Explorer/A_Explorer_Idle.A_Explorer_Idle"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Bike(TEXT("/Game/StanleyPark/Kit/SM_Bicycle_Animated.SM_Bicycle_Animated"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Wheel(TEXT("/Game/StanleyPark/Kit/SM_Wheel.SM_Wheel"));
    Walker->SetSkeletalMesh(Person.Object); WalkClip = Walk.Object; IdleClip = Idle.Object;
    Frame->SetStaticMesh(Bike.Object); FrontWheel->SetStaticMesh(Wheel.Object); RearWheel->SetStaticMesh(Wheel.Object);
    const TArray<UPrimitiveComponent*> Parts{Walker.Get(), Frame.Get(), FrontWheel.Get(), RearWheel.Get(), Rider.Get()};
    for (UPrimitiveComponent* Part : Parts)
    {
        Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Part->SetGenerateOverlapEvents(false); Part->SetCanEverAffectNavigation(false);
        Part->SetCullDistance(18000);
    }
    Walker->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::OnlyTickPoseWhenRendered;
}

void ASPParkVisitor::Configure(int32 InRoute, double Along, bool bRide, double Pace, double Offset)
{
    RouteIndex = InRoute; Distance = Along; bCyclist = bRide; TargetSpeed = Pace; SideOffset = Offset;
    Walker->SetVisibility(!bRide); Frame->SetVisibility(bRide, true); Rider->SetVisibility(bRide);
    Rider->SetComponentTickEnabled(bRide);
    const int32 Palette = int32(Along / 1000) % 4;
    for (UMeshComponent* Body : TArray<UMeshComponent*>{Walker.Get(),Rider.Get()})
        for (int32 Index=0; Index<Body->GetNumMaterials(); ++Index)
        {
            const UMaterialInterface* Original = Body->GetMaterial(Index);
            if (!Original) continue;
            const TCHAR* MaterialRole = Original->GetName().Contains(TEXT("Jacket")) ? TEXT("Jacket")
                : Original->GetName().Contains(TEXT("Skin")) ? TEXT("Skin") : nullptr;
            if (!MaterialRole) continue;
            const FString Path=FString::Printf(TEXT("/Game/StanleyPark/Seawall/ParkDetails_v05/Materials/M_Visitor%s_%d"),MaterialRole,Palette);
            if (UMaterialInterface* Material=LoadObject<UMaterialInterface>(nullptr,*Path)) Body->SetMaterial(Index,Material);
        }
}

void ASPParkVisitor::BeginPlay()
{
    Super::BeginPlay(); Walker->PlayAnimation(IdleClip, true);
}

void ASPParkVisitor::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    const ASPWorldDirector* Director = Cast<ASPWorldDirector>(GetOwner());
    if (!Director || !Director->GetData().Routes.IsValidIndex(RouteIndex)) return;
    const FSPRoute& Route = Director->GetData().Routes[RouteIndex];
    const APlayerController* Player = GetWorld()->GetFirstPlayerController();
    const APawn* Pawn = Player ? Player->GetPawn() : nullptr;
    FVector Tangent;
    const FVector Centre = Route.Sample(Distance, &Tangent);
    const FVector Side(-Tangent.Y,Tangent.X,0);
    const FVector PlayerPosition = Pawn ? Pawn->GetActorLocation() : FVector::ZeroVector;
    const bool bNear = FVector::DistSquared2D(Centre,PlayerPosition) < FMath::Square(18000.0);
    const bool bYield = Pawn && FVector::DistSquared2D(Centre,PlayerPosition) < FMath::Square(550.0)
        && FVector::DotProduct(PlayerPosition-Centre,Tangent) > -120;
    Speed = FMath::FInterpConstantTo(Speed, bYield ? 0.0 : TargetSpeed, DeltaSeconds, 180.0);
    const double Next = FMath::Fmod(Distance + Speed * DeltaSeconds, Route.Length);
    FVector Direction;
    FVector Position = Route.Sample(Next,&Direction) + Side * (SideOffset + (Director->IsBellNear(Centre) ? 35.0 : 0.0));
    FHitResult Ground;
    FCollisionQueryParams Query(SCENE_QUERY_STAT(VisitorGround),true,this);
    if (!GetWorld()->LineTraceSingleByChannel(Ground,Position+FVector(0,0,100),Position-FVector(0,0,250),ECC_WorldStatic,Query)
        || Ground.ImpactNormal.Z < .65)
    {
        Position = Route.Sample(Next,&Direction);
        if (!GetWorld()->LineTraceSingleByChannel(Ground,Position+FVector(0,0,100),Position-FVector(0,0,250),ECC_WorldStatic,Query)) return;
    }
    // Do not walk through a solid prop. Wait while the segment is occupied.
    FHitResult Obstacle;
    if (bNear && GetWorld()->SweepSingleByChannel(Obstacle,GetActorLocation()+FVector(0,0,95),
        Ground.ImpactPoint+FVector(0,0,95),FQuat::Identity,ECC_WorldStatic,FCollisionShape::MakeCapsule(24,65),Query)) Speed = 0;
    else
    {
        Distance = Next;
        SetActorLocationAndRotation(Ground.ImpactPoint+FVector(0,0,2),FRotator(0,Direction.Rotation().Yaw,0));
    }
    const bool bNowMoving = Speed > 5;
    if (!bCyclist && bMoving != bNowMoving) Walker->PlayAnimation(bNowMoving ? WalkClip : IdleClip,true);
    if (auto* Animation = Walker->GetSingleNodeInstance()) Animation->SetPlayRate(float(FMath::Clamp(Speed/260.0,.3,1.2)));
    bMoving = bNowMoving;
    Rider->SetAmbientMotion(Speed/100.0);
    Rider->SetComponentTickEnabled(bCyclist && bNear);
    WheelAngle += FMath::RadiansToDegrees(Speed * DeltaSeconds / 34);
    FrontWheel->SetRelativeRotation(FRotator(WheelAngle,0,0)); RearWheel->SetRelativeRotation(FRotator(WheelAngle,0,0));
    SetActorTickInterval(bNear ? 0.f : .5f);
}
