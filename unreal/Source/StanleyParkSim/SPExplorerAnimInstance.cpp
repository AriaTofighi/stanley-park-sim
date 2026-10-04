#include "SPExplorerAnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimNodeBase.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimationPoseData.h"
#include "AnimationRuntime.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "UObject/ConstructorHelpers.h"

struct FSPExplorerAnimProxy final : FAnimInstanceProxy
{
    explicit FSPExplorerAnimProxy(UAnimInstance* Instance) : FAnimInstanceProxy(Instance) {}

    // Actor state is read only on the game thread. Update and Evaluate use this
    // snapshot, so no character or movement component is touched by a worker.
    virtual void PreUpdate(UAnimInstance* Instance, float DeltaSeconds) override
    {
        FAnimInstanceProxy::PreUpdate(Instance, DeltaSeconds);
        const USPExplorerAnimInstance* Explorer = CastChecked<USPExplorerAnimInstance>(Instance);
        Idle = Explorer->Idle; Walk = Explorer->Walk; Run = Explorer->Run; Air = Explorer->Air;
        const ACharacter* Character = Cast<ACharacter>(Instance->TryGetPawnOwner());
        Speed = Character ? float(Character->GetVelocity().Size2D()) : 0.f;
        bAirborne = Character && Character->GetCharacterMovement()->IsFalling();
    }

    virtual void Update(float DeltaSeconds) override
    {
        const float Delta = FMath::Max(0.f, DeltaSeconds);
        // Smooth weights remain continuous when an input reverses mid-transition.
        const float GroundAlpha = 1.f - FMath::Exp(-Delta / .12f);
        const float AirAlpha = 1.f - FMath::Exp(-Delta / (bAirborne ? .07f : .10f));
        const float TargetMove = FMath::Clamp((Speed - 5.f) / 75.f, 0.f, 1.f);
        const float TargetRun = FMath::Clamp((Speed - 260.f) / 340.f, 0.f, 1.f);
        MoveWeight = FMath::Lerp(MoveWeight, TargetMove, GroundAlpha);
        RunWeight = FMath::Lerp(RunWeight, TargetRun, GroundAlpha);
        AirWeight = FMath::Lerp(AirWeight, bAirborne ? 1.f : 0.f, AirAlpha);

        const float WalkLength = Walk ? FMath::Max(Walk->GetPlayLength(), .01f) : 1.f;
        const float RunLength = Run ? FMath::Max(Run->GetPlayLength(), .01f) : 1.f;
        const float WalkCycles = FMath::Clamp(Speed / 260.f, .35f, 1.4f) / WalkLength;
        const float RunCycles = FMath::Clamp(Speed / 600.f, .35f, 1.4f) / RunLength;
        // Walk and run have the same foot-strike phase in their authored clips.
        // One shared cycle prevents a leg swap when the player presses Shift.
        if (Speed > 5.f)
            MovePhase = FMath::Fmod(MovePhase + Delta * FMath::Lerp(WalkCycles, RunCycles, RunWeight), 1.f);
        IdleTime = Advance(IdleTime, Delta, Idle);
        AirTime = bAirborne ? Advance(AirTime, Delta, Air) : 0.f;
    }

    virtual bool Evaluate(FPoseContext& Output) override
    {
        Sample(Idle, IdleTime, Output);
        if (MoveWeight > KINDA_SMALL_NUMBER && (Walk || Run))
        {
            FPoseContext Locomotion(Output);
            Sample(Walk ? Walk : Run, MovePhase * (Walk ? Walk : Run)->GetPlayLength(), Locomotion);
            if (Walk && Run && RunWeight > KINDA_SMALL_NUMBER)
            {
                FPoseContext Running(Output);
                Sample(Run, MovePhase * Run->GetPlayLength(), Running);
                BlendInto(Locomotion, Running, RunWeight);
            }
            BlendInto(Output, Locomotion, MoveWeight);
        }
        if (Air && AirWeight > KINDA_SMALL_NUMBER)
        {
            FPoseContext Airborne(Output);
            Sample(Air, AirTime, Airborne);
            BlendInto(Output, Airborne, AirWeight);
        }
        return true;
    }

private:
    UAnimSequence* Idle = nullptr;
    UAnimSequence* Walk = nullptr;
    UAnimSequence* Run = nullptr;
    UAnimSequence* Air = nullptr;
    float Speed = 0.f, MoveWeight = 0.f, RunWeight = 0.f, AirWeight = 0.f;
    float MovePhase = 0.f, IdleTime = 0.f, AirTime = 0.f;
    bool bAirborne = false;

    static float Advance(float Time, float Delta, const UAnimSequence* Clip)
    {
        return Clip && Clip->GetPlayLength() > 0.f ? FMath::Fmod(Time + Delta, Clip->GetPlayLength()) : 0.f;
    }

    static void Sample(UAnimSequence* Clip, float Time, FPoseContext& Output)
    {
        Output.ResetToRefPose();
        if (!Clip) return;
        FAnimationPoseData PoseData(Output);
        Clip->GetAnimationPose(PoseData, FAnimExtractContext(double(Time), false));
    }

    static void BlendInto(FPoseContext& Base, FPoseContext& Other, float OtherWeight)
    {
        FAnimationPoseData BaseData(Base);
        const FAnimationPoseData OtherData(Other);
        FAnimationRuntime::BlendTwoPosesTogetherInPlace(BaseData, OtherData, 1.f - OtherWeight);
    }
};

USPExplorerAnimInstance::USPExplorerAnimInstance()
{
    static ConstructorHelpers::FObjectFinder<UAnimSequence> IdleAsset(TEXT("/Game/StanleyPark/Explorer/A_Explorer_Idle.A_Explorer_Idle"));
    static ConstructorHelpers::FObjectFinder<UAnimSequence> WalkAsset(TEXT("/Game/StanleyPark/Explorer/A_Explorer_Walk.A_Explorer_Walk"));
    static ConstructorHelpers::FObjectFinder<UAnimSequence> RunAsset(TEXT("/Game/StanleyPark/Explorer/A_Explorer_Run.A_Explorer_Run"));
    static ConstructorHelpers::FObjectFinder<UAnimSequence> AirAsset(TEXT("/Game/StanleyPark/Explorer/A_Explorer_Jump.A_Explorer_Jump"));
    Idle = IdleAsset.Object; Walk = WalkAsset.Object; Run = RunAsset.Object; Air = AirAsset.Object;
}

FAnimInstanceProxy* USPExplorerAnimInstance::CreateAnimInstanceProxy()
{
    return new FSPExplorerAnimProxy(this);
}

void USPExplorerAnimInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy* Proxy)
{
    delete static_cast<FSPExplorerAnimProxy*>(Proxy);
}
