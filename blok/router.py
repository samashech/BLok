"""Tool intents: strict rules first, then two-stage Laya routing with Python slot extraction.

Laya answers bounded `choice` questions only, so it picks an area and then an
action within it (≤10 options each). Python extracts the literal arguments for
the chosen action from the utterance; if they cannot be found, nothing runs and
BLoK asks for the missing part.
"""
from dataclasses import dataclass
import json
import re
from urllib.parse import quote_plus

from blok.commands import Action

NONE = 'None of these'
AREAS = {
    'Files and folders': {
        'Find a file': 'file_find', 'Open a file or folder': 'file_open',
        'Read or show what is in a file': 'file_read', 'Add text to a file': 'file_append',
        'Create a new file': 'file_create', 'Rename or move a file': 'file_rename',
        'Copy a file': 'file_copy', 'Delete a file': 'file_delete',
    },
    'Web browser and websites': {
        'Search Google': 'web_google', 'Search YouTube': 'web_youtube', 'Open a website': 'web_site',
        'Download something': 'download', 'Open a new tab': 'new_tab',
    },
    'Music and video playback': {
        'Play a song': 'media_play', 'Pause or resume': 'media_toggle',
        'Next track': 'media_next', 'Previous track': 'media_previous',
    },
    'App windows and workspaces': {
        'Open an app': 'app_open', 'Close the window': 'window_close',
        'Make the window fullscreen': 'window_fullscreen', 'Float or tile the window': 'window_float',
        'Switch workspace': 'workspace', 'Move window to another workspace': 'window_move',
        'Switch to an open app': 'window_focus',
    },
    'Volume, brightness and system': {
        'Volume up': 'volume_up', 'Volume down': 'volume_down', 'Mute or unmute': 'volume_mute',
        'Set the volume to a level': 'volume_set', 'Brightness up': 'brightness_up',
        'Brightness down': 'brightness_down', 'Lock the screen': 'lock', 'Change the theme': 'theme',
    },
    'Focus and window layouts': {
        'Put two apps side by side': 'arrange', 'Save the window layout': 'layout_save',
        'Restore a saved window layout': 'layout_restore', 'Start focus mode': 'focus_on', 'End focus mode': 'focus_off',
    },
    'Notes': {'Create a note': 'note_create', 'Write in the note': 'note_write', 'Open notes': 'notes_open'},
    'Camera': {'Open camera': 'camera_open', 'Take a photo': 'photo'},
    'Questions about time, date or battery': {
        'Tell the time': 'ask_time', 'Tell the date': 'ask_date', 'Tell battery level': 'ask_battery',
    },
}
# Laya-routed actions that change state get an approval card unless Laya is sure.
RISKY = {'file_rename', 'file_copy', 'file_delete', 'file_append', 'file_create', 'window_close', 'lock', 'download', 'layout_restore'}

NUMBERS = {w: i for i, w in enumerate('zero one two three four five six seven eight nine ten eleven twelve '
                                      'thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split())}
TENS = {'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90}


def number(text: str) -> int | None:
    m = re.search(r'\b(\d{1,3})\b', text)
    if m:
        return int(m[1])
    if re.search(r'\b(?:a hundred|one hundred|max(?:imum)?|full)\b', text, re.I):
        return 100
    m = re.search(r'\b(' + '|'.join(TENS) + r')(?:[\s-](' + '|'.join(list(NUMBERS)[:10]) + r'))?\b', text, re.I)
    if m:
        return TENS[m[1].lower()] + (NUMBERS[m[2].lower()] if m[2] else 0)
    m = re.search(r'\b(' + '|'.join(NUMBERS) + r')\b', text, re.I)
    return NUMBERS[m[1].lower()] if m else None


def tool(tool_name: str, **slots) -> Action:
    return Action('tool', json.dumps({'tool': tool_name, **slots}))


def _plugin_label(task: dict) -> str:
    from blok import plugins
    item = plugins.commands().get(task.get('name', ''))
    return item.description if item else str(task.get('name'))


def label(task: dict) -> str:
    name = task['tool']
    query = task.get('query', '')
    labels = {
        'file_find': f'Find {query}', 'file_open': f'Open {query}', 'file_read': f'Read {query}',
        'file_append': f'Add "{task.get("text", "")}" to {query}', 'file_create': f'Create file {task.get("name", "")}',
        'file_rename': f'Rename {query} to {task.get("name", "")}', 'file_move': f'Move {query} to {task.get("dest", "")}',
        'file_copy': f'Copy {query} to {task.get("dest", "")}', 'file_delete': f'Move {query} to the trash',
        'file_pick': f'Open file {task.get("index", "")}',
        'volume': {'up': 'Volume up', 'down': 'Volume down', 'mute': 'Mute or unmute',
                   'set': f'Set volume to {task.get("level")}%'}.get(task.get('op'), 'Volume'),
        'brightness': {'up': 'Brightness up', 'down': 'Brightness down',
                       'set': f'Set brightness to {task.get("level")}%'}.get(task.get('op'), 'Brightness'),
        'media': {'toggle': 'Pause or resume playback', 'next': 'Next track', 'previous': 'Previous track'}.get(task.get('op'), 'Media'),
        'window': {'close': 'Close the active window', 'fullscreen': 'Toggle fullscreen', 'float': 'Toggle floating',
                   'move': f'Move window to workspace {task.get("workspace")}',
                   'focus': f'Switch to {task.get("app")}'}.get(task.get('op'), 'Window'),
        'plugin': _plugin_label(task), 'watch': 'Watch and learn' if task.get('on') else 'Stop watching',
        'skill_save': f'Save skill {task.get("name")}', 'skill_run': f'Run skill {task.get("name")}',
        'skill_list': 'List skills', 'skill_forget': f'Forget skill {task.get("name")}', 'arrange': f'{task.get("left")} left, {task.get("right")} right',
        'layout_save': f'Save layout {task.get("name")}', 'layout_restore': f'Restore layout {task.get("name")}',
        'layout_list': 'List saved layouts', 'focus': 'Focus mode ' + ('on' if task.get('on') else 'off'),
        'where': f'Find the {task.get("app")} window', 'workspace_info': f'What is on workspace {task.get("workspace")}',
        'close_others': f'Close everything except {task.get("keep")}', 'lock': 'Lock the screen', 'theme': f'Switch to the {task.get("name")} theme', 'answer': f'Tell the {task.get("topic")}',
        'download': f'Download {task.get("url") or query}',
    }
    return labels.get(name, name)


# ---------------------------------------------------------------- slot extraction
FILE_HINT = re.compile(r'\b(?:files?|folders?|director(?:y|ies)|documents?|pdfs?|downloads|'
                       r'screenshots?|spreadsheets?|presentations?|notes? file|todo|readme|resume|cv)\b|\.[a-z0-9]{1,5}\b', re.I)
# Media words only mean files when they are yours ("my photos", not "funny videos").
MEDIA_HINT = re.compile(r'\b(?:my|i (?:had|have|saved|downloaded|took|made))\b.*\b(?:photos?|pictures|images?|videos?|songs?|music)\b'
                        r'|\b(?:photos?|pictures|images?|videos?|songs?) (?:i|that i) (?:had|have|saved|downloaded|took|made)\b', re.I)
PERSONAL = re.compile(r"\b(?:my|i (?:had|have|saved|downloaded|made|wrote))\b", re.I)
DOMAIN = re.compile(r'(?:www\.)?(?:[a-z0-9-]+\.)+(?:com|org|net|io|dev|app|gov|edu|co|me|tv|ai|in|uk|us|xyz|so|gg|info|blog|news|site|tech)(?:/\S*)?', re.I)
WEB_HINT = re.compile(r'\b(?:online|on (?:the )?(?:web|internet|google|youtube)|website)\b', re.I)


def _strip(text: str, verbs: str) -> str:
    rest = re.sub(rf'^(?:{verbs})\s+', '', text.strip(), flags=re.I)
    rest = re.sub(r'\s+(?:on my (?:computer|pc|laptop|machine)|in my files|for me|please)$', '', rest, flags=re.I)
    return rest.strip(' .?!"\'')


def _clean_target(text: str) -> str:
    text = re.sub(r'\s+(?:thing|stuff|one)?\s*(?:that )?i (?:had|have|saved|downloaded|made|wrote|took)(?: .*)?$', '', text.strip(' .?!"\''), flags=re.I)
    text = re.sub(r'\s+(?:thing|stuff)$', '', text, flags=re.I)
    return re.sub(r'^(?:my|the|a|an|this|that)\s+', '', text, flags=re.I)


def extract(intent: str, text: str) -> Action | str:
    """Build the action for a chosen intent, or return a clarification question."""
    t = text.strip().strip('.!?')
    if intent in ('arrange', 'layout_save', 'layout_restore', 'focus_on', 'focus_off'):
        from blok import choreo
        found = choreo.intent(t)
        if found and found['tool'] in (intent, 'focus') and (intent != 'focus_off' or not found.get('on')):
            return tool(**{'tool_name': found.pop('tool'), **found})
        if intent == 'focus_on':
            return tool('focus', on=True, minutes=number(t) if re.search(r'\bminutes?\b', t, re.I) else None)
        if intent == 'focus_off':
            return tool('focus', on=False)
        if intent == 'layout_restore':
            name = next((n for n in choreo.layouts() if re.search(rf'\b{re.escape(n.replace("-", " "))}\b', t, re.I)), None)
            return tool('layout_restore', name=name) if name else 'Which layout? Say "list my layouts" to hear them.'
        if intent == 'arrange':
            return 'Say it like "code on the left, browser on the right".'
        return 'What should I call this layout? Say "save this layout as coding".'
    if intent.startswith('skill:'):
        from blok import skills
        name = intent.split(':', 1)[1]
        found = skills.match(t)
        return tool('skill_run', name=name, values=found[1] if found and found[0]['name'] == name else {})
    if intent.startswith('plugin:'):
        from blok import plugins
        item = plugins.commands().get(intent.split(':', 1)[1])
        if item is None:
            return 'That command is no longer installed.'
        found = plugins.match(t)
        if found and found[0] is item:
            return tool('plugin', name=item.name, args=found[1])
        if item.slots:
            return f'Say it like "{item.phrases[0]}".'
        return tool('plugin', name=item.name, args={})
    if intent == 'file_pick':
        ordinals = {'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5, 'sixth': 6, 'seventh': 7, 'eighth': 8}
        m = re.search(r'\b(' + '|'.join(ordinals) + r')\b', t, re.I)
        return tool('file_pick', index=ordinals[m[1].lower()] if m else (number(t) or 1))
    if intent == 'file_find':
        q = _clean_target(_strip(t, r"find(?: me)?|search for|search|look for|locate|where is|where's|show me where|which folder has|what's on|what is on|what's in|what is in"))
        return tool('file_find', query=q) if q else 'Which file should I look for?'
    if intent == 'file_open':
        q = _strip(t, r'open(?: up)?|show(?: me)?|pull up|bring up|go to|launch')
        return tool('file_open', query=q) if q else 'Which file or folder should I open?'
    if intent == 'file_read':
        q = _strip(t, r"read(?: me| out| aloud)?|what's in|what is in|show me what's in|tell me what's in|show (?:me )?the contents of|what does .+? say")
        m = re.fullmatch(r'what does (.+?) say', t, re.I)
        q = m[1] if m else q
        return tool('file_read', query=_clean_target(q)) if q else 'Which file should I read?'
    if intent == 'file_append':
        m = re.fullmatch(r'(?:add|append|write|put|jot down|note down)\s+(.+?)\s+(?:to|into|in|onto|at the end of)\s+(?:my |the )?(.+?)(?:\s+file)?', t, re.I)
        if not m:
            return 'Say it like "add buy milk to my todo file".'
        return tool('file_append', text=m[1].strip(' "\''), query=m[2])
    if intent == 'file_create':
        m = re.fullmatch(r'(?:create|make|new)(?: a)?(?: new)?(?: text)? file(?: called| named)?\s+(.+?)'
                         r'(?:\s+in (?:my |the )?(.+?)(?: folder)?)?(?:\s+(?:with|saying|containing|that says)\s+(.+))?', t, re.I)
        if not m:
            return 'What should the new file be called?'
        return tool('file_create', name=m[1], folder=m[2] or '', content=m[3] or '')
    if intent == 'file_rename':
        m = re.fullmatch(r'(?:rename|call)\s+(.+?)\s+(?:to|as)\s+(.+)', t, re.I)
        if m:
            return tool('file_rename', query=_clean_target(m[1]), name=m[2].strip(' "\''))
        m = re.fullmatch(r'(?:move|put|send)\s+(.+?)\s+(?:to|into|in)\s+(?:my |the )?(.+?)(?:\s+folder)?', t, re.I)
        if m:
            return tool('file_move', query=_clean_target(m[1]), dest=m[2])
        return 'Say "rename <file> to <new name>" or "move <file> to <folder>".'
    if intent == 'file_copy':
        m = re.fullmatch(r'(?:copy|duplicate)\s+(.+?)\s+(?:to|into|in)\s+(?:my |the )?(.+?)(?:\s+folder)?', t, re.I)
        return tool('file_copy', query=_clean_target(m[1]), dest=m[2]) if m else 'Say "copy <file> to <folder>".'
    if intent == 'file_delete':
        q = _strip(t, r'delete|remove|trash|get rid of|throw away|bin|erase')
        return tool('file_delete', query=_clean_target(q)) if q else 'Which file should I move to the trash?'
    if intent in ('web_google', 'web_youtube'):
        site = 'youtube' if intent == 'web_youtube' else 'google'
        q = re.sub(r'^(?:search|look up|find|google|youtube|look for|show me)(?: for)?\s+', '', t, flags=re.I)
        q = re.sub(r'^(?:on |in )?(?:youtube|google)(?: for)?\s+', '', q, flags=re.I)
        q = re.sub(r'\s+(?:on|in|using) (?:youtube|google)$', '', q, flags=re.I).strip()
        return Action('web_task', json.dumps({'action': 'search', 'site': site, 'query': q})) if q else 'What should I search for?'
    if intent == 'web_site':
        m = re.search(r'((?:[a-z0-9-]+\.)+[a-z]{2,24}(?:/\S*)?)', t, re.I)
        return Action('url', 'https://' + m[1].lower()) if m else 'Which website should I open?'
    if intent == 'download':
        m = re.search(r'(https?://\S+)', t)
        if m:
            return tool('download', url=m[1])
        q = _strip(t, r'download|get me|grab|install|get')
        q = re.sub(r'\s+(?:from|on|using|with|in) (?:the )?(?:browser|brave|internet|web|online)$', '', q, flags=re.I)
        return tool('download', query=q) if q else 'What should I download?'
    if intent == 'new_tab':
        return Action('web_task', json.dumps({'action': 'new_tab'}))
    if intent == 'media_play':
        q = _strip(t, r'play(?: me)?(?: some)?|put on|blast|throw on|queue up')
        return Action('web_task', json.dumps({'action': 'play', 'site': 'spotify', 'query': q})) if q else 'What should I play?'
    if intent in ('media_toggle', 'media_next', 'media_previous'):
        return tool('media', op=intent.split('_')[1])
    if intent == 'app_open':
        from blok.desktop import catalog
        from blok.nlu import APPS
        q = _clean_target(_strip(t, r'open(?: up)?|launch|start|run|fire up|bring up')).lower().removesuffix(' app')
        if q in APPS:
            return Action('open', APPS[q])
        if q in catalog():
            return Action('open', q)
        # Laya chose "open an app"; the app may be named anywhere ("I need my terminal").
        for name in sorted(APPS, key=len, reverse=True):
            if re.search(rf'\b{re.escape(name)}\b', t, re.I):
                return Action('open', APPS[name])
        for name in sorted(catalog(), key=len, reverse=True):
            if len(name) > 2 and re.search(rf'\b{re.escape(name)}\b', t, re.I):
                return Action('open', name)
        return f'No installed app named "{q}".' if q else 'Which app should I open?'
    if intent in ('window_close', 'window_fullscreen', 'window_float'):
        return tool('window', op=intent.split('_')[1])
    if intent in ('workspace', 'window_move'):
        n = number(t)
        if n is None or not 1 <= n <= 10:
            return 'Which workspace number?'
        return Action('workspace', str(n)) if intent == 'workspace' else tool('window', op='move', workspace=str(n))
    if intent == 'window_focus':
        q = _clean_target(_strip(t, r'switch to|go to|focus(?: on)?|show me|bring up'))
        return tool('window', op='focus', app=q) if q else 'Which app should I switch to?'
    if intent in ('volume_up', 'volume_down', 'volume_mute'):
        return tool('volume', op=intent.split('_')[1])
    if intent == 'volume_set':
        n = number(t)
        return tool('volume', op='set', level=n) if n is not None else 'What volume level, from 0 to 100?'
    if intent in ('brightness_up', 'brightness_down'):
        return tool('brightness', op=intent.split('_')[1])
    if intent == 'lock':
        return tool('lock')
    if intent == 'theme':
        from blok.themes import THEMES
        m = re.search(r'\b(' + '|'.join(THEMES) + r'|spooky|scary|festive|festival|lights|blocky|creeper)\b', t, re.I)
        name = {'spooky': 'halloween', 'scary': 'halloween', 'festive': 'diwali', 'festival': 'diwali',
                'lights': 'diwali', 'blocky': 'minecraft', 'creeper': 'minecraft'}.get(m[1].lower(), m[1].lower()) if m else 'next'
        return tool('theme', name=name)
    if intent in ('ask_time', 'ask_date', 'ask_battery'):
        return tool('answer', topic=intent.split('_')[1])
    if intent == 'note_create':
        m = re.search(r'note(?: called| titled| named| saying)?\s+(.+)', t, re.I)
        return Action('new_note', m[1]) if m else Action('new_note', 'Untitled')
    if intent == 'note_write':
        q = _strip(t, r'write(?: down)?|add|jot down|note down|take a note')
        return Action('write', q) if q else 'What should I write?'
    if intent == 'notes_open':
        return Action('open', 'notes')
    if intent == 'camera_open':
        return Action('open', 'camera')
    if intent == 'photo':
        return Action('photo')
    return 'I could not tell what to do. Try a shorter command.'


# ---------------------------------------------------------------- strict rules
RULES: list[tuple[str, str]] = [
    # (regex over the normalized utterance, intent)
    (r'(?:what(?:\'s| is) the time|what time is it|tell me the time|time(?: is it)? now|current time)', 'ask_time'),
    (r'(?:what(?:\'s| is) (?:the |today\'s )?date(?: today)?|what day is (?:it|today)(?: today)?|today\'s date|what\'s today|what(?:\'s| is) the day(?: today)?|which day is (?:it|today))', 'ask_date'),
    (r"(?:.*\b(?:battery|charge|charging)\b.*)", 'ask_battery'),
    (r'(?:how much battery(?: do i have| is left)?|battery(?: level| status| percentage)?|what(?:\'s| is) (?:my |the )?battery(?: level| at)?|how(?:\'s| is) (?:my |the )?battery)', 'ask_battery'),
    (r'(?:turn|crank|bring|pump|bump) (?:the )?(?:volume|sound|it|music) up(?: a (?:little )?bit| a little| some| more)?|(?:turn|crank|pump|bump) up (?:the )?(?:volume|sound|music)|(?:volume|sound) up|louder|make it louder|(?:raise|increase|boost) (?:the )?(?:volume|sound)', 'volume_up'),
    (r'(?:turn|bring|keep) (?:the )?(?:volume|sound|it|music) down(?: a (?:little )?bit| a little| some)?|turn down (?:the )?(?:volume|sound|music)|too loud|(?:volume|sound) down|quieter|make it quieter|(?:lower|decrease|reduce) (?:the )?(?:volume|sound)', 'volume_down'),
    (r'(?:mute|unmute)(?: (?:the )?(?:sound|audio|volume|speakers?))?', 'volume_mute'),
    (r'(?:set|change|put) (?:the )?volume (?:to|at) .+|volume (?:to |at )?\d{1,3}(?: percent|%)?', 'volume_set'),
    (r"(?:(?:it'?s|it is|this is|that'?s|the (?:music|sound|volume|screen) is|my screen is) )?(?:(?:way|so|a bit|a little|kinda|really|super) )*too (?:loud|noisy)", 'volume_down'),
    (r"(?:(?:it'?s|it is|this is|that'?s|the (?:music|sound|volume|screen) is|my screen is) )?(?:(?:way|so|a bit|a little|kinda|really|super) )*too (?:quiet|soft|low)|(?:i )?can'?t hear (?:it|anything|this)", 'volume_up'),
    (r"(?:(?:it'?s|it is|this is|that'?s|the (?:music|sound|volume|screen) is|my screen is) )?(?:(?:way|so|a bit|a little|kinda|really|super) )*too bright|(?:it'?s )?hurting my eyes", 'brightness_down'),
    (r"(?:(?:it'?s|it is|this is|that'?s|the (?:music|sound|volume|screen) is|my screen is) )?(?:(?:way|so|a bit|a little|kinda|really|super) )*too (?:dark|dim)|i can'?t see (?:anything|the screen)", 'brightness_up'),
    (r'(?:turn|bring) (?:the )?brightness up|brightness up|(?:make (?:the )?screen |screen )brighter|brighter|(?:raise|increase) (?:the )?brightness', 'brightness_up'),
    (r'(?:turn|bring) (?:the )?brightness down|brightness down|(?:make (?:the )?screen |screen )(?:dimmer|darker)|dim (?:the )?screen|(?:lower|decrease|reduce) (?:the )?brightness', 'brightness_down'),
    (r'(?:pause|resume|unpause)(?: (?:the )?(?:music|song|video|playback|media|track))?|(?:stop|pause) (?:the )?(?:music|song|playback)|play pause', 'media_toggle'),
    (r'(?:previous|last) (?:song|track)|go back (?:a|one) (?:song|track)|play (?:the )?previous (?:song|track)', 'media_previous'),
    (r'lock (?:the |my )?(?:screen|computer|pc|laptop|desktop)|lock it', 'lock'),
    (r'(?:switch|change|set|use|go|put)(?: it)?(?: to| on)?(?: the)? (?:halloween|diwali|omarchy|liquid|minecraft|spooky|festive|blocky)(?: theme| mode| look)?|'
     r'(?:halloween|diwali|omarchy|liquid|minecraft|spooky|festive) (?:theme|mode)|(?:change|switch|next|cycle)(?: the)? theme|make it (?:spooky|festive|blocky)', 'theme'),
    (r'close (?:this|the|current|active|that) (?:window|app)|close (?:it|this)|quit (?:this|the) (?:app|window)|kill (?:this|the) window', 'window_close'),
    (r'(?:make (?:this |the )?(?:window )?|toggle |go )?full ?screen(?: (?:this|the) window)?|maximi[sz]e (?:this|the) window', 'window_fullscreen'),
    (r'(?:float|unfloat|tile) (?:this|the) window|(?:make (?:this|the) window|toggle) float(?:ing)?', 'window_float'),
    (r'(?:move|send|put) (?:this |the )?(?:window|app) (?:to|on|onto) workspace .+', 'window_move'),
    (r'(?:what\'s in|what is in|show me what\'s in|read(?: me| out)?) (?:my |the )?(.+)', 'file_read'),
    (r'(?:add|append|jot down|put) .+ (?:to|into|onto|in) (?:my |the )?.+?(?: file|\.[a-z]{1,5}| list)', 'file_append'),
    (r'(?:create|make)(?: a)?(?: new)?(?: text)? file .+', 'file_create'),
    (r'rename .+ to .+', 'file_rename'),
    (r'(?:move|put) .+ (?:to|into) (?:my |the )?.+? folder|move .+\.[a-z0-9]{1,5} (?:to|into) .+', 'file_rename'),
    (r'(?:copy|duplicate) .+ (?:to|into) .+', 'file_copy'),
    (r'(?:delete|trash|throw away|get rid of|remove) (?:my |the |this |that )?.+', 'file_delete'),
    (r'download .+', 'download'),
    (r'(?:find|locate|where(?:\'s| is)|look for|search for) .+', 'file_find'),
    (r'open (?:it|that(?: file| one)?)|(?:open|pick|choose|use) (?:the )?(?:first|second|third|fourth|fifth|sixth|seventh|eighth|\d) (?:file|one)|(?:open )?file (?:number )?(?:\d|one|two|three|four|five|six|seven|eight)', 'file_pick'),
    (r'(?:open|show(?: me)?|pull up|bring up) (?:my |the )?.+', 'file_open'),
]
_COMPILED = [(re.compile(p, re.I), intent) for p, intent in RULES]
FILE_INTENTS = {'file_read', 'file_append', 'file_find', 'file_open', 'file_delete', 'file_rename', 'file_copy'}


def match_rule(text: str) -> tuple[str, Action] | None:
    """A strict rule that names its tool unambiguously; file rules need a file-like target."""
    t = text.strip().strip('.!?')
    for pattern, intent in _COMPILED:
        if not pattern.fullmatch(t):
            continue
        if intent in FILE_INTENTS:
            from blok.nlu import APPS, SITES
            target = _clean_target(re.sub(r'^\S+(?: me| up)?\s+', '', t)).lower()
            if target in APPS or target in SITES or target.removesuffix(' app') in APPS or DOMAIN.fullmatch(target):
                continue
            hinted = FILE_HINT.search(t) or MEDIA_HINT.search(t)
            personal = re.match(r"(?:find|locate|where(?:'s| is)|look for|search for) ", t, re.I) and PERSONAL.search(t)
            if intent in ('file_find', 'file_open') and (WEB_HINT.search(t) or not (hinted or personal)):
                continue
            if intent in ('file_delete', 'file_read') and not hinted:
                continue
        if intent == 'download' and re.search(r'\b(?:folder|downloads)\b', t, re.I) and not re.search(r'https?://', t):
            continue
        action = extract(intent, t)
        if isinstance(action, Action):
            return intent, action
    return None


@dataclass
class Route:
    action: Action | None
    intent: str
    probability: float
    reason: str = ''
    needs_approval: bool = False


PLUGIN_AREA = 'Your own commands'


def all_areas() -> dict:
    """Built-in areas plus drop-in commands (≤9 per question keeps Laya calibrated)."""
    from blok import plugins, skills
    own = {c.description: 'plugin:' + c.name for c in plugins.commands().values()}
    own.update({'Run my skill: ' + k['name']: 'skill:' + k['name'] for k in skills.all_skills().values()})
    own = dict(list(own.items())[:9])
    return {**AREAS, PLUGIN_AREA: own} if own else AREAS


def route(text: str, distribution) -> Route:
    """Two-stage Laya routing. `distribution(text, options, question)` returns {option: p}."""
    catalog = all_areas()
    areas = distribution(text, list(catalog), "Which area is the user's request about?")
    best = None
    for area, p_area in sorted(areas.items(), key=lambda kv: -kv[1])[:2]:
        options = list(catalog[area]) + [NONE]
        probs = distribution(text, options, 'Which action does the user want?')
        choice, p_intent = max(probs.items(), key=lambda kv: kv[1])
        if choice == NONE:
            continue
        score = p_area * p_intent
        if best is None or score > best[0]:
            best = (score, catalog[area][choice], p_intent)
    if best is None or best[2] < 0.5 or best[0] < 0.15:
        return Route(None, 'none', best[0] if best else 0.0, "I'm not sure what you want. Try saying it another way.")
    score, intent, p_intent = best
    action = extract(intent, text)
    if isinstance(action, str):
        return Route(None, intent, score, action)
    return Route(action, intent, score, needs_approval=intent in RISKY and p_intent < 0.9)
