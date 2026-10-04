"""Author original seamless water normal textures without opening an application.

Run with Python + NumPy + Pillow, or in a Blender environment with those modules.
There is no bpy dependency and this script never edits a blend file. The Fourier
height field is saved as an editable source beside the RGB normal-map export.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
SPEC = json.loads((ROOT / "manifests/seawall-water-sky.json").read_text(encoding="utf-8"))
AUTHOR = SPEC["water"]["texture_authoring"]
GENERATOR_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
SOURCE_ID = hashlib.sha256(json.dumps(AUTHOR, sort_keys=True).encode() + GENERATOR_SHA.encode()).hexdigest()
OUT = ROOT / "exports/textures/seawall-water" / SOURCE_ID[:12]
MANIFEST = ROOT / SPEC["water"]["texture_manifest"]


def relative(path):
    return path.relative_to(ROOT).as_posix()


def file_record(path):
    return dict(path=relative(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)


def sample_wrapped(normal, q):
    """Bilinear source sampling for authoring diagnostics, not an engine render."""
    size = normal.shape[0]
    texel = np.mod(q, 1.0) * size - 0.5
    ij = np.floor(texel).astype(np.int64)
    fraction = texel - ij
    x0, y0 = ij[..., 0] % size, ij[..., 1] % size
    x1, y1 = (x0 + 1) % size, (y0 + 1) % size
    a = normal[y0, x0] * (1.0 - fraction[..., 0, None]) + normal[y0, x1] * fraction[..., 0, None]
    b = normal[y1, x0] * (1.0 - fraction[..., 0, None]) + normal[y1, x1] * fraction[..., 0, None]
    return a * (1.0 - fraction[..., 1, None]) + b * fraction[..., 1, None]


def evaluate_world_normals(normal, position_cm, seconds):
    slope = np.zeros_like(position_cm, dtype=np.float64)
    for layer in SPEC["water"]["texture_layers"]:
        axis_u = np.asarray(layer["axis_xy"])
        axis_v = np.array([-axis_u[1], axis_u[0]])
        axes = np.stack([axis_u, axis_v])
        flow = np.asarray(layer["flow_world_cm_per_second"])
        q = ((position_cm - seconds * flow) @ axes.T) / layer["tile_cm"] + layer["offset_uv"]
        value = sample_wrapped(normal, q)
        local_slope = value[..., :2] / np.maximum(value[..., 2, None], 0.25)
        slope += (local_slope @ axes) * layer["strength"]
    slope *= np.minimum(1.0, 0.60 / np.maximum(np.linalg.norm(slope, axis=-1, keepdims=True), 0.0001))
    combined = np.concatenate([slope, np.ones_like(slope[..., :1])], axis=-1)
    return combined / np.linalg.norm(combined, axis=-1, keepdims=True)


def main():
    size = AUTHOR["resolution"]
    if size not in (512, 1024, 2048):
        raise ValueError("Use a power-of-two source resolution between 512 and 2048")
    if len(SPEC["water"]["texture_layers"]) != 3:
        raise ValueError("This source diagnostic expects exactly three texture layers")
    OUT.mkdir(parents=True, exist_ok=True)
    length_m = AUTHOR["tile_metres"]
    rng = np.random.default_rng(AUTHOR["seed"])
    frequencies = np.fft.fftfreq(size, d=length_m / size)
    fx, fy = np.meshgrid(frequencies, frequencies)
    radial = np.sqrt(fx * fx + fy * fy)
    safe = np.maximum(radial, 1.0 / length_m)
    wind = np.asarray(AUTHOR["wind_axis_xy"], dtype=np.float64)
    direction = (fx * wind[0] + fy * wind[1]) / safe
    # A continuous spread of wave directions and wavelengths removes the square
    # lattice cells and three rigid bands of the earlier material. The periodic
    # FFT domain provides seamless values AND seamless derivatives at each edge.
    distribution = 0.30 + 0.70 * direction ** 4
    spectrum = np.zeros_like(radial)
    for band in AUTHOR["bands"]:
        centre = 1.0 / band["wavelength_metres"]
        spectrum += band["weight"] * np.exp(-0.5 * (np.log(safe / centre) / band["log_width"]) ** 2)
    min_freq = 1.0 / AUTHOR["longest_wavelength_metres"]
    max_freq = 1.0 / AUTHOR["shortest_wavelength_metres"]
    # Smooth low/high cutoff, not an abrupt Fourier truncation.
    spectrum *= (1.0 - np.exp(-(radial / min_freq) ** 6)) * np.exp(-(radial / max_freq) ** 6)
    spectrum *= distribution
    spectrum[0, 0] = 0.0
    white = rng.normal(size=(size, size))
    height_spectrum = np.fft.fft2(white) * np.sqrt(spectrum) / (safe * 2 * np.pi)
    height_spectrum[0, 0] = 0.0
    height = np.fft.ifft2(height_spectrum).real
    dx = np.fft.ifft2(2j * np.pi * fx * height_spectrum).real
    dy = np.fft.ifft2(2j * np.pi * fy * height_spectrum).real
    original_rms = np.sqrt(np.mean(dx * dx + dy * dy))
    multiplier = AUTHOR["slope_rms"] / original_rms
    height *= multiplier
    dx *= multiplier
    dy *= multiplier
    normals = np.stack([-dx, -dy, np.ones_like(dx)], axis=-1)
    normals /= np.linalg.norm(normals, axis=-1, keepdims=True)
    encoded = np.rint(np.clip(normals * 0.5 + 0.5, 0, 1) * 255).astype(np.uint8)
    normal_path = OUT / "T_SeawallSpectralWaves_N.png"
    source_path = OUT / "spectral-height-metres.npz"
    Image.fromarray(encoded).save(normal_path)
    np.savez_compressed(source_path, height_metres=height.astype(np.float32),
                        dx=dx.astype(np.float32), dy=dy.astype(np.float32), tile_metres=length_m)
    # The quantized normal is the exported source that Unreal will read.
    decoded = encoded.astype(np.float64) / 255.0 * 2.0 - 1.0
    decoded /= np.linalg.norm(decoded, axis=-1, keepdims=True)
    step_x = np.linalg.norm(np.roll(decoded, -1, axis=1) - decoded, axis=-1)
    step_y = np.linalg.norm(np.roll(decoded, -1, axis=0) - decoded, axis=-1)
    seam = dict(x_edge_mean=float(step_x[:, -1].mean()), y_edge_mean=float(step_y[-1, :].mean()),
                all_x_mean=float(step_x.mean()), all_y_mean=float(step_y.mean()),
                method="Periodic finite-difference seam compared with interior texel differences; edge pixels are not duplicates.")
    # Bind source motion to fixed WORLD locations. A change comes from sampling
    # displaced wave detail, not changing random colors or moving the camera.
    positions = rng.uniform([-1200.0, -1200.0], [1200.0, 1200.0], size=(8192, 2))
    at_zero = evaluate_world_normals(decoded, positions, 0.0)
    motion = []
    for seconds in (0.5, 1.0, 2.0):
        later = evaluate_world_normals(decoded, positions, seconds)
        angular = np.degrees(np.arccos(np.clip(np.sum(at_zero * later, axis=-1), -1, 1)))
        motion.append(dict(seconds=seconds, median_normal_angle_change_deg=float(np.median(angular)),
                           p95_normal_angle_change_deg=float(np.percentile(angular, 95)),
                           fraction_over_two_degrees=float(np.mean(angular > 2)),
                           layer_displacements_cm=[float(np.linalg.norm(layer["flow_world_cm_per_second"]) * seconds)
                                                   for layer in SPEC["water"]["texture_layers"]]))
    # A clearly labelled diagnostic animation shows directional highlights on
    # a fixed 18 m square. It is not an Unreal water or reflection render.
    width, height_px = 512, 384
    xx, yy = np.meshgrid(np.linspace(-900, 900, width), np.linspace(-675, 675, height_px))
    plane = np.stack([xx, yy], axis=-1)
    light = np.array([0.45, -0.55, 0.70]); light /= np.linalg.norm(light)
    frames = []
    for index in range(41):
        seconds = index / 20.0
        ns = evaluate_world_normals(decoded, plane, seconds)
        diffuse = np.clip(np.sum(ns * light, axis=-1), 0, 1)
        highlight = np.clip(ns[..., 0] * 0.52 - ns[..., 1] * 0.43 + ns[..., 2] * 0.735, 0, 1) ** 20
        shade = np.clip(0.09 + 0.33 * diffuse + 0.55 * highlight, 0, 1)
        pixels = (np.stack([shade * 0.62, shade * 0.82, shade], axis=-1) * 255).astype(np.uint8)
        frame = Image.fromarray(pixels)
        ImageDraw.Draw(frame).rectangle((0, 0, width, 34), fill=(20, 24, 29))
        ImageDraw.Draw(frame).text((10, 5), f"SOURCE NORMAL MOTION - fixed world area - {seconds:.2f} s", fill=(240, 240, 240))
        ImageDraw.Draw(frame).text((10, 19), "Authoring diagnostic only. This is not an Unreal capture.", fill=(185, 195, 200))
        frames.append(frame)
    gif_path = OUT / "source-normal-motion.gif"
    frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=50, loop=0, disposal=2)
    for index in (0, 10, 20, 40):
        frames[index].save(OUT / f"source-normal-motion-{index:02d}.png")
    source_normal_path = OUT / "normal-map-preview.png"
    Image.fromarray(encoded).resize((512, 512)).save(source_normal_path)
    report = dict(schema_version=1, created_utc=datetime.now(timezone.utc).isoformat(),
                  source_id=SOURCE_ID, generator_sha256=GENERATOR_SHA, authoring=AUTHOR,
                  material_layers=SPEC["water"]["texture_layers"],
                  license="Original project wave data and texture. No copied image or outside asset.",
                  method="Seeded Fourier height spectrum; analytic spectral derivatives; RGB signed normal encoded to UNORM8.",
                  normal_texture=file_record(normal_path), editable_height_source=file_record(source_path),
                  source_preview=file_record(source_normal_path), source_motion_preview=file_record(gif_path),
                  resolution=[size, size], normal_slope_rms=float(np.sqrt(np.mean(dx*dx+dy*dy))),
                  normal_slope_p99=float(np.percentile(np.sqrt(dx*dx+dy*dy), 99)),
                  height_std_metres=float(np.std(height)), periodic_seam=seam,
                  temporal_source_diagnostics=motion,
                  diagnostic_limits="CPU source sampling only. Does not establish engine Time, texture compression, mip behavior, motion appearance or GPU cost.",
                  expected_bc5_bytes_with_mips=int(sum(((max(1, size >> mip)+3)//4)**2*16
                                                     for mip in range(int(np.log2(size))+1))),
                  application_test_run=False, unreal_material_applied=False)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(dict(manifest=relative(MANIFEST), source_id=SOURCE_ID,
                          texture=relative(normal_path), motion=motion), indent=2))


if __name__ == "__main__":
    main()
