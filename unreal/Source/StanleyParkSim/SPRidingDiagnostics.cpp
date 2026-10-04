#include "SPRidingDiagnostics.h"
#include "SPBicyclePawn.h"
#include "SPGraphicsSettings.h"
#include "SPWorldDirector.h"
#include "EngineUtils.h"
#include "ProfilingDebugging/CpuProfilerTrace.h"
#include "DynamicRHI.h"
#include "RenderTimer.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "UnrealClient.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformMemory.h"
#include "Dom/JsonObject.h"
#include "HAL/FileManager.h"
#include "Misc/DateTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Serialization/JsonSerializer.h"

namespace
{
    // These options select the existing bounded F9 scenario. They never start
    // gameplay or a diagnostic, and are ignored outside the separate M2 map.
    TAutoConsoleVariable<float> CVarSeawallReviewStart(TEXT("sp.SeawallReview.StartMetres"), -1.f,
        TEXT("M2 F9 initial route station. Negative uses the normal spawn."));
    TAutoConsoleVariable<int32> CVarSeawallReviewRecord(TEXT("sp.SeawallReview.Record"), 0,
        TEXT("Record the M2 F9 viewport. Recording timings are not a benchmark."));
}

FSPRidingDiagnostics::~FSPRidingDiagnostics()
{
    // EndPlay may remove the last world tick. Preserve the frozen ride result
    // and report any unrendered frame or unfinished image write as incomplete.
    Capture.Stop();
    if (PendingResult.IsValid()) SavePendingResult();
}

bool FSPRidingDiagnostics::Start(ASPBicyclePawn& Pawn, bool bFullCircuit)
{
    if (IsActive()) return false;
    // The complete circuit is validated only with this movement profile.
    // A restricted steering range can fail to follow its tight bends. Reject
    // unsupported tuning before fixture placement; never rewrite preferences.
    if (bFullCircuit && !Pawn.GetRideTuning().HasRoamMovementDefaults())
    {
        Label = TEXT("F10 needs Roam defaults: 40 km/h, 3.5 acceleration, 6 braking, 28° steering. Select Roam defaults in F1.");
        UE_LOG(LogTemp, Warning, TEXT("SP_RIDE_CHECK: %s"), *Label);
        return false;
    }
    TRACE_CPUPROFILER_EVENT_SCOPE(SP_RideCheckStart);
    const double SetupStart = FPlatformTime::Seconds();
    Data = FSPWorldData();
    for (TActorIterator<ASPWorldDirector> It(Pawn.GetWorld()); It; ++It)
    {
        if (!It->GetData().Routes.IsEmpty()) { Data = It->GetData(); break; }
    }
    // Reuse the already loaded runtime graph. Reading and parsing the packaged
    // JSON on the game thread adds avoidable work to the first ride frame.
    if (!Data.FindRoute(TEXT("main_circuit")))
    {
        Label = TEXT("Ride check cannot start: world data is missing.");
        return false;
    }
    const bool bSeawallMap = Pawn.GetWorld()->GetMapName().EndsWith(TEXT("StanleyParkSeawall"));
    const float ReviewStart = CVarSeawallReviewStart.GetValueOnGameThread();
    if (!bFullCircuit && bSeawallMap && ReviewStart >= 0)
    {
        const FSPRoute* Route = Data.FindRoute(TEXT("main_circuit"));
        if (!FMath::IsFinite(ReviewStart) || ReviewStart * 100 >= Route->Length)
        { Label = TEXT("The M2 review station is outside the route."); return false; }
        FVector Tangent;
        Data.Spawn = Route->Sample(ReviewStart * 100, &Tangent);
        Data.SpawnYaw = Tangent.Rotation().Yaw;
        Data.ReviewStartMetres = ReviewStart;
    }
    // This option selects a scenario only. Start still requires the F9 UI
    // action; neither loading the map nor passing a command line starts it.
    bGateCheck = !bFullCircuit && FParse::Param(FCommandLine::Get(), TEXT("SPGateCheck"));
    FString JoinId;
    bJoinCheck = !bFullCircuit && FParse::Value(FCommandLine::Get(), TEXT("SPJoinCheck="), JoinId);
    if (bJoinCheck)
    {
        if (bGateCheck || FParse::Param(FCommandLine::Get(), TEXT("SPFastRideCheck")))
        { Label = TEXT("Choose only one F9 scenario."); return false; }
        if (!JoinCheck.Load(Data, JoinId, Label)) return false;
    }
    GateCheckIndex = INDEX_NONE;
    GateCheckEnd = 0;
    if (bGateCheck)
    {
        const double StartCm = Data.ReviewStartMetres * 100;
        for (int32 Index = 0; Index < Data.WalkZones.Num(); ++Index)
        {
            const FSPWalkZone& Zone = Data.WalkZones[Index];
            if (Zone.Guide.Length > 0 && StartCm < Zone.GuideStart - 25.
                && StartCm >= FMath::Max(0., Zone.Start - 10000.))
            { GateCheckIndex = Index; GateCheckEnd = Zone.End + 250.; break; }
        }
        if (GateCheckIndex == INDEX_NONE || GateCheckEnd >= Data.FindRoute(TEXT("main_circuit"))->Length)
        {
            Label = TEXT("Gate check needs SPStartMetres before a guide, within 100m of its walk zone.");
            return false;
        }
    }
    if (bFullCircuit)
    {
        // A local review start must never count as a complete-lap start.
        FVector Tangent;
        const FVector Start = Data.FindRoute(TEXT("main_circuit"))->Sample(0, &Tangent);
        Pawn.PlaceOnRoute(Start, Tangent.Rotation().Yaw);
    }
    else if (bJoinCheck)
    {
        FVector Tangent;
        const FVector Start = JoinCheck.Guide.Sample(0, &Tangent);
        // Explicit fixture setup. All movement after this placement uses the
        // existing inputs, support checks and collision sweeps.
        Pawn.PlaceOnRoute(Start, Tangent.Rotation().Yaw);
    }
    else Pawn.PlaceOnRoute(Data.Spawn, Data.SpawnYaw);
    FrameTimes.Reset();
    EngineTimings.Reset();
    Samples.Reset();
    Elapsed = NextSample = MaximumSpeed = MaximumRouteError = BrakeEndSpeed = 0;
    StartDistance = Pawn.GetDistanceMetres();
    StartDropped = Pawn.GetDroppedSimulationTime();
    FramesWithoutSurface = 0;
    StartSurfaceMisses = Pawn.GetSurfaceMissCount();
    bCircuit = bFullCircuit;
    bFastRoamCheck = !bCircuit && !bGateCheck && !bJoinCheck && FParse::Param(FCommandLine::Get(), TEXT("SPFastRideCheck"));
    bFinishing = false;
    Progress = PreviousChainage = LastAdvanceTime = NextProgressReport = 0;
    if (bGateCheck) PreviousChainage = Data.ReviewStartMetres * 100;
    LastAdvanceProgress = 0;
    PassedGates = WalkingTransitions = 0;
    JoinCheckpoints = 0;
    GateTraversals.Reset();
    GateTraversals.SetNum(Data.WalkZones.Num());
    Failure.Empty();
    bActive = true;
    bCaptureRequested = bCircuit || bGateCheck || bJoinCheck || FParse::Param(FCommandLine::Get(), TEXT("SPRecordRide"))
        || (bSeawallMap && CVarSeawallReviewRecord.GetValueOnGameThread() != 0);
    if (bCaptureRequested) Capture.Start();
    Label = bCircuit ? TEXT("Full circuit check. F10 cancels.") : bJoinCheck
        ? TEXT("Local junction contact check. F9 cancels.") : bGateCheck
        ? TEXT("Local gate check. F9 cancels.") : bFastRoamCheck
        ? TEXT("Fast roam check: pedal, coast, brake. F9 cancels.")
        : TEXT("Ride check: pedal, speed-limited coast, brake. F9 cancels.");
    SetupMilliseconds = (FPlatformTime::Seconds() - SetupStart) * 1000;
    return true;
}

void FSPRidingDiagnostics::Inputs(ASPBicyclePawn& Pawn, float& Pedal, float& Brake, float& Steer)
{
    bCircuitRidingFeedback = false;
    if (PendingResult.IsValid())
    {
        Pedal = Steer = 0;
        Brake = 1;
        return;
    }
    if (!bActive) return;
    const FSPRoute& Route = bJoinCheck ? JoinCheck.Guide : *Data.FindRoute(TEXT("main_circuit"));
    double Squared;
    const FVector Contact = Pawn.GetActorLocation() - FVector(0, 0, 72);
    const double Distance = Route.FindNearest(Contact, Squared);
    const FSPWalkZone* GateZone = !bJoinCheck && Pawn.IsWalking() ? Data.FindWalkingGuideZone(Distance) : nullptr;
    const FSPRoute* GateGuide = GateZone ? &GateZone->Guide : nullptr;
    const double LookAhead = bJoinCheck ? 90. : GateGuide ? 15. : Pawn.IsWalking() ? 180.
        : FMath::Clamp(Pawn.GetSpeedKmh() * 26., 250., bFastRoamCheck ? 1200. : 400.);
    FVector Target = Route.Sample(Distance + LookAhead);
    if (GateGuide)
    {
        double GuideSquared;
        const double GuideTarget = GateGuide->FindNearest(Contact, GuideSquared) + LookAhead;
        // Continue onto the main route when the look-ahead leaves the guide.
        // Clamping at the endpoint can stop progress or turn the walker back.
        Target = GuideTarget <= GateGuide->Length ? GateGuide->Sample(GuideTarget)
            : Route.Sample(GateZone->GuideEnd + GuideTarget - GateGuide->Length);
    }
    const double Heading = (Target - Contact).Rotation().Yaw;
    const double Angle = FMath::DegreesToRadians(FMath::FindDeltaAngleDegrees(Pawn.GetActorRotation().Yaw, Heading));
    const double SteeringDegrees = FMath::RadiansToDegrees(FMath::Atan(220 * FMath::Sin(Angle) / LookAhead));
    Steer = Pawn.IsWalking() ? FMath::Clamp(Angle * (GateGuide ? 4. : 2.), -1., 1.)
        : FMath::Clamp(SteeringDegrees / Pawn.GetRideTuning().Get(ESPRideSetting::Steering), -1., 1.);
    if (bJoinCheck)
    {
        Pedal = !bFinishing && Pawn.GetSpeedKmh() < 6. ? 1 : 0;
        Brake = bFinishing || Pawn.GetSpeedKmh() > 6.3 ? 1 : 0;
        return;
    }
    if (bCircuit || bGateCheck)
    {
        bool bWalk = false;
        for (const auto& Zone : Data.WalkZones)
            bWalk |= Distance >= Zone.Start - 700 && Distance <= Zone.End + 100;
        if (bWalk != Pawn.IsWalking())
        {
            Pedal = 0; Brake = 1;
            if (Pawn.GetSpeedKmh() < .1 && Pawn.SetWalking(bWalk)) ++WalkingTransitions;
            return;
        }
        FVector Ahead, Later;
        Route.Sample(Distance + 300, &Ahead);
        Route.Sample(Distance + 800, &Later);
        const double Bend = FMath::Abs(FMath::FindDeltaAngleDegrees(Ahead.Rotation().Yaw, Later.Rotation().Yaw));
        // Small look-ahead and low speed preserve the geometric clearance at
        // maze turns. All movement still uses the normal controller and sweep.
        const bool bTurnAtGate = GateGuide && FMath::Abs(Angle) > FMath::DegreesToRadians(20.);
        const double TargetSpeed = bTurnAtGate ? 0 : GateGuide ? 1.0
            : Pawn.IsWalking() ? 4.5 : FMath::Clamp(14.3 - Bend * .15, 5.0, 14.3);
        Pedal = !bFinishing && Pawn.GetSpeedKmh() < TargetSpeed ? 1 : 0;
        Brake = bFinishing || bTurnAtGate || Pawn.GetSpeedKmh() > TargetSpeed + (GateGuide ? .08 : .7) ? 1 : 0;
        if (bCircuit && !Pawn.IsWalking())
        {
            bCircuitRidingFeedback = true;
            CircuitRidingTarget = TargetSpeed;
            CircuitRidingBrakeThreshold = TargetSpeed + .7;
        }
        return;
    }
    Pedal = Elapsed < 15 && (bFastRoamCheck || Pawn.GetSpeedKmh() < 12) ? 1.f : 0.f;
    Brake = Elapsed >= 21 ? 1.f : 0.f;
    if (!bFastRoamCheck) RefreshCircuitRidingSpeedInputs(Pawn, Pedal, Brake);
}

void FSPRidingDiagnostics::RefreshCircuitRidingSpeedInputs(const ASPBicyclePawn& Pawn, float& Pedal, float& Brake) const
{
    if (!bActive || Pawn.IsWalking()) return;
    if (!bCircuit && !bGateCheck && !bJoinCheck && !bFastRoamCheck)
    {
        // Coasting still cuts pedal, but a downhill grade must not defeat the
        // short scenario's existing 15.1 km/h acceptance limit. Re-evaluate
        // the ordinary brake input on every movement step, including catch-up.
        Pedal = Elapsed < 15 && Pawn.GetSpeedKmh() < 12 ? 1 : 0;
        Brake = Elapsed >= 21 || Pawn.GetSpeedKmh() > 12.7 ? 1 : 0;
        return;
    }
    if (!bCircuit || !bCircuitRidingFeedback) return;
    // Reuse this world tick's target, but read speed before every fixed step.
    // A long tick must not hold full pedal through all eight retained steps.
    // Walk transitions and maze walking retain their existing driver.
    Pedal = !bFinishing && Pawn.GetSpeedKmh() < CircuitRidingTarget ? 1 : 0;
    Brake = bFinishing || Pawn.GetSpeedKmh() > CircuitRidingBrakeThreshold ? 1 : 0;
}

void FSPRidingDiagnostics::RecordGateTraversals(const ASPBicyclePawn& Pawn,
    const FVector& Contact, double MainChainage)
{
    // A 50 m main-route checkpoint does not prove passage through a maze.
    // Observe every frame, including walking mode, guide entry/exit and the
    // planar tracking budget derived from the gate's capsule-clearance check.
    constexpr double EndpointTolerance = 25.; // cm; guides start/end away from the frames.
    for (int32 Index = 0; Index < Data.WalkZones.Num(); ++Index)
    {
        const FSPWalkZone& Zone = Data.WalkZones[Index];
        if (bGateCheck && Index != GateCheckIndex) continue;
        FSPGateTraversal& Traversal = GateTraversals[Index];
        if (Zone.Guide.Length <= 0 || Traversal.bPassed || MainChainage < Zone.GuideStart) continue;
        if (MainChainage > Zone.GuideEnd)
        {
            if (!Traversal.bEntered || Traversal.LastDistance < Zone.Guide.Length - EndpointTolerance)
            { Failure = TEXT("Physical gate guide was skipped or left before its end: ") + Zone.Name; return; }
            Traversal.bPassed = true;
            continue;
        }
        double Squared;
        const double GuideDistance = Zone.Guide.FindNearest(Contact, Squared);
        const double PlanarOffset = FVector::Dist2D(Contact, Zone.Guide.Sample(GuideDistance));
        Traversal.MaximumPlanarOffset = FMath::Max(Traversal.MaximumPlanarOffset, PlanarOffset);
        ++Traversal.ObservedFrames;
        if (!Pawn.IsWalking())
        { Failure = TEXT("Physical gate entered while riding: ") + Zone.Name; return; }
        if (PlanarOffset > Zone.GuideTrackingLimit)
        { Failure = TEXT("Physical gate tracking exceeded its geometric clearance budget: ") + Zone.Name; return; }
        if (!Traversal.bEntered)
        {
            if (GuideDistance > EndpointTolerance)
            { Failure = TEXT("Physical gate guide entry was skipped: ") + Zone.Name; return; }
            Traversal.bEntered = true;
            Traversal.FirstDistance = GuideDistance;
        }
        else if (GuideDistance - Traversal.LastDistance > 100. || GuideDistance - Traversal.LastDistance < -25.)
        { Failure = TEXT("Physical gate projection jumped or reversed: ") + Zone.Name; return; }
        Traversal.LastDistance = GuideDistance;
    }
}

void FSPRidingDiagnostics::Record(ASPBicyclePawn& Pawn, float DeltaSeconds)
{
    if (PendingResult.IsValid())
    {
        // Do not change elapsed time, contact counters, samples, or coverage
        // after the terminal snapshot. These ticks only drain real captures.
        if (Capture.PollStop()) SavePendingResult();
        return;
    }
    if (!bActive) return;
    Elapsed += DeltaSeconds;
    if (bCaptureRequested) Capture.Tick(Elapsed);
    FrameTimes.Add(DeltaSeconds * 1000);
    // These are the same unsmoothed engine counters used by stat unit.
    // They describe previous frames and must not be summed as serial work.
    FSPFrameTiming Timing;
    Timing.Frame = DeltaSeconds * 1000;
    Timing.Game = FPlatformTime::ToMilliseconds(GGameThreadTime);
    Timing.Render = FPlatformTime::ToMilliseconds(GRenderThreadTime);
    Timing.Rhi = FPlatformTime::ToMilliseconds(GRHIThreadTime);
    const uint32 GPUCycles = RHIGetGPUFrameCycles();
    if (GPUCycles > 0) Timing.Gpu = FPlatformTime::ToMilliseconds(GPUCycles);
    EngineTimings.Add(Timing);
    MaximumSpeed = FMath::Max(MaximumSpeed, Pawn.GetSpeedKmh());
    if (!Pawn.HasSurface()) ++FramesWithoutSurface;
    if (!bCircuit && !bGateCheck && !bJoinCheck && Elapsed >= 27) BrakeEndSpeed = FMath::Max(BrakeEndSpeed, Pawn.GetSpeedKmh());
    double Squared;
    const FSPRoute& Main = *Data.FindRoute(TEXT("main_circuit"));
    const FSPRoute& Route = bJoinCheck ? JoinCheck.Guide : Main;
    const FVector Contact = Pawn.GetActorLocation() - FVector(0, 0, 72);
    const double Chainage = Route.FindNearest(Contact, Squared);
    double MainSquared = Squared;
    const double MainChainage = bJoinCheck ? Main.FindNearest(Contact, MainSquared) : Chainage;
    const double PavementOffset = FMath::Sqrt(MainSquared) / 100;
    const FSPWalkZone* GateZone = bJoinCheck ? nullptr : Data.FindWalkingGuideZone(Chainage);
    const FSPRoute* GateGuide = GateZone ? &GateZone->Guide : nullptr;
    double GatePlanarOffset = 0;
    if (GateGuide)
    {
        double GuideSquared;
        const double GuideDistance = GateGuide->FindNearest(Contact, GuideSquared);
        GatePlanarOffset = FVector::Dist2D(Contact, GateGuide->Sample(GuideDistance));
        Squared = GuideSquared;
    }
    const double Offset = FMath::Sqrt(Squared) / 100;
    MaximumRouteError = FMath::Max(MaximumRouteError, Offset);
    if (Elapsed >= NextSample)
    {
        auto Row = MakeShared<FJsonObject>();
        const FVector Position = Pawn.GetActorLocation();
        Row->SetNumberField(TEXT("seconds"), Elapsed);
        Row->SetNumberField(TEXT("north_cm"), Position.X);
        Row->SetNumberField(TEXT("east_cm"), Position.Y);
        Row->SetNumberField(TEXT("height_cm"), Position.Z);
        Row->SetNumberField(TEXT("speed_kmh"), Pawn.GetSpeedKmh());
        Row->SetNumberField(TEXT("route_distance_m"), Offset);
        Row->SetNumberField(TEXT("pavement_centre_distance_m"), PavementOffset);
        Row->SetBoolField(TEXT("physical_gate_guide"), GateGuide != nullptr);
        Row->SetStringField(TEXT("route_distance_reference"), bJoinCheck ? JoinCheck.Id : GateGuide ? GateGuide->Id : TEXT("main_circuit"));
        if (GateZone)
        {
            Row->SetNumberField(TEXT("gate_planar_distance_m"), GatePlanarOffset / 100);
            Row->SetNumberField(TEXT("gate_tracking_limit_m"), GateZone->GuideTrackingLimit / 100);
        }
        Row->SetBoolField(TEXT("has_surface"), Pawn.HasSurface());
        Row->SetNumberField(TEXT("surface_misses"), double(Pawn.GetSurfaceMissCount() - StartSurfaceMisses));
        Row->SetBoolField(TEXT("walking"), Pawn.IsWalking());
        Row->SetNumberField(TEXT("chainage_m"), MainChainage / 100);
        if (bJoinCheck) Row->SetNumberField(TEXT("join_guide_distance_m"), Chainage / 100);
        Samples.Add(MakeShared<FJsonValueObject>(Row));
        NextSample += bCircuit ? 1. : .1;
    }
    if (bCircuit || bGateCheck || bJoinCheck)
    {
        if (!bJoinCheck) RecordGateTraversals(Pawn, Contact, Chainage);
        double Advance = Chainage - PreviousChainage;
        if (Route.bClosed && Advance < -Route.Length * .5) Advance += Route.Length;
        if (Route.bClosed && Advance > Route.Length * .5) Advance -= Route.Length;
        // A large discontinuity must fail; it is never accepted as route coverage.
        if (FMath::Abs(Advance) > (bJoinCheck ? 100. : 1000.)) Failure = TEXT("Route projection exceeded the scenario step limit.");
        else Progress += Advance;
        PreviousChainage = Chainage;
        // Accumulate progress across frames. At 1 km/h a high frame rate can
        // advance less than 1 mm each frame without being stalled.
        if (Progress > LastAdvanceProgress + 1.)
        {
            LastAdvanceTime = Elapsed;
            LastAdvanceProgress = Progress;
        }
        if (bCircuit && Progress >= (PassedGates + 1) * 5000.) ++PassedGates;
        if (bJoinCheck)
            while (Progress >= (JoinCheckpoints + 1) * 100.) ++JoinCheckpoints;
        bFinishing = bJoinCheck ? Progress >= JoinCheck.FinishDistance
            : bGateCheck ? Chainage >= GateCheckEnd : Progress >= Route.Length;
        if (Elapsed - LastAdvanceTime > 30) Failure = TEXT("No forward progress for 30 seconds.");
        if (Offset > (bJoinCheck ? .35 : 2.0)) Failure = TEXT("Bicycle left the scenario route check envelope.");
        if (bJoinCheck && Pawn.IsWalking()) Failure = TEXT("Junction contact check must remain in riding mode.");
        if (FramesWithoutSurface > 3) Failure = TEXT("Ground contact was lost.");
        if (Pawn.GetSurfaceMissCount() > StartSurfaceMisses) Failure = TEXT("A fixed movement step could not find a valid support surface.");
        if (Elapsed > 5400) Failure = TEXT("Circuit check exceeded 90 minutes.");
        if (bGateCheck && Elapsed > 600) Failure = TEXT("Local gate check exceeded 10 minutes.");
        if (bJoinCheck && Elapsed > 120) Failure = TEXT("Junction contact check exceeded 2 minutes.");
        if (Elapsed >= NextProgressReport)
        {
            Label = bJoinCheck ? FString::Printf(TEXT("Join %s: %.1f m. F9 cancels."), *JoinCheck.Id, Progress / 100.)
                : bGateCheck ? FString::Printf(TEXT("Gate check %.1f m. F9 cancels."), Progress / 100.)
                : FString::Printf(TEXT("Circuit check %.2f / %.2f km. F10 cancels."), Progress / 100000., Route.Length / 100000.);
            UE_LOG(LogTemp, Display, TEXT("SP_CIRCUIT_PROGRESS: %.1fm %.1fs gates=%d"), Progress / 100, Elapsed, PassedGates);
            NextProgressReport += 30;
        }
        if (!Failure.IsEmpty()) Stop(Pawn, false);
        else if (bFinishing && Pawn.GetSpeedKmh() < .1) { BrakeEndSpeed = Pawn.GetSpeedKmh(); Stop(Pawn, true); }
    }
    else if (Elapsed >= 32) Stop(Pawn, true);
}

void FSPRidingDiagnostics::Stop(const ASPBicyclePawn& Pawn, bool bCompleted)
{
    if (!bActive) return;
    bActive = false;
    auto Root = MakeShared<FJsonObject>();
    Root->SetBoolField(TEXT("video_capture_requested"), bCaptureRequested);
    Root->SetStringField(TEXT("scenario"), bCircuit ? TEXT("full-circuit-normal-inputs-physical-gates-v4")
        : bJoinCheck ? TEXT("local-junction-contact-normal-inputs-v1")
        : bGateCheck ? TEXT("local-physical-gate-normal-inputs-v1")
        : bFastRoamCheck ? TEXT("fast-roam-pedal15-coast6-brake11-v1")
        : Data.ReviewStartMetres > 0 ? TEXT("route-section-pedal15-limited-coast6-brake11-v2")
        : TEXT("entrance-pedal15-limited-coast6-brake11-v6"));
    if (!bCircuit && !bGateCheck && !bJoinCheck && !bFastRoamCheck)
        Root->SetStringField(TEXT("speed_control"), TEXT("Pedal below 12 km/h for 15 s; coast for 6 s; brake for 11 s. Brake above 12.7 km/h throughout. Feedback uses each fixed movement step. Acceptance remains 15.1 km/h."));
    if (bCircuit)
        Root->SetStringField(TEXT("required_movement_profile"), TEXT("Roam defaults: 40 km/h, 3.5 m/s2 acceleration, 6 m/s2 braking, 28 degrees steering. Camera preferences may differ."));
    Root->SetNumberField(TEXT("scenario_start_chainage_m"), bCircuit ? 0 : bJoinCheck ? JoinCheck.MainChainage / 100 : Data.ReviewStartMetres);
    if (bJoinCheck)
    {
        Root->SetStringField(TEXT("join_check_id"), JoinCheck.Id);
        Root->SetStringField(TEXT("join_branch_id"), JoinCheck.BranchId);
        Root->SetStringField(TEXT("join_direction"), JoinCheck.Direction);
        Root->SetStringField(TEXT("join_fixture_file_sha1"), JoinCheck.FixtureFileHash);
        Root->SetStringField(TEXT("join_source_world_sha1"), JoinCheck.SourceWorldHash);
        Root->SetNumberField(TEXT("join_finish_distance_m"), JoinCheck.FinishDistance / 100);
        Root->SetNumberField(TEXT("passed_1m_join_checkpoints"), JoinCheckpoints);
        const FVector Fixture = JoinCheck.Guide.Points[0];
        auto Setup = MakeShared<FJsonObject>();
        Setup->SetNumberField(TEXT("north_cm"), Fixture.X);
        Setup->SetNumberField(TEXT("east_cm"), Fixture.Y);
        Setup->SetNumberField(TEXT("contact_height_cm"), Fixture.Z);
        Root->SetObjectField(TEXT("join_initial_fixture_contact"), Setup);
        Root->SetStringField(TEXT("join_fixture_setup"), TEXT("One placement before capture. Subsequent crossing uses normal inputs, support traces and collision; no branch permission changes."));
        Root->SetStringField(TEXT("join_collision_scope"), TEXT("Existing riding capsule and ground support. Walking bicycle probes are inactive in this riding scenario."));
        Root->SetNumberField(TEXT("required_1m_join_checkpoints"), FMath::FloorToInt(JoinCheck.FinishDistance / 100.));
    }
    if (bGateCheck) Root->SetNumberField(TEXT("scenario_end_chainage_m"), GateCheckEnd / 100);
    Root->SetNumberField(TEXT("scenario_setup_ms"), SetupMilliseconds);
    Root->SetStringField(TEXT("scope"), bCircuit ? TEXT("Ordered full circuit with normal controller inputs. Does not establish source accuracy.")
        : bJoinCheck ? TEXT("First 12 m of a source-supported branch crossing in the recorded direction. Not a complete main-route turning manoeuvre, full-branch or graph acceptance.")
        : bGateCheck ? TEXT("One physical gate, walking transitions and stop with normal controller inputs. Not full route or performance acceptance.")
        : TEXT("Short controller check only. Not full route or performance acceptance."));
    Root->SetStringField(TEXT("failure"), Failure);
    Root->SetNumberField(TEXT("circuit_progress_m"), Progress / 100);
    Root->SetNumberField(TEXT("passed_50m_gates"), PassedGates);
    Root->SetNumberField(TEXT("walking_transitions"), WalkingTransitions);
    const FSPRoute* Circuit = Data.FindRoute(TEXT("main_circuit"));
    const int32 RequiredGates = bCircuit && Circuit ? FMath::FloorToInt(Circuit->Length / 5000.) : 0;
    const int32 RequiredWalkingTransitions = bJoinCheck ? 0 : bGateCheck ? 2 : Data.WalkZones.Num() * 2;
    int32 RequiredPhysicalGates = 0, PassedPhysicalGates = 0;
    TArray<TSharedPtr<FJsonValue>> GateRows;
    for (int32 Index = 0; Index < Data.WalkZones.Num(); ++Index)
    {
        const FSPWalkZone& Zone = Data.WalkZones[Index];
        if (bJoinCheck) continue;
        if (bGateCheck && Index != GateCheckIndex) continue;
        if (Zone.Guide.Length <= 0) continue;
        const FSPGateTraversal& Traversal = GateTraversals[Index];
        ++RequiredPhysicalGates;
        if (Traversal.bPassed) ++PassedPhysicalGates;
        auto Row = MakeShared<FJsonObject>();
        Row->SetStringField(TEXT("id"), Zone.Guide.Id);
        Row->SetBoolField(TEXT("entry_observed"), Traversal.bEntered);
        Row->SetBoolField(TEXT("passage_pass"), Traversal.bPassed);
        Row->SetNumberField(TEXT("observed_frames"), Traversal.ObservedFrames);
        Row->SetNumberField(TEXT("first_guide_distance_m"), Traversal.FirstDistance / 100);
        Row->SetNumberField(TEXT("last_guide_distance_m"), Traversal.LastDistance / 100);
        Row->SetNumberField(TEXT("guide_length_m"), Zone.Guide.Length / 100);
        Row->SetNumberField(TEXT("maximum_planar_distance_m"), Traversal.MaximumPlanarOffset / 100);
        Row->SetNumberField(TEXT("tracking_limit_m"), Zone.GuideTrackingLimit / 100);
        Row->SetNumberField(TEXT("geometric_contact_margin_m"), Zone.GuideClearanceMargin / 100);
        GateRows.Add(MakeShared<FJsonValueObject>(Row));
    }
    const bool bPhysicalGatesPassed = (bCircuit || bGateCheck) && RequiredPhysicalGates > 0
        && PassedPhysicalGates == RequiredPhysicalGates;
    const bool bCoveragePassed = bJoinCheck
        ? Progress >= JoinCheck.FinishDistance && JoinCheckpoints >= FMath::FloorToInt(JoinCheck.FinishDistance / 100.)
        : bGateCheck
        ? Progress >= GateCheckEnd - Data.ReviewStartMetres * 100
            && WalkingTransitions == RequiredWalkingTransitions && bPhysicalGatesPassed
        : !bCircuit || (Circuit && Progress >= Circuit->Length
            && PassedGates >= RequiredGates && WalkingTransitions == RequiredWalkingTransitions && bPhysicalGatesPassed);
    Root->SetNumberField(TEXT("required_50m_gates"), RequiredGates);
    Root->SetNumberField(TEXT("required_walking_transitions"), RequiredWalkingTransitions);
    Root->SetNumberField(TEXT("required_physical_gates"), RequiredPhysicalGates);
    Root->SetNumberField(TEXT("passed_physical_gates"), PassedPhysicalGates);
    Root->SetBoolField(TEXT("physical_gate_coverage_pass"), bPhysicalGatesPassed);
    Root->SetArrayField(TEXT("physical_gate_traversals"), GateRows);
    Root->SetStringField(TEXT("physical_gate_scope"), bJoinCheck ? TEXT("No physical gate coverage in this junction scenario.")
        : TEXT("Observed guide coverage, 32 cm rider capsule and centred walking-bicycle sphere probes. Approximate contact model; dimensions remain estimated and video review is required."));
    Root->SetStringField(TEXT("walking_bicycle_contact_model"), TEXT("walking-bike-spheres-v1; 41 probes; manifests/walking-bike-contact.json"));
    Root->SetBoolField(TEXT("ordered_coverage_pass"), bCoveragePassed);
    Root->SetBoolField(TEXT("completed"), bCompleted);
    Root->SetNumberField(TEXT("seconds"), Elapsed);
    Root->SetNumberField(TEXT("distance_m"), Pawn.GetDistanceMetres() - StartDistance);
    Root->SetNumberField(TEXT("maximum_speed_kmh"), MaximumSpeed);
    Root->SetNumberField(TEXT("maximum_route_distance_m"), MaximumRouteError);
    Root->SetNumberField(TEXT("frames_without_surface"), FramesWithoutSurface);
    Root->SetNumberField(TEXT("surface_misses"), double(Pawn.GetSurfaceMissCount() - StartSurfaceMisses));
    Root->SetNumberField(TEXT("brake_end_speed_kmh"), BrakeEndSpeed);
    Root->SetNumberField(TEXT("blocking_contacts"), Pawn.GetBlockingContactCount());
    Root->SetNumberField(TEXT("dropped_simulation_seconds"), Pawn.GetDroppedSimulationTime() - StartDropped);
    const double SpeedCap = Pawn.GetRideTuning().Get(ESPRideSetting::TopSpeed);
    const double RequiredSpeed = bJoinCheck ? 2. : bGateCheck ? .1 : bFastRoamCheck ? SpeedCap * .9 : 8.;
    const double AcceptedSpeed = bJoinCheck ? 8. : bFastRoamCheck ? SpeedCap + .1 : 15.1;
    const bool bControllerPassed = bCompleted && Failure.IsEmpty() && bCoveragePassed && MaximumSpeed >= RequiredSpeed && MaximumSpeed <= AcceptedSpeed
        && FramesWithoutSurface == 0 && Pawn.GetSurfaceMissCount() == StartSurfaceMisses
        && MaximumRouteError <= (bJoinCheck ? .35 : 1.25) && BrakeEndSpeed < .1
        && Pawn.GetBlockingContactCount() == 0;
    Root->SetBoolField(TEXT("controller_and_coverage_pass"), bControllerPassed);
    TArray<TSharedPtr<FJsonValue>> Frames;
    for (float Time : FrameTimes) Frames.Add(MakeShared<FJsonValueNumber>(Time));
    Root->SetArrayField(TEXT("observed_frame_ms"), Frames);
    TArray<TSharedPtr<FJsonValue>> TimingRows;
    TimingRows.Reserve(EngineTimings.Num());
    for (const FSPFrameTiming& Timing : EngineTimings)
    {
        auto Row = MakeShared<FJsonObject>();
        Row->SetNumberField(TEXT("game_ms"), Timing.Game);
        Row->SetNumberField(TEXT("render_ms"), Timing.Render);
        Row->SetNumberField(TEXT("rhi_ms"), Timing.Rhi);
        if (Timing.Gpu >= 0) Row->SetNumberField(TEXT("gpu_ms"), Timing.Gpu);
        else Row->SetField(TEXT("gpu_ms"), MakeShared<FJsonValueNull>());
        TimingRows.Add(MakeShared<FJsonValueObject>(Row));
    }
    Root->SetArrayField(TEXT("engine_timings_ms"), TimingRows);
    Root->SetStringField(TEXT("timing_method"), TEXT("Previous-frame unsmoothed stat-unit CPU/RHI/GPU counters. Threads overlap. Zero GPU counter is unavailable, not free."));
    auto Settings = MakeShared<FJsonObject>();
    Settings->SetStringField(TEXT("requested_graphics_preset"), SPGraphics::Name(SPGraphics::SavedPreset()));
    for (const TCHAR* Name : { TEXT("r.ScreenPercentage"), TEXT("r.VSync"), TEXT("t.MaxFPS"),
        TEXT("r.AntiAliasingMethod"), TEXT("r.DynamicGlobalIlluminationMethod"), TEXT("r.RayTracing"),
        TEXT("r.PSOPrecaching"), TEXT("r.Shadow.Virtual.Enable"), TEXT("r.Shadow.DistanceScale"),
        TEXT("r.Shadow.MaxResolution"), TEXT("sg.ViewDistanceQuality"), TEXT("sg.ShadowQuality"),
        TEXT("sg.TextureQuality"), TEXT("sg.EffectsQuality"), TEXT("sg.FoliageQuality") })
    {
        if (IConsoleVariable* Value = IConsoleManager::Get().FindConsoleVariable(Name))
            Settings->SetNumberField(Name, Value->GetFloat());
    }
    if (GEngine && GEngine->GameViewport && GEngine->GameViewport->Viewport)
    {
        const FIntPoint Size = GEngine->GameViewport->Viewport->GetSizeXY();
        Settings->SetNumberField(TEXT("width"), Size.X);
        Settings->SetNumberField(TEXT("height"), Size.Y);
    }
    Root->SetObjectField(TEXT("render_settings"), Settings);
    auto RideSettings = MakeShared<FJsonObject>();
    for (uint8 Index = 0; Index < static_cast<uint8>(ESPRideSetting::Count); ++Index)
    {
        const auto Setting = static_cast<ESPRideSetting>(Index);
        RideSettings->SetNumberField(GetRideSettingDefinition(Setting).Key, Pawn.GetRideTuning().Get(Setting));
    }
    Root->SetObjectField(TEXT("ride_settings"), RideSettings);
    Root->SetStringField(TEXT("ride_settings_scope"), TEXT("Active tuning used by this run. Opening settings cancels an active run before any change."));
    const auto Memory = FPlatformMemory::GetStats();
    Root->SetNumberField(TEXT("process_working_set_bytes"), double(Memory.UsedPhysical));
    Root->SetNumberField(TEXT("process_peak_working_set_bytes"), double(Memory.PeakUsedPhysical));
    Root->SetArrayField(TEXT("samples"), Samples);
    const FString Directory = FPaths::ProjectSavedDir() / TEXT("Diagnostics");
    IFileManager::Get().MakeDirectory(*Directory, true);
    PendingFilename = Directory / (TEXT("ride-") + FDateTime::UtcNow().ToString(TEXT("%Y%m%d-%H%M%S")) + TEXT(".json"));
    PendingResult = Root;
    if (bCaptureRequested)
    {
        Capture.BeginStop();
        Label = TEXT("Ride check stopped; saving final viewport frames.");
        // Do not poll here: this tick's last capture request needs a present.
    }
    else SavePendingResult();
}

void FSPRidingDiagnostics::SavePendingResult()
{
    if (!PendingResult.IsValid()) return;
    auto Root = PendingResult;
    const bool bCompleted = Root->GetBoolField(TEXT("completed"));
    const bool bEvidenceComplete = !bCaptureRequested || Capture.Passed();
    const bool bPassed = Root->GetBoolField(TEXT("controller_and_coverage_pass")) && bEvidenceComplete;
    if (bCaptureRequested)
    {
        Root->SetStringField(TEXT("video_capture_directory"), Capture.GetDirectory());
        Root->SetBoolField(TEXT("video_capture_complete"), Capture.Passed());
        Root->SetStringField(TEXT("video_capture_error"), Capture.GetError());
    }
    Root->SetBoolField(TEXT("requested_evidence_complete"), bEvidenceComplete);
    if (bCompleted && !bEvidenceComplete && Root->GetStringField(TEXT("failure")).IsEmpty())
        Root->SetStringField(TEXT("failure"), TEXT("Requested video evidence is incomplete. See the capture manifest."));
    Root->SetBoolField(bCircuit ? TEXT("full_circuit_check_pass") : bJoinCheck ? TEXT("junction_contact_check_pass")
        : bGateCheck ? TEXT("gate_section_check_pass")
        : TEXT("short_controller_check_pass"), bPassed);
    FString Text;
    FJsonSerializer::Serialize(Root, TJsonWriterFactory<>::Create(&Text));
    const bool bSaved = FFileHelper::SaveStringToFile(Text, *PendingFilename);
    Label = !bSaved ? TEXT("Ride check: evidence save failed.") : !bCompleted
        ? (Root->GetStringField(TEXT("failure")).IsEmpty() ? TEXT("Ride check cancelled; partial trace saved.") : TEXT("Ride check failed; partial trace saved.")) : bPassed
        ? TEXT("Ride check passed; trace saved.") : TEXT("Ride check failed; trace saved.");
    UE_LOG(LogTemp, Display, TEXT("SP_RIDE_CHECK: %s %s"), *Label, *PendingFilename);
    PendingResult.Reset();
    PendingFilename.Empty();
}
