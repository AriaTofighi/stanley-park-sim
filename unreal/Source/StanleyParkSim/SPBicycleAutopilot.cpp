#include "SPBicycleAutopilot.h"
#include "SPBicyclePawn.h"
#include "SPWorldDirector.h"
#include "SPRouteData.h"
#include "Algo/BinarySearch.h"

namespace
{
    FVector ContactPoint(const ASPBicyclePawn& Bicycle)
    {
        return Bicycle.GetActorLocation()-FVector(0,0,76);
    }

    // Project only near the previous route position. At crossings and folded
    // gate paths, a global nearest point can skip an entire part of the route.
    double Nearby(const FSPRoute& Route, const FVector& Position, double Previous,
        double Behind, double Ahead, double& Squared)
    {
        Squared = TNumericLimits<double>::Max();
        double Best = Previous;
        for (int32 Wrap = Route.bClosed ? -1 : 0; Wrap <= (Route.bClosed ? 1 : 0); ++Wrap)
        {
            const double Centre = Previous+Wrap*Route.Length;
            const double Low = FMath::Max(0.,Centre-Behind);
            const double High = FMath::Min(Route.Length,Centre+Ahead);
            if (High < Low) continue;
            const int32 First = FMath::Max(1,Algo::LowerBound(Route.Chainage,Low));
            for (int32 Index = First; Index < Route.Points.Num() && Route.Chainage[Index-1] <= High; ++Index)
            {
                const FVector Delta = Route.Points[Index]-Route.Points[Index-1];
                const double Length = Route.Chainage[Index]-Route.Chainage[Index-1];
                if (Length <= UE_DOUBLE_SMALL_NUMBER) continue;
                const double MinAlpha = FMath::Clamp((Low-Route.Chainage[Index-1])/Length,0.,1.);
                const double MaxAlpha = FMath::Clamp((High-Route.Chainage[Index-1])/Length,0.,1.);
                const double Alpha = FMath::Clamp(FVector::DotProduct(Position-Route.Points[Index-1],Delta)
                    /Delta.SizeSquared(),MinAlpha,MaxAlpha);
                const double Error = FVector::DistSquared(Position,Route.Points[Index-1]+Delta*Alpha);
                if (Error < Squared)
                {
                    Squared = Error;
                    Best = Route.Chainage[Index-1]+Length*Alpha;
                }
            }
        }
        return Best;
    }
}

bool FSPBicycleAutopilot::Start(const ASPBicyclePawn& Bicycle, ASPWorldDirector* World)
{
    Stop();
    const FSPRoute* Route = World ? World->GetData().FindRoute(TEXT("main_circuit")) : nullptr;
    if (!Route || Route->Length <= 0)
    { Failure = TEXT("Autopilot needs the Seawall ride route."); return false; }
    double Squared = 0;
    MainAlong = Route->FindNearest(ContactPoint(Bicycle),Squared);
    if (Squared > FMath::Square(600.0))
    { Failure = TEXT("Move near the Seawall ride, then press P for autopilot."); return false; }
    Director = World;
    bActive = true;
    return true;
}

void FSPBicycleAutopilot::Stop()
{
    bActive = false;
    Director.Reset();
    GuideIndex = CompletedGuide = INDEX_NONE;
    GuideAlong = StoppedTime = 0;
    Failure.Empty();
}

void FSPBicycleAutopilot::StopWithReason(const FString& Reason)
{
    Stop();
    Failure = Reason;
}

FSPAutopilotInputs FSPBicycleAutopilot::Update(const ASPBicyclePawn& Bicycle, double Step, bool bBoost)
{
    FSPAutopilotInputs Inputs;
    ASPWorldDirector* World = Director.Get();
    const FSPRoute* Main = World ? World->GetData().FindRoute(TEXT("main_circuit")) : nullptr;
    if (!bActive || !Main) { Stop(); return Inputs; }
    const FSPWorldData& Data = World->GetData();
    const FVector Contact = ContactPoint(Bicycle);
    double Squared = 0;
    const FSPWalkZone* Gate = nullptr;
    if (GuideIndex != INDEX_NONE)
    {
        Gate = &Data.WalkZones[GuideIndex];
        GuideAlong = Nearby(Gate->Guide,Contact,GuideAlong,30,150,Squared);
        // Keep main progress ordered while taking the physical zigzag guide.
        MainAlong = FMath::Lerp(Gate->GuideStart,Gate->GuideEnd,GuideAlong/Gate->Guide.Length);
        if (GuideAlong >= Gate->Guide.Length-15 && FVector::Dist2D(Contact,Gate->Guide.Points.Last()) < 50)
        {
            MainAlong = Gate->GuideEnd;
            CompletedGuide = GuideIndex;
            GuideIndex = INDEX_NONE;
            Gate = nullptr;
        }
    }
    else
    {
        MainAlong = Nearby(*Main,Contact,MainAlong,300,3000,Squared);
        for (int32 Index = 0; Index < Data.WalkZones.Num(); ++Index)
        {
            const FSPWalkZone& Zone = Data.WalkZones[Index];
            if (Index == CompletedGuide || Zone.Guide.Length <= 0
                || MainAlong < Zone.GuideStart-60 || MainAlong > Zone.GuideEnd) continue;
            GuideIndex = Index;
            Gate = &Zone;
            GuideAlong = Zone.Guide.FindNearest(Contact,Squared);
            break;
        }
    }
    if (Squared > FMath::Square(1200.0))
    { StopWithReason(TEXT("Autopilot stopped away from the route. Press R to return to the ride.")); return Inputs; }
    for (const FSPWalkZone& Zone : Data.WalkZones)
        Inputs.bWalking |= MainAlong >= Zone.Start-700 && MainAlong <= Zone.End+100;
    Inputs.bWalking |= Gate != nullptr;
    if (Inputs.bWalking != Bicycle.IsWalking()) { Inputs.Brake = 1; return Inputs; }

    const double SpeedCm = FMath::Abs(Bicycle.GetSpeedKmh())/.036;
    const double LookAhead = Gate ? 15. : Bicycle.IsWalking() ? 180. : FMath::Clamp(200.+SpeedCm*.6,250.,1000.);
    FVector Target = Main->Sample(MainAlong+LookAhead);
    if (Gate)
    {
        const double Along = GuideAlong+LookAhead;
        Target = Along <= Gate->Guide.Length ? Gate->Guide.Sample(Along)
            : Main->Sample(Gate->GuideEnd+Along-Gate->Guide.Length);
    }
    const double Angle = FMath::DegreesToRadians(FMath::FindDeltaAngleDegrees(
        Bicycle.GetActorRotation().Yaw,(Target-Contact).Rotation().Yaw));
    const double TargetDistance = FMath::Max(15.,FVector::Dist2D(Contact,Target));
    const double SteeringDegrees = FMath::RadiansToDegrees(FMath::Atan(220.*FMath::Sin(Angle)/TargetDistance));
    Inputs.Steer = Bicycle.IsWalking() ? FMath::Clamp(Angle*4.,-1.,1.)
        : FMath::Clamp(SteeringDegrees/SteeringRange(SpeedCm),-1.,1.);

    double TargetKmh = Bicycle.IsWalking() ? (Gate ? 1.0 : 4.5)
        : FMath::Min(bBoost ? 80.0 : 32.0,double(Bicycle.GetRideTuning().Get(ESPRideSetting::TopSpeed)));
    if (bBoost && !Bicycle.IsWalking()) TargetKmh = 80;
    if (!Bicycle.IsWalking())
    {
        // Look farther ahead than the steering target so braking starts before
        // a bend. Bound lateral acceleration and the pawn's 65 degree yaw rate.
        FVector Previous;
        Main->Sample(MainAlong,&Previous);
        double PreviousDistance = 0;
        double Curvature = 0;
        for (double Distance : {400.,800.,1600.,3200.,6400.})
        {
            FVector Direction;
            Main->Sample(MainAlong+Distance,&Direction);
            const double Bend = FMath::Abs(FMath::DegreesToRadians(FMath::FindDeltaAngleDegrees(
                Previous.Rotation().Yaw,Direction.Rotation().Yaw)));
            Curvature = FMath::Max(Curvature,Bend/(Distance-PreviousDistance));
            Previous = Direction;
            PreviousDistance = Distance;
        }
        if (Curvature > .00001)
        {
            const double CornerSpeed = FMath::Min(FMath::Sqrt(180./Curvature),FMath::DegreesToRadians(55.)/Curvature);
            TargetKmh = FMath::Min(TargetKmh,FMath::Max(4.,CornerSpeed*.036));
        }
        if (FMath::Abs(SteeringDegrees) > SteeringRange(SpeedCm)*.9) TargetKmh = FMath::Min(TargetKmh,10.);
        if (FMath::Abs(Angle) > FMath::DegreesToRadians(60.)) TargetKmh = FMath::Min(TargetKmh,4.);
        for (const FSPWalkZone& Zone : Data.WalkZones)
        {
            const double UntilWalking = Zone.Start-700-MainAlong;
            if (UntilWalking > 0 && UntilWalking < 6000)
                TargetKmh = FMath::Min(TargetKmh,FMath::Sqrt(2.*250.*FMath::Max(0.,UntilWalking-150.))*.036);
        }
    }
    const bool bTurnAtGate = Gate && FMath::Abs(Angle) > FMath::DegreesToRadians(20.);
    Inputs.Pedal = !bTurnAtGate && Bicycle.GetSpeedKmh() < TargetKmh ? 1 : 0;
    Inputs.Brake = bTurnAtGate || Bicycle.GetSpeedKmh() > TargetKmh+(Gate ? .08 : .6) ? 1 : 0;
    StoppedTime = Inputs.Pedal > 0 && SpeedCm < 5 ? StoppedTime+Step : 0;
    if (StoppedTime > 3)
    { StopWithReason(TEXT("Autopilot stopped at an obstacle. Hold Q to back away, or press R.")); return {}; }
    return Inputs;
}
