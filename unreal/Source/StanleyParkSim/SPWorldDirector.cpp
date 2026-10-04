#include "SPWorldDirector.h"
#include "SPSeawallBirds.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
    TAutoConsoleVariable<int32> SeawallPreviewTraffic(TEXT("sp.SeawallPreviewTraffic"), 0,
        TEXT("Opt in to unfinished pedestrian and cyclist proxies in the seawall map. Read at level start."));
}

ASPWorldDirector::ASPWorldDirector()
{
    PrimaryActorTick.bCanEverTick = true;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    SeawallBirds = CreateDefaultSubobject<USPSeawallBirds>(TEXT("SeawallBirds"));
    Walkers = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("PedestrianBlockout"));
    Riders = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("CyclistBlockout"));
    for (UInstancedStaticMeshComponent* Component : {Walkers.Get(), Riders.Get()})
    {
        Component->SetupAttachment(RootComponent);
        Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Component->SetCullDistances(18000, 22000);
    }
    static ConstructorHelpers::FObjectFinderOptional<UStaticMesh> WalkerAsset(TEXT("/Game/StanleyPark/Kit/SM_Walker.SM_Walker"));
    static ConstructorHelpers::FObjectFinderOptional<UStaticMesh> RiderAsset(TEXT("/Game/StanleyPark/Kit/SM_Cyclist.SM_Cyclist"));
    if (WalkerAsset.Succeeded()) Walkers->SetStaticMesh(WalkerAsset.Get());
    if (RiderAsset.Succeeded()) Riders->SetStaticMesh(RiderAsset.Get());
}

void ASPWorldDirector::BeginPlay()
{
    Super::BeginPlay();
    // Recovery still needs route data when ambient traffic is disabled.
    // The bird component owns an independent tick.
    SetActorTickEnabled(false);
    if (!Data.Load(Error))
    {
        UE_LOG(LogTemp, Error, TEXT("Stanley Park: %s"), *Error);
        return;
    }
    if (GetWorld()->GetMapName().EndsWith(TEXT("StanleyParkSeawall"))
        && SeawallPreviewTraffic.GetValueOnGameThread() == 0)
        return;
    FRandomStream Random(101);
    for (int32 Index = 0; Index < Data.Routes.Num(); ++Index)
    {
        const FSPRoute& Route = Data.Routes[Index];
        // Unresolved access never receives automatic traffic. The user can inspect it.
        if (Route.AccessStatus != TEXT("source_supported") || Route.Length < 10000) continue;
        const int32 Count = FMath::Min(24, FMath::FloorToInt(Route.Length / 45000));
        for (int32 AgentIndex = 0; AgentIndex < Count; ++AgentIndex)
        {
            FSPAmbientAgent Agent;
            Agent.RouteIndex = Index;
            Agent.bCyclist = Route.bCycling;
            Agent.Distance = Random.FRandRange(0, Route.Length);
            Agent.TargetSpeed = Route.bCycling ? Random.FRandRange(260, 380) : Random.FRandRange(95, 145);
            Agent.Speed = Agent.TargetSpeed;
            Agent.Phase = Random.FRandRange(0, 6.283185);
            UInstancedStaticMeshComponent* Component = Agent.bCyclist ? Riders : Walkers;
            if (!Component->GetStaticMesh()) continue;
            Agent.Instance = Component->AddInstance(FTransform(Route.Sample(Agent.Distance)));
            Agents.Add(Agent);
        }
    }
    SetActorTickEnabled(!Agents.IsEmpty());
}

void ASPWorldDirector::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    AmbientAccumulator += FMath::Min(double(DeltaSeconds), 0.1);
    if (AmbientAccumulator >= 0.05)
    {
        UpdateAgents(AmbientAccumulator);
        AmbientAccumulator = 0;
    }
}

void ASPWorldDirector::UpdateAgents(double DeltaSeconds)
{
    const APlayerController* Player = GetWorld()->GetFirstPlayerController();
    const APawn* Pawn = Player ? Player->GetPawn() : nullptr;
    const FVector PlayerPosition = Pawn ? Pawn->GetActorLocation() : FVector::ZeroVector;
    const double Time = GetWorld()->GetTimeSeconds();
    bool bWalkersUpdated = false;
    bool bRidersUpdated = false;
    for (FSPAmbientAgent& Agent : Agents)
    {
        const FSPRoute& Route = Data.Routes[Agent.RouteIndex];
        FVector Direction;
        const FVector Position = Route.Sample(Agent.Distance, &Direction);
        const double PlayerDistance = FVector::Dist2D(Position, PlayerPosition);
        double Target = Agent.TargetSpeed;
        if (PlayerDistance < 500 && FVector::DotProduct(PlayerPosition - Position, Direction) > -40) Target = 0;
        // Follow traffic on the same route, keeping a speed-dependent headway.
        for (const FSPAmbientAgent& Other : Agents)
        {
            if (&Other == &Agent || Other.RouteIndex != Agent.RouteIndex) continue;
            double Gap = Other.Distance - Agent.Distance;
            if (Route.bClosed && Gap < 0) Gap += Route.Length;
            if (Gap > 0 && Gap < 170 + Agent.Speed * 1.4) Target = FMath::Min(Target, Other.Speed * 0.75);
        }
        Agent.Speed = FMath::FInterpConstantTo(Agent.Speed, Target, DeltaSeconds, 260.0);
        Agent.Distance += Agent.Speed * DeltaSeconds;
        if (Route.bClosed) Agent.Distance = FMath::Fmod(Agent.Distance, Route.Length);
        else if (Agent.Distance >= Route.Length) Agent.Distance = 0; // Endpoints are outside the near visibility range in later authored networks.
        FVector NewPosition = Route.Sample(Agent.Distance, &Direction);
        const FVector Side(-Direction.Y, Direction.X, 0);
        const bool bBellNear = Time < BellUntil && FVector::Dist2D(NewPosition, BellPosition) < 1200;
        NewPosition += Side * (bBellNear ? 50 : 25);
        FTransform Transform(Direction.Rotation(), NewPosition);
        (Agent.bCyclist ? Riders : Walkers)->UpdateInstanceTransform(Agent.Instance, Transform, false, false, true);
        (Agent.bCyclist ? bRidersUpdated : bWalkersUpdated) = true;
    }
    if (bWalkersUpdated) Walkers->MarkRenderStateDirty();
    if (bRidersUpdated) Riders->MarkRenderStateDirty();
}

bool ASPWorldDirector::GetRecoveryLocation(const FVector& Position, FVector& Place, double& Yaw) const
{
    if (Data.Routes.IsEmpty()) return false;
    double BestSquared = TNumericLimits<double>::Max();
    const FSPRoute* BestRoute = nullptr;
    double Chainage = 0;
    for (const FSPRoute& Route : Data.Routes)
    {
        // Branch geometry is still a review layer. Recovery stays on the
        // engineered continuous circuit, including the correct tunnel level.
        if (Route.Id != TEXT("main_circuit")) continue;
        double Squared;
        const double Candidate = Route.FindNearest(Position, Squared);
        if (Squared < BestSquared) { BestSquared = Squared; BestRoute = &Route; Chainage = Candidate; }
    }
    if (!BestRoute || Position.IsNearlyZero() || BestSquared > FMath::Square(30000.0))
    {
        Place = Data.Spawn;
        Yaw = Data.SpawnYaw;
        return true;
    }
    FVector Direction;
    Place = BestRoute->Sample(Chainage, &Direction);
    Yaw = Direction.Rotation().Yaw;
    return true;
}

void ASPWorldDirector::OnBell(const FVector& Position)
{
    BellPosition = Position;
    BellUntil = GetWorld()->GetTimeSeconds() + 3;
}
