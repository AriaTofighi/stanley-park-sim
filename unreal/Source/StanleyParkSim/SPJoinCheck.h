#pragma once

#include "SPRouteData.h"

// Development fixture data only. It does not change the route graph or world.
struct FSPJoinCheck
{
    FSPRoute Guide;
    FString Id, JunctionId, BranchId, Direction, SourceWorldHash, FixtureFileHash;
    double MainChainage = 0, FinishDistance = 0;
    bool Load(const FSPWorldData& World, const FString& RequestedId, FString& Error);
};
