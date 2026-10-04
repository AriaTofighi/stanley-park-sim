#include "SPGameMode.h"
#include "SPBicyclePawn.h"
#include "SPExplorerCharacter.h"
#include "SPGraphicsSettings.h"
#include "SPReleaseCheck.h"
#include "SPWaterSafety.h"
#include "Components/CapsuleComponent.h"
#include "SPWorldDirector.h"
#include "SPHud.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

ASPGameMode::ASPGameMode()
{
    DefaultPawnClass = ASPBicyclePawn::StaticClass();
    HUDClass = ASPHud::StaticClass();
}

void ASPGameMode::StartPlay()
{
    Super::StartPlay();
    SPGraphics::ApplySavedPreset();
    ASPWorldDirector* Director = GetWorld()->SpawnActor<ASPWorldDirector>();
    if (!SPWaterSafety::Initialize() && Director)
        Director->Error = TEXT("Water recovery data is missing or invalid. Restore WorldData/water-safety.json.");
    if (APlayerController* Player = GetWorld()->GetFirstPlayerController())
    {
        Player->SetInputMode(FInputModeGameOnly());
        Player->bShowMouseCursor = false;
        if (ASPExplorerCharacter* Explorer = Cast<ASPExplorerCharacter>(Player->GetPawn()))
        {
            if (Director && Director->Error.IsEmpty() && !Director->GetData().Routes.IsEmpty())
                Explorer->PlaceOnGround(Director->GetData().Spawn, Director->GetData().SpawnYaw);
        }
        if (ASPBicyclePawn* Bicycle = Cast<ASPBicyclePawn>(Player->GetPawn()))
        {
            // Initial placement is explicit. Recovery selects the nearest route,
            // which can be an interior branch when a map start is at the origin.
            if (Director && Director->Error.IsEmpty() && !Director->GetData().Routes.IsEmpty())
                Bicycle->PlaceOnRoute(Director->GetData().Spawn, Director->GetData().SpawnYaw);
        }
    }
#if !UE_BUILD_SHIPPING
    if (FParse::Param(FCommandLine::Get(), TEXT("SPReleaseCheck")))
        GetWorld()->SpawnActor<ASPReleaseCheck>();
#endif
}

UClass* ASPGameMode::GetDefaultPawnClassForController_Implementation(AController* Controller)
{
    return GetWorld()->GetMapName().Contains(TEXT("StanleyParkSeawall"))
        ? ASPExplorerCharacter::StaticClass() : Super::GetDefaultPawnClassForController_Implementation(Controller);
}

void ASPGameMode::ToggleExplorer()
{
    APlayerController* Player = GetWorld()->GetFirstPlayerController();
    APawn* Previous = Player ? Player->GetPawn() : nullptr;
    if (!Previous) return;
    const bool bWasExplorer = Previous->IsA<ASPExplorerCharacter>();
    const FVector Position = Previous->GetActorLocation();
    const double Yaw = Previous->GetActorRotation().Yaw;
    FHitResult Ground;
    FCollisionQueryParams Query(SCENE_QUERY_STAT(ExploreSwitch), true, Previous);
    if (!GetWorld()->LineTraceSingleByChannel(Ground, Position, Position - FVector(0,0,300), ECC_WorldStatic, Query)) return;
    if (Ground.ImpactNormal.Z < .71) return;
    double WaterZ = 0;
    if (SPWaterSafety::GetSurfaceHeight(Ground.ImpactPoint, WaterZ) && Ground.ImpactPoint.Z < WaterZ + 5) return;
    // Account for the capsule's lower hemisphere on sloped terrain. The
    // engine may then adjust this position away from a nearby wall. Keep that
    // resolved position instead of teleporting back into the obstacle.
    const double Radius = bWasExplorer ? 32. : 34.;
    const double HalfHeight = bWasExplorer ? 70. : 90.;
    const double Clearance = HalfHeight - Radius + Radius / Ground.ImpactNormal.Z + 3;
    FActorSpawnParameters Params;
    Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButDontSpawnIfColliding;
    // Ignore the outgoing body during the incoming pawn's collision placement.
    Previous->SetActorEnableCollision(false);
    UClass* NextClass = bWasExplorer ? ASPBicyclePawn::StaticClass() : ASPExplorerCharacter::StaticClass();
    APawn* Next = GetWorld()->SpawnActor<APawn>(NextClass, Ground.ImpactPoint + FVector(0,0,Clearance), FRotator(0,Yaw,0), Params);
    if (!Next) { Previous->SetActorEnableCollision(true); return; }
    Player->Possess(Next);
    Player->FlushPressedKeys();
    Player->SetControlRotation(FRotator(-12, Yaw, 0));
    Previous->Destroy();
}
