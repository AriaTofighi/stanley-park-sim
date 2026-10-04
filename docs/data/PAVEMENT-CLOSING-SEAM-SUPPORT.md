> Historical source note from the development baseline. See [current release notes](../release-notes.md) for the public release. File paths below are relative to the project root. Raw inspection media remain in the local archive.

# Closing seam support

The v25 Unreal surface check missed control 2000 at the exact closed-route cross-section. The 16 nearby rays hit the two pavement actors. The failed report remains in `evidence/unreal-surface-transfer-v25-failure.json`. Do not move that control or change the transfer tolerance.

`pipeline/blender/pavement_seam_support.py` prepares one backing patch in the existing `SM_PavementSupport_049` object. `build_routes.py` calls it after top-face ownership is resolved, before scene objects are changed. It adds five vertices and four upward-facing triangles. It has no side walls. The patch is 0.20 m long and 2.96 m wide, with a 20 mm inset from the closing cross-section edges. The original pavement, source NPZ files, source controls and runtime route remain unchanged.

The patch is a fitted plane below the asphalt. Preparation checks its intersection with each retained source pavement triangle. The entire patch must remain inside their combined footprint. The separation must be at least 0.5 mm and at most 2 mm everywhere, including after predicted Blender and FBX centimetre float conversion. An off-centre fan puts the failed ray strictly inside one triangle. Its minimum barycentric coordinate must exceed 0.01 and its distance from each triangle edge must exceed 1 mm. A vertical or steep face fails preparation.

The saved design calculation has a separation of 0.750–1.248 mm. The failed ray is about 8.79 mm from its nearest patch triangle edge after the predicted centimetre conversion. These are numerical authoring results, not an Unreal pass.

During the live Blender route stage, the helper repeats the checks on the actual authored vertex data. The stage saves `evidence/blender-pavement-closing-seam-support.json`. The helper records its hash, source mesh hashes, control hash, failed report hash, patch vertices, faces and checks. Running the route stage again rebuilds from the original NPZ, so it does not append a second patch.

Root must then export, import, and repeat the unchanged exact ray and the nearby offset rays. The helper predicts FBX precision; it does not inspect the imported Unreal mesh. Keep that distinction in the evidence. A short normal-controller crossing must confirm ground contact before the seam is accepted. No application was launched to prepare this change.
