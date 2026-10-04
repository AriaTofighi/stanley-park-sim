#include "SPJoinCheck.h"
#include "Dom/JsonObject.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/SecureHash.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

static FString FileSha1(const FString& Path)
{
    TArray<uint8> Bytes;
    if (!FFileHelper::LoadFileToArray(Bytes, *Path)) return FString();
    FSHAHash Hash;
    FSHA1::HashBuffer(Bytes.GetData(), Bytes.Num(), Hash.Hash);
    return Hash.ToString();
}

static bool ReadJoinPoint(const TSharedPtr<FJsonValue>& Value, FVector& Point)
{
    const TArray<TSharedPtr<FJsonValue>>* Coordinates = nullptr;
    double X = 0, Y = 0, Z = 0;
    if (!Value.IsValid() || !Value->TryGetArray(Coordinates) || !Coordinates || Coordinates->Num()!=3
        || !(*Coordinates)[0]->TryGetNumber(X) || !(*Coordinates)[1]->TryGetNumber(Y)
        || !(*Coordinates)[2]->TryGetNumber(Z)
        || !FMath::IsFinite(X) || !FMath::IsFinite(Y) || !FMath::IsFinite(Z)) return false;
    Point = FVector(X,Y,Z);
    return Point.GetAbsMax()<10000000;
}

bool FSPJoinCheck::Load(const FSPWorldData& World, const FString& RequestedId, FString& Error)
{
    *this = FSPJoinCheck();
    const FString Directory = FPaths::ProjectContentDir()/TEXT("WorldData");
    const FString Path = Directory/TEXT("join_checks.json");
    FString Text;
    TSharedPtr<FJsonObject> Root;
    if (!FFileHelper::LoadFileToString(Text,*Path)
        || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Root) || !Root.IsValid()
        || Root->GetIntegerField(TEXT("schema_version"))!=1
        || Root->GetStringField(TEXT("coordinate_contract"))!=TEXT("unreal_north_east_up_cm"))
    { Error=TEXT("Missing or invalid join fixture data. Run build_join_check_fixtures.py."); return false; }
    Root->TryGetStringField(TEXT("source_world_sha1"),SourceWorldHash);
    if (SourceWorldHash.IsEmpty() || !SourceWorldHash.Equals(FileSha1(Directory/TEXT("world.json")),ESearchCase::IgnoreCase))
    { Error=TEXT("Join fixtures use different world data. Rebuild and package the fixtures."); return false; }
    FixtureFileHash=FileSha1(Path);
    const TArray<TSharedPtr<FJsonValue>>* Fixtures = nullptr;
    if (!Root->TryGetArrayField(TEXT("fixtures"),Fixtures) || !Fixtures)
    { Error=TEXT("Join fixture list is missing."); return false; }
    for (const auto& Value:*Fixtures)
    {
        const auto Object=Value->AsObject();
        if (!Object.IsValid() || Object->GetStringField(TEXT("id"))!=RequestedId) continue;
        Id=RequestedId;
        Object->TryGetStringField(TEXT("junction_id"),JunctionId);
        Object->TryGetStringField(TEXT("branch_id"),BranchId);
        Object->TryGetStringField(TEXT("direction"),Direction);
        FVector MainContact;
        const FSPRoute* Main=World.FindRoute(TEXT("main_circuit"));
        const TArray<TSharedPtr<FJsonValue>>* Points = nullptr;
        if (!Main || !World.FindRoute(BranchId) || JunctionId==TEXT("city_junction_041")
            || (Direction!=TEXT("out") && Direction!=TEXT("in"))
            || !Object->TryGetNumberField(TEXT("main_chainage_cm"),MainChainage)
            || !FMath::IsFinite(MainChainage) || MainChainage<0 || MainChainage>=Main->Length
            || !ReadJoinPoint(Object->TryGetField(TEXT("main_contact_cm")),MainContact)
            || FVector::Distance(Main->Sample(MainChainage),MainContact)>1.
            || !Object->TryGetNumberField(TEXT("finish_distance_cm"),FinishDistance)
            || !FMath::IsFinite(FinishDistance)
            || !Object->TryGetArrayField(TEXT("points_cm"),Points) || !Points)
        { Error=TEXT("Join fixture does not match its main route or branch."); return false; }
        Guide.Id=Id; Guide.Name=TEXT("Join contact check ")+Id; Guide.bCycling=true;
        for (const auto& PointValue:*Points)
        {
            FVector Point;
            if (!ReadJoinPoint(PointValue,Point))
            { Error=TEXT("Invalid join fixture coordinate."); return false; }
            if (Guide.Points.IsEmpty() || !Point.Equals(Guide.Points.Last(),.01)) Guide.Points.Add(Point);
        }
        Guide.BuildChainage();
        if (Guide.Points.Num()<2 || FinishDistance<1200. || FinishDistance>=Guide.Length)
        { Error=TEXT("Join fixture lacks its 12 m crossing or stopping allowance."); return false; }
        return true;
    }
    Error=TEXT("Unknown SPJoinCheck id. Use an ID from join_checks.json.");
    return false;
}
