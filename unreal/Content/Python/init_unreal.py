"""Load the project's bounded authoring tools in editors with the MCP plugin."""
from pathlib import Path
import runpy
import unreal

root = Path(__file__).resolve().parents[3]
bootstrap = root / "pipeline/unreal/register_park_tools.py"
if bootstrap.is_file() and hasattr(unreal, "ToolsetDefinition"):
    runpy.run_path(str(bootstrap))
