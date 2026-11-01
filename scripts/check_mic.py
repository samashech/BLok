#!/usr/bin/env python3
"""Record a few seconds, report the microphone level, and show what Whisper hears."""
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy
import soundfile
from blok import speech

seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 4
volume = subprocess.run(['wpctl', 'get-volume', '@DEFAULT_AUDIO_SOURCE@'], capture_output=True, text=True).stdout.strip()
print(f'Microphone input {volume or "unknown"}. Loading Whisper…')
speech.whisper()
with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / 'mic.wav'
    print(f'Speak a command now ({seconds:g} s)…', flush=True)
    recorder = subprocess.Popen(['pw-record', '--rate', '16000', '--channels', '1', '--format', 's16', str(path)])
    time.sleep(seconds)
    recorder.terminate()
    recorder.wait()
    audio, _ = soundfile.read(str(path), dtype='float32')
peak = float(numpy.abs(audio).max()) if len(audio) else 0.0
print(f'Peak level {peak:.3f}', end='  ')
if peak < 0.05:
    print('→ too quiet. Raise it with: wpctl set-volume @DEFAULT_AUDIO_SOURCE@ 0.8')
elif peak > 0.98:
    print('→ clipping. Lower it with: wpctl set-volume @DEFAULT_AUDIO_SOURCE@ 0.5')
else:
    print('→ good')
started = time.monotonic()
text = speech.transcribe(audio)
print(f'Whisper heard ({time.monotonic() - started:.1f} s): {text!r}' if text else 'Whisper heard no speech.')
