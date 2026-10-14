"""Auto-recording session actions into reusable routines.

Simular-inspired action recording, session history ring buffer,
precondition inference, and immediate routine persistence.
"""
from collections import deque
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import time
from typing import Any

from hyprash.commands import Action
from hyprash.routines import Routine, Precondition, save_routine_dict, list_routines

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("HYPRASH_DATA", ROOT / "data"))


def infer_routine_preconditions(steps: list[Any]) -> list[Precondition]:
    """Infer required environment preconditions from action steps."""
    preconditions = []
    has_browser = False
    has_vault = False
    has_notes = False
    apps = set()

    for s in steps:
        kind = getattr(s, "kind", getattr(s, "action_type", ""))
        value = getattr(s, "value", getattr(s, "action_value", ""))

        if kind in ("web_task", "url", "address", "browser_type", "browser_key"):
            has_browser = True
        elif kind == "obsidian_note":
            has_vault = True
        elif kind in ("new_note", "title", "write"):
            has_notes = True
        elif kind == "open":
            if value in ("notes", "hyprash_notes"):
                has_notes = True
            elif value == "obsidian":
                has_vault = True
            elif value == "browser":
                has_browser = True
            else:
                apps.add(value)

    if has_browser:
        preconditions.append(Precondition("browser"))
    if has_vault:
        preconditions.append(Precondition("vault"))
    if has_notes:
        preconditions.append(Precondition("notes"))
    for app in sorted(apps):
        preconditions.append(Precondition("app", app))

    return preconditions


def compile_routine(name: str, steps: list[Any], description: str = "", data_dir=None) -> Routine:
    """Compile verified steps into a validated Routine and save to routines directory."""
    clean_name = re.sub(r'[^a-z0-9_-]+', '_', name.strip().lower()).strip('_')
    if not clean_name:
        clean_name = f"routine_{int(time.time())}"

    if not description:
        description = f"Recorded routine: {clean_name.replace('_', ' ')}"

    normalized_actions = []
    for s in steps:
        kind = getattr(s, "kind", getattr(s, "action_type", ""))
        value = getattr(s, "value", getattr(s, "action_value", ""))
        if kind and value is not None:
            normalized_actions.append({"kind": kind, "value": value})

    if not normalized_actions:
        raise ValueError("Cannot save an empty routine with 0 steps.")

    if len(normalized_actions) > 8:
        normalized_actions = normalized_actions[-8:]

    preconditions = infer_routine_preconditions(steps)

    routine_dict = {
        "name": clean_name,
        "description": description[:200],
        "preconditions": [p.to_dict() for p in preconditions],
        "steps": normalized_actions,
    }

    return save_routine_dict(routine_dict, data_dir=data_dir)


class SessionActionRecorder:
    """Ring buffer of verified actions executed during the current session."""
    def __init__(self, maxlen: int = 30):
        self.history: deque[dict[str, Any]] = deque(maxlen=maxlen)

    def record(self, action: Any, label: str = ""):
        kind = getattr(action, "kind", getattr(action, "action_type", ""))
        value = getattr(action, "value", getattr(action, "action_value", ""))
        domain = getattr(action, "target_domain", "general")
        self.history.append({
            "kind": kind,
            "value": value,
            "domain": domain,
            "label": label,
            "timestamp": time.monotonic(),
        })

    def get_last_n(self, n: int = 1) -> list[Action]:
        count = min(n, len(self.history))
        items = list(self.history)[-count:]
        return [Action(item["kind"], item["value"]) for item in items]

    def clear(self):
        self.history.clear()
