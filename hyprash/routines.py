"""Reusable routines with explicit preconditions and bounded actions."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re

from hyprash.commands import Action

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("HYPRASH_DATA", ROOT / "data"))

VALID_ACTION_KINDS = {
    'open', 'new_note', 'title', 'write', 'photo', 'workspace',
    'address', 'browser_type', 'browser_key', 'url', 'web_task',
    'ui_control', 'obsidian_note', 'stop'
}
VALID_PRECONDITION_KINDS = {'browser', 'vault', 'app', 'notes'}
UNSAFE_WORD = re.compile(r'\b(?:delete|erase|format|destroy|reboot|shutdown)\b', re.I)


@dataclass(frozen=True)
class Precondition:
    kind: str  # 'browser', 'vault', 'app', 'notes'
    target: str = ''

    def to_dict(self):
        d = {'kind': self.kind}
        if self.target:
            d['target'] = self.target
        return d

    @classmethod
    def from_dict(cls, data):
        return cls(kind=data.get('kind', ''), target=data.get('target', ''))

    @property
    def type(self) -> str:
        return self.kind


@dataclass(frozen=True)
class Routine:
    name: str
    description: str
    steps: tuple[Action, ...]
    preconditions: tuple[Precondition, ...] = ()

    def to_dict(self):
        return {
            'name': self.name,
            'description': self.description,
            'preconditions': [p.to_dict() for p in self.preconditions],
            'steps': [{'kind': a.kind, 'value': a.value} for a in self.steps],
        }

    @classmethod
    def from_dict(cls, data):
        return validate_routine_dict(data)


BUILTIN_ROUTINES: dict[str, Routine] = {
    'morning': Routine(
        name='morning',
        description='Morning briefing: search weather and open notes',
        preconditions=(Precondition('browser'), Precondition('notes')),
        steps=(
            Action('url', 'https://www.google.com/search?q=weather'),
            Action('open', 'notes'),
        ),
    ),
    'daily_standup': Routine(
        name='daily_standup',
        description='Daily standup: open notes and start a standup note',
        preconditions=(Precondition('notes'),),
        steps=(
            Action('open', 'notes'),
            Action('new_note', 'Daily Standup'),
        ),
    ),
    'focus': Routine(
        name='focus',
        description='Focus session: play focus music on Spotify and open notes',
        preconditions=(Precondition('browser'), Precondition('notes')),
        steps=(
            Action('web_task', json.dumps({'action': 'play', 'site': 'spotify', 'query': 'lofi beats'})),
            Action('open', 'notes'),
        ),
    ),
    'code_review': Routine(
        name='code_review',
        description='Code review: open GitHub and open terminal',
        preconditions=(Precondition('browser'), Precondition('app', 'terminal')),
        steps=(
            Action('url', 'https://github.com'),
            Action('open', 'terminal'),
        ),
    ),
}

ROUTINE_ALIASES = {
    'morning': 'morning',
    'morning routine': 'morning',
    'morning briefing': 'morning',
    'daily standup': 'daily_standup',
    'standup': 'daily_standup',
    'standup routine': 'daily_standup',
    'focus': 'focus',
    'focus session': 'focus',
    'focus music': 'focus',
    'focus routine': 'focus',
    'deep work': 'focus',
    'code review': 'code_review',
    'code review routine': 'code_review',
}


def validate_routine_dict(data: dict) -> Routine:
    if not isinstance(data, dict):
        raise ValueError("Routine definition must be a JSON object.")
    name = data.get("name", "")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9_-]{1,64}", name):
        raise ValueError(f"Invalid routine name: {name}")
    description = data.get("description", "")
    if not isinstance(description, str) or not description.strip() or len(description) > 200:
        raise ValueError("Routine description must be a non-empty string up to 200 characters.")
    raw_preconditions = data.get("preconditions", [])
    if not isinstance(raw_preconditions, list):
        raise ValueError("Preconditions must be a list.")
    preconditions = []
    for item in raw_preconditions:
        if not isinstance(item, dict):
            raise ValueError("Precondition must be a JSON object.")
        p_kind = item.get("kind", "")
        if p_kind not in VALID_PRECONDITION_KINDS:
            raise ValueError(f"Unsupported precondition kind: {p_kind}")
        p_target = item.get("target", "")
        if not isinstance(p_target, str):
            raise ValueError("Precondition target must be a string.")
        preconditions.append(Precondition(p_kind, p_target))
    raw_steps = data.get("steps", [])
    if not isinstance(raw_steps, list) or not (1 <= len(raw_steps) <= 8):
        raise ValueError("Routine must contain between 1 and 8 steps.")
    steps = []
    for item in raw_steps:
        if not isinstance(item, dict):
            raise ValueError("Step must be a JSON object.")
        kind = item.get("kind", "")
        if kind not in VALID_ACTION_KINDS:
            raise ValueError(f"Unsupported step action kind: {kind}")
        value = item.get("value", "")
        if not isinstance(value, str):
            raise ValueError("Step value must be a string.")
        if UNSAFE_WORD.search(value):
            raise ValueError("Unsafe content in routine step.")
        if kind in ("web_task", "ui_control", "obsidian_note"):
            try:
                json.loads(value)
            except Exception:
                raise ValueError(f"Step value for {kind} must be a valid JSON string.")
        steps.append(Action(kind, value))
    return Routine(
        name=name,
        description=description,
        steps=tuple(steps),
        preconditions=tuple(preconditions),
    )


def list_routines(data_dir=None) -> dict[str, Routine]:
    routines = dict(BUILTIN_ROUTINES)
    routines_dir = (Path(data_dir) if data_dir else DATA) / "routines"
    if routines_dir.is_dir():
        for path in sorted(routines_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text())
                routine = validate_routine_dict(data)
                routines[routine.name] = routine
            except Exception:
                continue
    return routines


def get_routine(name_or_alias: str, data_dir=None) -> Routine | None:
    cleaned = name_or_alias.strip().lower().replace('-', '_')
    resolved = ROUTINE_ALIASES.get(cleaned, cleaned)
    routines = list_routines(data_dir)
    return routines.get(resolved) or routines.get(cleaned)


def save_routine_dict(data: dict, data_dir=None) -> Routine:
    routine = validate_routine_dict(data)
    routines_dir = (Path(data_dir) if data_dir else DATA) / "routines"
    routines_dir.mkdir(parents=True, exist_ok=True)
    path = routines_dir / f"{routine.name}.json"
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(routine.to_dict(), indent=2))
    temp.replace(path)
    return routine


def check_precondition(precondition: Precondition, backend=None) -> tuple[bool, str]:
    kind = precondition.kind
    target = precondition.target
    if kind == 'browser':
        try:
            from hyprash import browser
            res = browser.request({'action': 'ping'})
            if res.get('message') == 'Brave connected':
                return True, ''
            return False, 'Brave browser extension is not connected'
        except Exception as error:
            return False, f'Brave browser bridge unavailable: {error}'
    elif kind == 'vault':
        from hyprash import desktop
        vault = desktop.obsidian_vault()
        if vault and vault[1].is_dir():
            return True, ''
        return False, 'No configured Obsidian vault found'
    elif kind == 'app':
        from hyprash.desktop import catalog
        apps = catalog()
        standard = ('browser', 'terminal', 'files', 'code', 'notes', 'camera', 'obsidian', 'hyprash_notes', 'hyprash_camera')
        if target in standard or target in apps:
            return True, ''
        return False, f'Application "{target}" is not installed or available'
    elif kind == 'notes':
        return True, ''
    return False, f'Unknown precondition kind: {kind}'


def check_routine_preconditions(routine: Routine, backend=None) -> tuple[bool, str]:
    for p in routine.preconditions:
        ok, reason = check_precondition(p, backend)
        if not ok:
            return False, reason
    return True, ''
