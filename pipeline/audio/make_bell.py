"""Original modal-synthesis bicycle bell for the prototype; no external recording."""
import math
import struct
import wave
from pathlib import Path

root = Path(__file__).resolve().parents[2]
output = root / "exports/audio/S_Bell.wav"
output.parent.mkdir(parents=True, exist_ok=True)
sample_rate = 48000
samples = []
for index in range(int(sample_rate * 2.4)):
    time = index / sample_rate
    value = sum(amplitude * math.exp(-time / decay) * math.sin(2 * math.pi * frequency * time)
                for frequency, amplitude, decay in [(2370, 0.42, 0.55), (3180, 0.20, 0.36), (4760, 0.08, 0.20)])
    value *= min(1.0, time / 0.002)
    samples.append(struct.pack("<h", round(max(-1, min(1, value)) * 32767)))
with wave.open(str(output), "wb") as stream:
    stream.setparams((1, 2, sample_rate, 0, "NONE", "not compressed"))
    stream.writeframes(b"".join(samples))
print(output)
