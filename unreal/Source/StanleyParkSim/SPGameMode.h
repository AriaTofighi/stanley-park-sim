#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "SPGameMode.generated.h"

UCLASS()
class STANLEYPARKSIM_API ASPGameMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    ASPGameMode();
    virtual void StartPlay() override;
    virtual UClass* GetDefaultPawnClassForController_Implementation(AController* Controller) override;
    void ToggleExplorer();
};
