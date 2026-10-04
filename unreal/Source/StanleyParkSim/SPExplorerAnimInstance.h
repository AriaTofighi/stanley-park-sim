#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "SPExplorerAnimInstance.generated.h"

class UAnimSequence;
struct FSPExplorerAnimProxy;

// Native, phase-aligned locomotion blending for the original explorer clips.
// The clips stay referenced here so both cooking and garbage collection see them.
UCLASS()
class STANLEYPARKSIM_API USPExplorerAnimInstance : public UAnimInstance
{
    GENERATED_BODY()
public:
    USPExplorerAnimInstance();

protected:
    virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
    virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy) override;

private:
    friend struct FSPExplorerAnimProxy;
    UPROPERTY() TObjectPtr<UAnimSequence> Idle;
    UPROPERTY() TObjectPtr<UAnimSequence> Walk;
    UPROPERTY() TObjectPtr<UAnimSequence> Run;
    UPROPERTY() TObjectPtr<UAnimSequence> Air;
};
