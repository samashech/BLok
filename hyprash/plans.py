"""Bounded plans: validate every clause before asking Laya or taking action."""
from dataclasses import dataclass
import json
import re
from urllib.parse import quote_plus

from hyprash.commands import Action, START, parse
from hyprash.workflows import workflow

UNSUPPORTED_VERB = re.compile(
    r'\b(?:delete|erase|remove|send|upload|install|uninstall|download|rename|move|copy|close|'
    r'shut ?down|restart|reboot|format)\b', re.I)


@dataclass(frozen=True)
class Plan:
    steps: tuple[Action, ...]


def proposals(text):
    literals = {}

    def protect(match):
        key = f"hyprashliteral{len(literals)}token"
        literals[key] = match[1] if match[1] is not None else match[2]
        return key

    # Apostrophes inside words (God's Plan) are not quotation delimiters.
    masked = re.sub(r'"([^"\n]*)"|(?<!\w)\x27([^\x27\n]*)\x27(?!\w)', protect, text)
    if '"' in masked:
        raise ValueError('Close the quoted text before running the command.')
    boundary = r'\s+(?:and\s+then|then)\s+|\s*;\s*|\s+and\s+(?=(?:open|create|make|write|add|take|search|play|go|visit|launch|click|select|focus|type|enter|press|hit|reload|switch|find|delete|send|upload|install|remove|close|stop|rename|download|run|start|execute)\b)'
    chunks = re.split(boundary, masked, flags=re.I)
    if any(not chunk.strip() for chunk in chunks) or len(chunks) > 8:
        raise ValueError('Use between one and eight complete steps.')

    def restore(value):
        for key, literal in literals.items():
            value = value.replace(key, literal)
        return value

    result = []
    i = 0
    while i < len(chunks):
        clause = chunks[i].strip()
        action = None
        consumed = 1
        # Retain existing browser workflows as one tab-owned transaction.
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
                # A query may contain "and", but cannot hide another command.
                if any(re.search(boundary, step.get('query', ''), re.I)
                       for step in task.get('steps', [task])):
                    continue
                action, clause, consumed = Action(*found), joined, count
                break
        if action is None:
            candidate = re.sub(r'^(?:please |can you |could you )', '', clause, flags=re.I)
            parsed = parse(candidate)
            start = START.search(candidate)
            if len(parsed) != 1:
                if UNSUPPORTED_VERB.search(candidate):
                    raise ValueError('Unsupported step. Nothing was run.')
                if re.search(r'\b(?:run|start|execute)\b.*\broutine\b', candidate, re.I):
                    raise ValueError(f'Unknown routine: {restore(clause)}. Nothing was run.')
                # Preserve the small, existing natural-language route. It still
                # only permits Laya's bounded route labels in decision.py.
                if start is None and len(chunks) == 1:
                    result.append((restore(clause), None))
                    break
                raise ValueError(f'Unsupported step: {restore(clause)}. Nothing was run.')
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
                if isinstance(obj, str): return restore(obj)
                if isinstance(obj, dict): return {k: expand(v) for k, v in obj.items()}
                if isinstance(obj, list): return [expand(v) for v in obj]
                return obj
            value = json.dumps(expand(json.loads(value)))
        elif action.kind == 'url':
            for key, literal in literals.items():
                value = value.replace(key, quote_plus(literal))
        else:
            value = restore(value)
        result.append((restore(clause), Action(action.kind, value)))
        i += consumed
    return result
