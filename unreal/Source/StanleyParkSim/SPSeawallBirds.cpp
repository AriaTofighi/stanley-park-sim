#include "SPSeawallBirds.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
    TAutoConsoleVariable<int32> EnableSeawallBirds(TEXT("sp.SeawallBirds.Enable"), 1,
        TEXT("Enable the small gull layer in StanleyParkSeawall only. Requires imported bird assets."));
    constexpr double VisibleDistance = 30000.0;
    constexpr double NearDistance = 11000.0;
    constexpr double Clearance = 500.0;
    constexpr double ClearanceInterval = 0.2;
    constexpr double BobHeight = 45.0;
    constexpr int32 ArcSteps = 128;
    constexpr double TwoPi = 6.283185307179586;

    TSharedPtr<FJsonValue> JsonPoint(const FVector& Point)
    {
        return MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{
            MakeShared<FJsonValueNumber>(Point.X), MakeShared<FJsonValueNumber>(Point.Y),
            MakeShared<FJsonValueNumber>(Point.Z)});
    }
}

USPSeawallBirds::USPSeawallBirds()
{
    PrimaryComponentTick.bCanEverTick = true;
    PrimaryComponentTick.TickInterval = 0.25f;
}

void USPSeawallBirds::BeginPlay()
{
    Super::BeginPlay();
    // PIE prefixes are allowed; the original M1 map never receives birds.
    bSeawallMap = GetWorld()->GetMapName().EndsWith(TEXT("StanleyParkSeawall"));
    if (!bSeawallMap) SetComponentTickEnabled(false);
}

bool USPSeawallBirds::InitializeBirds()
{
    FString Text;
    TSharedPtr<FJsonObject> Root;
    const TArray<TSharedPtr<FJsonValue>>* Zones = nullptr;
    FString Coordinates;
    if (!FFileHelper::LoadFileToString(Text, *(FPaths::ProjectContentDir() / TEXT("WorldData/seawall-birds.json")))
        || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root)
        || !Root.IsValid() || !Root->HasTypedField<EJson::Number>(TEXT("schema_version"))
        || Root->GetIntegerField(TEXT("schema_version")) != 1
        || !Root->TryGetStringField(TEXT("coordinate_contract"), Coordinates)
        || Coordinates != TEXT("unreal_north_east_up_cm")
        || !Root->TryGetNumberField(TEXT("water_height_cm"), WaterHeight)
        || !FMath::IsFinite(WaterHeight) || FMath::Abs(WaterHeight) > 500
        || !Root->TryGetArrayField(TEXT("zones"), Zones) || Zones->IsEmpty() || Zones->Num() > 12)
        return false;

    // Asset paths are fixed and restricted to this visual layer.
    UStaticMesh* Meshes[] = {
        LoadObject<UStaticMesh>(nullptr, TEXT("/Game/StanleyPark/Seawall/Birds/SM_GullBody.SM_GullBody")),
        LoadObject<UStaticMesh>(nullptr, TEXT("/Game/StanleyPark/Seawall/Birds/SM_GullWingLeft.SM_GullWingLeft")),
        LoadObject<UStaticMesh>(nullptr, TEXT("/Game/StanleyPark/Seawall/Birds/SM_GullWingRight.SM_GullWingRight"))
    };
    for (const UStaticMesh* Mesh : Meshes) if (!Mesh) return false;
    FRandomStream Random(27182);
    TArray<FSPSeawallBird> Pending;
    for (const auto& Value : *Zones)
    {
        const auto Zone = Value->AsObject();
        const TArray<TSharedPtr<FJsonValue>>* Centre = nullptr;
        double North, East, Height, RadiusNorth, RadiusEast;
        if (!Zone.IsValid() || !Zone->TryGetArrayField(TEXT("centre_unreal_cm"), Centre)
            || Centre->Num() != 3 || !(*Centre)[0]->TryGetNumber(North)
            || !(*Centre)[1]->TryGetNumber(East) || !(*Centre)[2]->TryGetNumber(Height)
            || !Zone->TryGetNumberField(TEXT("radius_north_cm"), RadiusNorth)
            || !Zone->TryGetNumberField(TEXT("radius_east_cm"), RadiusEast)
            || !FMath::IsFinite(North) || !FMath::IsFinite(East) || !FMath::IsFinite(Height)
            || !FMath::IsFinite(RadiusNorth) || !FMath::IsFinite(RadiusEast)
            || FMath::Abs(North) > 400000 || FMath::Abs(East) > 400000
            || Height < 900 || Height > 6000 || RadiusNorth < 1200 || RadiusNorth > 8000
            || RadiusEast < 1200 || RadiusEast > 8000) return false;
        for (int32 Index = 0; Index < 3; ++Index)
        {
            FSPSeawallBird Bird;
            Zone->TryGetStringField(TEXT("id"), Bird.ZoneId);
            Bird.Centre = FVector(North, East, Height + Index * 120.0);
            const double Scale = Random.FRandRange(0.90f, 1.0f);
            Bird.Radius = FVector2D(RadiusNorth, RadiusEast) * Scale;
            Bird.Phase = Index * TwoPi / 3.0 + Random.FRandRange(-0.2f, 0.2f);
            Bird.Speed = Random.FRandRange(680.0f, 790.0f);
            Bird.FlapPhase = Random.FRandRange(0.0f, float(TwoPi));
            Bird.ArcLengths.Add(0.0);
            FVector2D Previous(Bird.Radius.X, 0);
            for (int32 Step = 1; Step <= ArcSteps; ++Step)
            {
                const double Angle = Step * TwoPi / ArcSteps;
                const FVector2D Point(Bird.Radius.X * FMath::Cos(Angle), Bird.Radius.Y * FMath::Sin(Angle));
                Bird.ArcLengths.Add(Bird.ArcLengths.Last() + (Point - Previous).Size());
                Previous = Point;
            }
            Pending.Add(Bird);
        }
    }
    Birds = MoveTemp(Pending);
    for (int32 Index = 0; Index < Birds.Num(); ++Index)
    {
        for (int32 Part = 0; Part < 3; ++Part)
        {
            const TCHAR* PartName[] = {TEXT("Body"), TEXT("WingLeft"), TEXT("WingRight")};
            const FName Name(*FString::Printf(TEXT("SeawallGull_%02d_%s"), Index, PartName[Part]));
            auto* Component = NewObject<UStaticMeshComponent>(GetOwner(), Name);
            GetOwner()->AddInstanceComponent(Component);
            Component->SetupAttachment(GetOwner()->GetRootComponent());
            Component->SetMobility(EComponentMobility::Movable);
            Component->SetStaticMesh(Meshes[Part]);
            Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
            Component->SetGenerateOverlapEvents(false);
            Component->SetCanEverAffectNavigation(false);
            Component->SetCastShadow(false);
            Component->SetVisibility(false);
            Component->SetCullDistance(float(VisibleDistance));
            Component->RegisterComponent();
            Parts.Add(Component);
        }
    }
    return true;
}

void USPSeawallBirds::HideBird(int32 Index)
{
    if (!Birds[Index].bVisible) return;
    for (int32 Part = 0; Part < 3; ++Part) Parts[Index * 3 + Part]->SetVisibility(false);
    Birds[Index].bVisible = false;
}

FVector USPSeawallBirds::SampleFlight(const FSPSeawallBird& Bird, double Time, double* OutAngle) const
{
    // Invert a small arc-length table so the gull does not slow down at the
    // narrow end of its ellipse. This table is built once, not every frame.
    const double Perimeter = Bird.ArcLengths.Last();
    const double Distance = FMath::Fmod(FMath::Fmod(Time * Bird.Speed
        + Bird.Phase * Perimeter / TwoPi, Perimeter) + Perimeter, Perimeter);
    int32 Low = 1, High = ArcSteps;
    while (Low < High)
    {
        const int32 Middle = (Low + High) / 2;
        if (Bird.ArcLengths[Middle] < Distance) Low = Middle + 1;
        else High = Middle;
    }
    const double Alpha = (Distance - Bird.ArcLengths[Low - 1])
        / (Bird.ArcLengths[Low] - Bird.ArcLengths[Low - 1]);
    const double Angle = (Low - 1 + Alpha) * TwoPi / ArcSteps;
    if (OutAngle) *OutAngle = Angle;
    return Bird.Centre + FVector(Bird.Radius.X * FMath::Cos(Angle), Bird.Radius.Y * FMath::Sin(Angle),
        BobHeight * FMath::Sin(Angle * 2.0 + Bird.FlapPhase));
}

bool USPSeawallBirds::CheckClearance(FSPSeawallBird& Bird, const FVector& Position, const FVector& LookAhead)
{
    ++Bird.ClearanceSamples;
    Bird.LastClearanceTime = GetWorld()->GetTimeSeconds();
    Bird.LastBlockingActor.Reset();
    Bird.LastFloorClearance = Position.Z - WaterHeight;
    FCollisionQueryParams Query(SCENE_QUERY_STAT(SeawallBirdClearance), true, GetOwner());
    FHitResult Hit;
    // Query from above the bird to detect an overhead structure too. Water is
    // a fixed fallback floor when the scene has no collision at that XY point.
    const FVector Bottom(Position.X, Position.Y, WaterHeight - 500.0);
    Bird.bFloorHit = GetWorld()->LineTraceSingleByChannel(Hit, Position + FVector(0, 0, 2000),
        Bottom, ECC_WorldStatic, Query);
    if (Bird.bFloorHit)
    {
        Bird.LastFloorClearance = FMath::Min(Bird.LastFloorClearance, Position.Z - Hit.ImpactPoint.Z);
        if (Hit.bStartPenetrating || Bird.LastFloorClearance < Clearance)
            Bird.LastBlockingActor = GetNameSafe(Hit.GetActor());
    }
    Bird.MinFloorClearance = FMath::Min(Bird.MinFloorClearance, Bird.LastFloorClearance);
    bool bClear = Bird.LastFloorClearance >= Clearance && !Hit.bStartPenetrating;
    // An 80 cm sphere contains the entire 1.44 m gull. Sweep ahead beyond the
    // next 5 Hz clearance update, instead of tracing only the body centre.
    ++Bird.SweepSamples;
    if (GetWorld()->SweepSingleByChannel(Hit, Position, LookAhead, FQuat::Identity,
        ECC_WorldStatic, FCollisionShape::MakeSphere(80.0f), Query))
    {
        bClear = false;
        Bird.LastBlockingActor = GetNameSafe(Hit.GetActor());
    }
    if (!bClear) ++Bird.BlockedSamples;
    return bClear;
}

void USPSeawallBirds::TickComponent(float DeltaTime, ELevelTick TickType,
    FActorComponentTickFunction* ThisTickFunction)
{
    Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
    if (!bSeawallMap) return;
    if (EnableSeawallBirds.GetValueOnGameThread() == 0)
    {
        for (int32 Index = 0; Index < Birds.Num(); ++Index) HideBird(Index);
        SetComponentTickInterval(0.25f);
        return;
    }
    if (bUnavailable) return;
    if (!bReady)
    {
        bReady = InitializeBirds();
        if (!bReady)
        {
            bUnavailable = true;
            UE_LOG(LogTemp, Warning, TEXT("Seawall birds are off: import their assets and WorldData config, then restart the level."));
            SetComponentTickEnabled(false);
            return;
        }
    }
    const APlayerController* Player = GetWorld()->GetFirstPlayerController();
    if (!Player)
    {
        for (int32 Index = 0; Index < Birds.Num(); ++Index) HideBird(Index);
        return;
    }
    FVector Eye;
    FRotator View;
    Player->GetPlayerViewPoint(Eye, View);
    const double Time = GetWorld()->GetTimeSeconds();
    bool bAnyNear = false;
    bool bAnyVisible = false;
    for (int32 Index = 0; Index < Birds.Num(); ++Index)
    {
        auto& Bird = Birds[Index];
        double Angle;
        const FVector Position = SampleFlight(Bird, Time, &Angle);
        const double S = FMath::Sin(Angle), C = FMath::Cos(Angle);
        const double DistanceSquared = FVector::DistSquared(Eye, Position);
        if (DistanceSquared > FMath::Square(VisibleDistance))
        {
            HideBird(Index);
            ++Bird.CulledSamples;
            Bird.ClearanceAt = 0;
            continue;
        }
        bAnyNear |= DistanceSquared < FMath::Square(NearDistance);
        bAnyVisible = true;
        if (Time >= Bird.ClearanceAt)
        {
            Bird.bClear = CheckClearance(Bird, Position, SampleFlight(Bird, Time + ClearanceInterval + 0.05));
            Bird.ClearanceAt = Time + ClearanceInterval;
        }
        if (!Bird.bClear) { HideBird(Index); continue; }
        const FVector Tangent(-Bird.Radius.X * S, Bird.Radius.Y * C,
            BobHeight * 2.0 * FMath::Cos(Angle * 2.0 + Bird.FlapPhase));
        FRotator Heading = Tangent.Rotation();
        const double CurvatureRadius = FMath::Pow(FMath::Square(Bird.Radius.X * S)
            + FMath::Square(Bird.Radius.Y * C), 1.5) / (Bird.Radius.X * Bird.Radius.Y);
        Bird.BankDegrees = FMath::Clamp(FMath::RadiansToDegrees(FMath::Atan(
            FMath::Square(Bird.Speed) / (980.0 * CurvatureRadius))), 0.0, 30.0);
        // Increasing ellipse angle is a right turn in this UE frame. Positive
        // Rotator roll lowers the right wing into that turn.
        Heading.Roll = Bird.BankDegrees;
        const FQuat BodyRotation = Heading.Quaternion();
        // A short series of clear wingbeats, then a stable glide. The envelope
        // has zero velocity at each boundary so there is no pose snap.
        const double Cycle = FMath::Fmod(Time + Bird.FlapPhase, 9.0);
        const double Envelope = Cycle < 3.6 ? FMath::Square(FMath::Sin(PI * Cycle / 3.6)) : 0.0;
        Bird.FlapDegrees = 6.0 + 38.0 * Envelope * FMath::Sin(Time * TwoPi * 1.8 + Bird.FlapPhase);
        const double Flap = FMath::DegreesToRadians(Bird.FlapDegrees);
        Parts[Index * 3]->SetWorldTransform(FTransform(BodyRotation, Position));
        for (int32 Wing = 0; Wing < 2; ++Wing)
        {
            const double Side = Wing == 0 ? -1.0 : 1.0;
            const FVector Shoulder(0, Side * 9.0, 3.0);
            const FQuat WingRotation = BodyRotation * FQuat(FVector::ForwardVector, Side * Flap);
            Parts[Index * 3 + Wing + 1]->SetWorldTransform(FTransform(WingRotation,
                Position + BodyRotation.RotateVector(Shoulder)));
        }
        if (!Bird.bVisible)
            for (int32 Part = 0; Part < 3; ++Part) Parts[Index * 3 + Part]->SetVisibility(true);
        Bird.bVisible = true;
        ++Bird.TransformSamples;
        Bird.MinShownFlapDegrees = FMath::Min(Bird.MinShownFlapDegrees, Bird.FlapDegrees);
        Bird.MaxShownFlapDegrees = FMath::Max(Bird.MaxShownFlapDegrees, Bird.FlapDegrees);
        if (Envelope > 0.001) ++Bird.FlapSamples;
        else ++Bird.GlideSamples;
    }
    // Nearby birds need render-frame transforms: a 20 Hz step is conspicuous
    // at 25 m. Collision work remains at 5 Hz per visible bird.
    SetComponentTickInterval(bAnyNear ? 0.0f : bAnyVisible ? 0.05f : 0.5f);
}

FString USPSeawallBirds::GetReviewSnapshot() const
{
    auto Root = MakeShared<FJsonObject>();
    Root->SetStringField(TEXT("map"), GetWorld() ? GetWorld()->GetMapName() : TEXT("NoWorld"));
    Root->SetNumberField(TEXT("world_time_seconds"), GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0);
    Root->SetBoolField(TEXT("map_guard_passed"), bSeawallMap);
    Root->SetBoolField(TEXT("enabled"), EnableSeawallBirds.GetValueOnGameThread() != 0);
    Root->SetBoolField(TEXT("ready"), bReady);
    Root->SetBoolField(TEXT("unavailable"), bUnavailable);
    Root->SetNumberField(TEXT("tick_interval_seconds"), PrimaryComponentTick.TickInterval);
    Root->SetNumberField(TEXT("gull_wingspan_cm"), 144.0);
    FVector Eye = FVector::ZeroVector;
    FRotator View = FRotator::ZeroRotator;
    const APlayerController* Player = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
    if (Player)
    {
        Player->GetPlayerViewPoint(Eye, View);
        Root->SetField(TEXT("view_position_cm"), JsonPoint(Eye));
        Root->SetField(TEXT("view_rotation_pitch_yaw_roll"), JsonPoint(FVector(View.Pitch, View.Yaw, View.Roll)));
    }
    Root->SetStringField(TEXT("limits"), TEXT("Query counters describe authored collision only. Non-collision scenery and visible appearance need image review."));
    TArray<TSharedPtr<FJsonValue>> Rows;
    for (int32 Index = 0; Index < Birds.Num(); ++Index)
    {
        const auto& Bird = Birds[Index];
        auto Row = MakeShared<FJsonObject>();
        Row->SetNumberField(TEXT("index"), Index);
        Row->SetStringField(TEXT("zone"), Bird.ZoneId);
        Row->SetBoolField(TEXT("visible"), Bird.bVisible);
        Row->SetBoolField(TEXT("clearance_passed"), Bird.bClear);
        Row->SetNumberField(TEXT("last_clearance_world_time"), Bird.LastClearanceTime);
        Row->SetBoolField(TEXT("last_floor_trace_hit"), Bird.bFloorHit);
        Row->SetNumberField(TEXT("last_floor_or_water_clearance_cm"), Bird.LastFloorClearance);
        if (Bird.ClearanceSamples > 0)
            Row->SetNumberField(TEXT("minimum_sampled_floor_or_water_clearance_cm"), Bird.MinFloorClearance);
        Row->SetNumberField(TEXT("clearance_samples"), Bird.ClearanceSamples);
        Row->SetNumberField(TEXT("sweep_samples"), Bird.SweepSamples);
        Row->SetNumberField(TEXT("blocked_samples"), Bird.BlockedSamples);
        Row->SetNumberField(TEXT("culled_samples"), Bird.CulledSamples);
        Row->SetNumberField(TEXT("transform_samples"), Bird.TransformSamples);
        Row->SetNumberField(TEXT("glide_samples"), Bird.GlideSamples);
        Row->SetNumberField(TEXT("flap_samples"), Bird.FlapSamples);
        if (Bird.TransformSamples > 0)
        {
            Row->SetArrayField(TEXT("flap_min_max_shown_degrees"), TArray<TSharedPtr<FJsonValue>>{
                MakeShared<FJsonValueNumber>(Bird.MinShownFlapDegrees),
                MakeShared<FJsonValueNumber>(Bird.MaxShownFlapDegrees)});
            if (Player) Row->SetNumberField(TEXT("distance_to_view_cm"),
                FVector::Distance(Eye, Parts[Index * 3]->GetComponentLocation()));
        }
        Row->SetNumberField(TEXT("speed_cm_per_second"), Bird.Speed);
        Row->SetNumberField(TEXT("flap_degrees"), Bird.FlapDegrees);
        Row->SetNumberField(TEXT("bank_degrees"), Bird.BankDegrees);
        Row->SetStringField(TEXT("last_blocking_actor"), Bird.LastBlockingActor);
        TArray<TSharedPtr<FJsonValue>> Transforms;
        for (int32 Part = 0; Part < 3; ++Part)
        {
            const auto* Component = Parts[Index * 3 + Part].Get();
            const FTransform Transform = Component->GetComponentTransform();
            const FQuat Q = Transform.GetRotation();
            auto PartRow = MakeShared<FJsonObject>();
            PartRow->SetStringField(TEXT("component"), Component->GetName());
            PartRow->SetField(TEXT("position_cm"), JsonPoint(Transform.GetLocation()));
            PartRow->SetArrayField(TEXT("quaternion_xyzw"), TArray<TSharedPtr<FJsonValue>>{
                MakeShared<FJsonValueNumber>(Q.X), MakeShared<FJsonValueNumber>(Q.Y),
                MakeShared<FJsonValueNumber>(Q.Z), MakeShared<FJsonValueNumber>(Q.W)});
            if (Part > 0)
                PartRow->SetField(TEXT("outer_wingtip_cm"), JsonPoint(Transform.TransformPosition(
                    FVector(-18, Part == 1 ? -63 : 63, 1.2))));
            Transforms.Add(MakeShared<FJsonValueObject>(PartRow));
        }
        Row->SetArrayField(TEXT("parts"), Transforms);
        Rows.Add(MakeShared<FJsonValueObject>(Row));
    }
    Root->SetArrayField(TEXT("birds"), Rows);
    FString Text;
    FJsonSerializer::Serialize(Root, TJsonWriterFactory<>::Create(&Text));
    return Text;
}
