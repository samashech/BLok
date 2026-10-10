#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
for tool in uv quickshell voxtype wtype; do
  command -v "$tool" >/dev/null || { echo "Missing prerequisite: $tool" >&2; exit 1; }
done
uv venv --python 3.12 --allow-existing .venv
uv pip install --python .venv/bin/python -r requirements.txt --torch-backend=cpu
.venv/bin/python scripts/download_laya.py
echo 'Ready. Run ./hyprash.sh'
