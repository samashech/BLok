#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
for tool in uv quickshell pw-record curl unzip; do
  command -v "$tool" >/dev/null || { echo "Missing prerequisite: $tool" >&2; exit 1; }
done
uv venv --python 3.12 --allow-existing .venv
uv pip install --python .venv/bin/python -r requirements.txt --torch-backend=cpu
if [[ ! -d models/vosk-model-small-en-us-0.15 ]]; then
  archive="$(mktemp)"
  trap 'rm -f "$archive"' EXIT
  curl -fL https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -o "$archive"
  mkdir -p models
  unzip -q "$archive" -d models
fi
.venv/bin/python scripts/download_laya.py
echo 'Ready. Run ./hyprash.sh'
