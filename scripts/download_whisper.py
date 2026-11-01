#!/usr/bin/env python3
"""Explicit online step: fetch an open-source Whisper model (faster-whisper format).

Usage: download_whisper.py [base.en | small.en | medium.en | base | small | medium]   (default small.en;
sizes without .en are multilingual, for Hindi/Hinglish)
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from blok.paths import MODELS  # noqa: E402

SIZES = {'tiny.en': 'Systran/faster-whisper-tiny.en', 'base.en': 'Systran/faster-whisper-base.en',
         'small.en': 'Systran/faster-whisper-small.en', 'medium.en': 'Systran/faster-whisper-medium.en',
         # Multilingual: Hindi, Hinglish and other languages
         'base': 'Systran/faster-whisper-base', 'small': 'Systran/faster-whisper-small', 'medium': 'Systran/faster-whisper-medium'}

if __name__ == '__main__':
    size = sys.argv[1] if len(sys.argv) > 1 else 'small.en'
    if size not in SIZES:
        sys.exit('Choose one of: ' + ', '.join(SIZES))
    target = MODELS / f'whisper-{size}'
    if (target / 'model.bin').exists():
        print('present', target)
        sys.exit(0)
    from huggingface_hub import snapshot_download
    snapshot_download(SIZES[size], local_dir=str(target),
                      allow_patterns=['config.json', 'model.bin', 'tokenizer.json', 'vocabulary.*', 'preprocessor_config.json'])
    print('saved', target)
