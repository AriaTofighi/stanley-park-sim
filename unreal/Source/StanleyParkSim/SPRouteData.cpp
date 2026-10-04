#include "SPRouteData.h"
#include "Dom/JsonObject.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

void FSPRoute::BuildChainage()
{
    Chainage.Reset();
    Length = 0;
    for (int32 Index = 0; Index < Points.Num(); ++Index)
    {
        if (Index > 0) Length += FVector::Distance(Points[Index - 1], Points[Index]);
        Chainage.Add(Length);
    }
}

FVector FSPRoute::Sample(double Distance, FVector* Tangent) const
{
    if (Points.Num() < 2 || Length <= 0) return FVector::ZeroVector;
    if (bClosed) Distance = FMath::Fmod(FMath::Fmod(Distance, Length) + Length, Length);
    else Distance = FMath::Clamp(Distance, 0.0, Length);
    int32 Low = 1, High = Chainage.Num() - 1;
    while (Low < High)
    {
        const int32 Mid = (Low + High) / 2;
        if (Chainage[Mid] < Distance) Low = Mid + 1;
        else High = Mid;
    }
    const double SegmentLength = Chainage[Low] - Chainage[Low - 1];
    const FVector Delta = Points[Low] - Points[Low - 1];
    if (Tangent) *Tangent = Delta.GetSafeNormal();
    return FMath::Lerp(Points[Low - 1], Points[Low],
        SegmentLength > 0 ? (Distance - Chainage[Low - 1]) / SegmentLength : 0.0);
}

double FSPRoute::FindNearest(const FVector& Position, double& OutSquaredDistance) const
{
    OutSquaredDistance = TNumericLimits<double>::Max();
    double Best = 0;
    for (int32 Index = 1; Index < Points.Num(); ++Index)
    {
        const FVector Delta = Points[Index] - Points[Index - 1];
        const double Alpha = FMath::Clamp(FVector::DotProduct(Position - Points[Index - 1], Delta)
            / FMath::Max(Delta.SizeSquared(), 0.001), 0.0, 1.0);
        const double Squared = FVector::DistSquared(Position, Points[Index - 1] + Delta * Alpha);
        if (Squared < OutSquaredDistance)
        {
            OutSquaredDistance = Squared;
            Best = FMath::Lerp(Chainage[Index - 1], Chainage[Index], Alpha);
        }
    }
    return Best;
}

static bool ReadPoint(const TSharedPtr<FJsonValue>& Value, FVector& Point)
{
    const TArray<TSharedPtr<FJsonValue>>* Values;
    if (!Value.IsValid() || !Value->TryGetArray(Values) || Values->Num() != 3) return false;
    double X, Y, Z;
    if (!(*Values)[0]->TryGetNumber(X) || !(*Values)[1]->TryGetNumber(Y)
        || !(*Values)[2]->TryGetNumber(Z)) return false;
    Point = FVector(X, Y, Z);
    return !Point.ContainsNaN() && Point.GetAbsMax() < 10000000;
}

bool FSPWorldData::Load(FString& Error)
{
    FString Text;
    const FString Path = FPaths::ProjectContentDir() / TEXT("WorldData/world.json");
    if (!FFileHelper::LoadFileToString(Text, *Path))
    {
        Error = TEXT("World data is missing. Run the Blender export and Unreal import pipeline.");
        return false;
    }
    TSharedPtr<FJsonObject> Root;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid()
        || Root->GetIntegerField(TEXT("schema_version")) != 1
        || Root->GetStringField(TEXT("coordinate_contract")) != TEXT("unreal_north_east_up_cm"))
    {
        Error = TEXT("World data has an unsupported schema or coordinate system.");
        return false;
    }
    Root->TryGetStringField(TEXT("status"), Status);
    const TArray<TSharedPtr<FJsonValue>>* RouteValues;
    if (!Root->TryGetArrayField(TEXT("routes"), RouteValues))
    {
        Error = TEXT("World data has no routes.");
        return false;
    }
    Routes.Reset();
    for (const auto& Value : *RouteValues)
    {
        const auto Object = Value->AsObject();
        if (!Object.IsValid()) continue;
        FSPRoute Route;
        Route.Id = Object->GetStringField(TEXT("id"));
        Route.Name = Object->GetStringField(TEXT("name"));
        Object->TryGetStringField(TEXT("access_status"), Route.AccessStatus);
        Object->TryGetBoolField(TEXT("closed"), Route.bClosed);
        Object->TryGetBoolField(TEXT("cycling"), Route.bCycling);
        const TArray<TSharedPtr<FJsonValue>>* Points;
        if (!Object->TryGetArrayField(TEXT("points"), Points)) continue;
        for (const auto& PointValue : *Points)
        {
            FVector Point;
            if (!ReadPoint(PointValue, Point)) { Error = TEXT("Invalid route coordinate."); return false; }
            if (Route.Points.IsEmpty() || !Point.Equals(Route.Points.Last(), 0.01)) Route.Points.Add(Point);
        }
        Route.BuildChainage();
        if (Route.Points.Num() >= 2 && Route.Length > 0) Routes.Add(MoveTemp(Route));
    }
    if (Routes.IsEmpty()) { Error = TEXT("No valid routes in world data."); return false; }
    if (!ReadPoint(Root->TryGetField(TEXT("spawn")), Spawn))
    {
        Error = TEXT("Invalid player start."); return false;
    }
    Root->TryGetNumberField(TEXT("spawn_yaw"), SpawnYaw);
    ReviewStartMetres = 0;
#if !UE_BUILD_SHIPPING
    if (FParse::Value(FCommandLine::Get(), TEXT("SPStartMetres="), ReviewStartMetres))
    {
        const FSPRoute* Circuit = FindRoute(TEXT("main_circuit"));
        if (!Circuit || !FMath::IsFinite(ReviewStartMetres) || ReviewStartMetres < 0
            || ReviewStartMetres * 100 >= Circuit->Length)
        {
            Error = TEXT("Development start is outside the main circuit."); return false;
        }
        FVector Tangent;
        Spawn = Circuit->Sample(ReviewStartMetres * 100, &Tangent);
        SpawnYaw = Tangent.Rotation().Yaw;
        UE_LOG(LogTemp, Display, TEXT("SP_REVIEW_START: %.3f metres"), ReviewStartMetres);
    }
#endif
    WalkZones.Reset();
    const FSPRoute* MainCircuit = FindRoute(TEXT("main_circuit"));
    const TArray<TSharedPtr<FJsonValue>>* Zones;
    if (Root->TryGetArrayField(TEXT("walk_zones"), Zones))
    {
        for (const auto& Value : *Zones)
        {
            const auto Object = Value->AsObject();
            FSPWalkZone Zone;
            if (!Object.IsValid() || !Object->TryGetStringField(TEXT("name"), Zone.Name)
                || !Object->TryGetNumberField(TEXT("start_cm"), Zone.Start)
                || !Object->TryGetNumberField(TEXT("end_cm"), Zone.End)
                || !FMath::IsFinite(Zone.Start) || !FMath::IsFinite(Zone.End)
                || !MainCircuit || Zone.Start < 0 || Zone.End <= Zone.Start
                || Zone.End > MainCircuit->Length
                || (!WalkZones.IsEmpty() && Zone.Start <= WalkZones.Last().End))
            { Error = TEXT("Invalid, overlapping or unordered walking zone."); return false; }
            Object->TryGetStringField(TEXT("evidence"), Zone.Evidence);
            Object->TryGetBoolField(TEXT("survey_accepted"), Zone.bSurveyAccepted);
            const TArray<TSharedPtr<FJsonValue>>* GuidePoints;
            if (Object->TryGetArrayField(TEXT("guide_points"), GuidePoints))
            {
                double CapsuleRadius = 0;
                if (!Object->TryGetNumberField(TEXT("guide_start_cm"), Zone.GuideStart)
                    || !Object->TryGetNumberField(TEXT("guide_end_cm"), Zone.GuideEnd)
                    || !FMath::IsFinite(Zone.GuideStart) || !FMath::IsFinite(Zone.GuideEnd)
                    || Zone.GuideStart < Zone.Start || Zone.GuideEnd > Zone.End
                    || Zone.GuideEnd <= Zone.GuideStart)
                { Error = TEXT("Invalid gate guide limits."); return false; }
                if (!Object->TryGetStringField(TEXT("guide_id"), Zone.Guide.Id)
                    || Zone.Guide.Id.IsEmpty()
                    || !Object->TryGetNumberField(TEXT("guide_capsule_radius_cm"), CapsuleRadius)
                    || !Object->TryGetNumberField(TEXT("guide_clearance_margin_cm"), Zone.GuideClearanceMargin)
                    || !Object->TryGetNumberField(TEXT("guide_tracking_limit_cm"), Zone.GuideTrackingLimit)
                    || !FMath::IsFinite(CapsuleRadius) || !FMath::IsFinite(Zone.GuideClearanceMargin)
                    || !FMath::IsFinite(Zone.GuideTrackingLimit) || FMath::Abs(CapsuleRadius - 32.) > .001
                    || Zone.GuideTrackingLimit <= 0
                    || Zone.GuideTrackingLimit > Zone.GuideClearanceMargin - 1.999)
                { Error = TEXT("Invalid gate clearance contract. Rebuild runtime route data."); return false; }
                Zone.Guide.Name = Zone.Name;
                for (const auto& PointValue : *GuidePoints)
                {
                    FVector Point;
                    if (!ReadPoint(PointValue, Point))
                    { Error = TEXT("Invalid gate guide coordinate."); return false; }
                    if (Zone.Guide.Points.IsEmpty() || !Point.Equals(Zone.Guide.Points.Last(), .01))
                        Zone.Guide.Points.Add(Point);
                }
                Zone.Guide.BuildChainage();
                if (Zone.Guide.Points.Num() < 2 || Zone.Guide.Length <= 0)
                { Error = TEXT("Empty gate guide."); return false; }
                if (FVector::Distance(Zone.Guide.Points[0], MainCircuit->Sample(Zone.GuideStart)) > 1.
                    || FVector::Distance(Zone.Guide.Points.Last(), MainCircuit->Sample(Zone.GuideEnd)) > 1.)
                { Error = TEXT("Gate guide does not meet the main route within 1 cm."); return false; }
            }
            WalkZones.Add(MoveTemp(Zone));
        }
    }
    return true;
}

const FSPRoute* FSPWorldData::FindRoute(const FString& Id) const
{
    return Routes.FindByPredicate([&](const FSPRoute& Route) { return Route.Id == Id; });
}

const FSPWalkZone* FSPWorldData::FindWalkingGuideZone(double MainChainage) const
{
    for (const FSPWalkZone& Zone : WalkZones)
        if (Zone.Guide.Length > 0 && MainChainage >= Zone.GuideStart
            && MainChainage <= Zone.GuideEnd)
            return &Zone;
    return nullptr;
}
