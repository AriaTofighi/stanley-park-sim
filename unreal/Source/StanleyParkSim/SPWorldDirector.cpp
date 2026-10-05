#include "SPWorldDirector.h"
#include "SPSeawallBirds.h"
#include "SPParkVisitor.h"
#include "Components/AudioComponent.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Misc/ConfigCacheIni.h"
#include "Sound/SoundBase.h"
#include "UObject/ConstructorHelpers.h"

ASPWorldDirector::ASPWorldDirector()
{
    PrimaryActorTick.bCanEverTick = false;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    SeawallBirds = CreateDefaultSubobject<USPSeawallBirds>(TEXT("SeawallBirds"));
    Ambience = CreateDefaultSubobject<UAudioComponent>(TEXT("ForestAmbience"));
    Ambience->SetupAttachment(RootComponent);
    Ambience->bAutoActivate = false;
    Ambience->bAllowSpatialization = false;
    Ambience->bIsUISound = false;
    Ambience->SetVolumeMultiplier(.32f);
    static ConstructorHelpers::FObjectFinderOptional<USoundBase> Forest(TEXT("/Game/StanleyPark/Audio/S_ForestAmbience.S_ForestAmbience"));
    if (Forest.Succeeded()) Ambience->SetSound(Forest.Get());
}

void ASPWorldDirector::BeginPlay()
{
    Super::BeginPlay();
    if (!Data.Load(Error)) { UE_LOG(LogTemp,Error,TEXT("Stanley Park: %s"),*Error); return; }
    if (!GetWorld()->GetMapName().Contains(TEXT("StanleyParkSeawall"))) return;
    bool bNature = true;
    if (GConfig) GConfig->GetBool(TEXT("StanleyPark.Audio"),TEXT("NatureSounds"),bNature,GGameUserSettingsIni);
    if (bNature && Ambience->Sound) Ambience->Play();
    FRandomStream Random(20261005);
    for (int32 Index=0; Index<Data.Routes.Num(); ++Index)
    {
        const FSPRoute& Route=Data.Routes[Index];
        if (Route.Id != TEXT("main_circuit")) continue;
        constexpr int32 Count = 72;
        for (int32 VisitorIndex=0; VisitorIndex<Count; ++VisitorIndex)
        {
            const double Along=FMath::Fmod(800.0 + Route.Length * VisitorIndex / Count,Route.Length);
            FVector Direction;
            const FVector Place=Route.Sample(Along,&Direction);
            FActorSpawnParameters Params; Params.Owner=this;
            Params.SpawnCollisionHandlingOverride=ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
            auto* Visitor=GetWorld()->SpawnActor<ASPParkVisitor>(Place,FRotator(0,Direction.Rotation().Yaw,0),Params);
            if (!Visitor) continue;
            const bool bRide=VisitorIndex%3==2;
            Visitor->Configure(Index,Along,bRide,bRide ? Random.FRandRange(290,420) : Random.FRandRange(100,145),
                bRide ? -35.0 : Random.FRandRange(75,110));
            Visitors.Add(Visitor);
        }
    }
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
    BellUntil = GetWorld()->GetTimeSeconds()+3;
}

bool ASPWorldDirector::IsBellNear(const FVector& Position) const
{
    return GetWorld()->GetTimeSeconds()<BellUntil && FVector::Dist2D(Position,BellPosition)<1200;
}

void ASPWorldDirector::ToggleAmbience()
{
    const bool bEnable=!Ambience->IsPlaying();
    if (bEnable) Ambience->Play(); else Ambience->Stop();
    if (GConfig)
    {
        GConfig->SetBool(TEXT("StanleyPark.Audio"),TEXT("NatureSounds"),bEnable,GGameUserSettingsIni);
        GConfig->Flush(false,GGameUserSettingsIni);
    }
}
