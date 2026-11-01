"""Window choreography for Hyprland: arrange apps, save and restore setups, focus mode.

Every action targets windows by address through Hyprland's Lua dispatchers
(`hl.dsp.window.move({ ..., window = "address:0x…" })`), so nothing depends on
which window happens to be focused.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time

from blok.paths import CONFIG, DATA

LAYOUTS = CONFIG / 'layouts'
FOCUS_STATE = DATA / 'focus-state.json'
FOCUS_WORKSPACE = 'special:blok-focus'
# Apps hidden by focus mode; extend with BLOK_FOCUS_HIDE="class1|class2".
DISTRACTIONS = r'discord|vesktop|telegram|slack|signal|whatsapp|element|teams|zoom|thunderbird|steam|lutris|heroic'
ALIASES = {'code': 'code|vscodium|code-oss', 'vs code': 'code|vscodium|code-oss', 'editor': 'code|vscodium|zed|nvim|helix',
           'browser': 'brave|chromium|chrome|firefox|zen', 'terminal': 'foot|kitty|alacritty|ghostty|wezterm',
           'files': 'nautilus|thunar|dolphin|nemo', 'file manager': 'nautilus|thunar|dolphin|nemo', 'notes': 'obsidian',
           'music': 'spotify', 'chat': 'discord|vesktop|telegram|slack|signal'}


def hypr(*args):
    result = subprocess.run(['hyprctl', *args], capture_output=True, text=True, timeout=8)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[:160] or 'hyprctl failed')
    return result.stdout


def dispatch(expression: str):
    out = hypr('dispatch', expression).strip()
    if out and 'ok' not in out.lower():
        raise RuntimeError('Hyprland refused: ' + out[:150])


def clients() -> list[dict]:
    return [c for c in json.loads(hypr('-j', 'clients')) if c.get('mapped') and re.fullmatch(r'0x[0-9a-fA-F]+', c.get('address', ''))]


def active_workspace() -> dict:
    return json.loads(hypr('-j', 'activeworkspace'))


def window_arg(client: dict) -> str:
    return f'window = "address:{client["address"]}"'


def find(app: str, among: list[dict] | None = None) -> list[dict]:
    """Windows whose class or title matches a spoken app name, most recently used first."""
    name = app.lower().strip()
    pattern = ALIASES.get(name, re.escape(name))
    found = [c for c in (among if among is not None else clients())
             if re.search(pattern, (c.get('class') or '') + ' ' + (c.get('initialClass') or ''), re.I)
             or re.search(re.escape(name), c.get('title') or '', re.I)]
    return sorted(found, key=lambda c: c.get('focusHistoryID', 999))


def label(client: dict) -> str:
    return (client.get('class') or client.get('title') or 'window').split('.')[-1]


def move_to(client: dict, workspace: str, follow: bool = False):
    dispatch(f'hl.dsp.window.move({{ workspace = "{workspace}", follow = {str(follow).lower()}, {window_arg(client)} }})')


def place(client: dict, x: int, y: int, width: int, height: int):
    dispatch(f'hl.dsp.window.float({{ action = "enable", {window_arg(client)} }})')
    dispatch(f'hl.dsp.window.move({{ x = {x}, y = {y}, relative = false, {window_arg(client)} }})')
    dispatch(f'hl.dsp.window.resize({{ x = {width}, y = {height}, {window_arg(client)} }})')


def usable_area() -> tuple[int, int, int, int]:
    monitor = next(m for m in json.loads(hypr('-j', 'monitors')) if m.get('focused'))
    left, top, right, bottom = (monitor.get('reserved') or [0, 0, 0, 0])[:4]
    scale = monitor.get('scale') or 1
    width, height = int(monitor['width'] / scale), int(monitor['height'] / scale)
    gap = 10
    return (monitor['x'] + left + gap, monitor['y'] + top + gap,
            width - left - right - 2 * gap, height - top - bottom - 2 * gap)


def empty_workspace() -> str:
    used = {c['workspace']['id'] for c in clients()}
    return str(next(n for n in range(1, 11) if n not in used)) if len(used) < 10 else str(active_workspace()['id'])


# ---------------------------------------------------------------- arranging
def arrange(left: str, right: str) -> str:
    """Two apps side by side on a free workspace: `left` on the left, `right` on the right."""
    windows = clients()
    a, b = find(left, windows), find(right, windows)
    if not a:
        raise RuntimeError(f'No open window matches "{left}".')
    if not b:
        raise RuntimeError(f'No open window matches "{right}".')
    first, second = a[0], next((c for c in b if c['address'] != a[0]['address']), None)
    if second is None:
        raise RuntimeError(f'"{left}" and "{right}" are the same window.')
    workspace = empty_workspace()
    for client in (first, second):
        dispatch(f'hl.dsp.window.float({{ action = "disable", {window_arg(client)} }})')
        move_to(client, workspace)
    dispatch(f'hl.dsp.focus({{ workspace = "{workspace}" }})')
    time.sleep(0.25)
    now = {c['address']: c for c in clients()}
    l, r = now.get(first['address']), now.get(second['address'])
    side_by_side = l and r and abs(l['at'][1] - r['at'][1]) < 40
    if side_by_side and l['at'][0] > r['at'][0]:
        dispatch(f'hl.dsp.window.swap({{ direction = "l", {window_arg(r)} }})')
    elif not side_by_side:
        # The layout stacked them; fall back to exact halves of the screen.
        x, y, width, height = usable_area()
        half = (width - 10) // 2
        place(first, x, y, half, height)
        place(second, x + half + 10, y, half, height)
    return f'{label(first)} on the left, {label(second)} on the right (workspace {workspace})'


# ---------------------------------------------------------------- saved setups
def _slug(name: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    if not slug:
        raise RuntimeError('Give the layout a name, like "save this layout as coding".')
    return slug


def _command_for(client: dict) -> list[str] | None:
    """How to reopen a window's app: its desktop entry, else the process command line."""
    from blok.desktop import catalog
    wanted = (client.get('initialClass') or client.get('class') or '').lower()
    for name, stem in catalog().items():
        if stem.lower() == wanted or stem.lower().split('.')[-1] == wanted.split('.')[-1] or name == wanted:
            return ['gtk-launch', stem]
    try:
        argv = Path(f'/proc/{client["pid"]}/cmdline').read_bytes().split(b'\0')
        argv = [a.decode() for a in argv if a]
        return argv if argv and shutil.which(argv[0]) else None
    except (OSError, KeyError, UnicodeDecodeError):
        return None


def save_layout(name: str) -> str:
    slug = _slug(name)
    windows = [c for c in clients() if not str(c['workspace'].get('name', '')).startswith('special:')]
    if not windows:
        raise RuntimeError('There are no windows to save.')
    saved = {'name': name, 'active_workspace': active_workspace().get('name'), 'windows': [
        {'class': c.get('class'), 'initialClass': c.get('initialClass'), 'title': c.get('title'),
         'workspace': c['workspace'].get('name'), 'floating': c.get('floating', False), 'at': c.get('at'),
         'size': c.get('size'), 'command': _command_for(c)}
        for c in sorted(windows, key=lambda c: (str(c['workspace'].get('name')), c['at'][0], c['at'][1]))]}
    LAYOUTS.mkdir(parents=True, exist_ok=True)
    (LAYOUTS / f'{slug}.json').write_text(json.dumps(saved, indent=2) + '\n')
    count = len(saved['windows'])
    return f'Saved {count} window{"s" if count != 1 else ""} as {name}'


def layouts() -> list[str]:
    return sorted(p.stem for p in LAYOUTS.glob('*.json')) if LAYOUTS.is_dir() else []


def has_layout(name: str) -> bool:
    try:
        return (LAYOUTS / f'{_slug(name)}.json').exists()
    except RuntimeError:
        return False


def _wait_for(cls: str, known: set[str], seconds: float = 10) -> dict | None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        for c in clients():
            if c['address'] not in known and (c.get('class') == cls or c.get('initialClass') == cls):
                return c
        time.sleep(0.25)
    return None


def restore_layout(name: str) -> str:
    path = LAYOUTS / f'{_slug(name)}.json'
    if not path.exists():
        options = ', '.join(layouts()) or 'none yet'
        raise RuntimeError(f'There is no layout called "{name}". Saved layouts: {options}.')
    saved = json.loads(path.read_text())
    used, opened, missing = set(), 0, []
    for entry in saved['windows']:
        current = clients()
        match = next((c for c in current if c['address'] not in used and c.get('class') == entry.get('class')
                      and c.get('title') == entry.get('title')), None) \
            or next((c for c in current if c['address'] not in used and c.get('class') == entry.get('class')), None)
        if match is None and entry.get('command'):
            subprocess.Popen(entry['command'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            match = _wait_for(entry.get('class'), {c['address'] for c in current})
            opened += bool(match)
        if match is None:
            missing.append(entry.get('class') or '?')
            continue
        used.add(match['address'])
        move_to(match, entry['workspace'])
        if entry.get('floating') and entry.get('at') and entry.get('size'):
            place(match, *entry['at'], *entry['size'])
        else:
            dispatch(f'hl.dsp.window.float({{ action = "disable", {window_arg(match)} }})')
    if saved.get('active_workspace'):
        dispatch(f'hl.dsp.focus({{ workspace = "{saved["active_workspace"]}" }})')
    message = f'Restored {saved["name"]}: {len(used)} window{"s" if len(used) != 1 else ""}'
    message += f', opened {opened}' if opened else ''
    message += f'; could not open {", ".join(missing)}' if missing else ''
    return message


# ---------------------------------------------------------------- focus mode
_focus_timer = {'timer': None}


def _dnd(on: bool):
    """Omarchy's do-not-disturb is a toggle that prints the new state; flip until it matches."""
    if not shutil.which('omarchy-shell'):
        return
    for _ in range(2):
        state = subprocess.run(['omarchy-shell', 'notifications', 'toggleDnd'], capture_output=True, text=True, timeout=5).stdout.strip()
        if state == ('on' if on else 'off'):
            break
    subprocess.run(['omarchy-shell', '-q', 'omarchy.indicators', 'refresh'], capture_output=True, timeout=5)


def focus_on(minutes: int | None = None, on_end=None) -> str:
    if FOCUS_STATE.exists():
        return 'Focus mode is already on. Say "end focus mode" to stop.'
    pattern = os.environ.get('BLOK_FOCUS_HIDE', DISTRACTIONS)
    hidden = []
    for c in clients():
        if re.search(pattern, (c.get('class') or '') + ' ' + (c.get('initialClass') or ''), re.I) \
                and not str(c['workspace'].get('name', '')).startswith('special:'):
            hidden.append({'address': c['address'], 'workspace': c['workspace']['name'], 'class': label(c)})
            move_to(c, FOCUS_WORKSPACE)
    _dnd(True)
    FOCUS_STATE.parent.mkdir(parents=True, exist_ok=True)
    FOCUS_STATE.write_text(json.dumps({'hidden': hidden, 'started': time.time(), 'minutes': minutes}) + '\n')
    if minutes:
        timer = threading.Timer(minutes * 60, lambda: on_end(focus_off(finished=True)) if on_end else focus_off(finished=True))
        timer.daemon = True
        timer.start()
        _focus_timer['timer'] = timer
    names = ', '.join(sorted({h['class'] for h in hidden}))
    message = 'Focus mode on: notifications silenced'
    message += f', hid {names}' if names else ''
    return message + (f'. I\'ll tell you when {minutes} minutes are up.' if minutes else '.')


def focus_off(finished: bool = False) -> str:
    if _focus_timer['timer']:
        _focus_timer['timer'].cancel()
        _focus_timer['timer'] = None
    if not FOCUS_STATE.exists():
        return 'Focus mode is not on.'
    state = json.loads(FOCUS_STATE.read_text())
    present = {c['address']: c for c in clients()}
    for item in state.get('hidden', []):
        client = present.get(item['address'])
        if client:
            move_to(client, item['workspace'])
    _dnd(False)
    FOCUS_STATE.unlink(missing_ok=True)
    minutes = round((time.time() - state.get('started', time.time())) / 60)
    return (f'Focus time is over after {minutes} minutes.' if finished else f'Focus mode off after {minutes} minutes.') \
        + ' Notifications and hidden apps are back.'


# ---------------------------------------------------------------- questions
def where(app: str) -> str:
    found = find(app)
    if not found:
        return f'No open window matches "{app}".'
    spots = sorted({str(c['workspace']['name']).replace('special:blok-focus', 'hidden by focus mode') for c in found})
    return f'{label(found[0])} is on workspace {", ".join(spots)}'


def on_workspace(number: str) -> str:
    here = [label(c) for c in clients() if str(c['workspace'].get('name')) == str(number)]
    return f'Workspace {number}: ' + (', '.join(here) if here else 'empty')


def close_others(keep: str) -> tuple[list[dict], str]:
    """Windows on the current workspace other than `keep` (for an approval card)."""
    workspace = active_workspace().get('id')
    here = [c for c in clients() if c['workspace'].get('id') == workspace]
    keep_ids = {c['address'] for c in find(keep, here)}
    if not keep_ids:
        raise RuntimeError(f'No window on this workspace matches "{keep}".')
    others = [c for c in here if c['address'] not in keep_ids]
    return others, ', '.join(label(c) for c in others)


def close(windows: list[dict]) -> str:
    for c in windows:
        dispatch(f'hl.dsp.window.close({{ {window_arg(c)} }})')
    return f'Closed {len(windows)} window{"s" if len(windows) != 1 else ""}'


# ---------------------------------------------------------------- what people say
def intent(text: str) -> dict | None:
    """Phrase rules for window choreography; returns a tool request or None."""
    from blok.router import number
    t = text.strip().strip('.!?')
    side = r'(?:put |place |move |keep )?(?:the |my )?'
    m = re.fullmatch(side + r'(?P<a>.+?) (?:on|to) the (?P<sa>left|right)(?: side)?,?(?: and)? '
                     + side + r'(?P<b>.+?) (?:on|to) the (?P<sb>left|right)(?: side)?', t, re.I)
    if m and m['sa'].lower() != m['sb'].lower():
        left, right = (m['a'], m['b']) if m['sa'].lower() == 'left' else (m['b'], m['a'])
        return {'tool': 'arrange', 'left': left.strip(), 'right': right.strip()}
    m = re.fullmatch(r'(?:put |place )?(?:the |my )?(?P<a>.+?) and (?:the |my )?(?P<b>.+?) side by side', t, re.I)
    if m:
        return {'tool': 'arrange', 'left': m['a'].strip(), 'right': m['b'].strip()}
    m = re.fullmatch(r'(?:save|remember|store|keep)(?: this| the| my| current| these)? (?:layout|setup|workspace|windows|arrangement|window layout)'
                     r'(?: as| called| named| for)? (?P<name>[\w -]+?)(?: layout| setup| mode)?', t, re.I)
    if m:
        return {'tool': 'layout_save', 'name': m['name'].strip()}
    if re.fullmatch(r'(?:save|remember|store)(?: how)?(?: my| the| these)? windows(?: are (?:arranged|set up|laid out))?(?: right now)?|save (?:this|the) layout', t, re.I):
        return {'tool': 'layout_save', 'name': ''}
    if re.fullmatch(r'(?:list|show|what are)(?: me)?(?: my| the)? (?:saved )?(?:layouts|setups)|what (?:layouts|setups) do i have', t, re.I):
        return {'tool': 'layout_list'}
    m = re.fullmatch(r"(?:start |turn on |enter |go into |begin )?focus mode(?: on)?(?: for (?P<m1>.+?) minutes?)?|"
                     r"(?:i (?:need|want) to|time to|let me|help me) (?:focus|concentrate)(?: for (?P<m2>.+?) minutes?)?|"
                     r"focus for (?P<m3>.+?) minutes?|focus(?: time)?|do not disturb mode|(?:start |begin )?deep work(?: mode)?(?: for (?P<m4>.+?) minutes?)?", t, re.I)
    if m:
        amount = m['m1'] or m['m2'] or m['m3'] or m['m4']
        return {'tool': 'focus', 'on': True, 'minutes': number(amount) if amount else None}
    if re.fullmatch(r"(?:stop|end|exit|turn off|quit|leave|cancel) (?:focus(?:ing| mode)?|deep work)|focus mode off|"
                    r"(?:alright |ok |okay )?i'?m (?:done|finished)(?: focusing| with (?:focus(?: mode)?|deep work|work))?(?:,? bring (?:my stuff|everything|it all) back)?|"
                    r"done focusing|bring (?:my stuff|everything|my apps) back", t, re.I):
        return {'tool': 'focus', 'on': False}
    m = re.fullmatch(r"what(?:'s| is| apps are| windows are) (?:open )?on workspace (?P<n>\w+)", t, re.I)
    if m and number(m['n']):
        return {'tool': 'workspace_info', 'workspace': str(number(m['n']))}
    m = re.fullmatch(r"close (?:everything|all(?: the| my)? (?:windows|apps)|all other (?:windows|apps)|the rest) (?:except|but) (?:the |my )?(?P<keep>.+?)(?: window)?", t, re.I)
    if m:
        return {'tool': 'close_others', 'keep': m['keep'].strip()}
    m = re.fullmatch(r"(?:restore|load|bring back|set up|start|switch to|go to|open)(?: my| the)? (?P<name>[\w -]+?)(?: layout| setup| mode| workspace)?", t, re.I) \
        or re.fullmatch(r"(?P<name>[\w -]+?) (?:mode|layout|setup)", t, re.I)
    if m and has_layout(m['name'].strip()):
        return {'tool': 'layout_restore', 'name': m['name'].strip()}
    m = re.fullmatch(r"where(?:'s| is| are)(?: my| the)? (?P<app>[\w .-]+?)(?: window| app)?", t, re.I)
    if m:
        try:
            if find(m['app']):
                return {'tool': 'where', 'app': m['app'].strip()}
        except (RuntimeError, OSError, subprocess.SubprocessError, ValueError):
            pass
    return None
