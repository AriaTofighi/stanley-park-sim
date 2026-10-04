"""Audit module image resources; make unpacked local image paths relative."""
from pathlib import Path
import json
import sys
import bpy

ROOT = Path(__file__).resolve().parents[2]
record = []
for source in sorted((ROOT / 'blender/modules').glob('*.blend')):
    bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False)
    bpy.context.preferences.filepaths.file_preview_type = 'NONE'
    bpy.context.preferences.filepaths.save_version = 0
    changes = []
    images = []
    for image in bpy.data.images:
        if image.source not in {'FILE', 'TILED', 'SEQUENCE', 'MOVIE'}:
            continue
        original = image.filepath
        if not original:
            continue
        packed = bool(image.packed_file) or bool(image.packed_files)
        target = Path(bpy.path.abspath(original, library=image.library)).resolve()
        exists = target.is_file()
        inside = target.is_relative_to(ROOT)
        if not packed and not original.startswith('//'):
            if not exists or not inside or image.library:
                raise RuntimeError(f'Cannot make module image portable: {source.name}: {original}')
            image.filepath = bpy.path.relpath(str(target), start=str(source.parent))
            changes.append(dict(image=image.name, previous=original, relative=image.filepath))
        if not packed and (not exists or not inside):
            raise RuntimeError(f'Unpacked image is missing from the source bundle: {source.name}: {original}')
        images.append(dict(image=image.name, path=image.filepath, packed=packed,
            target=target.relative_to(ROOT).as_posix() if inside else str(target), exists=exists, inside_project=inside))
    if changes:
        bpy.ops.wm.save_as_mainfile(filepath=str(source), compress=True)
    record.append(dict(file=source.relative_to(ROOT).as_posix(), changes=changes, images=images))
    (ROOT / 'evidence/blender-module-portability.json').write_text(json.dumps(dict(
        method='Blender image datablock inspection; only unpacked absolute file paths changed',
        files=record, complete=False), indent=2))
(ROOT / 'evidence/blender-module-portability.json').write_text(json.dumps(dict(
    method='Blender image datablock inspection; only unpacked absolute file paths changed',
    files=record, complete=True), indent=2))
