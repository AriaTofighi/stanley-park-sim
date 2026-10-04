using UnrealBuildTool;

public class StanleyParkSim : ModuleRules
{
    public StanleyParkSim(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] {
            "Core", "CoreUObject", "Engine", "InputCore", "Json", "JsonUtilities"
        });
        PrivateDependencyModuleNames.AddRange(new[] {
            "RHI", "RenderCore", "MovieSceneCapture", "Slate", "SlateCore", "ImageWriteQueue", "ImageWrapper"
        });
    }
}
