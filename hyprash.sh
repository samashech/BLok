#!/usr/bin/env bash
set -euo pipefail
HYPRASH_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export HYPRASH_ROOT
cd "$HYPRASH_ROOT"
case "${1:-show}" in
  show|toggle)
    action="${1:-show}"
    [[ "$action" == show ]] && action=present
    for attempt in {1..50}; do
      status="$(quickshell ipc -p "$HYPRASH_ROOT/ui" call hyprash status 2>/dev/null || true)"
      if [[ "$status" == \{* ]]; then
        quickshell ipc -p "$HYPRASH_ROOT/ui" call hyprash "$action"
        exit 0
      fi
      if [[ "$attempt" == 1 ]]; then quickshell -d -n -p "$HYPRASH_ROOT/ui"; fi
      sleep 0.1
    done
    echo 'Hyprash did not become ready; run ./hyprash.sh foreground for details.' >&2
    exit 1
    ;;
  ptt-start) exec python3 scripts/ptt.py start ;;
  ptt-finish) exec python3 scripts/ptt.py finish ;;
  foreground) exec quickshell -n -p "$HYPRASH_ROOT/ui" ;;
  hide|quit|status) quickshell ipc -p "$HYPRASH_ROOT/ui" call hyprash "$1" ;;
  theme) quickshell ipc -p "$HYPRASH_ROOT/ui" call hyprash appearance "${2:?Choose omarchy or liquid}" ;;
  text) quickshell ipc -p "$HYPRASH_ROOT/ui" call hyprash text "${2:?Provide a command}" ;;
  *) echo 'Usage: ./hyprash.sh [show|toggle|hide|quit|foreground|theme omarchy|theme liquid|text "command"]' >&2; exit 2 ;;
esac
