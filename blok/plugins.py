"""Drop-in commands: a .toml file for a shell action, a .py file for anything else.

BLoK looks in commands/ (shipped with BLoK) and ~/.config/blok/commands/ (yours,
which wins on a name clash). Files are re-read when they change, so a new
command works on the next thing you say. Run `./blok.sh commands` to list them.

TOML command:

    description = "Take a screenshot"            # what Laya sees; keep it short
    phrases = ["take a screenshot", "screenshot [the screen]", "grab the screen"]
    run = "omarchy-capture-screenshot"
    reply = "Screenshot taken"                    # optional; {slots} allowed
    confirm = false                               # true shows an approval card first

Phrases are matched against what was said, ignoring case and fillers.
`[words]` are optional and `{name}` captures a slot, passed shell-quoted to `run`
("set the volume to {level}" → run = "wpctl set-volume @DEFAULT_AUDIO_SINK@ {level}%").

Python command:

    from blok.plugins import command

    @command("Roll a dice", phrases=["roll a dice", "roll a {sides} sided dice"])
    def roll(sides="6"):
        import random
        return f"You rolled {random.randint(1, int(sides))}."

The function's return value is shown and spoken; raising an exception reports an error.
"""
from dataclasses import dataclass, field
import importlib.util
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import threading
import tomllib
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'blok'
SEARCH = [ROOT / 'commands', CONFIG / 'commands']


@dataclass
class Command:
    name: str
    description: str
    phrases: list[str]
    patterns: list[re.Pattern] = field(default_factory=list)
    run: str | None = None
    handler: Callable | None = None
    reply: str = ''
    confirm: bool = False
    source: Path | None = None

    @property
    def slots(self) -> set[str]:
        return {slot for phrase in self.phrases for slot in re.findall(r'\{(\w+)\}', phrase)}


def phrase_pattern(phrase: str) -> re.Pattern:
    """"set a timer for {minutes} [minutes]" → a full-match regex with a named group."""
    out, i = [], 0
    for token in re.finditer(r'\{(\w+)\}|\[([^\]]+)\]', phrase):
        out.append(re.escape(phrase[i:token.start()]))
        out.append(f'(?P<{token[1]}>.+?)' if token[1] else f'(?:{re.escape(token[2])})?')
        i = token.end()
    out.append(re.escape(phrase[i:]))
    source = re.sub(r'(?:\\ )+', r'\\s*', ''.join(out).strip())   # optional parts leave flexible spaces
    return re.compile(source + r'[.!?]*', re.I)


_pending: list[Command] = []


def command(description: str, phrases: list[str], confirm: bool = False, name: str | None = None):
    """Decorator for Python commands (see module docstring)."""
    def register(function):
        _pending.append(Command(name or function.__name__, description, list(phrases),
                                [phrase_pattern(p) for p in phrases], handler=function, confirm=confirm))
        return function
    return register


_lock = threading.Lock()
_state = {'signature': None, 'commands': {}, 'errors': []}


def _files() -> list[Path]:
    found = []
    for folder in SEARCH:
        if folder.is_dir():
            found += sorted(p for p in folder.iterdir() if p.suffix in ('.toml', '.py') and not p.name.startswith(('_', '.')))
    return found


def _load_file(path: Path) -> list[Command]:
    if path.suffix == '.toml':
        data = tomllib.loads(path.read_text())
        phrases = data.get('phrases') or []
        if not (data.get('description') and phrases and data.get('run')):
            raise ValueError('needs description, phrases and run')
        return [Command(data.get('name', path.stem), data['description'], list(phrases), [phrase_pattern(p) for p in phrases],
                        run=data['run'], reply=data.get('reply', ''), confirm=bool(data.get('confirm', False)), source=path)]
    _pending.clear()
    spec = importlib.util.spec_from_file_location(f'blok_command_{path.stem}', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(spec.name, None)
    spec.loader.exec_module(module)
    loaded = list(_pending)
    _pending.clear()
    for item in loaded:
        item.source = path
    if not loaded:
        raise ValueError('defines no @command')
    return loaded


def commands() -> dict[str, Command]:
    """All commands, reloaded when any file is added, removed or edited."""
    files = _files()
    signature = tuple((str(p), p.stat().st_mtime_ns) for p in files)
    with _lock:
        if signature != _state['signature']:
            loaded, errors = {}, []
            for path in files:
                try:
                    for item in _load_file(path):
                        loaded[item.name] = item   # ~/.config/blok/commands comes last and wins
                except Exception as error:  # a broken plugin must not break BLoK
                    errors.append(f'{path.name}: {error}')
            _state.update(signature=signature, commands=loaded, errors=errors)
        return _state['commands']


def errors() -> list[str]:
    commands()
    return list(_state['errors'])


def match(text: str) -> tuple[Command, dict] | None:
    said = text.strip()
    for item in commands().values():
        for pattern in item.patterns:
            found = pattern.fullmatch(said)
            if found:
                return item, {k: v.strip() for k, v in found.groupdict().items() if v}
    return None


def run(item: Command, args: dict) -> str:
    missing = item.slots - set(args)
    if item.handler is not None:
        result = item.handler(**args)
        return str(result) if result else item.description
    if missing and any('{' + slot + '}' in (item.run or '') for slot in missing):
        raise RuntimeError(f'Say it like "{item.phrases[0]}".')
    line = item.run
    for key, value in args.items():
        line = line.replace('{' + key + '}', shlex.quote(value))
    result = subprocess.run(['bash', '-c', line], capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f'{item.description} failed: ' + (result.stderr.strip() or result.stdout.strip())[:160])
    reply = item.reply or item.description
    for key, value in args.items():
        reply = reply.replace('{' + key + '}', value)
    return reply


if __name__ == '__main__':
    # Plugins import blok.plugins; list through that module, not this __main__ copy.
    from blok.plugins import commands, errors
    found = commands()
    for item in found.values():
        where = item.source.parent if item.source else '?'
        print(f'{item.name:18} {item.description:34} “{item.phrases[0]}”  ({where})')
    for problem in errors():
        print('not loaded:', problem)
    if not found:
        print('No commands found in', ', '.join(str(p) for p in SEARCH))
