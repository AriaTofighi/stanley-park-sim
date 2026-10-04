"""Use fixed exposure and bounded shadows for the non-Nanite M1 blockout."""
import unreal

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
unreal.SystemLibrary.execute_console_command(None, "r.Shadow.Virtual.Enable 0")
for actor in actors.get_all_level_actors():
    if actor.get_actor_label() == "SP_Sun_FixedAfternoon":
        light = actor.light_component
        light.set_editor_property("dynamic_shadow_distance_movable_light", 20000.0)
        light.set_editor_property("dynamic_shadow_cascades", 4)
        light.set_editor_property("cascade_distribution_exponent", 3.0)
        light.set_editor_property("cascade_transition_fraction", 0.2)
        light.set_editor_property("shadow_distance_fadeout_fraction", 0.1)
exposure = next((a for a in actors.get_all_level_actors() if a.get_actor_label() == "SP_InspectionExposure"), None)
if exposure is None:
    exposure = actors.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0))
    exposure.set_actor_label("SP_InspectionExposure")
    exposure.tags = ["SP_Generated"]
exposure.set_editor_property("unbound", True)
settings = unreal.PostProcessSettings()
settings.set_editor_property("override_auto_exposure_bias", True)
settings.set_editor_property("auto_exposure_bias", -0.5)
settings.set_editor_property("override_auto_exposure_min_brightness", True)
settings.set_editor_property("override_auto_exposure_max_brightness", True)
settings.set_editor_property("auto_exposure_min_brightness", 1.0)
settings.set_editor_property("auto_exposure_max_brightness", 1.0)
exposure.set_editor_property("settings", settings)
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
