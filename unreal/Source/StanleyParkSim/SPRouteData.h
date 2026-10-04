#pragma once

#include "CoreMinimal.h"

// Runtime coordinates are centimetres: +X north, +Y east, +Z up.
// This is the only runtime route representation. Conversion happens in the exporter.
struct FSPRoute
{
    FString Id;
    FString Name;
    FString AccessStatus;
    bool bClosed = false;
    bool bCycling = false;
    TArray<FVector> Points;
    TArray<double> Chainage;
    double Length = 0.0;

    void BuildChainage();
    FVector Sample(double Distance, FVector* Tangent = nullptr) const;
    double FindNearest(const FVector& Position, double& OutSquaredDistance) const;
};

struct FSPWalkZone
{
    FString Name;
    FString Evidence;
    double Start = 0, End = 0; // Main-circuit chainage, centimetres.
    double GuideStart = 0, GuideEnd = 0;
    double GuideClearanceMargin = 0, GuideTrackingLimit = 0; // Planar centimetres; 32 cm capsule only.
    FSPRoute Guide; // Optional physical gate path; does not move the pavement.
    bool bSurveyAccepted = false;
};

struct FSPWorldData
{
    TArray<FSPRoute> Routes;
    TArray<FSPWalkZone> WalkZones;
    FVector Spawn = FVector(0, 0, 500);
    double SpawnYaw = 0;
    double ReviewStartMetres = 0; // Development-only route inspection start.
    FString Status;
    bool Load(FString& Error);
    const FSPRoute* FindRoute(const FString& Id) const;
    const FSPWalkZone* FindWalkingGuideZone(double MainChainage) const;
};
