"""Prepare the CC0 TinyWorlds forest loop for Unreal (no application run)."""
import argparse
import hashlib
import subprocess
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
URL='https://opengameart.org/sites/default/files/Forest_Ambience.mp3'
EXPECTED='9850aa1d0d5d66bd9c5daf8bb77c6d852e01f2f4de22f283bd5621e8bed13b75'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--ffmpeg',default='ffmpeg')
args=parser.parse_args()
source=ROOT/'exports/audio/sources/Forest_Ambience.mp3'
source.parent.mkdir(parents=True,exist_ok=True)
if not source.exists():
    with urllib.request.urlopen(URL,timeout=45) as response:
        data=response.read(5*1024*1024+1)
    if len(data)>5*1024*1024 or hashlib.sha256(data).hexdigest()!=EXPECTED:
        raise ValueError('Audio source differs from the recorded CC0 acquisition')
    source.write_bytes(data)
if hashlib.sha256(source.read_bytes()).hexdigest()!=EXPECTED:
    raise ValueError('Cached audio source differs from its recorded hash')
subprocess.run([args.ffmpeg,'-hide_banner','-loglevel','error','-y','-i',str(source),
    '-ar','48000','-ac','2','-c:a','pcm_s16le',str(ROOT/'exports/audio/S_ForestAmbience.wav')],check=True)
