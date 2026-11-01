"""Optional local rephraser: everyday speech → plain commands that the rules and Laya understand.

A small instruction model already installed in Ollama (Qwen2.5 3B preferred,
Gemma 2 2B otherwise) rewrites only what the rules could not fully understand.
It never decides or runs anything: its output goes back through the same rules
and Laya gates. A rewrite that introduces names absent from what was said is
discarded, so the model cannot invent apps, files or sites. Nothing is ever
downloaded; with Ollama stopped or no suitable model, this stage is skipped.
"""
from dataclasses import dataclass
import json
import os
import re
import threading
import time
import urllib.request

HOST = os.environ.get('HYPRASH_OLLAMA_HOST', 'http://127.0.0.1:11434')
PREFERRED = ('qwen2.5:3b', 'qwen2.5', 'qwen2.5:1.5b', 'gemma2:2b', 'gemma2')

SYSTEM = """You rewrite casual, messy spoken English into short plain commands for a desktop assistant.
The speaker may ramble, use slang, fumble words, repeat themselves or correct themselves. Keep exactly what they want.

Use only these command forms (fill in the angle brackets with the speaker's own words):
open <app> | open <website> | search google for <query> | search youtube for <query> | play <song or artist> on spotify |
play <video> on youtube | open a new tab | find my <file> | open my <file or folder> | read my <file> |
add <text> to my <file> file | create a file called <name> | rename <file> to <name> | move <file> to my <folder> folder |
delete <file> | download <thing> | turn the volume up | turn the volume down | set the volume to <number> | mute |
brightness up | brightness down | pause the music | next track | previous track | close this window |
make this window fullscreen | move this window to workspace <number> | switch to workspace <number> | switch to <app> |
lock the screen | what time is it | what is the date | how much battery do i have | create a note called <title> |
write <text> | take a photo | switch to the <theme> theme
Join several requests with " and then ". Never invent names, files, apps, sites or queries the speaker did not say.
If the request is too vague to act on, set "command" to "" and ask one short question in "question".
Reply with JSON only: {"command": "...", "question": ""}"""

EXAMPLES = [
    ("hey man so uh can you like pull up that spotify thing and put on some arijit or something",
     {"command": "open spotify and then play arijit on spotify", "question": ""}),
    ("yo i wanna check out what's new with uh elden ring like videos or whatever",
     {"command": "search youtube for elden ring", "question": ""}),
    ("ugh it's way too loud man bring it down a notch",
     {"command": "turn the volume down", "question": ""}),
    ("can you open that thing, you know, the app",
     {"command": "", "question": "Which app should I open?"}),
    ("put uh the, the terminal window on like the second workspace",
     {"command": "switch to terminal and then move this window to workspace 2", "question": ""}),
    ("note down buy eggs in my shopping list",
     {"command": "add buy eggs to my shopping list file", "question": ""}),
    ("i'm bored show me something cool to watch",
     {"command": "search youtube for something cool", "question": ""}),
    ("wait what was i saying, uh, the uh thing",
     {"command": "", "question": "What would you like me to do?"}),
]
# A rewrite that still points at nothing concrete is worse than asking.
VAGUE = re.compile(r'<|>|\b(?:this|that|some|the) (?:app|thing|stuff|one|program)\b|\bsomething\b(?! (?:cool|funny|new|good|fun|relaxing|chill))', re.I)

# Words a rewrite may add that the speaker did not say: the command vocabulary.
SERVICES = {'google', 'youtube', 'spotify'}
COMMAND_WORDS = (set(re.findall(r'[a-z]+', SYSTEM.split('Join several')[0].lower())) | {
    'then', 'and', 'my', 'the', 'a', 'an', 'to', 'on', 'for', 'in', 'of', 'it', 'this', 'that', 'is'}) - SERVICES
# A service the speaker did not name may only appear as where to search or play
# something they did name ("search youtube for …", "play … on spotify").
SERVICE_USE = re.compile(r'\bsearch (?:google|youtube) for \S|\S+ on (?:youtube|spotify)\b')


@dataclass
class Rewrite:
    command: str
    question: str
    model: str
    elapsed_ms: int


_models = {'checked': 0.0, 'name': None}
_lock = threading.Lock()


def model_name() -> str | None:
    """The installed model to use, rechecked at most once a minute. Never pulls."""
    if os.environ.get('HYPRASH_REPHRASE') == '0':
        return None
    with _lock:
        if time.monotonic() - _models['checked'] < 60:
            return _models['name']
        _models['checked'] = time.monotonic()
        _models['name'] = None
        try:
            with urllib.request.urlopen(HOST + '/api/tags', timeout=0.5) as response:
                installed = [m.get('name', '') for m in json.loads(response.read()).get('models', [])]
        except (OSError, ValueError):
            return None
        wanted = os.environ.get('HYPRASH_REPHRASE_MODEL')
        candidates = [wanted] if wanted else PREFERRED
        for name in candidates:
            match = next((m for m in installed if m == name or m.startswith(name + ':') or m.split(':')[0] == name), None)
            if match:
                _models['name'] = match
                break
        return _models['name']


def _messages(text: str) -> list[dict]:
    messages = [{'role': 'system', 'content': SYSTEM}]
    for said, reply in EXAMPLES:
        messages += [{'role': 'user', 'content': said}, {'role': 'assistant', 'content': json.dumps(reply)}]
    return messages + [{'role': 'user', 'content': text}]


def grounded(rewrite: str, original: str) -> bool:
    """Every content word the rewrite uses was said, or is command vocabulary / a known app or site."""
    from hyprash.nlu import APPS, SITES, tidy_speech
    said = set(re.findall(r"[a-z0-9']+", (original + ' ' + tidy_speech(original)).lower()))
    known = set(re.findall(r'[a-z0-9]+', ' '.join(list(APPS) + list(SITES))))
    services_ok = bool(SERVICE_USE.search(rewrite.lower()))
    for word in re.findall(r"[a-z0-9']+", rewrite.lower()):
        if word in said or word in COMMAND_WORDS or len(word) < 3:
            continue
        if word in SERVICES and services_ok:
            continue
        # Known names only count when the speaker said something close ("insta" → instagram).
        if word in known and any(w[:4] == word[:4] for w in said if len(w) >= 4):
            continue
        if word.isdigit() and word in re.sub(r'\D', ' ', original):
            continue
        return False
    return True


def rewrite(text: str, timeout: float = 8.0) -> Rewrite | None:
    model = model_name()
    if not model:
        return None
    started = time.monotonic()
    payload = {'model': model, 'messages': _messages(text), 'stream': False, 'format': 'json', 'keep_alive': '30m',
               'options': {'temperature': 0, 'num_predict': 80, 'num_ctx': 2048}}
    request = urllib.request.Request(HOST + '/api/chat', data=json.dumps(payload).encode(),
                                     headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            reply = json.loads(json.loads(response.read())['message']['content'])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    command = str(reply.get('command') or '').strip().strip('.')[:300]
    question = str(reply.get('question') or '').strip()[:160]
    if command and (VAGUE.search(command) or not grounded(command, text)):
        return None
    if not command and not question:
        return None
    return Rewrite(command, question if not command else '', model, round((time.monotonic() - started) * 1000))


def warm_up():
    """Load the model into memory in the background so the first request is fast."""
    def run():
        if model_name():
            rewrite('open the terminal', timeout=60)
    threading.Thread(target=run, daemon=True).start()
