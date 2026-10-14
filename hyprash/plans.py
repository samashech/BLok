"""Bounded plans: dependency-aware multi-step validation and execution.

Phase 6 DAG / Dependency-Aware Sequential Execution with isolated contexts,
typed PlanStep schemas, idempotency guards, and partial failure recovery.
"""
from dataclasses import dataclass, field
import json
import re
from typing import Any
from urllib.parse import quote_plus

from hyprash.commands import Action, START, parse
from hyprash.workflows import workflow
from hyprash.nlu import split_compound_utterance, resolve_intent, ConversationContext

UNSUPPORTED_VERB = re.compile(
    r'\b(?:delete|erase|remove|send|upload|install|uninstall|download|rename|move|copy|close|'
    r'shut ?down|restart|reboot|format|destroy)\b', re.I)


@dataclass(frozen=True, eq=False)
class PlanStep(Action):
    step_id: str = "step_1"
    target_domain: str = "general"
    depends_on: tuple[str, ...] = field(default_factory=tuple)
    idempotency: str = "IDEMPOTENT"  # "IDEMPOTENT" | "NON_IDEMPOTENT"
    preconditions: tuple[str, ...] = field(default_factory=tuple)
    postconditions: tuple[str, ...] = field(default_factory=tuple)
    on_failure: str = "ABORT_DEPENDENT"  # "ABORT_DEPENDENT" | "ABORT_ALL"
    target_tab_id: int | None = None
    output_binding: str | None = None
    input_bindings: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def action_type(self) -> str:
        return self.kind

    @property
    def action_value(self) -> str:
        return self.value

    @property
    def input_bindings_dict(self) -> dict[str, str]:
        return dict(self.input_bindings)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Action):
            return self.kind == other.kind and self.value == other.value
        return False

    def __hash__(self) -> int:
        return hash((self.kind, self.value, self.offset))

    @classmethod
    def from_action(cls, action: Any, step_id: str = "step_1") -> "PlanStep":
        kind = getattr(action, "kind", getattr(action, "action_type", ""))
        value = getattr(action, "value", getattr(action, "action_value", ""))
        offset = getattr(action, "offset", 0)
        domain, idemp, pre, post = _infer_step_attributes(kind, value)
        return cls(
            kind=kind,
            value=value,
            offset=offset,
            step_id=step_id,
            target_domain=domain,
            idempotency=idemp,
            preconditions=tuple(pre),
            postconditions=tuple(post),
            on_failure="ABORT_ALL",
        )


@dataclass
class PlanExecutionReport:
    completed_steps: list[str] = field(default_factory=list)
    failed_steps: list[dict[str, Any]] = field(default_factory=list)  # {step_id, stage, error}
    skipped_steps: list[str] = field(default_factory=list)
    uncertain_steps: list[str] = field(default_factory=list)
    step_results: dict[str, Any] = field(default_factory=dict)
    overall_status: str = "completed"  # "completed" | "failed" | "cancelled" | "partial_success"


@dataclass(frozen=True)
class Plan:
    steps: tuple[PlanStep, ...]

    def __init__(self, steps: tuple[Any, ...]):
        normalized: list[PlanStep] = []
        for idx, s in enumerate(steps, 1):
            if isinstance(s, PlanStep):
                normalized.append(s)
            elif hasattr(s, "kind") and hasattr(s, "value"):
                normalized.append(PlanStep.from_action(s, step_id=f"step_{idx}"))
            else:
                raise TypeError(f"Expected PlanStep or Action, got {type(s)}")
        object.__setattr__(self, "steps", tuple(normalized))


def _infer_step_attributes(kind: str, value: str) -> tuple[str, str, list[str], list[str]]:
    """Infer domain, idempotency, preconditions, and postconditions from action kind and value."""
    domain = "general"
    idempotency = "IDEMPOTENT"
    preconditions: list[str] = []
    postconditions: list[str] = []

    if kind == "web_task":
        try:
            task = json.loads(value)
            action = task.get("action")
            site = task.get("site", "browser")
            if site in ("youtube", "spotify", "google", "github"):
                domain = f"browser:{site}"
            else:
                domain = "browser:general"

            if action == "new_tab":
                domain = "browser:general"
                idempotency = "NON_IDEMPOTENT"
                postconditions = ["tab_active"]
            elif action == "search":
                idempotency = "IDEMPOTENT"
                postconditions = ["results_loaded"]
            elif action == "play":
                idempotency = "NON_IDEMPOTENT"
                postconditions = ["media_playing"]
            elif action == "result":
                idempotency = "IDEMPOTENT"
                postconditions = ["media_playing" if task.get("play") else "destination_matched"]
            elif action == "sequence":
                sub_steps = task.get("steps", [])
                if sub_steps:
                    first_site = sub_steps[0].get("site", "browser")
                    domain = f"browser:{first_site}"
                idempotency = "NON_IDEMPOTENT"
            elif action in ("click", "fill"):
                domain = "browser:page"
                idempotency = "NON_IDEMPOTENT" if action == "click" else "IDEMPOTENT"
        except Exception:
            domain = "browser:general"
    elif kind == "open":
        if value == "browser":
            domain = "browser:general"
        elif value in ("notes", "obsidian", "hyprash_notes"):
            domain = "desktop:notes"
        elif value in ("camera", "snapshot", "hyprash_camera"):
            domain = "desktop:camera"
        else:
            domain = f"desktop:{value}"
        idempotency = "IDEMPOTENT"
    elif kind == "obsidian_note":
        domain = "desktop:obsidian"
        idempotency = "NON_IDEMPOTENT"
        postconditions = ["note_saved"]
    elif kind in ("new_note", "title", "write"):
        domain = "desktop:notes"
        idempotency = "NON_IDEMPOTENT" if kind == "new_note" else "IDEMPOTENT"
    elif kind == "photo":
        domain = "desktop:camera"
        idempotency = "NON_IDEMPOTENT"
    elif kind == "workspace":
        domain = "desktop:workspace"
        idempotency = "IDEMPOTENT"
    elif kind == "routine":
        domain = f"routine:{value}"
        idempotency = "NON_IDEMPOTENT"
    elif kind == "url":
        if "youtube.com" in value:
            domain = "browser:youtube"
        elif "spotify.com" in value:
            domain = "browser:spotify"
        elif "google.com" in value:
            domain = "browser:google"
        else:
            domain = "browser:general"
        idempotency = "IDEMPOTENT"
        postconditions = ["destination_matched"]
    elif kind in ("address", "browser_type", "browser_key"):
        domain = "browser:chrome"
        idempotency = "NON_IDEMPOTENT" if kind == "browser_key" and value == "new tab" else "IDEMPOTENT"

    return domain, idempotency, preconditions, postconditions


def proposals(text: str, context: ConversationContext | None = None) -> list[tuple[str, PlanStep]]:
    """Produce validated DAG plan proposals from an utterance."""
    literals = {}

    def protect(match):
        key = f"hyprashliteral{len(literals)}token"
        literals[key] = match[1] if match[1] is not None else match[2]
        return key

    # Apostrophes inside words (God's Plan) are not quotation delimiters.
    masked = re.sub(r'"([^"\n]*)"|(?<!\w)\x27([^\x27\n]*)\x27(?!\w)', protect, text)
    if '"' in masked:
        raise ValueError('Close the quoted text before running the command.')

    # Protect known entity conjunctions like "rock and roll"
    known_phrases = [
        r'\brock and roll\b',
        r'\bdungeons and dragons\b',
        r'\bbread and butter\b',
        r'\bme and my shadow\b',
        r'\bpeace and love\b',
    ]
    for kp in known_phrases:
        def protect_phrase(m):
            key = f"hyprashliteral{len(literals)}token"
            literals[key] = m.group(0)
            return key
        masked = re.sub(kp, protect_phrase, masked, flags=re.I)

    boundary = (
        r'\s+(?:and\s+then|then|after\s+that)\s+|\s*;\s*|'
        r'\s+and\s+(?=(?:open|create|make|write|add|take|search|play|go|visit|launch|'
        r'click|select|focus|type|enter|press|hit|reload|switch|find|delete|send|'
        r'upload|install|remove|close|stop|rename|download|run|start|execute)\b)'
    )
    chunks = re.split(boundary, masked, flags=re.I)
    if any(not chunk.strip() for chunk in chunks) or len(chunks) > 8:
        raise ValueError('Use between one and eight complete steps.')

    def restore(value: str) -> str:
        for key, literal in literals.items():
            value = value.replace(key, literal)
        return value

    result: list[tuple[str, PlanStep]] = []
    i = 0
    step_counter = 1

    while i < len(chunks):
        clause = chunks[i].strip()
        action = None
        consumed = 1

        # Retain existing browser workflows as one tab-owned transaction
        for count in range(min(4, len(chunks) - i), 1, -1):
            joined = ' and '.join(chunks[i:i + count])
            found = workflow(joined.lower())
            if not found or found[0] != 'web_task':
                continue
            task = json.loads(found[1])
            if task['action'] in ('sequence', 'github_repo') or (
                count == 2 and task['action'] in ('search', 'play')
                and re.fullmatch(r'(?:open|go to|visit) (?:www\.)?(?:google|youtube|spotify)(?:\.com)?', clause, re.I)
            ):
                # A query may contain "and", but cannot hide another command
                if any(re.search(boundary, step.get('query', ''), re.I)
                       for step in task.get('steps', [task])):
                    continue
                action, clause, consumed = Action(*found), joined, count
                break

        if action is None:
            candidate = re.sub(r'^(?:please |can you |could you |would you |i want you to |let\'s )', '', clause, flags=re.I)
            candidate = re.sub(r'\s+(?:for me|for us|right now|please)$', '', candidate, flags=re.I)
            parsed = parse(candidate, final=True, context=context)
            start = START.search(candidate)
            if len(parsed) != 1:
                if UNSUPPORTED_VERB.search(candidate):
                    raise ValueError('Unsupported step. Nothing was run.')
                if re.search(r'\b(?:run|start|execute)\b.*\broutine\b', candidate, re.I):
                    raise ValueError(f'Unknown routine: {restore(clause)}. Nothing was run.')
                # Preserve the small, existing natural-language route for a single clause
                if start is None and len(chunks) == 1:
                    resolved = resolve_intent(candidate, context)
                    if resolved.action_kind and resolved.intent_type not in ("cancel", "unsupported", "clarify"):
                        action = Action(resolved.action_kind, resolved.action_value)
                    else:
                        result.append((restore(clause), None))
                        break
                else:
                    raise ValueError(f'Unsupported step: {restore(clause)}. Nothing was run.')
            else:
                if start and start.start() != 0 and not workflow(candidate):
                    raise ValueError(f'Unsupported step: {restore(clause)}. Nothing was run.')
                action = parsed[0]

            fixed = {
                'photo': r'take(?: a)? (?:picture|photo|selfie)(?: of me)?',
                'browser_key': r'(?:press enter|hit enter|new tab|go back|go forward|reload(?: the page)?)',
                'address': r'(?:go to|focus|click(?: on)?|select|open)(?: the)? (?:address|url) bar',
                'stop': r'stop listening',
            }
            if action.kind in fixed and not re.fullmatch(fixed[action.kind] + r'[.!?]*', candidate, re.I):
                raise ValueError(f'Unsupported step: {restore(clause)}. Nothing was run.')
            if action.kind == 'routine':
                from hyprash.routines import get_routine
                if not get_routine(action.value):
                    raise ValueError(f'Unknown routine: {restore(clause)}. Nothing was run.')

        value = action.value
        if action.kind in ('web_task', 'ui_control', 'obsidian_note'):
            def expand(obj):
                if isinstance(obj, str):
                    return restore(obj)
                if isinstance(obj, dict):
                    return {k: expand(v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [expand(v) for v in obj]
                return obj
            value = json.dumps(expand(json.loads(value)))
        elif action.kind == 'url':
            for key, literal in literals.items():
                value = value.replace(key, quote_plus(literal))
        else:
            value = restore(value)

        step_id = f"step_{step_counter}"
        domain, idemp, pre, post = _infer_step_attributes(action.kind, value)

        deps: list[str] = []
        input_binds: list[tuple[str, str]] = []
        output_bind = None

        if action.kind == "web_task" and '"action": "new_tab"' in value:
            output_bind = "tab_id"

        # Connect dependencies and bindings within the plan
        if result:
            prev_clause, prev_step = result[-1]
            if prev_step:
                # Tab creation followed by search/navigation in browser:
                if prev_step.action_type == "web_task" and '"action": "new_tab"' in prev_step.action_value:
                    if domain.startswith("browser:"):
                        deps.append(prev_step.step_id)
                        input_binds.append(("target_tab_id", f"{prev_step.step_id}.tab_id"))
                # Note creation followed by title or write:
                elif prev_step.action_type in ("open", "new_note") and action.kind in ("title", "write"):
                    deps.append(prev_step.step_id)

        plan_step = PlanStep(
            kind=action.kind,
            value=value,
            offset=getattr(action, "offset", 0),
            step_id=step_id,
            target_domain=domain,
            depends_on=tuple(deps),
            idempotency=idemp,
            preconditions=tuple(pre),
            postconditions=tuple(post),
            on_failure="ABORT_DEPENDENT",
            output_binding=output_bind,
            input_bindings=tuple(input_binds),
        )

        result.append((restore(clause), plan_step))
        i += consumed
        step_counter += 1

    return result
