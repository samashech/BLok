#!/usr/bin/env python3
"""Explicit online step: fetch the Kokoro-82M (Apache-2.0) voice model for local speech."""
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from blok.paths import MODELS  # noqa: E402
TARGET = MODELS / 'kokoro'
RELEASE = 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/'
FILES = ('kokoro-v1.0.onnx', 'voices-v1.0.bin')


def fetch(name):
    path = TARGET / name
    if path.exists() and path.stat().st_size > 1_000_000:
        print('present', path)
        return
    temp = path.with_suffix(path.suffix + '.part')
    with urllib.request.urlopen(RELEASE + name, timeout=60) as response, temp.open('wb') as out:
        total = int(response.headers.get('Content-Length', 0))
        done = 0
        while chunk := response.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if total:
                print(f'\r{name}: {done * 100 // total}%', end='', flush=True)
    if total and temp.stat().st_size != total:
        temp.unlink()
        sys.exit(f'\n{name}: incomplete download')
    temp.replace(path)
    print(f'\nsaved {path}')


if __name__ == '__main__':
    TARGET.mkdir(parents=True, exist_ok=True)
    # --int8: the quantized model (~88 MB instead of ~310 MB), slightly lower quality.
    for name in (('kokoro-v1.0.int8.onnx', FILES[1]) if '--int8' in sys.argv else FILES):
        fetch(name)
