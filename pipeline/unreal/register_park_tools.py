"""Load the bounded park toolset from the normal Unreal Python console."""
import sys
from pathlib import Path
import unreal
import toolset_registry

folder = str(Path(__file__).resolve().parent)
if folder not in sys.path:
    sys.path.insert(0, folder)
if "park_toolset" in sys.modules:
    toolset_registry.reload_module(sys.modules["park_toolset"])
else:
    import park_toolset
unreal.SystemLibrary.execute_console_command(None, "ModelContextProtocol.RefreshTools")
unreal.log("StanleyParkTools registered for the official Unreal MCP server")
