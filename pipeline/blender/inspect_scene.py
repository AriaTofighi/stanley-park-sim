"""Read the open document before authoring a separate project scene."""
import bpy

result = {
    "version": bpy.app.version_string,
    "filepath": bpy.data.filepath,
    "scenes": [{"name": s.name, "object_count": len(s.objects)} for s in bpy.data.scenes],
    "objects": [{"name": o.name, "type": o.type} for o in bpy.context.scene.objects],
    "areas": [a.type for a in bpy.context.screen.areas],
}
