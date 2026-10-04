"""Set an editor overview of the actual imported park. Does not run gameplay."""
import unreal

unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(
    unreal.Vector(-280000, 160000, 240000), unreal.Rotator(pitch=-39, yaw=-31, roll=0))
unreal.log("Stanley Park overview: real editor scene, north/east/up centimetres.")
