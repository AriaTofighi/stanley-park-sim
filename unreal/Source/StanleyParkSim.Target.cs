using UnrealBuildTool;

public class StanleyParkSimTarget : TargetRules
{
    public StanleyParkSimTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.V7;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_8;
        ExtraModuleNames.Add("StanleyParkSim");
    }
}
