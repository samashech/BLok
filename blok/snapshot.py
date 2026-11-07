"""Work out which control on the page you meant, from a compact snapshot of it.

The extension lists the visible controls with reference IDs, the idea behind
Aside's accessibility snapshots. Where Aside has a cloud model read that list,
this scores it directly, so it stays offline and instant, and copes with Whisper
mishearing a word. Names are page text: data to match against, never instructions.
"""
from difflib import SequenceMatcher
import re

MATCH = 0.62        # below this, the words don't really match
TIE = 0.03          # scores this close are the same answer
FILLER = {'the', 'a', 'an', 'my', 'your', 'on', 'that', 'this', 'please', 'button', 'link', 'tab', 'field', 'box', 'icon', 'option', 'menu'}
ROLES = {'button': {'button'}, 'link': {'link'}, 'tab': {'tab', 'link'}, 'menu': {'menuitem'}, 'field': {'textbox', 'combobox', 'searchbox'}, 'box': {'textbox', 'combobox', 'searchbox', 'checkbox'}}
ORDINALS = {'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5, 'last': -1, '1st': 1, '2nd': 2, '3rd': 3, '4th': 4, '5th': 5}
NAVIGATION = {'link', 'tab', 'menuitem'}


class Ambiguous(RuntimeError):
    """Several controls fit equally well; the message says how to tell them apart."""


def _words(text: str) -> list[str]:
    return re.findall(r"[\w']+", str(text).lower().replace('’', "'"))


def _close(word: str, other: str) -> bool:
    if word == other:
        return True
    return len(word) > 2 and len(other) > 2 and SequenceMatcher(None, word, other).ratio() >= 0.75


def score(target: str, name: str) -> float:
    """0–1: how well what you said fits a control's name, allowing for misheard words."""
    said = [w for w in _words(target) if w not in FILLER] or _words(target)
    words = _words(name)
    if not said or not words:
        return 0.0
    if said == words:
        return 1.0
    if ''.join(said) == ''.join(words):       # "sign in" / "signin"
        return 0.98
    covered = sum(any(_close(w, n) for n in words) for w in said) / len(said)
    precise = sum(any(_close(n, w) for w in said) for n in words) / len(words)
    # Whole-phrase similarity only compares like with like: "download pdf" isn't "downloaded".
    whole = SequenceMatcher(None, ' '.join(said), ' '.join(words)).ratio() if len(said) == len(words) else 0.0
    if covered < 0.66 and whole < 0.8:      # half of what you said isn't there
        return 0.0
    return max(0.7 * covered + 0.3 * precise, whole * 0.9 if whole >= 0.8 else 0.0)


def _split(target: str):
    """'second save button in the footer' → ('save button', ordinal 2, section 'footer', role set)."""
    text = ' '.join(_words(target))
    section = None
    found = re.fullmatch(r'(.+?) (?:in|under|from) (?:the )?(.+)', text)
    if found:
        text, section = found[1], found[2]
    ordinal = None
    found = re.match(r'(?:the )?(first|second|third|fourth|fifth|last|1st|2nd|3rd|4th|5th) (.+)', text)
    if found:
        ordinal, text = ORDINALS[found[1]], found[2]
    last = text.split()[-1] if text else ''
    return text, ordinal, section, ROLES.get(last)


def resolve(target: str, controls: list[dict], navigate: bool = False) -> dict | None:
    """The control you meant, or None if nothing fits. Raises Ambiguous rather than guess."""
    text, ordinal, section, roles = _split(target)
    usable = [c for c in controls if not c.get('disabled')]
    if section:
        here = [c for c in usable if score(section, c.get('section', '')) >= MATCH]
        if here:
            usable = here
        else:       # "in" may be part of the name ("Log in to GitHub")
            text = ' '.join(_words(target))
    if roles and any(c.get('role') in roles for c in usable):
        scored = [(score(text, c['name']) + (0.05 if c.get('role') in roles else 0), c) for c in usable]
    else:
        scored = [(score(text, c['name']), c) for c in usable]
    best = max((s for s, _ in scored), default=0.0)
    if best < MATCH:
        if any(c.get('disabled') and score(text, c['name']) >= MATCH for c in controls):
            raise RuntimeError('That control is disabled.')
        return None
    fits = [c for s, c in scored if s >= best - TIE]
    if ordinal:
        fits = [c for s, c in scored if s >= MATCH]     # "second comments" counts "12 comments" too
        if ordinal > len(fits):
            raise RuntimeError(f'There are only {len(fits)} of those on this page.')
        return fits[ordinal - 1 if ordinal > 0 else -1]
    if len(fits) == 1:
        return fits[0]
    if navigate:
        return ([c for c in fits if c.get('role') in NAVIGATION] or fits)[0]
    shown = [c for c in fits if c.get('in_view')]
    if len(shown) == 1:
        return shown[0]                 # the one you can see
    return _tell_apart(shown or fits)


def _tell_apart(fits: list[dict]) -> dict:
    names = list(dict.fromkeys(c['name'] for c in fits))
    if len(names) > 1:
        raise Ambiguous('Which one: ' + ', or '.join(f'"{n}"' for n in names[:4]) + '?')
    sections = list(dict.fromkeys(c.get('section') for c in fits if c.get('section')))
    if len(sections) == len(fits):
        raise Ambiguous('Which one: ' + ', or '.join(f'"{names[0]}" in the {s}' for s in sections[:4]) + '?')
    raise Ambiguous(f'There are {len(fits)} called "{names[0]}". Say "first {names[0]}" or "second {names[0]}", or say "show numbers".')


def closest(target: str, controls: list[dict], limit: int = 8) -> list[str]:
    """The nearest names on the page, for Laya to choose from or to offer you."""
    names = list(dict.fromkeys(c['name'] for c in controls if not c.get('disabled')))
    return sorted(names, key=lambda name: score(target, name), reverse=True)[:limit]


def compact(seen: dict) -> str:
    """The snapshot as text an AI client can read: one line per control, by reference ID."""
    lines = [f'{seen.get("title", "")} — {seen.get("url", "")}']
    for control in seen.get('controls', []):
        tags = list(control.get('state') or [])
        if control.get('disabled'):
            tags.append('disabled')
        if not control.get('in_view'):
            tags.append('offscreen')
        line = f'{control["ref"]} {control["role"]} "{control["name"]}"'
        if control.get('section'):
            line += f' @{control["section"]}'
        lines.append(line + (f' [{", ".join(tags)}]' if tags else ''))
    if seen.get('truncated'):
        lines.append(f'… and {seen["total"] - len(seen["controls"])} more offscreen')
    return '\n'.join(lines)


def describe_click(result: dict) -> str:
    """What a click really did, from what the browser saw happen."""
    effects = result.get('effects') or {}
    message = result['message']
    if effects.get('download'):
        return message.replace(' · result not verified', '') + f' · downloading {effects["download"]}'
    if effects.get('new_tab'):
        return message.replace(' · result not verified', '') + ' · opened a new tab'
    if effects.get('navigated'):
        return message.replace(' · result not verified', '') + ' · the page changed'
    return message
