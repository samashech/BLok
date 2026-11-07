#!/usr/bin/env bash
# BLoK installer.
#
#   curl -fsSL https://raw.githubusercontent.com/samashech/BLoK/main/install.sh | bash
#   ./install.sh                 from a checkout
#
# Options:
#   --yes           accept the recommended choices without asking
#   --minimal       smallest setup (Whisper base.en, compact Kokoro voice, no rephraser)
#   --full          largest setup (Whisper medium.en, full Kokoro, Qwen rephraser)
#   --no-integration   skip the Ctrl+. keybinding, app launcher and browser host
#   --models-only   only (re)choose and download models
set -euo pipefail

REPO_URL="https://github.com/samashech/BLoK.git"
YES=0; PRESET=""; INTEGRATION=1; MODELS_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --yes|-y) YES=1 ;;
    --minimal) PRESET=minimal; YES=1 ;;
    --full) PRESET=full; YES=1 ;;
    --no-integration) INTEGRATION=0 ;;
    --models-only) MODELS_ONLY=1 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

bold=$'\e[1m'; dim=$'\e[2m'; green=$'\e[32m'; yellow=$'\e[33m'; red=$'\e[31m'; off=$'\e[0m'
[[ -t 1 ]] || { bold=; dim=; green=; yellow=; red=; off=; }
say()  { printf '%s\n' "$*"; }
step() { printf '\n%s==>%s %s%s%s\n' "$green" "$off" "$bold" "$*" "$off"; }
warn() { printf '%s!%s %s\n' "$yellow" "$off" "$*"; }
die()  { printf '%sx%s %s\n' "$red" "$off" "$*" >&2; exit 1; }

# Prompts read the terminal even when this script arrives through a pipe.
ask() {  # ask <question> <default>  → prints the answer
  local answer
  if (( YES )) || ! { : </dev/tty; } 2>/dev/null; then echo "$2"; return; fi
  read -rp "$1 " answer </dev/tty || true
  echo "${answer:-$2}"
}
yes_no() { [[ "$(ask "$1 [${2^^}/$( [[ $2 == y ]] && echo n || echo y )]" "$2")" =~ ^[Yy] ]]; }

# --- 1. Where BLoK lives -----------------------------------------------------
SOURCE="${BASH_SOURCE[0]:-}"
if [[ -n "$SOURCE" && -f "$(dirname -- "$SOURCE")/blok.sh" ]]; then
  ROOT="$(cd -- "$(dirname -- "$SOURCE")" && pwd)"
else
  ROOT="${BLOK_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/blok/app}"
  step "Getting BLoK"
  command -v git >/dev/null || die "git is needed: sudo pacman -S git"
  if [[ -d "$ROOT/.git" ]]; then git -C "$ROOT" pull --ff-only; else git clone --depth 1 "$REPO_URL" "$ROOT"; fi
  exec "$ROOT/install.sh" "$@"
fi
# A read-only checkout (e.g. the AUR package in /opt) keeps models and data in your home.
if [[ -w "$ROOT" ]]; then BLOK_HOME="${BLOK_HOME:-$ROOT}"; else BLOK_HOME="${BLOK_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/blok}"; fi
export BLOK_HOME
mkdir -p "$BLOK_HOME"
PY="$BLOK_HOME/.venv/bin/python"

say "${bold}BLoK${off} — an offline Jarvis for Hyprland."
say "${dim}Code: $ROOT   Models and data: $BLOK_HOME${off}"

# --- 2. System packages -------------------------------------------------------
if (( ! MODELS_ONLY )); then
  step "Checking system packages"
  [[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]] || warn "Hyprland isn't running in this session; BLoK needs it to run."
  declare -A need=([quickshell]=quickshell [pw-record]=pipewire [wtype]=wtype [fd]=fd [wl-copy]=wl-clipboard [uv]=uv [git]=git)
  declare -A nice=([espeak-ng]=espeak-ng [pdftotext]=poppler [hyprpicker]=hyprpicker [ydotool]=ydotool)
  missing=(); optional=()
  for cmd in "${!need[@]}"; do command -v "$cmd" >/dev/null || missing+=("${need[$cmd]}"); done
  for cmd in "${!nice[@]}"; do command -v "$cmd" >/dev/null || optional+=("${nice[$cmd]}"); done
  command -v pacman >/dev/null && ! pacman -Q qt6-multimedia >/dev/null 2>&1 && missing+=(qt6-multimedia)
  if (( ${#missing[@]} + ${#optional[@]} )); then
    say "Missing: ${missing[*]:-none}   ${dim}optional: ${optional[*]:-none}${off}"
    if command -v pacman >/dev/null && yes_no "Install them with sudo pacman?" y; then
      sudo pacman -S --needed --noconfirm "${missing[@]}" "${optional[@]}" ||
        warn "Some packages failed (quickshell may need the AUR: yay -S quickshell)."
    fi
    for cmd in quickshell pw-record uv; do command -v "$cmd" >/dev/null || die "$cmd is required. Install it and run this again."; done
  else
    say "All present."
  fi

  step "Python environment"
  uv venv --python 3.12 --allow-existing "$BLOK_HOME/.venv" >/dev/null
  uv pip install --python "$PY" -r "$ROOT/requirements.txt" --torch-backend=cpu
fi
[[ -x "$PY" ]] || die "No Python environment yet; run ./install.sh without --models-only first."

# --- 3. Models ------------------------------------------------------------------
installed() { [[ -e "$1" ]] && echo " ${green}(installed)${off}" || true; }
M="$BLOK_HOME/models"
step "Choose models"
say "BLoK always needs the ${bold}Laya decision model${off} (~820 MB)$(installed "$M/huggingface/hub/models--convaiinnovations--laya")."
say ""
say "Speech recognition (Whisper, runs on your CPU):"
say "  1) base.en    145 MB  fastest, least accurate$(installed "$M/whisper-base.en/model.bin")"
say "  2) small.en   465 MB  ${bold}recommended${off}, ~1 s per command$(installed "$M/whisper-small.en/model.bin")"
say "  3) medium.en  1.5 GB  best with accents, ~3 s per command$(installed "$M/whisper-medium.en/model.bin")"
say "  4) small      465 MB  English ${bold}+ Hindi/Hinglish${off} (\"YouTube pe gaane chalao\")$(installed "$M/whisper-small/model.bin")"
case "$PRESET" in minimal) w=1 ;; full) w=3 ;; *) w=$(ask "Choice [2]:" 2) ;; esac
whisper=$( case "$w" in 1) echo base.en ;; 3) echo medium.en ;; 4) echo small ;; *) echo small.en ;; esac )
whisper_mb=$( case "$whisper" in base.en) echo 145 ;; medium.en) echo 1500 ;; *) echo 465 ;; esac )
say ""
say "Voice replies:"
say "  1) Kokoro         340 MB  natural voice, ${bold}recommended${off}$(installed "$M/kokoro/kokoro-v1.0.onnx")"
say "  2) Kokoro compact 115 MB  slightly lower quality$(installed "$M/kokoro/kokoro-v1.0.int8.onnx")"
say "  3) espeak only      0 MB  robotic, already on most systems"
case "$PRESET" in minimal) v=2 ;; full) v=1 ;; *) v=$(ask "Choice [1]:" 1) ;; esac
voice_mb=$( case "$v" in 2) echo 115 ;; 3) echo 0 ;; *) echo 340 ;; esac )
qwen=0; qwen_mb=0
if command -v ollama >/dev/null; then
  say ""
  say "Optional: Qwen2.5 3B (1.9 GB, via Ollama) restates rambling speech before Laya decides."
  if [[ "$PRESET" == full ]] || { [[ -z "$PRESET" ]] && yes_no "Download it?" n; }; then qwen=1; qwen_mb=1900; fi
fi
# Count only what isn't on disk yet.
have() { [[ -e "$1" ]]; }
python_mb=$( (( MODELS_ONLY )) || have "$BLOK_HOME/.venv/lib/python3.12/site-packages/torch" && echo 0 || echo 1200 )
laya_mb=$( have "$M/huggingface/hub/models--convaiinnovations--laya" && echo 0 || echo 820 )
have "$M/whisper-$whisper/model.bin" && whisper_mb=0
case "$v" in 1) have "$M/kokoro/kokoro-v1.0.onnx" && voice_mb=0 ;; 2) have "$M/kokoro/kokoro-v1.0.int8.onnx" && voice_mb=0 ;; esac
(( qwen )) && ollama list 2>/dev/null | grep -q '^qwen2.5:3b' && qwen_mb=0
total=$(( python_mb + laya_mb + whisper_mb + voice_mb + qwen_mb ))
say ""
if (( total )); then
  say "To download: ${bold}$(awk "BEGIN{printf \"%.1f\", $total/1000}") GB${off}"
else
  say "Everything you chose is already installed."
fi
yes_no "Continue?" y || die "Stopped. Nothing else was downloaded."

step "Downloading models"
"$PY" "$ROOT/scripts/download_laya.py"
"$PY" "$ROOT/scripts/download_whisper.py" "$whisper"
case "$v" in 1) "$PY" "$ROOT/scripts/download_kokoro.py" ;; 2) "$PY" "$ROOT/scripts/download_kokoro.py" --int8 ;; esac
(( qwen )) && { ollama list >/dev/null 2>&1 || warn "Start Ollama (ollama serve) and run: ollama pull qwen2.5:3b"; ollama pull qwen2.5:3b || true; }

(( MODELS_ONLY )) && { step "Models ready."; exit 0; }

# --- 4. Desktop integration -------------------------------------------------------
step "Desktop integration"
BIN="$HOME/.local/bin"; mkdir -p "$BIN"
if [[ "$BLOK_HOME" == "$ROOT" ]]; then
  ln -sf "$ROOT/blok.sh" "$BIN/blok"
else
  printf '#!/bin/sh\nBLOK_HOME=%q exec %q "$@"\n' "$BLOK_HOME" "$ROOT/blok.sh" > "$BIN/blok"; chmod +x "$BIN/blok"
fi
say "Command: $BIN/blok"
if (( INTEGRATION )) && yes_no "Add the Ctrl+. hold-to-talk key, app launcher and browser host?" y; then
  python3 "$ROOT/scripts/install.py" --launcher "$BIN/blok" || warn "Keybinding not installed; see the message above."
fi

step "Done"
say "Start BLoK with ${bold}blok${off} (or the app launcher), then hold ${bold}Ctrl+.${off} and talk."
say ""
say "For browser control, load the extension once:"
say "  brave://extensions → Developer mode → Load unpacked → ${bold}$ROOT/browser-extension${off}"
say ""
say "${dim}Check your mic: blok mic-test · List commands: blok commands · Free space: $ROOT/scripts/slim.sh${off}"
