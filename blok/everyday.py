"""Everyday one-shot commands: tabs, zoom, copy and paste, power, wifi, media, and closing an app by name.

Checked before the other rules, because these phrasings used to be misread: "close this tab"
opened a tab, "close brave" closed whatever was in front, and "select all" clicked a link called
"all". Each phrase must match as a whole, so longer commands still reach their own rules.
"""
import json
import re

APP_WORDS = r"(?:computer|laptop|pc|system|machine|device)"

# (pattern, task). A task value that's a function gets the match and builds the task.
RULES = [
    # Browser tabs and pages
    (r"close (?:this |the |current |that |my )?tab|close tab|tab (?:close|band)", {'tool': 'shortcut', 'name': 'close_tab'}),
    (r"(?:re-?open|restore|bring back|undo close)(?: the| my)?(?: last| recently)?(?: closed)? tab(?: (?:i|that i) (?:just )?closed)?|"
     r"open (?:the |my )?(?:last |recently )?closed tab|"
     r"(?:re-?open|restore|bring back)(?: the| my)? last tab", {'tool': 'shortcut', 'name': 'reopen_tab'}),
    (r"(?:go to |switch to |move to |show )?(?:the )?next tab|tab (?:right|forward)|agla tab", {'tool': 'shortcut', 'name': 'next_tab'}),
    (r"(?:go to |switch to |move to |show )?(?:the )?(?:previous|prev) tab|(?:go )?back a tab|tab (?:left|back)|pichla tab", {'tool': 'shortcut', 'name': 'previous_tab'}),
    (r"(?:refresh|reload)(?: (?:the|this|my) (?:page|tab|site|website))?|(?:page|tab) (?:refresh|reload)|refresh it", {'tool': 'shortcut', 'name': 'refresh'}),
    (r"zoom in(?: a (?:bit|little))?|(?:make (?:the |this )?(?:page |text |it |everything )?)bigger|(?:increase|bigger) (?:the )?(?:text|font)(?: size)?", {'tool': 'shortcut', 'name': 'zoom_in'}),
    (r"zoom out(?: a (?:bit|little))?|(?:make (?:the |this )?(?:page |text |it |everything )?)smaller|(?:decrease|smaller) (?:the )?(?:text|font)(?: size)?", {'tool': 'shortcut', 'name': 'zoom_out'}),
    (r"(?:reset|normal|default|actual) (?:the )?(?:zoom|size)|zoom (?:back )?to (?:normal|100(?: percent|%)?)|reset (?:the )?page size", {'tool': 'shortcut', 'name': 'zoom_reset'}),
    (r"bookmark (?:this|the|that)(?: page| site| website| tab)?|bookmark it|add (?:this|the|that)(?: page| site)? to (?:my )?bookmarks|save (?:this|the) page as a bookmark",
     {'tool': 'shortcut', 'name': 'bookmark'}),
    # Editing, in whatever app is in front
    (r"copy(?: (?:this|that|it|the (?:text|selection|selected text)|selected text|what i selected))?(?: please)?", {'tool': 'shortcut', 'name': 'copy'}),
    (r"cut(?: (?:this|that|it|the (?:text|selection)|selected text))?", {'tool': 'shortcut', 'name': 'cut'}),
    (r"paste(?: (?:it|this|that|here|the text))?(?: here)?(?: please)?", {'tool': 'shortcut', 'name': 'paste'}),
    (r"undo(?: (?:that|it|this|the last (?:change|thing|step)|what i did))?", {'tool': 'shortcut', 'name': 'undo'}),
    (r"redo(?: (?:that|it|this))?", {'tool': 'shortcut', 'name': 'redo'}),
    (r"select (?:all|everything)(?: (?:the )?text)?|highlight (?:all|everything)", {'tool': 'shortcut', 'name': 'select_all'}),
    # Sound and media: say exactly what you want, never a toggle that might do the opposite
    (r"mute(?: (?:the )?(?:sound|audio|volume|speakers?|computer|laptop))?|(?:turn|switch) off (?:the )?(?:sound|audio)|silence", {'tool': 'volume', 'op': 'mute_on'}),
    (r"unmute(?: (?:the )?(?:sound|audio|volume|speakers?|computer|laptop))?|(?:turn|switch) (?:the )?(?:sound|audio) (?:back )?on|(?:turn|switch) on (?:the )?(?:sound|audio)",
     {'tool': 'volume', 'op': 'mute_off'}),
    (r"pause(?: (?:it|this|that|the (?:music|song|video|playback|media|track)))?|stop (?:the )?(?:music|song|video|playback)|pause karo|gaana (?:roko|band karo)",
     {'tool': 'media', 'op': 'pause'}),
    (r"(?:resume|unpause|continue|keep playing|start playing again)(?: (?:it|the (?:music|song|video|playback)|playing|playback))?|play (?:it )?again|chalu karo",
     {'tool': 'media', 'op': 'play'}),
    (r"(?:skip|next)(?: (?:this|the))?(?: (?:song|track|one))|skip(?: it| this)?|play the next (?:song|track)|agla gaana", {'tool': 'media', 'op': 'next'}),
    (r"(?:set|change|put|turn|make) (?:the )?(?:screen )?brightness (?:to |at |up to |down to )?(?P<n>\d{1,3})(?: ?%| percent)?|brightness (?:to |at )?(?P<n2>\d{1,3})(?: ?%| percent)?",
     lambda m: {'tool': 'brightness', 'op': 'set', 'level': int(m['n'] or m['n2'])}),
    # Wifi and bluetooth
    (r"(?:turn|switch|put) (?P<on>on|off) (?:the )?(?P<radio>wi-?fi|bluetooth|internet)|(?:turn|switch) (?:the )?(?P<radio2>wi-?fi|bluetooth) (?P<on2>on|off)|"
     r"(?P<verb>enable|disable|connect|disconnect)(?: the)? (?P<radio3>wi-?fi|bluetooth)|(?P<radio4>wi-?fi|bluetooth) (?P<on4>on|off|chalu karo|band karo|chalu|band)",
     lambda m: _radio(m)),
    # Power, always confirmed on screen
    (r"(?:go to sleep|sleep|suspend|hibernate)(?: (?:the |my )?" + APP_WORDS + r")?|put (?:the |my )?" + APP_WORDS + r" to sleep|(?:computer|laptop|pc) so jao",
     {'tool': 'power', 'op': 'suspend'}),
    (r"(?:shut ?down|power off|switch off|turn off)(?: (?:the |my )?" + APP_WORDS + r")?|" + r"(?:computer|laptop|pc|system) band karo", {'tool': 'power', 'op': 'poweroff'}),
    (r"(?:restart|reboot)(?: (?:the |my )?" + APP_WORDS + r")?", {'tool': 'power', 'op': 'reboot'}),
    # Windows
    (r"(?:take a |grab a )?screenshot (?:of )?(?:this|the|current|active|that) (?:window|app)|screenshot (?:this|the) (?:window|app)|(?:window|app) (?:ka )?screenshot(?: lo)?",
     {'tool': 'screenshot_window'}),
    (r"minimi[sz]e(?: (?:this|the|that|it))?(?: window| app)?|hide (?:this|the) window", {'tool': 'window', 'op': 'minimize'}),
    # Weather has no offline answer, so it's a search, in the tab you're on
    (r"(?:what(?:'s| is| will be) the weather(?: like)?|how(?:'s| is) the weather|weather(?: report| forecast| today| now)?|"
     r"(?:is it|will it|is it going to) (?:rain|be (?:hot|cold|sunny))|mausam (?:kaisa hai|kya hai))(?: (?:in|at|for) (?P<place>[a-z][a-z .'-]{1,40}?))?(?: today| tomorrow| now| this week)?",
     lambda m: {'action': 'search', 'site': 'google', 'query': 'weather' + (f' in {m["place"].strip()}' if m['place'] else '')}),
]

# "open the github tab" switches; "open a tab", "open another tab" or "pop open a fresh tab" make a new one.
SWITCH_TAB = re.compile(r"(?:switch|go|jump|change|take me) (?:back )?to (?:the |my )?(?P<q>.+?) tab|(?:open|show) (?:the|my) (?P<q2>.+?) tab(?: (?:again|that's open))?")
NEW_TAB_WORDS = re.compile(r"(?:(?:a|an|another|one|one more|some|the|my) )?(?:new|blank|empty|fresh|extra|other|incognito|private|clean)?(?: (?:new|blank|empty))?|another|a|an|one", re.I)
CLOSE_APP = re.compile(r"(?:close|quit|exit|kill) (?:the |my )?(?P<app>[a-z][a-z0-9 .+-]{1,30}?)(?: (?:app|application|window|program))?(?: please| for me)?")
NOT_AN_APP = re.compile(r"^(?:it|this|that|the window|window|this window|tab|this tab|the tab|everything|all|all windows|others|other windows|the others|"
                        r"the door|my eyes|the first result|.* tab|.* result|.* (?:button|link)|it down|down|"
                        r"wi-?fi|bluetooth|internet|net|computer|laptop|pc|system|music|song|video|sound|volume|the (?:music|song|video|sound|volume))$")
_COMPILED = [(re.compile(pattern, re.I), task) for pattern, task in RULES]


def _radio(match) -> dict:
    groups = match.groupdict()
    radio = next(groups[k] for k in ('radio', 'radio2', 'radio3', 'radio4') if groups.get(k))
    state = next((groups[k] for k in ('on', 'on2', 'on4') if groups.get(k)), None)
    verb = groups.get('verb')
    on = (verb in ('enable', 'connect')) if verb else (state in ('on', 'chalu', 'chalu karo'))
    return {'tool': 'radio', 'radio': 'bluetooth' if 'blue' in radio else 'wifi', 'on': on}


def intent(text: str) -> tuple[str, str] | None:
    """(action kind, value) for an everyday command, or None."""
    said = re.sub(r"[.!?]+$", '', text.strip().lower().replace('’', "'")).strip()
    said = re.sub(r"^(?:please |can you |could you |would you |hey |ok |okay )+|(?: please| for me| now| right now)+$", '', said).strip()
    for pattern, task in _COMPILED:
        found = pattern.fullmatch(said)
        if found:
            task = task(found) if callable(task) else task
            return ('web_task' if 'action' in task else 'tool'), json.dumps(task)
    found = SWITCH_TAB.fullmatch(said)
    if found:
        query = (found['q'] or found['q2']).strip()
        if not NEW_TAB_WORDS.fullmatch(query) and not re.fullmatch(r'(?:next|previous|last|closed|last closed|first|1st|new|blank|empty|fresh)(?: one)?', query):
            return 'tool', json.dumps({'tool': 'switch_tab', 'query': query})
    found = CLOSE_APP.fullmatch(said)
    if found and not NOT_AN_APP.match(found['app'].strip()):
        return 'tool', json.dumps({'tool': 'window', 'op': 'close', 'app': found['app'].strip()})
    return None
