"""Desktop and system controls through Omarchy's own commands and Hyprland's Lua dispatchers."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import time



def run(args, timeout=8):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[:180] or result.stdout.strip()[:180] or f'{args[0]} failed')
    return result.stdout


def dispatch(expression: str):
    out = run(['hyprctl', 'dispatch', expression])
    if out.strip() and 'ok' not in out.lower():
        raise RuntimeError('Hyprland refused the request: ' + out.strip()[:150])


def volume_percent() -> int | None:
    try:
        out = run(['wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@'])
        m = re.search(r'([\d.]+)', out)
        return round(float(m[1]) * 100) if m else None
    except (OSError, RuntimeError):
        return None


def volume(op: str, level: int | None = None) -> str:
    if op == 'set':
        level = max(0, min(100, int(level or 0)))
        run(['wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', f'{level}%'])
    elif shutil.which('omarchy-audio-output-volume'):
        arg = {'up': 'raise', 'down': 'lower', 'mute': 'mute-toggle'}[op]
        run(['omarchy-audio-output-volume', arg])
    else:
        arg = {'up': ['set-volume', '-l', '1.0', '@DEFAULT_AUDIO_SINK@', '10%+'],
               'down': ['set-volume', '@DEFAULT_AUDIO_SINK@', '10%-'],
               'mute': ['set-mute', '@DEFAULT_AUDIO_SINK@', 'toggle']}[op]
        run(['wpctl', *arg])
    if op == 'mute':
        muted = 'MUTED' in run(['wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@'])
        return 'Sound muted' if muted else 'Sound unmuted'
    current = volume_percent()
    return f'Volume {current}%' if current is not None else 'Volume changed'


def brightness(op: str, level: int | None = None) -> str:
    value = {'up': '+10%', 'down': '10%-', 'set': f'{max(1, min(100, int(level or 50)))}%'}[op]
    if shutil.which('omarchy-brightness-display'):
        run(['omarchy-brightness-display', value])
    else:
        run(['brightnessctl', 'set', value])
    try:
        current, maximum = (int(run(['brightnessctl', flag]).strip()) for flag in ('get', 'max'))
        return f'Brightness {round(current * 100 / maximum)}%'
    except (OSError, RuntimeError, ValueError):
        return 'Brightness changed'


def media(op: str) -> str:
    method = {'toggle': 'playPause', 'next': 'next', 'previous': 'previous'}[op]
    run(['omarchy-shell', 'media', method])
    return {'toggle': 'Toggled playback', 'next': 'Next track', 'previous': 'Previous track'}[op]


def lock() -> str:
    if shutil.which('omarchy-system-lock'):
        subprocess.Popen(['omarchy-system-lock'], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        run(['loginctl', 'lock-session'])
    return 'Locking the screen'


def active_window() -> dict:
    return json.loads(run(['hyprctl', '-j', 'activewindow']) or '{}')


def window(op: str, workspace: str | None = None, app: str | None = None) -> str:
    if op == 'focus':
        clients = json.loads(run(['hyprctl', '-j', 'clients']))
        name = (app or '').lower()
        matches = [c for c in clients if c.get('mapped') and (name in c.get('class', '').lower() or name in c.get('title', '').lower())]
        if not matches:
            raise RuntimeError(f'No open window matches "{app}".')
        target = min(matches, key=lambda c: c.get('focusHistoryID', 999))
        if not re.fullmatch(r'0x[0-9a-fA-F]+', target['address']):
            raise RuntimeError('Invalid window identifier')
        dispatch(f'hl.dsp.focus({{window="address:{target["address"]}"}})')
        return 'Switched to ' + (target.get('class') or target.get('title'))
    active = active_window()
    if not active.get('address'):
        raise RuntimeError('No window is focused.')
    label = active.get('class') or active.get('title') or 'window'
    if op == 'close':
        dispatch('hl.dsp.window.close()')
        return 'Closed ' + label
    if op == 'fullscreen':
        dispatch('hl.dsp.window.fullscreen({ mode = "fullscreen" })')
        return 'Toggled fullscreen for ' + label
    if op == 'float':
        dispatch('hl.dsp.window.float({ action = "toggle" })')
        return 'Toggled floating for ' + label
    if op == 'move':
        if not (workspace and workspace.isdigit() and 1 <= int(workspace) <= 10):
            raise RuntimeError('Say a workspace number from one to ten.')
        dispatch(f'hl.dsp.window.move({{ workspace = "{workspace}" }})')
        return f'Moved {label} to workspace {workspace}'
    raise RuntimeError('Unsupported window action')


def battery() -> str:
    batteries = sorted(Path('/sys/class/power_supply').glob('BAT*'))
    if not batteries:
        return 'No battery found; this machine is on mains power.'
    capacity = (batteries[0] / 'capacity').read_text().strip()
    status = (batteries[0] / 'status').read_text().strip().lower()
    return f'Battery is at {capacity}% and {status}.'


def answer(topic: str) -> str:
    now = time.localtime()
    if topic == 'time':
        return 'It is ' + time.strftime('%-I:%M %p', now) + '.'
    if topic == 'date':
        return 'Today is ' + time.strftime('%A, %B %-d, %Y', now) + '.'
    if topic == 'battery':
        return battery()
    raise RuntimeError('Unsupported question')
