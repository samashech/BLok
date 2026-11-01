"""Natural-language understanding: canonical intents, entities, and normalization.

Phase 6 Tier-1 deterministic normalization and grammar, typed schemas,
and conversation context tracking for BLoK.
"""
from dataclasses import dataclass, field
import json
import re
import time
from typing import Any
from urllib.parse import quote_plus

ORDINALS = {
    'first': 1, '1st': 1, 'second': 2, '2nd': 2, 'third': 3, '3rd': 3,
    'fourth': 4, '4th': 4, 'fifth': 5, '5th': 5, 'sixth': 6, '6th': 6,
    'seventh': 7, '7th': 7, 'eighth': 8, '8th': 8, 'ninth': 9, '9th': 9,
    'tenth': 10, '10th': 10,
}

APPS = {
    "browser": "browser", "arc browser": "browser", "brave": "browser", "brave browser": "browser",
    "chrome": "browser", "google chrome": "browser", "web browser": "browser",
    "terminal": "terminal", "foot": "terminal", "console": "terminal", "command line": "terminal",
    "files": "files", "file manager": "files", "nautilus": "files",
    "code": "code", "visual studio code": "code", "vs code": "code", "code editor": "code", "editor": "code",
    "notes": "notes", "notes app": "notes", "note app": "notes",
    "blok notes": "blok_notes", "blok camera": "blok_camera",
    "block notes": "blok_notes", "block camera": "blok_camera",
    "obsidian": "obsidian", "snapshot": "snapshot",
    "camera": "camera", "photo booth": "camera", "photobooth": "camera", "webcam": "camera",
}

SITES = {
    "youtube": "https://www.youtube.com",
    "github": "https://github.com",
    "google": "https://www.google.com",
    "spotify": "https://open.spotify.com",
    "x": "https://x.com",
    "twitter": "https://x.com",
    "reddit": "https://www.reddit.com",
    "wikipedia": "https://www.wikipedia.org",
    "gmail": "https://mail.google.com", "mail": "https://mail.google.com", "email": "https://mail.google.com",
    "my mail": "https://mail.google.com", "my email": "https://mail.google.com", "my inbox": "https://mail.google.com",
    "netflix": "https://www.netflix.com", "amazon": "https://www.amazon.in", "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com", "linkedin": "https://www.linkedin.com", "twitch": "https://www.twitch.tv",
    "chatgpt": "https://chatgpt.com", "claude": "https://claude.ai", "whatsapp": "https://web.whatsapp.com",
    "discord": "https://discord.com/app", "steam": "https://store.steampowered.com", "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com", "drive": "https://drive.google.com", "google drive": "https://drive.google.com",
    "calendar": "https://calendar.google.com", "stack overflow": "https://stackoverflow.com", "chess": "https://www.chess.com",
    "flipkart": "https://www.flipkart.com", "ebay": "https://www.ebay.com", "imdb": "https://www.imdb.com",
}

# Sites whose own search is a URL, so "search for X" while on them stays on them.
SITE_SEARCH = {
    "steam": "https://store.steampowered.com/search/?term={q}", "amazon": "https://www.amazon.in/s?k={q}",
    "reddit": "https://www.reddit.com/search/?q={q}", "github": "https://github.com/search?q={q}&type=repositories",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={q}", "x": "https://x.com/search?q={q}",
    "twitch": "https://www.twitch.tv/search?term={q}", "netflix": "https://www.netflix.com/search?q={q}",
    "stack overflow": "https://stackoverflow.com/search?q={q}", "maps": "https://www.google.com/maps/search/{q}",
    "linkedin": "https://www.linkedin.com/search/results/all/?keywords={q}", "gmail": "https://mail.google.com/mail/u/0/#search/{q}",
    "drive": "https://drive.google.com/drive/search?q={q}", "flipkart": "https://www.flipkart.com/search?q={q}",
    "ebay": "https://www.ebay.com/sch/i.html?_nkw={q}", "imdb": "https://www.imdb.com/find/?q={q}",
}
SITE_ALIASES = {"steam store": "steam", "stackoverflow": "stack overflow", "twitter": "x", "google maps": "maps",
                "mail": "gmail", "my mail": "gmail", "email": "gmail", "my email": "gmail", "my inbox": "gmail",
                "wiki": "wikipedia", "google drive": "drive"}


def site_of(url: str | None) -> str | None:
    """Spoken site name for a URL ("youtube", "steam"), else its bare hostname."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url or "")
    except ValueError:
        return None
    host = (parsed.hostname or "").removeprefix("www.")
    if not host:
        return None
    if host.startswith("google.") and parsed.path.startswith("/maps"):
        return "maps"
    best = None
    for name, site_url in SITES.items():
        known = (urlparse(site_url).hostname or "").removeprefix("www.")
        # The first name listed for a host wins ("x" over "twitter", "gmail" over "mail").
        if known and (host == known or host.endswith("." + known)) and (best is None or len(known) > best[0]):
            best = (len(known), name)
    return SITE_ALIASES.get(best[1], best[1]) if best else host

FILLER_PREFIXES = re.compile(
    r'^(?:'
    r'yo bro|yo|bro|dude|man|'
    r'can you please|could you please|would you please|will you please|'
    r'can you|could you|would you|will you|'
    r'hey blok|hey block|hey assistant|hey|hi blok|hi block|hi|hello|'
    r'okay blok|okay block|ok block|okay now|okay|ok now|ok|'
    r'i wanna|i want you to|i want to|i would like you to|i would like to|i\'d like you to|i\'d like to|'
    r'i need you to|i need to|i have to|i gotta|i\'m trying to|im trying to|trying to|help me|'
    r'do me a favor and|do me a favour and|would you mind|could you maybe|can you maybe|'
    r'let\'s|lets|'
    r'go ahead and|feel free to|'
    r'now please|now|just|'
    r'for me real quick|real quick|'
    r'please|pls'
    r')[,:]?\s+', re.I
)

FILLER_SUFFIXES = re.compile(
    r'[,.]?\s+(?:'
    r'for me real quick|real quick|for me please|for us please|for me|for us|'
    r'you know|please|pls|thanks|thank you|'
    r'right now|quickly'
    r')[.!?]*\s*$', re.I
)

NEGATION_PATTERN = re.compile(r'\b(?:don\'t|do not|never|cancel(?: that)?)\b', re.I)
UNSUPPORTED_VERB = re.compile(
    r'\b(?:delete all files|erase the disk|format drive c|shutdown|shut down|reboot|restart|destroy|drop database|uninstall)\b', re.I
)


def repair_self_corrections(text: str) -> str:
    """Detect and resolve mid-sentence repairs, self-corrections, and disfluencies."""
    s = text.strip()
    s = re.sub(r'[\u2013\u2014]+|--', ' - ', s)

    # 1. Full-clause / phrase repairs: "no wait", "wait no", "scratch that", "sorry no"
    clause_repair = re.search(r'[,.\s-]+\b(?:no wait|wait no|scratch that|sorry no)\b[,:\s-]*', s, re.I)
    if clause_repair:
        before = s[:clause_repair.start()].strip()
        after = s[clause_repair.end():].strip()
        if after:
            if re.match(r'^(?:open|launch|start|fire|spin|bring|search|look|find|play|put|create|make|write|go|visit|switch|take|stop|gimme|give)\b', after, re.I):
                return after
            m_entity = re.search(r'\b(search for|look up|find|play|put on|open|launch|create note|note titled)\s+(.+)$', before, re.I)
            if m_entity:
                lead = before[:m_entity.start(2)].strip()
                return f"{lead} {after}".strip()
            return after

    # 2. Entity / Slot repairs: "actually", "or rather", "i mean"
    slot_repair = re.search(r'[,.\s-]+\b(?:actually|or rather|i mean)\b[,:\s-]*', s, re.I)
    if slot_repair:
        before = s[:slot_repair.start()].strip()
        after = s[slot_repair.end():].strip()
        if after:
            if re.match(r'^(?:open|launch|start|fire|spin|bring|search|look|find|play|put|create|make|write|go|visit|switch|take|stop|gimme|give)\b', after, re.I):
                return after
            m_verb = re.search(r'\b(search(?: for)?|look up|find(?: online)?|play|put on|open(?: up)?|launch|visit|go to|create note|title(?: it)?)\s+(.+)$', before, re.I)
            if m_verb:
                prefix = before[:m_verb.start(2)].strip()
                return f"{prefix} {after}".strip()
            return after

    return s


@dataclass(frozen=True)
class ResolvedIntent:
    intent_type: str
    entities: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    ambiguity_reason: str = ""
    requires_clarification: bool = False
    raw_text: str = ""
    normalized_text: str = ""
    action_kind: str = ""
    action_value: str = ""
    sub_intents: list[Any] = field(default_factory=list)

    @property
    def action_tuple(self) -> tuple[str, str] | None:
        if self.action_kind:
            return self.action_kind, self.action_value
        return None

    @property
    def slots(self) -> dict[str, Any]:
        return self.entities


@dataclass
class ConversationContext:
    active_tab_id: int | None = None
    last_active_tab_id: int | None = None
    active_site: str | None = None
    active_url: str | None = None
    last_intent: str | None = None
    search_context: dict[str, Any] | None = None  # {tabId, url, site, query, created_at}
    active_app: str | None = None
    media_state: dict[str, Any] | None = None
    hints_until: float = 0.0  # numbered hints are showing until this monotonic time
    last_executed_plan: Any = None
    awaiting_approval: dict[str, Any] | None = None

    @property
    def active_domain(self) -> str | None:
        return self.active_site

    def update_tab(self, tab_id: int | None, url: str | None = None, site: str | None = None):
        if tab_id is not None and tab_id != self.active_tab_id:
            self.last_active_tab_id = self.active_tab_id
        self.active_tab_id = tab_id
        if url:
            self.active_url = url
        # The site follows the page actually shown; "x" must not match every URL with an x.
        self.active_site = site or site_of(url) or self.active_site

    def set_search_context(self, tab_id: int, url: str, site: str, query: str):
        self.search_context = {
            'tabId': tab_id,
            'url': url,
            'site': site,
            'query': query,
            'created_at': time.monotonic(),
        }
        self.last_active_tab_id = self.active_tab_id
        self.active_tab_id = tab_id
        self.active_site = site
        self.active_url = url

    def is_search_context_valid(self, ttl_seconds: float = 300.0) -> bool:
        if not self.search_context:
            return False
        created_at = self.search_context.get('created_at', 0)
        return (time.monotonic() - created_at) <= ttl_seconds

    def clear_search_context(self):
        self.search_context = None

    def to_summary(self) -> dict[str, Any]:
        return {
            'active_tab_id': self.active_tab_id,
            'last_active_tab_id': self.last_active_tab_id,
            'active_site': self.active_site,
            'active_url': self.active_url,
            'last_intent': self.last_intent,
            'has_valid_search': self.is_search_context_valid(),
            'active_app': self.active_app,
        }


HESITATIONS = re.compile(r"\b(?:u+h+m*|u+m+|e+r+m*|hm+|mm+|ah+|uh-huh|whatchamacallit|"
                         r"what'?s it called|what is it called|what do you call it|how do you say it|"
                         r"you know what i mean|you know|i guess|i think|kind of|kinda|sort of|sorta|"
                         r"basically|literally|honestly|like literally)\b[,.]?", re.I)
VAGUE_TAILS = re.compile(r"[,.]?\s+(?:or something(?: like that)?|or whatever|or anything|or so|"
                         r"if you can|if you could|if that'?s okay|when you get a chance|real quick|"
                         r"quickly|thanks?(?: you)?(?: so much)?|please|pls|plz|man|bro|dude|buddy|mate|"
                         r"my friend|for me|for us|i guess|right now|now)\s*[.!?]*$", re.I)
OPENERS = re.compile(r"^(?:(?:hey|hi|hello|yo|oi|okay|ok|alright|all right|right|so|well|yeah|yes|yep|"
                     r"uh|um|blok|block|assistant|computer|man|bro|dude|buddy|mate)\b[,.!]?|(?:listen|look)[,!])\s+", re.I)
SLANG = {
    r"\bu\b": "you", r"\bur\b": "your", r"\bpls\b|\bplz\b": "please", r"\bwanna\b": "want to",
    r"\bgonna\b": "going to", r"\bgimme\b": "give me", r"\blemme\b": "let me", r"\bgotta\b": "have to",
    r"\byt\b": "youtube", r"\byoutubes?\b": "youtube", r"\bthe youtube\b": "youtube",
    r"\bvs ?code\b": "vs code", r"\bgmail\b": "gmail", r"\blookup\b": "look up",
    r"\bcan ya\b": "can you", r"\bcould ya\b": "could you",
}


def tidy_speech(text: str) -> str:
    """Spoken, fumbled English → a plain request, keeping the words that carry meaning.

    Removes hesitations ("uh", "what's it called"), stutters ("open the open the
    browser"), vague tails ("or something"), friendly openers ("hey man") and
    expands chat slang ("u", "wanna", "yt"). Quoted text is left untouched.
    """
    literals = {}
    def protect(m):
        key = f"blokquote{len(literals)}x"
        literals[key] = m.group(0)
        return key
    s = re.sub(r'"[^"\n]*"', protect, text.strip().replace('’', "'"))
    s = re.sub(r"[\u2013\u2014]+|--|\.\.\.+", " ", s)
    for pattern, replacement in SLANG.items():
        s = re.sub(pattern, replacement, s, flags=re.I)
    s = HESITATIONS.sub(" ", s)
    # Filler "like": "can you like open", ", like, ", "just like open" — not "i like turtles".
    s = re.sub(r"(?:(?<=\byou)|(?<=\bjust)|(?<=\bso)|(?<=,)|^)\s*,?\s*like\s*,?\s+", " ", s, flags=re.I)
    s = re.sub(r"\s*,\s*like\s*,\s*", " ", s, flags=re.I)
    s = re.sub(r"\b(?:just|kindly|maybe|perhaps|quickly|real quick)\s+(?=\w)", "", s, flags=re.I)
    s = re.sub(r"\s*,\s*", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Stutters: a repeated word or phrase of up to four words ("search for search for").
    for _ in range(3):
        s = re.sub(r"\b((?:\w+'?\w*\s+){0,3}\w+'?\w*)\s+\1\b", r"\1", s, flags=re.I)
    prev = None
    while prev != s:
        prev = s
        s = OPENERS.sub("", s).strip()
        s = VAGUE_TAILS.sub("", s).strip()
    for key, literal in literals.items():
        s = s.replace(key, literal)
    return s.strip(" ,")


def normalize_utterance(text: str) -> str:
    """Clean conversational fillers, contractions, and domain words while preserving quotes and semantic entities."""
    from blok import hinglish
    text = hinglish.translate(text) or text
    repaired = repair_self_corrections(tidy_speech(text))
    s = repaired.strip().replace('’', "'")
    s = s.replace("dot com", ".com").replace("dot org", ".org").replace("dot net", ".net")
    s = re.sub(r"\s+\.", ".", s)

    # Protect quoted content (ignoring apostrophes in contractions like let's or God's)
    literals = {}
    def protect(m):
        k = f"__LITERAL_{len(literals)}__"
        literals[k] = m.group(0)
        return k
    s = re.sub(r'"[^"\n]*"|(?<!\w)\'[^\'\n]*(?!\w)', protect, s)

    # Protect known entity conjunctions like "rock and roll"
    known_phrases = [
        r'\brock and roll\b',
        r'\bdungeons and dragons\b',
        r'\bbread and butter\b',
        r'\bme and my shadow\b',
        r'\bpeace and love\b',
    ]
    for kp in known_phrases:
        s = re.sub(kp, protect, s, flags=re.I)

    # Iteratively remove filler prefixes and suffixes
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'[.!?]+$', '', s.strip())
        s = FILLER_PREFIXES.sub('', s).strip()
        s = FILLER_SUFFIXES.sub('', s).strip()
        s = re.sub(r'^[,.!?:]+\s*', '', s.strip())

    # Restore quotes and entities
    for k, v in literals.items():
        s = s.replace(k, v)

    s = re.sub(r'\s+', ' ', s).strip(" .!?")
    return s


def split_compound_utterance(text: str) -> list[str]:
    """Split compound utterance on distinct action boundaries, preserving conjunctions inside queries/entities."""
    repaired = repair_self_corrections(text)
    literals = {}
    def protect(m):
        k = f"__TOKEN_{len(literals)}__"
        literals[k] = m.group(0)
        return k

    # Protect quoted strings
    masked = re.sub(r'"[^"\n]*"|(?<!\w)\'[^\'\n]*(?!\w)', protect, repaired)

    # Protect known conjunction phrases in common media / titles
    known_phrases = [
        r'\brock and roll\b',
        r'\bdungeons and dragons\b',
        r'\bbread and butter\b',
        r'\bme and my shadow\b',
        r'\bpeace and love\b',
    ]
    for kp in known_phrases:
        masked = re.sub(kp, protect, masked, flags=re.I)

    # If sequencers ("then", "and then", "after that", "once that's done", "next", ";") exist, split on them first
    sequencer = r'\s*(?:,\s*)?(?:and\s+then|then|after\s+that|once that\'s done|next)\s*|\s*;\s*'
    if re.search(sequencer, masked, re.I):
        chunks = re.split(sequencer, masked, flags=re.I)
    else:
        # Otherwise split on 'and' before an imperative verb
        verb_boundary = (
            r'\s+and\s+(?=(?:open|create|make|write|add|take|search|look|play|put|blast|'
            r'go|visit|launch|fire|spin|bring|hop|click|select|focus|type|enter|press|'
            r'hit|reload|switch|find|delete|send|upload|install|remove|close|stop|'
            r'rename|download|run|start|execute|gimme|give)\b)'
        )
        chunks = re.split(verb_boundary, masked, flags=re.I)

    def restore(val: str) -> str:
        for k, v in literals.items():
            val = val.replace(k, v)
        return val.strip()

    cleaned = [restore(c) for c in chunks if c.strip()]
    return cleaned if cleaned else [text.strip()]


NUMBER_WORDS = (r'(?:\d{1,3}|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|'
                r'sixteen|seventeen|eighteen|nineteen|(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)'
                r'(?:[ -](?:one|two|three|four|five|six|seven|eight|nine))?)')
KEYS = {'tab': 'Tab', 'escape': 'Escape', 'esc': 'Escape', 'space': 'space', 'spacebar': 'space', 'backspace': 'BackSpace',
        'delete': 'Delete', 'up': 'Up', 'down': 'Down', 'left': 'Left', 'right': 'Right', 'home': 'Home', 'end': 'End',
        'page up': 'Prior', 'page down': 'Next'}


def _hands_free_intent(norm: str, context: "ConversationContext | None") -> dict | None:
    """Hands-free commands: numbered hints, scrolling, typing, keys and the listening mode."""
    from blok.router import number
    t = norm.strip().strip('.!?')
    if re.fullmatch(r'(?:(?:turn|switch|put) (?:on|me in)|start|enable|go) hands?[- ]?free(?: mode)?|hands?[- ]?free(?: mode)?(?: on)?', t, re.I):
        return {'tool': 'handsfree', 'on': True}
    if re.fullmatch(r'(?:(?:turn|switch) off|stop|disable|exit|leave) hands?[- ]?free(?: mode)?|hands?[- ]?free(?: mode)? off', t, re.I):
        return {'tool': 'handsfree', 'on': False}
    if re.fullmatch(r'(?:show|display|give me|put up|turn on)(?: me)?(?: the| all)? (?:numbers|hints|labels|links|buttons)'
                    r'(?: on (?:the|this) (?:page|screen))?|numbers|number (?:mode|them|everything)', t, re.I):
        return {'tool': 'hints', 'show': True}
    if re.fullmatch(r'(?:hide|clear|remove|close|get rid of|turn off)(?: the)? (?:numbers|hints|labels)|no (?:more )?numbers', t, re.I):
        return {'tool': 'hints', 'show': False}
    showing = bool(context and context.hints_until > time.monotonic())
    m = re.fullmatch(r'(?:(click|press|tap|open|select|choose|pick|hit|go to|follow)(?: on)?(?: the)?(?: number| link| button| item)? )?'
                     r'(?:number )?(' + NUMBER_WORDS + r')((?: in a)? new tab)?', t, re.I)
    if m and (m[1] or showing or t.lower().startswith('number')):
        n = number(m[2])
        if n:
            return {'tool': 'hint', 'n': n, 'new_tab': bool(m[3])}
    m = re.fullmatch(r'(?:keep )?(?:scroll(?:ing)?|page|go|move|swipe)(?: it| the page)? (down|up)'
                     r'( a (?:little )?bit| a little| slightly)?(?: more)?|page (down|up)|(?:keep )?scrolling', t, re.I)
    if m:
        direction = (m[1] or m[3] or 'down').lower()
        return {'tool': 'scroll', 'direction': direction, 'amount': 'little' if m[2] else 'page'}
    m = re.fullmatch(r'(?:scroll|go|jump|take me)(?: all the way)?(?: back)? (?:to|up to|down to) (?:the )?(top|bottom|end|start)(?: of the page)?', t, re.I)
    if m:
        return {'tool': 'scroll', 'direction': {'end': 'bottom', 'start': 'top'}.get(m[1].lower(), m[1].lower()), 'amount': 'page'}
    m = re.fullmatch(r'type (.+)', t, re.I)
    if m and not re.search(r'\s(?:into|in) (?:the )?.+? (?:field|box|bar)$|\s(?:into|in) the .+$', t, re.I):
        return {'tool': 'type', 'text': m[1].strip()}
    m = re.fullmatch(r'(?:press|hit|tap|push)(?: the)? (' + '|'.join(sorted(KEYS, key=len, reverse=True)) + r')(?: key| button)?', t, re.I)
    if m:
        return {'tool': 'key', 'key': KEYS[m[1].lower()]}
    return None


def resolve_intent(text: str, context: ConversationContext | None = None) -> ResolvedIntent:
    """Tier 1: Canonical deterministic intent resolution & slot extraction."""
    raw = text.strip()
    norm = normalize_utterance(raw)

    # 0. Empty input guard
    if not norm or not any(c.isalnum() for c in norm):
        return ResolvedIntent(
            intent_type="empty",
            confidence=0.0,
            raw_text=raw,
            normalized_text="",
            ambiguity_reason="No speech recognized."
        )

    # 1. Negation / Cancellation check
    if NEGATION_PATTERN.search(norm):
        return ResolvedIntent(
            intent_type="cancel",
            confidence=1.0,
            raw_text=raw,
            normalized_text=norm,
            ambiguity_reason="Negation or cancellation detected; no affirmative action taken."
        )

    # 2. Unsupported safety check
    if UNSUPPORTED_VERB.search(norm):
        return ResolvedIntent(
            intent_type="unsupported",
            confidence=0.0,
            raw_text=raw,
            normalized_text=norm,
            ambiguity_reason="Unsupported step. Nothing was run."
        )

    # 3. Stop command
    if norm.lower() in ("stop listening", "stop", "cancel"):
        return ResolvedIntent(
            intent_type="stop",
            confidence=1.0,
            raw_text=raw,
            normalized_text=norm,
            action_kind="stop",
            action_value="",
        )

    # 3a. HITL Approval / Rejection commands
    if re.fullmatch(r'(?:yes|yeah|yep|approve|confirm|proceed|go ahead|do it|sure|ok|okay|haan|haan ji|ha|ji|ji haan|theek hai|thik hai|kar do|chalo kar do)(?:\s+(?:please|go ahead|do it|proceed|yes|kar do|ji))?[.!]?', norm, re.I):
        return ResolvedIntent(
            intent_type="hitl_approve",
            confidence=0.99,
            raw_text=raw,
            normalized_text=norm,
            action_kind="hitl_approval",
            action_value="approve",
        )
    if re.fullmatch(r'(?:no|nope|reject|deny|cancel|skip(?: that)?|don\'t do that|abort|nahi|nahin|nai|mat karo|rehne do|rahne do|ruko|cancel karo)(?:\s+(?:thanks|thank you|cancel(?: that)?|no|don\'t|yaar|bhai|rehne do|rahne do|mat karo|abhi nahi))?[.!]?', norm, re.I):
        return ResolvedIntent(
            intent_type="hitl_reject",
            confidence=0.99,
            raw_text=raw,
            normalized_text=norm,
            action_kind="hitl_approval",
            action_value="reject",
        )

    # 3b. Routine Recording Commands
    m = re.fullmatch(r'(?:start|begin|turn on) recording (?:the |a )?routine(?: named| called)? ([a-z0-9_ -]+)|record (?:the |a )?routine(?: named| called)? ([a-z0-9_ -]+)', norm, re.I)
    if m:
        r_name = (m[1] or m[2]).strip().replace(' ', '_').lower()
        return ResolvedIntent(
            intent_type="start_recording_routine",
            entities={"name": r_name},
            confidence=0.98,
            raw_text=raw,
            normalized_text=norm,
            action_kind="recording_routine",
            action_value=json.dumps({"action": "start", "name": r_name}),
        )

    if re.fullmatch(r'(?:stop|finish|end) recording (?:the |a )?routine', norm, re.I):
        return ResolvedIntent(
            intent_type="stop_recording_routine",
            confidence=0.98,
            raw_text=raw,
            normalized_text=norm,
            action_kind="recording_routine",
            action_value=json.dumps({"action": "stop"}),
        )

    m = re.fullmatch(r'save (?:that|the last command|the last (first|second|third|fourth|fifth|[1-9]\d*) steps) as (?:my )?(?:routine )?([a-z0-9_ -]+?)(?: routine)?', norm, re.I)
    if m:
        steps_arg = m[1]
        r_name = m[2].strip().replace(' ', '_').lower()
        num_steps = ORDINALS.get(steps_arg.lower(), int(steps_arg) if steps_arg and steps_arg.isdigit() else None) if steps_arg else None
        return ResolvedIntent(
            intent_type="save_recent_routine",
            entities={"name": r_name, "steps": num_steps},
            confidence=0.98,
            raw_text=raw,
            normalized_text=norm,
            action_kind="recording_routine",
            action_value=json.dumps({"action": "save_recent", "name": r_name, "steps": num_steps}),
        )

    # 4. Under-specified bare queries that require clarification
    if norm.lower() in ("search", "search for something", "google", "search the web", "look up something", "find something"):
        return ResolvedIntent(
            intent_type="clarify",
            confidence=0.5,
            requires_clarification=True,
            raw_text=raw,
            normalized_text=norm,
            ambiguity_reason="What would you like to search for?",
        )
    if norm.lower() in ("play", "play music", "play a song", "start music"):
        return ResolvedIntent(
            intent_type="clarify",
            confidence=0.5,
            requires_clarification=True,
            raw_text=raw,
            normalized_text=norm,
            ambiguity_reason="What song or artist would you like to play?",
        )

    # 5. Routine triggers
    m = re.fullmatch(r'(?:run|start|execute)(?: the)? (?:routine )?([a-z0-9_ -]+?)(?: routine)?', norm, re.I)
    if m:
        from blok.routines import get_routine
        r_name = m[1].strip().replace(' ', '_').lower()
        routine = get_routine(r_name)
        actual_name = routine.name if routine else r_name
        return ResolvedIntent(
            intent_type="routine",
            entities={"name": actual_name, "routine": actual_name},
            confidence=0.98 if routine else 0.92,
            raw_text=raw,
            normalized_text=norm,
            action_kind="routine",
            action_value=actual_name,
        )

    # 6. Tab creation
    # Matches: "tab", "open a tab", "open a new tab", "can you open another tab for me?", "create a tab", "new tab", "gimme another tab", "fresh tab"
    if re.fullmatch(
        r'(?:(?:open|create|launch|start|spin up|pop open|bring up|gimme|give me)(?: up)? )?'
        r'(?:a |an |another |the |fresh |new )*'
        r'(?:browser |brave )?'
        r'tabs?'
        r'(?: in (?:brave|browser))?',
        norm, re.I
    ):
        return ResolvedIntent(
            intent_type="new_tab",
            confidence=0.98,
            raw_text=raw,
            normalized_text=norm,
            action_kind="web_task",
            action_value=json.dumps({"action": "new_tab"}),
        )

    # 7. Obsidian note creation
    m = re.fullmatch(r'(?:create|make)(?: a)?(?: new)? note (?:saying|that says|containing|with (?:the )?(?:text|content)) (.+?) in obsidian', norm, re.I)
    if not m:
        m = re.fullmatch(r'(?:in obsidian[,.]? |(?:open )?obsidian and )(?:create|make)(?: a)?(?: new)? note (?:saying|that says|containing) (.+)', norm, re.I)
    if m:
        content = m[1].strip().strip('"\'')
        return ResolvedIntent(
            intent_type="obsidian_note",
            entities={"content": content},
            confidence=0.95,
            raw_text=raw,
            normalized_text=norm,
            action_kind="obsidian_note",
            action_value=json.dumps({"content": content}),
        )

    # 8. GitHub repository navigation
    m = re.fullmatch(r'(?:open|go to) github(?:\.com)? and (?:then )?(?:go to|open) my repositories and (?:then )?(?:find|search for) (.+?) and (?:then )?open (?:it|the repository)', norm, re.I)
    if not m:
        m = re.fullmatch(r'(?:open|find|go to) my github repository (.+)', norm, re.I)
    if m:
        repo = m[1].strip()
        return ResolvedIntent(
            intent_type="github_repo",
            entities={"query": repo},
            confidence=0.95,
            raw_text=raw,
            normalized_text=norm,
            action_kind="web_task",
            action_value=json.dumps({"action": "github_repo", "query": repo}),
        )

    # 9. Result selection follow-up
    # Matches: "open the first result", "open the second result", "play the second video", "click the first link that showed up"
    m = re.fullmatch(r'(?:open|click|play)(?: on)? (?:the )?(first|second|third|fourth|fifth|[1-9]|\d+)(?:st|nd|rd|th)?(?: (?:link|result|video|one))(?: (?:that )?(?:showed up|popped up|on (?:the )?(?:google )?search))?', norm, re.I)
    if m:
        ordinal_key = m[1].lower()
        idx = ORDINALS.get(ordinal_key, int(ordinal_key) if ordinal_key.isdigit() else 1)
        is_play = norm.lower().startswith("play ")
        entities = {"index": idx, "play": is_play}
        task = {"action": "result", "index": idx}
        if is_play:
            task["play"] = True
        if context and context.search_context and context.search_context.get("tabId"):
            entities["target_tab_id"] = context.search_context.get("tabId")
            task["target_tab_id"] = context.search_context.get("tabId")
        return ResolvedIntent(
            intent_type="result",
            entities=entities,
            confidence=0.95,
            raw_text=raw,
            normalized_text=norm,
            action_kind="web_task",
            action_value=json.dumps(task),
        )

    # 10. Spotify Next track follow-up ("play another song", "next track", "skip this song")
    if re.fullmatch(r'(?:play |put on )?(?:another|something else|something new|something different|next)(?: (?:song|track|music))?|skip (?:this |the )?(?:song|track)', norm, re.I):
        if context and (context.active_site == "spotify" or context.media_state):
            return ResolvedIntent(
                intent_type="next_track",
                entities={"site": "spotify"},
                confidence=0.92,
                raw_text=raw,
                normalized_text=norm,
                action_kind="web_task",
                action_value=json.dumps({"action": "next_track", "site": "spotify"}),
            )
        # Without media context, under-specified request requires clarification
        return ResolvedIntent(
            intent_type="clarify",
            confidence=0.5,
            requires_clarification=True,
            raw_text=raw,
            normalized_text=norm,
            ambiguity_reason="No music or media is currently playing. What song or artist would you like to play?",
        )

    # 11. YouTube / Google compound search & play
    m = re.fullmatch(r'(.+?) (?:and(?: then)?|then) (?:play|open) (?:the )?(first|second|third|fourth|fifth|[1-9])(?: (?:video|result|one|link))?', norm, re.I)
    if m:
        first_part = resolve_intent(m[1], context)
        if first_part.action_kind == 'web_task':
            task = json.loads(first_part.action_value)
            if task.get('action') == 'search':
                ordinal_key = m[2].lower()
                idx = ORDINALS.get(ordinal_key, int(ordinal_key) if ordinal_key.isdigit() else 1)
                seq_task = {
                    'action': 'sequence',
                    'steps': [
                        task,
                        {'action': 'result', 'index': idx, 'play': task.get('site') == 'youtube'}
                    ]
                }
                return ResolvedIntent(
                    intent_type="search_and_select",
                    entities={"query": task.get("query"), "index": idx, "site": task.get("site")},
                    confidence=0.96,
                    raw_text=raw,
                    normalized_text=norm,
                    action_kind="web_task",
                    action_value=json.dumps(seq_task),
                )

    # 11a. Drop-in commands (commands/, ~/.config/blok/commands/) win over built-ins
    from blok import plugins
    found = plugins.match(norm)
    if found:
        item, args = found
        return ResolvedIntent(
            intent_type="plugin:" + item.name, entities=args, confidence=0.96, raw_text=raw, normalized_text=norm,
            action_kind="tool", action_value=json.dumps({"tool": "plugin", "name": item.name, "args": args}),
        )

    # 11b. Desktop tools: files, volume, brightness, media, windows, questions, downloads
    from blok.router import match_rule
    tool_match = match_rule(norm)
    if tool_match:
        tool_intent, tool_action = tool_match
        return ResolvedIntent(
            intent_type="tool:" + tool_intent,
            confidence=0.95,
            raw_text=raw,
            normalized_text=norm,
            action_kind=tool_action.kind,
            action_value=tool_action.value,
        )

    # 11c. Everyday phrasing for media and sites
    here = context.active_site if context else None
    # "get me a bbs or pewdiepie video" → play one; on YouTube "play/get me X" needs no "video"
    m = re.fullmatch(r'(?:get me|give me|play(?: me)?|put on|pull up|bring up|show me|find me)(?: a| an| one| some| the)? (.+?) (?:video|vid|clip)', norm, re.I)
    if not m and here == 'youtube':
        m = re.fullmatch(r'(?:get me|give me|play(?: me)?|put on|queue up)(?: a| an| one| some| the)? (.+?)(?: videos?)?', norm, re.I)
    if m and not re.fullmatch(r'(?:first|second|third|fourth|fifth|next|another|that|this|it)(?: one)?', m[1], re.I):
        query = m[1].strip()
        task = {"action": "play", "site": "youtube", "query": query}
        if here == 'youtube' and context.active_tab_id:
            task["target_tab_id"] = context.active_tab_id
        return ResolvedIntent(intent_type="play", entities={"site": "youtube", "query": query}, confidence=0.94,
                              raw_text=raw, normalized_text=norm, action_kind="web_task", action_value=json.dumps(task))
    # "search steam for phantom blade" / "search for phantom blade on steam"
    for pattern, site_group, query_group in (
            (r'(?:search|look up|look for|find)(?: on| in)? (?:the )?([a-z][a-z ]*?) for (.+)', 1, 2),
            (r'(?:search(?: for)?|look up|look for|find) (.+?) (?:on|in) (?:the )?([a-z][a-z ]*)', 2, 1)):
        m = re.fullmatch(pattern, norm, re.I)
        site = SITE_ALIASES.get(m[site_group].lower(), m[site_group].lower()) if m else None
        if site in SITE_SEARCH:
            query = m[query_group].strip()
            return ResolvedIntent(intent_type="search", entities={"site": site, "query": query}, confidence=0.94, raw_text=raw,
                                  normalized_text=norm, action_kind="url", action_value=SITE_SEARCH[site].format(q=quote_plus(query)))
    # "search here for X" / "search this site for X" → the page's own search box
    m = (re.fullmatch(r'(?:search|look up|look for|find) (?:here|on this (?:site|page|website)|this (?:site|page|website)) for (.+)', norm, re.I)
         or re.fullmatch(r'(?:search(?: for)?|look up|look for|find) (.+?) (?:here|on this (?:site|page|website))', norm, re.I))
    if m:
        task = {"action": "site_search", "query": m[1].strip()}
        return ResolvedIntent(intent_type="search", entities=task, confidence=0.94, raw_text=raw, normalized_text=norm,
                              action_kind="web_task", action_value=json.dumps(task))
    # Hands-free: numbered hints, scrolling, typing, keys, listening mode
    hands_free = _hands_free_intent(norm, context)
    if hands_free:
        return ResolvedIntent(intent_type="hands_free:" + hands_free["tool"], entities=hands_free, confidence=0.95,
                              raw_text=raw, normalized_text=norm, action_kind="tool", action_value=json.dumps(hands_free))
    # "click that button" → whatever the mouse is pointing at in the browser
    if re.fullmatch(r'(?:click|press|hit|tap|select|push)(?: on)? (?:that|this|it|here|there|the one under (?:the|my) (?:mouse|cursor|pointer))'
                    r'(?: (?:button|link|thing|one|tab|video|item|icon|option))?(?: (?:right )?(?:here|there))?', norm, re.I):
        task = {"action": "click", "pointer": True, "target": "the control under the mouse"}
        return ResolvedIntent(intent_type="ui_control", entities=task, confidence=0.94, raw_text=raw, normalized_text=norm,
                              action_kind="ui_control", action_value=json.dumps(task))
    # "watch/see some cat videos (on youtube)" → YouTube search
    m = re.fullmatch(r'(?:watch|see|show me|find me|look for|look at|check out|pull up|bring up)(?: some| a| the)? (.+?)(?: videos?| clips?)?(?: on| in) (?:youtube|youtub)', norm, re.I) \
        or re.fullmatch(r'watch(?: some| a| the)? (.+?)(?: videos?| clips?)?', norm, re.I) \
        or re.fullmatch(r'(?:see|show me|find me)(?: some| a)? (.+? (?:videos?|clips?|trailers?|gameplay))', norm, re.I)
    if m:
        query = m[1].strip() + (' videos' if re.search(r'\bvideos?\b', norm, re.I) and not re.search(r'videos?|trailer|gameplay', m[1], re.I) else '')
        task = {"action": "search", "site": "youtube", "query": query}
        return ResolvedIntent(intent_type="search", entities={"site": "youtube", "query": query}, confidence=0.93,
                              raw_text=raw, normalized_text=norm, action_kind="web_task", action_value=json.dumps(task))
    # "listen to arijit singh" → play on Spotify
    m = re.fullmatch(r'(?:listen to|hear)(?: some)? (.+)', norm, re.I)
    if m and not re.fullmatch(r'me|this|that|it', m[1], re.I):
        norm = 'play ' + m[1]
    # "look up / pull up / check reddit" → open the site, not a Google search for its name
    m = re.fullmatch(r'(?:look up|pull up|bring up|check|check out|go on|get on|hop on|load|show me|take me to) (?:the |my )?(.+?)(?: website| site| page)?', norm, re.I)
    if m:
        target = m[1].strip().lower()
        url = SITES.get(target) or SITES.get(target.removesuffix('.com'))
        if not url and re.fullmatch(r'(?:www\.)?(?:[a-z0-9-]+\.)+[a-z]{2,24}(?:/\S*)?', target):
            url = 'https://' + target
        if url:
            return ResolvedIntent(intent_type="navigate", entities={"url": url}, confidence=0.94, raw_text=raw,
                                  normalized_text=norm, action_kind="url", action_value=url)
    # "pull up the weather in mumbai on google" → Google search
    m = re.fullmatch(r'(?:pull up|bring up|check|show me|find|get me|tell me|what\'s|what is) (?:the )?(.+?) (?:on|in|using|with) google', norm, re.I)
    if m:
        task = {"action": "search", "site": "google", "query": m[1].strip()}
        return ResolvedIntent(intent_type="search", entities=task, confidence=0.94, raw_text=raw, normalized_text=norm,
                              action_kind="web_task", action_value=json.dumps(task))
    # "open this app" / "open something" → ask which one instead of guessing
    if re.fullmatch(r'(?:open|launch|start|run|pull up|bring up) (?:this|that|an?|the|some|my)? ?(?:app|application|program|thing|something|stuff|one)', norm, re.I):
        return ResolvedIntent(intent_type="clarify", confidence=0.5, requires_clarification=True, raw_text=raw,
                              normalized_text=norm, ambiguity_reason="Which app should I open?")

    # 12. Search or Play on Specific Site (Google, YouTube, Spotify)
    site_pattern = r'(google|youtube|youtub|spotify|spotfy)(?:\s*dot\s*com|\.com)?'

    # "google search games", "youtube search bbs", "spotify play god's plan"
    m = re.fullmatch(rf'^{site_pattern} (search(?: for| up)?|play(?: some)?|look up|put on|blast|throw on|spin) (.+)$', norm, re.I)
    if not m:
        # "open google and search for games", "go to youtube and play bbs"
        m = re.fullmatch(rf'^(?:open|go to|visit) (?:www\.)?{site_pattern}(?: and(?: then)?| then) (search(?: for| up)?|play(?: some)?|look up|put on|blast|throw on|spin) (.+)$', norm, re.I)
    if not m:
        # "search youtube for elden ring", "look up on youtube for cats"
        m_for = re.fullmatch(rf'^(?:search|look up|look for|find)(?: on| in)? {site_pattern} for (.+)$', norm, re.I)
        if m_for:
            m = re.fullmatch(rf'^{site_pattern} (search) (.+)$', f'{m_for[1]} search {m_for[2]}', re.I)
    if not m:
        # "search for games on google", "play god's plan on spotify"
        m = re.fullmatch(rf'^(search(?: for| up)?|play(?: some)?|put on|blast|throw on|spin|look up|find(?: some)?) (.+?) (?:on|in) {site_pattern}$', norm, re.I)
    if m:
        groups = m.groups()
        if len(groups) == 3:
            if groups[0].lower() in ('google', 'youtube', 'youtub', 'spotify', 'spotfy'):
                site_name, verb, query = groups[0].lower(), groups[1].lower(), groups[2].strip()
            else:
                verb, query, site_name = groups[0].lower(), groups[1].strip(), groups[2].lower()
        else:
            site_name, verb, query = groups[0].lower(), groups[1].lower(), groups[2].strip()

        site_name = "youtube" if "youtub" in site_name else "spotify" if "spotfy" in site_name else site_name
        is_play = any(verb.startswith(p) for p in ('play', 'put', 'blast', 'throw', 'spin'))
        task: dict[str, Any] = {
            'action': 'play' if is_play else 'search',
            'site': site_name,
            'query': query,
        }
        if context and context.active_tab_id:
            task['target_tab_id'] = context.active_tab_id

        if is_play and site_name == 'spotify':
            artist_m = re.fullmatch(r'(?:a |any |some )?(.+?)(?: song| songs| music)', query, re.I) or re.fullmatch(r'(?:a |any |some )?(?:song|music) by (.+)', query, re.I)
            if artist_m:
                task.update(query=artist_m[1], mode='artist')

        return ResolvedIntent(
            intent_type="play" if is_play else "search",
            entities={"site": site_name, "query": task.get("query"), "mode": task.get("mode")},
            confidence=0.96,
            raw_text=raw,
            normalized_text=norm,
            action_kind="web_task",
            action_value=json.dumps(task),
        )

    # 13. "Google <query>" or "Google search <query>"
    m = re.fullmatch(r'(?:google search|google) (.+)', norm, re.I)
    if m:
        query = m[1].strip()
        task = {"action": "search", "site": "google", "query": query}
        if context and context.active_tab_id:
            task["target_tab_id"] = context.active_tab_id
        return ResolvedIntent(
            intent_type="search",
            entities={"site": "google", "query": query},
            confidence=0.95,
            raw_text=raw,
            normalized_text=norm,
            action_kind="web_task",
            action_value=json.dumps(task),
        )

    # 14. General "search for <query>", "look up <query>", "find <query> online"
    m = re.fullmatch(r'(?:search(?: for| up)?|look up|find me|check out|see what\'s on|find online|look online for|search the web for|find|google search|look for) (.+?)(?: online| on the (?:web|internet))?', norm, re.I)
    if m:
        query = re.sub(r'^(?:the|some|a) ', '', m[1].strip(), flags=re.I)
        if context and context.active_site in SITE_SEARCH:
            return ResolvedIntent(intent_type="search", entities={"site": context.active_site, "query": query}, confidence=0.94,
                                  raw_text=raw, normalized_text=norm, action_kind="url",
                                  action_value=SITE_SEARCH[context.active_site].format(q=quote_plus(query)))
        site = context.active_site if (context and context.active_site in ('google', 'youtube', 'spotify')) else "google"
        task = {"action": "search", "site": site, "query": query}
        if context and context.active_tab_id:
            task["target_tab_id"] = context.active_tab_id
        return ResolvedIntent(
            intent_type="search",
            entities={"site": site, "query": query},
            confidence=0.94,
            raw_text=raw,
            normalized_text=norm,
            action_kind="web_task",
            action_value=json.dumps(task),
        )

    # 15. "Play <track/artist>" (defaults to Spotify, unless explicit)
    m = re.fullmatch(r'(?:play|put on|blast|throw on|spin(?!\s+up)|queue up)(?: me)?(?: some| a few| a little)? (.+)', norm, re.I)
    if m and not re.match(r'(?:the )?(?:first|second|third|fourth|fifth|[1-9])(?: |$)', m[1], re.I):
        song = m[1].strip()
        task = {'action': 'play', 'site': 'spotify', 'query': song}
        if context and context.active_tab_id:
            task['target_tab_id'] = context.active_tab_id
        artist_m = re.fullmatch(r'(?:a |any |some )?(.+?)(?: song| songs| music)', song, re.I) or re.fullmatch(r'(?:a |any |some )?(?:song|music) by (.+)', song, re.I)
        if artist_m:
            task.update(query=artist_m[1], mode='artist')
        return ResolvedIntent(
            intent_type="play",
            entities={"site": "spotify", "query": task.get("query"), "mode": task.get("mode")},
            confidence=0.93,
            raw_text=raw,
            normalized_text=norm,
            action_kind="web_task",
            action_value=json.dumps(task),
        )

    # 16. UI Controls
    m = re.fullmatch(r'(?:click|select|focus)(?: on)? (?:the )?(.+)', norm, re.I)
    if m and not re.fullmatch(r'(?:address|url) bar', m[1], re.I):
        target = m[1].strip()
        if target.lower() == 'search bar':
            task = {'action': 'click', 'target': 'Search', 'role': 'field'}
        else:
            task = {'action': 'click', 'target': target}
        return ResolvedIntent(
            intent_type="ui_control",
            entities=task,
            confidence=0.92,
            raw_text=raw,
            normalized_text=norm,
            action_kind="ui_control",
            action_value=json.dumps(task),
        )

    m = re.fullmatch(r'(?:type|enter) (.+?) (?:into (?:the )?|in the )(.+?)(?: field)?', norm, re.I)
    if m:
        task = {'action': 'fill', 'target': m[2].strip(), 'text': m[1].strip()}
        return ResolvedIntent(
            intent_type="ui_control",
            entities=task,
            confidence=0.92,
            raw_text=raw,
            normalized_text=norm,
            action_kind="ui_control",
            action_value=json.dumps(task),
        )

    # 17. Address bar & Browser controls
    if re.fullmatch(r'(?:go to|focus|click(?: on)?|select|open)(?: the)? (?:address|url) bar', norm, re.I):
        return ResolvedIntent(
            intent_type="address",
            confidence=0.95,
            raw_text=raw,
            normalized_text=norm,
            action_kind="address",
            action_value="",
        )

    m = re.fullmatch(r'type (.+?) in (?:the )?(?:address|url) bar', norm, re.I)
    if m:
        return ResolvedIntent(
            intent_type="browser_type",
            entities={"text": m[1].strip()},
            confidence=0.95,
            raw_text=raw,
            normalized_text=norm,
            action_kind="browser_type",
            action_value=m[1].strip(),
        )

    m = re.fullmatch(r'(?:press|hit) enter', norm, re.I)
    if m:
        return ResolvedIntent(
            intent_type="browser_key",
            entities={"key": "enter"},
            confidence=0.95,
            raw_text=raw,
            normalized_text=norm,
            action_kind="browser_key",
            action_value="enter",
        )

    if norm.lower() in ("go back", "back"):
        return ResolvedIntent(
            intent_type="browser_key", entities={"key": "back"}, confidence=0.95,
            raw_text=raw, normalized_text=norm, action_kind="browser_key", action_value="back"
        )
    if norm.lower() in ("go forward", "forward"):
        return ResolvedIntent(
            intent_type="browser_key", entities={"key": "forward"}, confidence=0.95,
            raw_text=raw, normalized_text=norm, action_kind="browser_key", action_value="forward"
        )
    if norm.lower() in ("reload", "reload the page", "refresh", "refresh the page"):
        return ResolvedIntent(
            intent_type="browser_key", entities={"key": "reload"}, confidence=0.95,
            raw_text=raw, normalized_text=norm, action_kind="browser_key", action_value="reload"
        )

    # 18. Application Launching & Site Navigation
    m = re.fullmatch(r'(?:open(?: up)?|launch|bring up|go to|visit|fire up|spin up|hop over to|hop to|pull up|pop open|switch to|i need|i want|gimme|give me|go on|get on|hop on|load up|start up) (?:the |my )?(.+)', norm, re.I)
    if m:
        target = m[1].strip().lower().removesuffix(" app").removesuffix(" application")
        if target in APPS:
            app_id = APPS[target]
            return ResolvedIntent(
                intent_type="open_app",
                entities={"app": app_id},
                confidence=0.95,
                raw_text=raw,
                normalized_text=norm,
                action_kind="open",
                action_value=app_id,
            )
        if target in SITES:
            return ResolvedIntent(
                intent_type="navigate",
                entities={"url": SITES[target]},
                confidence=0.95,
                raw_text=raw,
                normalized_text=norm,
                action_kind="url",
                action_value=SITES[target],
            )
        target_site = target.removesuffix(".com").removesuffix(".org")
        if target_site in SITES:
            return ResolvedIntent(
                intent_type="navigate",
                entities={"url": SITES[target_site]},
                confidence=0.95,
                raw_text=raw,
                normalized_text=norm,
                action_kind="url",
                action_value=SITES[target_site],
            )
        if re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,24}(?:/[^\s]*)?', target):
            url = f"https://{target}"
            return ResolvedIntent(
                intent_type="navigate",
                entities={"url": url},
                confidence=0.92,
                raw_text=raw,
                normalized_text=norm,
                action_kind="url",
                action_value=url,
            )

    # 19. Notes manipulation
    m = re.fullmatch(r'(?:create|make)(?: a)?(?: new)? note(?: (?:called|titled|named))? (.+)', norm, re.I)
    if m:
        title = m[1].strip().strip('"\'')
        return ResolvedIntent(
            intent_type="new_note",
            entities={"title": title},
            confidence=0.95,
            raw_text=raw,
            normalized_text=norm,
            action_kind="new_note",
            action_value=title,
        )

    m = re.fullmatch(r'(?:make|set|change) (?:the |its )?title(?: to| say)? (.+)', norm, re.I) or re.fullmatch(r'(?:title|call) it (.+)', norm, re.I)
    if m:
        title = m[1].strip().strip('"\'')
        return ResolvedIntent(
            intent_type="title",
            entities={"title": title},
            confidence=0.95,
            raw_text=raw,
            normalized_text=norm,
            action_kind="title",
            action_value=title,
        )

    m = re.fullmatch(r'(?:write|add)(?: down)? (.+)', norm, re.I)
    if m:
        body = m[1].strip().strip('"\'')
        return ResolvedIntent(
            intent_type="write",
            entities={"body": body},
            confidence=0.95,
            raw_text=raw,
            normalized_text=norm,
            action_kind="write",
            action_value=body,
        )

    # 20. Photo
    if re.fullmatch(r'take(?: a)? (?:picture|photo|selfie)(?: of me)?', norm, re.I):
        return ResolvedIntent(
            intent_type="photo",
            confidence=0.95,
            raw_text=raw,
            normalized_text=norm,
            action_kind="photo",
            action_value="",
        )

    # 21. Workspace switching
    m = re.fullmatch(r'(?:switch to|go to) workspace (.+)', norm, re.I)
    if m:
        w_arg = m[1].strip().lower()
        w_num = ORDINALS.get(w_arg, w_arg)
        num_str = str(w_num)
        if num_str.isdigit() and 1 <= int(num_str) <= 10:
            return ResolvedIntent(
                intent_type="workspace",
                entities={"workspace": num_str},
                confidence=0.95,
                raw_text=raw,
                normalized_text=norm,
                action_kind="workspace",
                action_value=num_str,
            )

    # Unclassified deterministically
    return ResolvedIntent(
        intent_type="unclassified",
        confidence=0.0,
        raw_text=raw,
        normalized_text=norm,
    )
