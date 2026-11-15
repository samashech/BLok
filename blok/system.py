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
    if op in ('mute_on', 'mute_off'):          # say exactly which: a toggle can do the opposite
        run(['wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', '1' if op == 'mute_on' else '0'])
        return 'Sound muted' if op == 'mute_on' else 'Sound unmuted'
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
    method = {'toggle': 'playPause', 'next': 'next', 'previous': 'previous', 'pause': 'pause', 'play': 'play'}[op]
    run(['omarchy-shell', 'media', method])
    return {'toggle': 'Toggled playback', 'next': 'Next track', 'previous': 'Previous track', 'pause': 'Paused', 'play': 'Playing'}[op]


# name: (modifiers, key, done message, browser only)
SHORTCUTS = {
    'copy': (['ctrl'], 'c', 'Copied', False), 'cut': (['ctrl'], 'x', 'Cut', False), 'paste': (['ctrl'], 'v', 'Pasted', False),
    'undo': (['ctrl'], 'z', 'Undone', False), 'redo': (['ctrl', 'shift'], 'z', 'Redone', False), 'select_all': (['ctrl'], 'a', 'Selected everything', False),
    'close_tab': (['ctrl'], 'w', 'Closed the tab', True), 'reopen_tab': (['ctrl', 'shift'], 't', 'Reopened the last closed tab', True),
    'next_tab': (['ctrl'], 'Tab', 'Next tab', True), 'previous_tab': (['ctrl', 'shift'], 'Tab', 'Previous tab', True),
    'refresh': ([], 'F5', 'Refreshed the page', True), 'zoom_in': (['ctrl'], 'equal', 'Zoomed in', True),
    'zoom_out': (['ctrl'], 'minus', 'Zoomed out', True), 'zoom_reset': (['ctrl'], '0', 'Zoom reset', True), 'bookmark': (['ctrl'], 'd', 'Bookmarked', True),
}


def shortcut(name: str) -> str:
    """A keyboard shortcut. Browser ones go to the browser, even if something else is in front."""
    mods, key, done, browser_only = SHORTCUTS[name]
    if browser_only:
        from blok import browser
        browser.focus()
    args = ['wtype']
    for mod in mods:
        args += ['-M', mod]
    args += ['-k', key]
    for mod in reversed(mods):
        args += ['-m', mod]
    run(args)
    return done


def radio(kind: str, on: bool) -> str:
    if kind == 'wifi':
        run(['nmcli', 'radio', 'wifi', 'on' if on else 'off'])
        return 'Wi-Fi on' if on else 'Wi-Fi off'
    if shutil.which('bluetoothctl'):
        run(['bluetoothctl', 'power', 'on' if on else 'off'])
    else:
        run(['rfkill', 'unblock' if on else 'block', 'bluetooth'])
    return 'Bluetooth on' if on else 'Bluetooth off'


POWER = {'suspend': (['systemctl', 'suspend'], 'Going to sleep'), 'poweroff': (['systemctl', 'poweroff'], 'Shutting down'),
         'reboot': (['systemctl', 'reboot'], 'Restarting')}


def power(op: str) -> str:
    command, done = POWER[op]
    subprocess.Popen(command, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return done


def screenshot_window(hide_overlay=None) -> str:
    """The window in front, saved to Pictures and copied to the clipboard."""
    import os
    import time
    from pathlib import Path
    active = active_window()
    if not active.get('size'):
        raise RuntimeError('No window is focused.')
    (x, y), (w, h) = active['at'], active['size']
    folder = Path(os.environ.get('XDG_PICTURES_DIR') or Path.home() / 'Pictures')
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / time.strftime('screenshot-%Y-%m-%d_%H-%M-%S.png')
    if hide_overlay:
        hide_overlay(True)
    try:
        run(['grim', '-g', f'{x},{y} {w}x{h}', str(path)])
    finally:
        if hide_overlay:
            hide_overlay(False)
    if shutil.which('wl-copy'):
        with path.open('rb') as image:
            subprocess.run(['wl-copy', '--type', 'image/png'], stdin=image, timeout=5)
    return 'Screenshot of ' + (active.get('class') or 'the window') + ' saved to Pictures'


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
    if op == 'close' and app:
        # "close brave": that app's windows, not whatever happens to be in front
        clients = json.loads(run(['hyprctl', '-j', 'clients']))
        name = app.lower().replace(' ', '')
        matches = [c for c in clients if c.get('mapped') and (name in c.get('class', '').lower().replace(' ', '')
                                                               or name in c.get('initialClass', '').lower().replace(' ', ''))]
        if not matches:
            raise RuntimeError(f'No open window belongs to "{app}".')
        for target in matches:
            if not re.fullmatch(r'0x[0-9a-fA-F]+', target['address']):
                raise RuntimeError('Invalid window identifier')
            dispatch(f'hl.dsp.window.close({{ window = "address:{target["address"]}" }})')
        label = matches[0].get('class') or app
        return f'Closed {label}' + (f' ({len(matches)} windows)' if len(matches) > 1 else '')
    if op == 'minimize':
        raise RuntimeError('Hyprland has no minimize. Say "move this window to workspace 5" to put it out of the way.')
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


def press(key: str, times: int = 1) -> None:
    """Send a key to whichever window has focus (hands-free mode)."""
    if not re.fullmatch(r'[A-Za-z_]+', key):
        raise RuntimeError('Unsupported key')
    for _ in range(max(1, min(times, 20))):
        run(['wtype', '-k', key])


def type_text(text: str) -> None:
    """Type literal text into the focused window; control characters are refused."""
    if any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise RuntimeError('That text contains control characters.')
    run(['wtype', '-s', '15', '--', text])
