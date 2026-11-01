#!/usr/bin/env bash
# Reclaim disk space used by BLoK and its tooling.
#
#   ./scripts/slim.sh                 report only (changes nothing)
#   ./scripts/slim.sh --apply         remove the safe items
#   ./scripts/slim.sh --apply --all   also remove the optional items
#   ./scripts/slim.sh --apply --kokoro-int8   swap Kokoro for its 88 MB int8 model
#
# Safe items are unused or re-creatable (download caches, dev dependencies).
# Optional items are models BLoK no longer uses but you might.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
APPLY=0; ALL=0; INT8=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;; --all) ALL=1 ;; --kokoro-int8) INT8=1 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

size() { du -sh "$@" 2>/dev/null | awk '{print $1}' | paste -sd+ - ; }
step() {  # step <label> <size> <command...>
  local label="$1" amount="$2"; shift 2
  if (( APPLY )); then printf '  removing  %-58s %s\n' "$label" "$amount"; "$@"
  else printf '  would remove  %-54s %s\n' "$label" "$amount"; fi
}

echo "Safe (unused or re-creatable):"
VENV="$ROOT/.venv/bin/python"
if "$VENV" -c 'import vosk' 2>/dev/null; then
  step "vosk speech packages (replaced by Whisper)" "$(size "$ROOT"/.venv/lib/python3*/site-packages/{vosk,websockets,requests})" \
    uv pip uninstall --python "$VENV" vosk srt websockets requests
fi
for dir in "$ROOT/node_modules" "$ROOT/scripts/orb-build/node_modules"; do
  [[ -d "$dir" ]] && step "${dir#"$ROOT"/} (test/build tools; npm ci restores)" "$(size "$dir")" rm -rf -- "$dir"
done
CACHES=$(find "$ROOT" -path "$ROOT/.venv" -prune -o -type d -name __pycache__ -print)
[[ -n "$CACHES" ]] && step "Python __pycache__ folders" "$(size $CACHES)" rm -rf -- $CACHES
[[ -d "$HOME/.cache/uv" ]] && command -v uv >/dev/null && step "uv download cache (~/.cache/uv)" "$(size "$HOME/.cache/uv")" uv cache clean
[[ -d "$HOME/.cache/pip" ]] && step "pip download cache (~/.cache/pip)" "$(size "$HOME/.cache/pip")" rm -rf -- "$HOME/.cache/pip"

# Model variants BLoK isn't using (e.g. left over after switching sizes).
MODELS="${BLOK_HOME:-$ROOT}/models"
active_whisper=$("$VENV" -c 'from blok import speech; print(speech.whisper_model_path())' 2>/dev/null || true)
for dir in "$MODELS"/whisper-*; do
  [[ -d "$dir" && "$dir" != "$active_whisper" ]] && step "unused Whisper model ${dir##*/} (using ${active_whisper##*/})" "$(size "$dir")" rm -rf -- "$dir"
done
if [[ -f "$MODELS/kokoro/kokoro-v1.0.onnx" && -f "$MODELS/kokoro/kokoro-v1.0.int8.onnx" ]] && (( ! INT8 )); then
  step "unused compact Kokoro model (using the full one)" "$(size "$MODELS/kokoro/kokoro-v1.0.int8.onnx")" rm -f -- "$MODELS/kokoro/kokoro-v1.0.int8.onnx"
fi

echo
echo "Optional (models BLoK no longer uses; add --all):"
voxtype_model=$(grep -Po '^\s*model\s*=\s*"\K[^"]+' "$HOME/.config/voxtype/config.toml" 2>/dev/null | head -1 || true)
for model in "$HOME"/.local/share/voxtype/models/ggml-*.bin; do
  [[ -f "$model" ]] || continue
  name=$(basename "$model" .bin); name=${name#ggml-}
  [[ "$name" == "$voxtype_model" ]] && continue   # the model your F9 dictation uses stays
  if (( ALL )); then step "Voxtype model $name (your Voxtype uses ${voxtype_model:-base.en})" "$(size "$model")" rm -f -- "$model"
  else printf '  optional  %-58s %s\n' "Voxtype model $name (unused by your Voxtype config)" "$(size "$model")"; fi
done
if command -v ollama >/dev/null && ollama list >/dev/null 2>&1; then
  for model in moondream:latest gemma2:2b; do
    ollama list | grep -q "^$model" || continue
    if (( ALL )); then step "Ollama model $model (BLoK uses qwen2.5:3b)" "" ollama rm "$model"
    else printf '  optional  %-58s\n' "Ollama model $model (BLoK uses qwen2.5:3b)"; fi
  done
else
  printf '  optional  %-58s\n' "Ollama models moondream, gemma2:2b (start ollama to manage them)"
fi

echo
FULL="$MODELS/kokoro/kokoro-v1.0.onnx"
if (( INT8 )) && [[ -f "$FULL" ]]; then
  if (( APPLY )); then
    "$VENV" "$ROOT/scripts/download_kokoro.py" --int8 && rm -f -- "$FULL"
    echo "  Kokoro now uses the int8 model (~88 MB)."
  else echo "  would swap Kokoro for its int8 model, saving about 220 MB"; fi
elif [[ -f "$FULL" ]]; then
  echo "Tip: --kokoro-int8 swaps the voice model for one a quarter the size (slightly lower quality)."
fi
(( APPLY )) || echo "Nothing was changed. Re-run with --apply to remove the safe items."
