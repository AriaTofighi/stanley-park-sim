"""Start the installed local MCP bridge in the new seawall authoring file."""
from pathlib import Path
import bpy

expected = Path(__file__).resolve().parents[2] / "blender/StanleyPark_Seawall.blend"
if Path(bpy.data.filepath).resolve() != expected.resolve():
    raise RuntimeError("Open the separate seawall working file before starting this session")
outcome = bpy.ops.blmcp.server_start()
print("SP_SEAWALL_MCP_START", outcome)
