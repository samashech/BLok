#!/usr/bin/env bash
set -euo pipefail
BLOK_ROOT="$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" && pwd)"
# Models, the Python environment and data live in BLOK_HOME (the checkout by default).
BLOK_HOME="${BLOK_HOME:-$BLOK_ROOT}"
BLOK_PYTHON="$BLOK_HOME/.venv/bin/python"
export BLOK_ROOT BLOK_HOME BLOK_PYTHON
export PYTHONPATH="$BLOK_ROOT${PYTHONPATH:+:$PYTHONPATH}"
cd "$BLOK_ROOT"
case "${1:-show}" in
  show|toggle)
    action="${1:-show}"
    [[ "$action" == show ]] && action=present
    for attempt in {1..50}; do
      status="$(quickshell ipc -p "$BLOK_ROOT/ui" call blok status 2>/dev/null || true)"
      if [[ "$status" == \{* ]]; then
        quickshell ipc -p "$BLOK_ROOT/ui" call blok "$action"
        exit 0
      fi
      if [[ "$attempt" == 1 ]]; then quickshell -d -n -p "$BLOK_ROOT/ui"; fi
      sleep 0.1
    done
    echo 'BLoK did not become ready; run ./blok.sh foreground for details.' >&2
    exit 1
    ;;
  ptt-start) exec python3 scripts/ptt.py start ;;
  ptt-finish) exec python3 scripts/ptt.py finish ;;
  foreground) exec quickshell -n -p "$BLOK_ROOT/ui" ;;
  hide|quit|status) quickshell ipc -p "$BLOK_ROOT/ui" call blok "$1" ;;
  theme) quickshell ipc -p "$BLOK_ROOT/ui" call blok appearance "${2:?Choose omarchy, liquid, halloween, diwali, minecraft or next}" ;;
  mic-test) exec "$BLOK_PYTHON" scripts/check_mic.py "${2:-4}" ;;
  click-test) exec "$BLOK_PYTHON" scripts/check_click.py ;;
  commands) exec "$BLOK_PYTHON" -m blok.plugins ;;
  mcp) exec "$BLOK_PYTHON" -m blok.mcp ;;
  heard) exec "$BLOK_PYTHON" - <<'PY'
import json, socket
from blok.mcp_bridge import SOCKET
try:
    with socket.socket(socket.AF_UNIX) as conn:
        conn.connect(str(SOCKET)); conn.sendall(b'{"internal": "heard"}\n')
        reply = json.loads(conn.makefile('rb').readline())
except OSError:
    raise SystemExit('BLoK is not running.')
if not reply['on']:
    print('Hands-free is off. Say "hands free on" or run: blok handsfree on')
for item in reply['heard'] or [{'at': '', 'text': '(nothing heard yet)', 'acted': False}]:
    command = f"   → ran: {item['command']}" if item.get('command') else ('   → waited for your command' if item['acted'] else '')
    print(f"{item['at']}  {'acted  ' if item['acted'] else 'ignored'}  {item['text']}{command}")
PY
  ;;
  handsfree) quickshell ipc -p "$BLOK_ROOT/ui" call blok handsfree "${2:?Choose on or off}" ;;
  setup) shift; exec "$BLOK_ROOT/install.sh" "$@" ;;
  voice) quickshell ipc -p "$BLOK_ROOT/ui" call blok voice "${2:?Choose kokoro, elevenlabs, local or off}" ;;
  elevenlabs-key)
    # Hidden prompt; stored in ~/.config/blok/elevenlabs.key (mode 600), never in this repo.
    read -rsp 'ElevenLabs API key: ' key; echo
    [[ -n "$key" ]] || { echo 'No key entered.' >&2; exit 1; }
    printf '%s' "$key" | "$BLOK_PYTHON" -c 'import sys; sys.path.insert(0, "'"$BLOK_ROOT"'"); from blok.voice import save_key; save_key(sys.stdin.read())'
    echo 'Saved. Restart BLoK (blok quit; blok) to use the ElevenLabs voice.' ;;
  text) quickshell ipc -p "$BLOK_ROOT/ui" call blok text "${2:?Provide a command}" ;;
  *) echo 'Usage: blok [show|toggle|hide|quit|foreground|theme <omarchy|liquid|halloween|diwali|minecraft|next>|voice <kokoro|elevenlabs|local|off>|elevenlabs-key|mic-test|click-test|heard|commands|mcp|handsfree on|off|setup|text "command"]' >&2; exit 2 ;;
esac
