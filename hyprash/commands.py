"""Bounded voice intents. Transcripts are never interpreted as shell code."""
from dataclasses import dataclass
import re
from urllib.parse import quote_plus

@dataclass(frozen=True)
class Action:
    kind: str
    value: str = ""
    offset: int = 0

APPS = {
    "browser": "browser", "arc browser": "browser", "brave": "browser",
    "terminal": "terminal", "files": "files", "file manager": "files",
    "code": "code", "visual studio code": "code", "vs code": "code",
    "notes": "notes", "notes app": "notes", "note app": "notes",
    "camera": "camera", "photo booth": "camera", "photobooth": "camera",
}
SITES = {"youtube": "https://www.youtube.com", "github": "https://github.com",
         "google": "https://www.google.com", "x": "https://x.com",
         "twitter": "https://x.com"}
START = re.compile(
    r"\b(?:(?:go to|focus|click(?: on)?|select|open)(?: the)? (?:address|url|search) bar|type|press enter|hit enter|new tab|go back|go forward|reload(?: the page)?|look up|look online for|find online|open(?: up)?|launch|go to|visit|search(?: (?:the web|google))? for|"
    r"search|google|(?:create|make)(?: a)?(?: new)? note|new note|"
    r"(?:set|make|change)(?: the| its)? title(?: to| say)?|title(?: it)?|call it|"
    r"(?:write|add)(?: down)?|take(?: a)? (?:picture|photo|selfie)(?: of me)?|"
    r"(?:switch to|go to) workspace|stop listening)\b", re.I)

def clean(value):
    value = re.sub(r"\s+", " ", value).strip(" .,!?\"")
    return re.sub(r"(?:^|\s+)(?:and|then|and then|please|for me|and once.*|once.*|can you|and can you)$", "", value).strip()

def parse(text, final=True):
    text = text.lower().replace("dot com", ".com").replace("dot org", ".org")
    text = re.sub(r"\s+\.", ".", text)
    # Never reinterpret negated or quoted requests as affirmative commands.
    if re.search(r"\b(?:don't|do not|never|cancel|actually|instead)\b", text):
        return []
    matches = []
    for candidate in START.finditer(text):
        # Command words inside dictated content ("write open source software")
        # are data unless introduced by an explicit clause boundary.
        if not matches or re.search(r"(?:[.!?]\s*|\b(?:and(?: then)?|then|can you|could you|please|let's|lets)\s+)$", text[:candidate.start()]):
            matches.append(candidate)
    result = []
    for i, match in enumerate(matches):
        verb = match.group().lower()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        arg = clean(text[match.end():end])
        closed = final or i + 1 < len(matches)
        action = None
        if verb.endswith(" bar"):
            action = Action("address")
        elif verb == "type" and closed and arg:
            action = Action("browser_type", arg)
        elif verb in ("press enter", "hit enter", "new tab", "go back", "go forward", "reload", "reload the page"):
            action = Action("browser_key", {"press enter":"enter", "hit enter":"enter", "go back":"back", "go forward":"forward", "reload the page":"reload"}.get(verb, verb))
        elif verb == "stop listening":
            action = Action("stop")
        elif "workspace" in verb and closed:
            number = {"one":"1", "two":"2", "three":"3", "four":"4", "five":"5", "six":"6", "seven":"7", "eight":"8", "nine":"9", "ten":"10"}.get(arg, arg)
            if number.isdigit() and 1 <= int(number) <= 10:
                action = Action("workspace", number)
        elif verb.startswith(("open", "launch", "go to", "visit")):
            target = re.sub(r"^(?:the|my) ", "", arg)
            target = re.sub(r" (?:app|application|for me|please)$", "", target)
            if target in APPS:
                action = Action("open", APPS[target])
            elif target in SITES:
                action = Action("url", SITES[target])
            elif closed and re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,24}(?:/[^\s]*)?", target):
                action = Action("url", "https://" + target)
        elif verb.startswith(("search", "google", "look up", "look online for", "find online")) and closed and arg:
            action = Action("url", "https://www.google.com/search?q=" + quote_plus(arg))
        elif "note" in verb and closed:
            title = re.sub(r"^(?:called|titled|named|saying|that says) ", "", arg)
            action = Action("new_note", title or "Untitled")
        elif ("title" in verb or verb == "call it") and closed and arg:
            action = Action("title", arg)
        elif verb.startswith(("write", "add")) and closed and arg:
            action = Action("write", arg)
        elif verb.startswith("take") and closed:
            action = Action("photo")
        if action:
            result.append(Action(action.kind, action.value, match.start()))
    return result

class StreamPlanner:
    """Require a stable partial, and execute each intent once per utterance."""
    def __init__(self):
        self.done = set()
        self.candidates = {}

    def feed(self, text, final, now):
        ready = []
        for action in parse(text, final):
            key = (action.offset, action.kind)
            signature = (key, action.value)
            since = self.candidates.setdefault(signature, now)
            if key not in self.done and (final or now - since >= 0.6):
                self.done.add(key)
                ready.append(action)
        active = {((a.offset, a.kind), a.value) for a in parse(text, final)}
        self.candidates = {k:v for k,v in self.candidates.items() if k in active}
        if final:
            self.done.clear()
            self.candidates.clear()
        return ready
