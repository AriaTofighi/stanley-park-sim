#include "SPWaterSafety.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
    struct FWaterEdge
    {
        FVector2D A;
        FVector2D B;
    };

    struct FWaterRegion
    {
        FString Name;
        double Height = 0;
        FVector2D Minimum = FVector2D(TNumericLimits<double>::Max());
        FVector2D Maximum = FVector2D(-TNumericLimits<double>::Max());
        TArray<FWaterEdge> Edges;
        TMap<int32, TArray<int32>> Bands;

        bool Contains(const FVector2D& Point, double BandHeight) const
        {
            if (Point.X < Minimum.X || Point.X > Maximum.X || Point.Y < Minimum.Y || Point.Y > Maximum.Y) return false;
            const TArray<int32>* Candidates = Bands.Find(FMath::FloorToInt(Point.Y / BandHeight));
            if (!Candidates) return false;
            bool bInside = false;
            for (int32 Index : *Candidates)
            {
                const FWaterEdge& Edge = Edges[Index];
                // Include the exact boundary. A 0.01 cm tolerance only guards
                // floating-point comparisons; it does not expand the shoreline.
                const FVector2D Delta = Edge.B - Edge.A;
                const double Alpha = FMath::Clamp(FVector2D::DotProduct(Point - Edge.A, Delta) / Delta.SizeSquared(), 0., 1.);
                if ((Point - (Edge.A + Delta * Alpha)).SizeSquared() <= .0001) return true;
                if ((Edge.A.Y > Point.Y) != (Edge.B.Y > Point.Y))
                {
                    const double CrossingX = Edge.A.X + (Point.Y - Edge.A.Y) * Delta.X / Delta.Y;
                    if (CrossingX > Point.X) bInside = !bInside;
                }
            }
            // The same parity rule handles the exterior and all island holes.
            return bInside;
        }
    };

    struct FWaterIndex
    {
        bool bReady = false;
        double BandHeight = 0;
        TArray<FWaterRegion> Regions;

        bool Load()
        {
            FString Text;
            const FString Path = FPaths::ProjectContentDir() / TEXT("WorldData/water-safety.json");
            if (!FFileHelper::LoadFileToString(Text, *Path)) return false;
            TSharedPtr<FJsonObject> Root;
            if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid()) return false;
            double Schema = 0;
            FString Coordinates;
            const TArray<TSharedPtr<FJsonValue>>* RegionValues = nullptr;
            if (!Root->TryGetNumberField(TEXT("schema_version"), Schema) || Schema != 1
                || !Root->TryGetStringField(TEXT("coordinate_contract"), Coordinates)
                || Coordinates != TEXT("unreal_north_east_up_cm")
                || !Root->TryGetNumberField(TEXT("band_height_cm"), BandHeight)
                || !FMath::IsFinite(BandHeight) || BandHeight < 100 || BandHeight > 100000
                || !Root->TryGetArrayField(TEXT("regions"), RegionValues)
                || RegionValues->IsEmpty() || RegionValues->Num() > 64) return false;
            int32 TotalPoints = 0;
            for (const TSharedPtr<FJsonValue>& Value : *RegionValues)
            {
                if (!Value.IsValid() || Value->Type != EJson::Object) return false;
                const TSharedPtr<FJsonObject> Object = Value->AsObject();
                FWaterRegion Region;
                const TArray<TSharedPtr<FJsonValue>>* Rings = nullptr;
                if (!Object->TryGetStringField(TEXT("name"), Region.Name) || Region.Name.IsEmpty()
                    || !Object->TryGetNumberField(TEXT("surface_z_cm"), Region.Height)
                    || !FMath::IsFinite(Region.Height) || FMath::Abs(Region.Height) > 100000
                    || !Object->TryGetArrayField(TEXT("rings"), Rings) || Rings->IsEmpty() || Rings->Num() > 1024) return false;
                for (const TSharedPtr<FJsonValue>& RingValue : *Rings)
                {
                    const TArray<TSharedPtr<FJsonValue>>* Points = nullptr;
                    if (!RingValue.IsValid() || !RingValue->TryGetArray(Points) || Points->Num() < 3) return false;
                    TotalPoints += Points->Num();
                    if (TotalPoints > 100000) return false;
                    TArray<FVector2D> Ring;
                    Ring.Reserve(Points->Num());
                    for (const TSharedPtr<FJsonValue>& PointValue : *Points)
                    {
                        const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
                        double X = 0, Y = 0;
                        if (!PointValue.IsValid() || !PointValue->TryGetArray(Values) || Values->Num() != 2
                            || !(*Values)[0]->TryGetNumber(X) || !(*Values)[1]->TryGetNumber(Y)
                            || !FMath::IsFinite(X) || !FMath::IsFinite(Y) || FMath::Abs(X) >= 10000000 || FMath::Abs(Y) >= 10000000) return false;
                        const FVector2D Point(X, Y);
                        Ring.Add(Point);
                        Region.Minimum.X = FMath::Min(Region.Minimum.X, X); Region.Minimum.Y = FMath::Min(Region.Minimum.Y, Y);
                        Region.Maximum.X = FMath::Max(Region.Maximum.X, X); Region.Maximum.Y = FMath::Max(Region.Maximum.Y, Y);
                    }
                    for (int32 Index = 0; Index < Ring.Num(); ++Index)
                    {
                        const FVector2D A = Ring[Index], B = Ring[(Index + 1) % Ring.Num()];
                        if ((B - A).SizeSquared() <= UE_DOUBLE_SMALL_NUMBER) continue;
                        const int32 FirstBand = FMath::FloorToInt(FMath::Min(A.Y, B.Y) / BandHeight);
                        const int32 LastBand = FMath::FloorToInt(FMath::Max(A.Y, B.Y) / BandHeight);
                        if (LastBand - FirstBand > 4096) return false;
                        const int32 EdgeIndex = Region.Edges.Add({A, B});
                        for (int32 Band = FirstBand; Band <= LastBand; ++Band) Region.Bands.FindOrAdd(Band).Add(EdgeIndex);
                    }
                }
                if (Region.Edges.Num() < 3) return false;
                Regions.Add(MoveTemp(Region));
            }
            return true;
        }

        FWaterIndex()
        {
            bReady = Load();
            if (!bReady)
            {
                Regions.Reset();
                UE_LOG(LogTemp, Error, TEXT("SP_WATER_SAFETY: missing or invalid WorldData/water-safety.json; water recovery data is unavailable."));
            }
            else UE_LOG(LogTemp, Display, TEXT("SP_WATER_SAFETY: loaded %d water regions with cached %.0f cm edge bands."), Regions.Num(), BandHeight);
        }
    };

    const FWaterIndex& WaterIndex()
    {
        static const FWaterIndex Index;
        return Index;
    }
}

bool SPWaterSafety::Initialize()
{
    return WaterIndex().bReady;
}

bool SPWaterSafety::GetSurfaceHeight(const FVector& WorldPosition, double& OutSurfaceZ)
{
    if (WorldPosition.ContainsNaN() || WorldPosition.GetAbsMax() >= 10000000) return false;
    const FWaterIndex& Index = WaterIndex();
    if (!Index.bReady) return false;
    bool bFound = false;
    double Height = -TNumericLimits<double>::Max();
    const FVector2D Point(WorldPosition.X, WorldPosition.Y);
    for (const FWaterRegion& Region : Index.Regions)
    {
        if (Region.Contains(Point, Index.BandHeight)) { Height = FMath::Max(Height, Region.Height); bFound = true; }
    }
    if (bFound) OutSurfaceZ = Height;
    return bFound;
}
