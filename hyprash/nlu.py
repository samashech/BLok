"""Natural-language understanding: canonical intents, entities, and normalization.

Phase 6 Tier-1 deterministic normalization and grammar, typed schemas,
and conversation context tracking for Hyprash.
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
    "hyprash notes": "hyprash_notes", "hyprash camera": "hyprash_camera",
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
}

FILLER_PREFIXES = re.compile(
    r'^(?:'
    r'can you please|could you please|would you please|will you please|'
    r'can you|could you|would you|will you|'
    r'hey hyprash|hey assistant|hey|hi hyprash|hi|hello|'
    r'okay hyprash|okay now|okay|ok now|ok|'
    r'i want you to|i want to|i would like you to|i would like to|i\'d like you to|i\'d like to|'
    r'i need you to|i need to|'
    r'let\'s|lets|'
    r'go ahead and|feel free to|'
    r'now please|now|just|'
    r'please|pls'
    r')[,:]?\s+', re.I
)

FILLER_SUFFIXES = re.compile(
    r'[,.]?\s+(?:'
    r'for me please|for us please|for me|for us|'
    r'please|pls|thanks|thank you|'
    r'right now|quickly'
    r')[.!?]*\s*$', re.I
)

NEGATION_PATTERN = re.compile(r'\b(?:don\'t|do not|never|cancel|actually|instead)\b', re.I)
UNSUPPORTED_VERB = re.compile(
    r'\b(?:delete|erase|remove|format|shutdown|shut down|reboot|restart|destroy|drop database|install|uninstall)\b', re.I
)


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


@dataclass
class ConversationContext:
    active_tab_id: int | None = None
    active_site: str | None = None
    last_intent: str | None = None
    search_context: dict[str, Any] | None = None  # {tabId, url, site, query, created_at}
    active_app: str | None = None
    media_state: dict[str, Any] | None = None

    def update_tab(self, tab_id: int | None, url: str | None = None, site: str | None = None):
        self.active_tab_id = tab_id
        if site:
            self.active_site = site
        elif url:
            for s in SITES:
                if s in url:
                    self.active_site = s
                    break

    def set_search_context(self, tab_id: int, url: str, site: str, query: str):
        self.search_context = {
            'tabId': tab_id,
            'url': url,
            'site': site,
            'query': query,
            'created_at': time.monotonic(),
        }
        self.active_tab_id = tab_id
        self.active_site = site

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
            'active_site': self.active_site,
            'last_intent': self.last_intent,
            'has_valid_search': self.is_search_context_valid(),
            'active_app': self.active_app,
        }


def normalize_utterance(text: str) -> str:
    """Clean conversational fillers, contractions, and domain words while preserving quotes and semantic entities."""
    s = text.strip().replace('’', "'")
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
    literals = {}
    def protect(m):
        k = f"__TOKEN_{len(literals)}__"
        literals[k] = m.group(0)
        return k

    # Protect quoted strings
    masked = re.sub(r'"[^"\n]*"|(?<!\w)\'[^\'\n]*(?!\w)', protect, text)

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

    # If sequencers ("then", "and then", "after that", ";") exist, split on them first
    sequencer = r'\s*(?:,\s*)?(?:and\s+then|then|after\s+that)\s*|\s*;\s*'
    if re.search(sequencer, masked, re.I):
        chunks = re.split(sequencer, masked, flags=re.I)
    else:
        # Otherwise split on 'and' before an imperative verb
        verb_boundary = (
            r'\s+and\s+(?=(?:open|create|make|write|add|take|search|play|go|visit|launch|'
            r'click|select|focus|type|enter|press|hit|reload|switch|find|delete|send|'
            r'upload|install|remove|close|stop|rename|download|run|start|execute)\b)'
        )
        chunks = re.split(verb_boundary, masked, flags=re.I)

    def restore(val: str) -> str:
        for k, v in literals.items():
            val = val.replace(k, v)
        return val.strip()

    cleaned = [restore(c) for c in chunks if c.strip()]
    return cleaned if cleaned else [text.strip()]


def resolve_intent(text: str, context: ConversationContext | None = None) -> ResolvedIntent:
    """Tier 1: Canonical deterministic intent resolution & slot extraction."""
    raw = text.strip()
    norm = normalize_utterance(raw)

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
        from hyprash.routines import get_routine
        routine = get_routine(m[1].strip())
        if routine:
            return ResolvedIntent(
                intent_type="routine",
                entities={"name": routine.name},
                confidence=0.98,
                raw_text=raw,
                normalized_text=norm,
                action_kind="routine",
                action_value=routine.name,
            )

    # 6. Tab creation
    # Matches: "open a tab", "open a new tab", "can you open another tab for me?", "create a tab", "new tab"
    if re.fullmatch(
        r'(?:(?:open|create|launch|start)(?: up)? )?'
        r'(?:a |an |another |the |fresh |new )*'
        r'(?:browser |brave )?'
        r'tab'
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

    # 12. Search or Play on Specific Site (Google, YouTube, Spotify)
    site_pattern = r'(google|youtube|spotify)(?:\s*dot\s*com|\.com)?'

    # "google search games", "youtube search bbs", "spotify play god's plan"
    m = re.fullmatch(rf'^{site_pattern} (search(?: for)?|play|look up) (.+)$', norm, re.I)
    if not m:
        # "open google and search for games", "go to youtube and play bbs"
        m = re.fullmatch(rf'^(?:open|go to|visit) (?:www\.)?{site_pattern}(?: and(?: then)?| then) (search(?: for)?|play|look up) (.+)$', norm, re.I)
    if not m:
        # "search for games on google", "play god's plan on spotify"
        m = re.fullmatch(rf'^(search(?: for)?|play|look up|find(?: some)?) (.+?) (?:on|in) {site_pattern}$', norm, re.I)
    if m:
        groups = m.groups()
        if len(groups) == 3:
            if groups[0].lower() in ('google', 'youtube', 'spotify'):
                site_name, verb, query = groups[0].lower(), groups[1].lower(), groups[2].strip()
            else:
                verb, query, site_name = groups[0].lower(), groups[1].strip(), groups[2].lower()
        else:
            site_name, verb, query = groups[0].lower(), groups[1].lower(), groups[2].strip()

        is_play = verb.startswith('play')
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
    m = re.fullmatch(r'(?:search for|look up|find online|look online for|search the web for|search|find) (.+?)(?: online)?', norm, re.I)
    if m:
        query = m[1].strip()
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
    m = re.fullmatch(r'play (.+)', norm, re.I)
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
    m = re.fullmatch(r'(?:open(?: up)?|launch|bring up|go to|visit) (?:the |my )?(.+)', norm, re.I)
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
