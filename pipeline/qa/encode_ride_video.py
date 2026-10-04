"""Encode the application's recorded viewport frames without changing their timing.

This consumes an existing ride record. It does not launch or operate the app.
The movie has no audio. Keep the capture manifest and ride trace with the movie.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path


def encode(capture, output):
    data = json.loads(capture.read_text(encoding="utf-8-sig"))
    frames = data["frames"]
    if not frames or any(not row["saved"] for row in frames):
        raise ValueError("The frame list is empty or contains failed writes")
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("The installed ffmpeg and ffprobe commands are required")
    lines = ["ffconcat version 1.0"]
    previous = -1.0
    for i, row in enumerate(frames):
        if not re.fullmatch(r"frame-[0-9]{6}\.jpg", row["file"]):
            raise ValueError("Unexpected capture filename")
        if row["seconds"] <= previous:
            raise ValueError("Capture times must increase")
        previous = row["seconds"]
        if not (capture.parent / row["file"]).is_file():
            raise FileNotFoundError(row["file"])
        end = frames[i + 1]["seconds"] if i + 1 < len(frames) else data["duration_seconds"]
        # The first still covers the small interval before the first capture.
        start = row["seconds"] if i else 0.0
        lines += [f"file '{row['file']}'", f"duration {max(.001, end - start):.9f}"]
    lines.append(f"file '{frames[-1]['file']}'")
    concat = capture.with_name("frames.ffconcat")
    concat.write_text("\n".join(lines) + "\n", encoding="utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "warning", "-n", "-f", "concat",
        "-safe", "1", "-i", str(concat), "-an", "-c:v", "libx264", "-preset", "fast",
        "-crf", "20", "-pix_fmt", "yuv420p", "-fps_mode", "vfr", "-movflags", "+faststart",
        str(output)], check=True)
    probe = json.loads(subprocess.check_output([ffprobe, "-v", "error", "-show_streams",
        "-show_format", "-of", "json", str(output)], text=True))
    video = next(x for x in probe["streams"] if x["codec_type"] == "video")
    duration_error = abs(float(probe["format"]["duration"]) - data["duration_seconds"])
    with output.open("rb") as stream:
        movie_digest = hashlib.file_digest(stream, "sha256").hexdigest()
    report = dict(capture=str(capture), movie=str(output),
        capture_sha256=hashlib.sha256(capture.read_bytes()).hexdigest(),
        movie_sha256=movie_digest,
        width=video["width"], height=video["height"], frames=len(frames),
        duration_seconds=float(probe["format"]["duration"]), duration_error_seconds=duration_error,
        capture_complete=data["capture_complete"], audio=False,
        encoding_pass=duration_error <= .3 and (video["width"], video["height"]) == (960, 540),
        scope="Continuous visual evidence from the application viewport. Route acceptance is in the separate ride trace.")
    output.with_name(output.stem + "-video.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["encoding_pass"]:
        raise RuntimeError("Movie dimensions or duration did not pass")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    encode(args.capture.resolve(), args.output.resolve())
