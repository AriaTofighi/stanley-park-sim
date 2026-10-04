#pragma once

#include "CoreMinimal.h"

// The ocean uses the existing coastline mask, not the display plane that also
// extends below land. Lake footprints and all heights retain their source data.
namespace SPWaterSafety
{
    // Loads once per process. A failed load is logged and stays failed until
    // restart; callers must treat failure as unavailable safety data.
    bool Initialize();

    // Queries world north/east centimetres. Returns the highest surface at XY.
    // No region (or unavailable data) returns false and leaves OutSurfaceZ alone.
    // The caller supplies foot/support height and chooses its recovery margin.
    bool GetSurfaceHeight(const FVector& WorldPosition, double& OutSurfaceZ);
}
