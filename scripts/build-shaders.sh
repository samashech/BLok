#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
for name in goo-blur goo-merge; do
  /usr/lib/qt6/bin/qsb --glsl '100 es,120,150' --hlsl 50 --msl 12 -o "ui/shaders/$name.frag.qsb" "ui/shaders/$name.frag"
done
