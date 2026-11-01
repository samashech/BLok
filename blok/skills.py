"""Taught skills: browser steps you showed BLoK ("watch me"), replayable by name.

A skill is plain JSON in ~/.config/blok/skills/<name>.json: the page it starts
on, then steps that name each control by its label and role (never screen
coordinates). Each typed value is a field you can change when you call it:
"file an expense, amount 450, note lunch". Unnamed fields keep what you typed.
"""
import json
import re

from blok.paths import CONFIG

SKILLS = CONFIG / 'skills'
OPS = {'navigate', 'click', 'fill', 'enter', 'secret'}


def slug(name: str) -> str:
    value = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    if not value:
        raise RuntimeError('Give it a name, like "call it file an expense".')
    return value


def clean_steps(steps: list) -> list[dict]:
    """Keep only well-formed steps; drop clicks that merely focused a field before typing."""
    kept = []
    for step in steps:
        if not isinstance(step, dict) or step.get('op') not in OPS:
            continue
        step = {k: str(v)[:2000] for k, v in step.items() if k in ('op', 'name', 'role', 'value', 'url')}
        if step['op'] == 'navigate' and not re.match(r'https?://', step.get('url', '')):
            continue
        if step['op'] != 'navigate' and not step.get('name'):
            continue
        kept.append(step)
    return kept


def fields(steps: list[dict]) -> list[dict]:
    seen, out = set(), []
    for step in steps:
        if step['op'] == 'fill' and step['name'].lower() not in seen:
            seen.add(step['name'].lower())
            out.append({'name': step['name'], 'default': step.get('value', '')})
    return out


def save(name: str, steps: list) -> dict:
    steps = clean_steps(steps)
    if not any(s['op'] != 'navigate' for s in steps):
        raise RuntimeError("I didn't see you do anything. Say \"watch me\", then click and type in the page.")
    skill = {'name': name.strip(), 'phrases': [name.strip().lower()], 'steps': steps, 'fields': fields(steps)}
    SKILLS.mkdir(parents=True, exist_ok=True)
    (SKILLS / f'{slug(name)}.json').write_text(json.dumps(skill, indent=2) + '\n')
    return skill


def all_skills() -> dict[str, dict]:
    found = {}
    if SKILLS.is_dir():
        for path in sorted(SKILLS.glob('*.json')):
            try:
                found[path.stem] = json.loads(path.read_text())
            except ValueError:
                continue
    return found


def forget(name: str) -> bool:
    path = SKILLS / f'{slug(name)}.json'
    if not path.exists():
        return False
    path.unlink()
    return True


def match(text: str) -> tuple[dict, dict] | None:
    """("file an expense, amount 450, note lunch") → (skill, {'Amount': '450', 'Note': 'lunch'})."""
    t = re.sub(r'^(?:run|do|start|use)\s+(?:the\s+|my\s+)?', '', text.strip().strip('.!?'), flags=re.I)
    best = None
    for skill in all_skills().values():
        names = [f['name'].lower() for f in skill.get('fields', [])]
        for phrase in skill.get('phrases', []):
            after = t[len(phrase):].strip().lower() if t.lower().startswith(phrase + ' ') else ''
            # Speech cleanup drops commas, so a plain space works when a field name (or the only field's value) follows.
            spaced = bool(after) and (any(after.startswith(n) for n in names) or len(names) == 1)
            if t.lower() == phrase or spaced or re.match(re.escape(phrase) + r'(?:\s*,|\s+with\b|\s+for\b|\s*:|\s+-)\s*', t, re.I):
                if best is None or len(phrase) > len(best[1]):
                    best = (skill, phrase)
    if not best:
        return None
    skill, phrase = best
    rest = re.sub(r'^\s*(?:,|with\b|for\b|:|-)\s*', '', t[len(phrase):], flags=re.I).strip()
    return skill, _values(skill.get('fields', []), rest)


def _values(field_list: list[dict], rest: str) -> dict:
    if not rest or not field_list:
        return {}
    names = sorted((f['name'] for f in field_list), key=len, reverse=True)
    pattern = '|'.join(re.escape(n) for n in names)
    values = {}
    for m in re.finditer(rf'\b({pattern})\b\s*(?:is\s+|=\s*|:\s*|to\s+|of\s+)?(.+?)(?=\s*(?:,|\band\b)?\s*\b(?:{pattern})\b|$)', rest, re.I):
        name = next(n for n in names if n.lower() == m[1].lower())
        values[name] = m[2].strip(' ,')
    if not values and len(field_list) == 1:
        values[field_list[0]['name']] = rest           # one field: "file an expense, 450"
    return values


def replay_steps(skill: dict, values: dict) -> list[dict]:
    wanted = {k.lower(): v for k, v in values.items()}
    return [{**s, 'value': wanted[s['name'].lower()]} if s['op'] == 'fill' and s['name'].lower() in wanted else dict(s)
            for s in skill['steps']]


def risky(steps: list[dict]) -> list[str]:
    from blok.plans import SENSITIVE_WORDS
    return [s['name'] for s in steps if s['op'] in ('click', 'enter') and SENSITIVE_WORDS.search(s['name'])]


def describe(skill: dict) -> str:
    names = [f['name'] for f in skill.get('fields', [])]
    count = sum(1 for s in skill['steps'] if s['op'] != 'navigate')
    return f'{skill["name"]} ({count} steps' + (f'; fields: {", ".join(names)})' if names else ')')


def intent(text: str, watching: bool = False) -> dict | None:
    t = text.strip().strip('.!?')
    if re.fullmatch(r"(?:watch|watch me|watch this|learn this|learn how(?: to do this)?|let me show you|i'?ll show you|"
                    r"start watching|record this|teach(?: you)?(?: something)?)", t, re.I):
        return {'tool': 'watch', 'on': True}
    m = re.fullmatch(r"(?:(?:ok(?:ay)?|alright|done|that'?s it|finished)[,.]?\s*)?(?:call it|name it|save (?:that|this|it) as|"
                     r"that'?s how (?:you|to|i))\s+(?P<name>[\w ,'&-]{2,60})", t, re.I)
    if m:
        return {'tool': 'skill_save', 'name': m['name'].strip(" ,'")}
    if watching and re.fullmatch(r"(?:done|stop(?: watching)?|that'?s it|finished|i'?m done(?: showing you)?|stop recording)", t, re.I):
        return {'tool': 'watch', 'on': False}
    if re.fullmatch(r"(?:what (?:skills|things) (?:have you learned|do you know)|list (?:my |your )?skills|what have you learned)", t, re.I):
        return {'tool': 'skill_list'}
    m = re.fullmatch(r"(?:forget|delete|remove) (?:the |my )?(?:skill )?(?P<name>.+?)(?: skill)?", t, re.I)
    if m:
        try:
            if (SKILLS / f'{slug(m["name"])}.json').exists():
                return {'tool': 'skill_forget', 'name': m['name']}
        except RuntimeError:
            pass
    found = match(t)
    if found:
        skill, values = found
        return {'tool': 'skill_run', 'name': skill['name'], 'values': values}
    return None
