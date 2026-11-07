"""Hinglish (code-mixed Hindi + English) → the plain English phrasings BLoK's rules know.

Hindi puts the verb last ("YouTube pe Arijit ke gaane chalao"), so this works
with whole-phrase patterns rather than word swaps. Romanized spellings vary
(chalao / chalaao / chala do), and Whisper's English model writes Hindi words by
sound, so each verb accepts its common variants. Devanagari input is
transliterated first. English text passes through unchanged.
"""
import subprocess
import shutil
import functools
import re

# Verb endings that mark a Hinglish command, with their English meaning.
V = {
    'open': r'(?:kholo|kolo|khulo|khol\s*do|khol\s*de|khol\s*dijiye|kholiye|kholna|open\s*kar(?:o|\s*do|\s*de)|chalu\s*kar(?:o|\s*do)|start\s*kar(?:o|\s*do)|launch\s*kar(?:o|\s*do))',
    'play': r'(?:chalao|chalaao|chala\s*do|chala\s*de|bajao|bajaao|baja\s*do|baja\s*de|play\s*kar(?:o|\s*do|\s*de)|lagao|laga\s*do|sunao|suna\s*do|chalaiye)',
    'search': r'(?:(?:search|sarch|sarj|serch|surch|sarach)\s*kar(?:o|\s*do|\s*de)|dhundo|dhoondo|dhundho|dhundh\s*do|dhoondh\s*do|khojo|khoj\s*do|search\s*karke\s*dikhao)',
    'close': r'(?:band\s*kar(?:o|\s*do|\s*de)|bandh\s*kar(?:o|\s*do)|close\s*kar(?:o|\s*do|\s*de)|hatao\s*screen\s*se)',
    'up': r'(?:badhao|badhaao|badao|barhao|badha\s*do|tez\s*kar(?:o|\s*do)|zyada\s*kar(?:o|\s*do)|jyada\s*kar(?:o|\s*do)|upar\s*kar(?:o|\s*do))',
    'down': r'(?:kam\s*kar(?:o|\s*do|\s*de)|ghatao|ghata\s*do|dheere\s*kar(?:o|\s*do)|dheema\s*kar(?:o|\s*do)|neeche\s*kar(?:o|\s*do)|niche\s*kar(?:o|\s*do))',
    'stop': r'(?:roko|rok\s*do|rok\s*de|ruko|pause\s*kar(?:o|\s*do)|band\s*kar(?:o|\s*do))',
    'show': r'(?:dikhao|dikhaao|dikao|dikha\s*do|dikhaiye)',
    'type': r'(?:type\s*kar(?:o|\s*do)|likho|likh\s*do|likh\s*de)',
    'take': r'(?:lo|le\s*lo|le|lelo|khicho|kheencho|khinch\s*lo|lena)',
    'go': r'(?:jao|jaao|chalo|le\s*chalo|pe\s*jao|par\s*jao)',
    'delete': r'(?:delete\s*kar(?:o|\s*do)|hatao|hata\s*do|mitao|mita\s*do|trash\s*mein\s*dalo)',
    'click': r'(?:click\s*kar(?:o|\s*do)|dabao|daba\s*do|press\s*kar(?:o|\s*do))',
}
ON = r'(?:pe|par|pr|mein|me|mai|main)'
FILLER_START = re.compile(r'^(?:(?:zara|jara|please|plz|bhai|bhaiya|yaar|yar|arre|are|abe|oye|accha|achha|acha|haan|ha|toh|to|suno|sun|ek\s*kaam\s*karo|ek\s*baar)\b[\s,]*)+', re.I)
FILLER_END = re.compile(r'(?:[\s,]+(?:na|please|plz|yaar|yar|bhai|zara|jaldi|abhi|mere\s*liye|ek\s*baar|jaldi\s*se|thoda))+[\s.!?]*$', re.I)
HINDI_NUMBERS = {'ek': 1, 'do': 2, 'teen': 3, 'char': 4, 'chaar': 4, 'paanch': 5, 'panch': 5, 'chhe': 6, 'chhah': 6,
                 'saat': 7, 'aath': 8, 'nau': 9, 'das': 10, 'pehla': 1, 'pehle': 1, 'doosra': 2, 'dusra': 2, 'doosre': 2,
                 'dusre': 2, 'teesra': 3, 'tisra': 3, 'teesre': 3, 'chautha': 4, 'chauthe': 4, 'paanchva': 5, 'panchve': 5,
                 'gyarah': 11, 'gyaarah': 11, 'barah': 12, 'baarah': 12, 'terah': 13, 'chaudah': 14, 'pandrah': 15,
                 'solah': 16, 'satrah': 17, 'atharah': 18, 'unnis': 19, 'bees': 20, 'bis': 20}
MARKER = re.compile(r'\b(?:' + '|'.join(V.values()) + r'|kitne|kitni|kya|kaun|aaj|awaaz|awaz|aawaz|gaane|gane|gaana|gana|'
                    r'agla|pichla|neeche|niche|upar|wala|waala|ke\s+baare|ko|hai|hain|karo|kar\s+do|liye|naam|rakho|mein|lagao|dekho|seekho|gaya|khatam|dikhata|dikhati|sikhata)\b', re.I)


def _num(word: str) -> str:
    word = word.lower()
    return str(HINDI_NUMBERS.get(word, word))


# Ordered (pattern, English template). Named groups fill the template.
RULES: list[tuple[str, str]] = [
    # Questions
    (r'(?:abhi\s+)?(?:kitne\s+baje\s+(?:hain|hai|hue)|kya\s+(?:time|samay|waqt)\s+(?:hua|hai|ho\s*gaya)|(?:time|samay|waqt)\s+kya\s+(?:hua|hai|ho\s*gaya)(?:\s+hai)?|time\s+batao|time\s+bata\s*do)', 'what time is it'),
    (r'(?:aaj\s+)?(?:kya|kaun\s*si|konsi|kaunsi)\s+(?:date|tarikh|tareekh|taarikh|tarik|tareek|tariq)\s+hai(?:\s+aaj)?|aaj\s+ki\s+(?:date|tarikh)(?:\s+kya\s+hai)?|aaj\s+(?:kaun\s*sa|konsa|kya)\s+din\s+hai|date\s+batao', 'what is the date'),
    (r'(?:battery\s+(?:kitni|kitne)\s+(?:hai|bachi\s+hai|bachi)|(?:kitni|kitne)\s+battery\s+(?:hai|bachi\s+hai|bachi)|battery\s+(?:kitna|kitni)\s+(?:percent|percentage)\s+hai|battery\s+batao)', 'how much battery do i have'),
    # Volume / brightness / media
    (r'(?:awaaz|awaz|aawaz|aawaaz|volume|sound)\s+(?:thoda\s+|thodi\s+|aur\s+)?' + V['up'], 'turn the volume up'),
    (r'(?:awaaz|awaz|aawaz|aawaaz|volume|sound)\s+(?:thoda\s+|thodi\s+)?' + V['down'], 'turn the volume down'),
    (r'(?:awaaz|awaz|aawaz|volume|sound)\s+(?:band\s+kar(?:o|\s*do)|mute\s+kar(?:o|\s*do)|bandh\s+karo)|mute\s+kar(?:o|\s*do)', 'mute'),
    (r'(?:brightness|roshni|light|screen\s+ki\s+roshni)\s+(?:thoda\s+|thodi\s+)?' + V['up'], 'brightness up'),
    (r'(?:brightness|roshni|light|screen\s+ki\s+roshni)\s+(?:thoda\s+|thodi\s+)?' + V['down'], 'brightness down'),
    (r'(?:agla|agle|next|dusra|doosra)\s+(?:gaana|gana|song|track)(?:\s+(?:chalao|lagao|bajao|play\s+karo))?|(?:gaana|gana|song)\s+(?:badlo|badal\s+do|change\s+karo|skip\s+karo)', 'next track'),
    (r'(?:pichla|pichle|purana|previous)\s+(?:gaana|gana|song|track)(?:\s+(?:chalao|lagao|bajao|play\s+karo))?', 'previous track'),
    (r'(?:gaana|gana|music|song|video|gaane)\s+' + V['stop'], 'pause the music'),
    (r'(?:gaana|gana|music|song|video|gaane)\s+(?:wapas\s+|phir\s+se\s+|fir\s+se\s+)?(?:chalao|chala\s+do|resume\s+karo|shuru\s+karo)', 'resume the music'),
    # Hands-free
    (r'hands?\s*free\s+(?:mode\s+)?(?:chalu|on|start|shuru)\s+kar(?:o|\s*do)', 'hands free on'),
    (r'hands?\s*free\s+(?:mode\s+)?(?:band|off|bandh)\s+kar(?:o|\s*do)', 'hands free off'),
    (r'(?:sab(?:ke)?\s+)?(?:numbers?|number)\s+' + V['show'], 'show numbers'),
    (r'(?:numbers?|number)\s+(?:hatao|hata\s+do|band\s+karo)', 'hide numbers'),
    (r'(?P<n>\d{1,3}|\w+)\s+(?:number\s+)?(?:' + ON + r'\s+)?' + V['click'], 'click {n}'),
    (r'(?:neeche|niche|nichey)\s+(?:scroll\s+kar(?:o|\s*do)|jao|chalo|karo|kar\s+do)|scroll\s+(?:neeche|niche)\s+kar(?:o|\s*do)', 'scroll down'),
    (r'(?:upar|oopar|uper)\s+(?:scroll\s+kar(?:o|\s*do)|jao|chalo|karo|kar\s+do)|scroll\s+(?:upar|oopar)\s+kar(?:o|\s*do)', 'scroll up'),
    (r'(?:sabse\s+)?(?:upar|oopar)\s+(?:tak\s+)?(?:jao|le\s+chalo)', 'go to the top'),
    (r'(?:likho|likh\s+do|type\s+karo)\s+(?P<text>.+)', 'type {text}'),
    (r'(?P<text>.+?)\s+' + V['type'], 'type {text}'),
    (r'(?:enter|tab|escape)\s+(?:dabao|daba\s+do|press\s+karo)', 'press {0}'),
    # Teaching
    (r'(?:dekho|dekh\s+lo|seekho)(?:\s+(?:main|mai|me)\s+kaise\s+kar(?:ta|ti)\s+(?:hun|hoon|hu))?|(?:main|mai)\s+(?:dikhata|dikhati|sikhata|sikhati)\s+(?:hun|hoon|hu)', 'watch me'),
    (r'(?:iska|isko|ise|is\s*ka)\s+naam\s+(?P<name>.+?)\s+(?:rakho|rakh\s+do|do)|(?:ise|isko)\s+(?P<name2>.+?)\s+naam\s+se\s+(?:save\s+karo|yaad\s+rakho)', 'call it {name}'),
    (r'ho\s+gaya|bas(?:\s+itna\s+hi)?|khatam', 'done'),
    # Reading the screen
    (r'(?:ye|yeh|is)?\s*(?:page|article|screen)?\s*(?:ko\s+)?(?:padh\s*(?:ke|kar)\s+sunao|padho|padh\s+do|sunao)', 'read this to me'),
    (r'(?:ye|yeh)\s+(?:page|article|video|screen)\s+(?:kis\s+(?:baare|bare)\s+(?:mein|me)\s+hai|kya\s+hai)|(?:iska\s+)?(?:summary|saransh)\s+(?:do|batao|bata\s+do)', 'what is this page about'),
    (r'(?:ye|yeh)?\s*error\s+(?:kya\s+hai|kya\s+keh\s+raha\s+hai|samjhao)|kya\s+galat\s+hua', 'what does this error mean'),
    # Focus mode and window layouts
    (r'focus\s+mode\s+(?:chalu|on|start|shuru)\s+kar(?:o|\s*do)|(?:mujhe\s+)?focus\s+karna\s+hai', 'focus mode'),
    (r'(?P<n>\d+|\w+)\s+minute\s+(?:ke\s+liye\s+)?focus\s+(?:mode\s+)?(?:chalu\s+)?kar(?:o|\s*do|na\s+hai)', 'focus for {n} minutes'),
    (r'focus\s+mode\s+(?:band|off|khatam)\s+kar(?:o|\s*do)|focus\s+khatam', 'end focus mode'),
    (r'(?P<a>.+?)\s+(?:left|baayein|baaye|bayen)\s+(?:mein|me|pe|par)\s+(?:aur\s+)?(?P<b>.+?)\s+(?:right|daayein|daaye|dayen)\s+(?:mein|me|pe|par)\s+(?:rakho|kar\s+do|lagao)',
     '{a} on the left and {b} on the right'),
    (r'(?:ye|yeh|is)?\s*layout\s+(?P<name>[\w-]+)\s+(?:naam\s+se\s+)?(?:save\s+kar(?:o|\s*do)|yaad\s+rakho)', 'save this layout as {name}'),
    (r'(?P<name>[\w-]+)\s+(?:wala\s+|waala\s+)?layout\s+(?:lagao|laga\s+do|kholo|load\s+karo)', 'restore {name} layout'),
    # Screenshots, themes, windows, workspaces
    (r'(?:ek\s+)?screenshot\s+' + V['take'], 'take a screenshot'),
    (r'(?P<theme>halloween|diwali|minecraft|omarchy|liquid)\s+(?:wala\s+|waala\s+)?(?:theme\s+)?(?:lagao|laga\s+do|kar\s+do|set\s+karo|chalu\s+karo)', 'switch to the {theme} theme'),
    (r'(?:ye|yeh|is|iss)?\s*(?:window|app)\s+(?:ko\s+)?' + V['close'], 'close this window'),
    (r'(?:ye|yeh|is|iss)?\s*(?:window|app)\s+(?:ko\s+)?(?:full\s*screen|bada)\s+kar(?:o|\s*do)', 'make this window fullscreen'),
    (r'(?:ye|yeh|is|iss)?\s*(?:window|app)\s+(?:ko\s+)?(?:workspace|desktop)\s+(?P<n>\w+)\s+(?:' + ON + r'\s+)?(?:bhejo|bhej\s+do|daalo|dalo|le\s+jao)', 'move this window to workspace {n}'),
    (r'(?:workspace|desktop)\s+(?P<n>\w+)\s+(?:' + ON + r'\s+)?' + V['go'] + r'|(?P<n2>\w+)\s+(?:workspace|desktop)\s+(?:' + ON + r'\s+)?' + V['go'], 'switch to workspace {n}'),
    # Play / search / open with an optional site ("YouTube pe …")
    (r'(?:(?P<site>youtube|yt|spotify)\s+' + ON + r'\s+)?(?P<q>.+?)\s+(?:ke|ki|ka)\s+(?:gaane|gane|songs?|gaana|gana)\s+' + V['play'], 'play {q} songs{site}'),
    (r'(?:(?P<site>youtube|yt|spotify)\s+' + ON + r'\s+)?(?P<q>.+?)\s+(?:ka|ki|ke)\s+(?:video|videos)\s+' + V['play'], 'play {q} video{site}'),
    (r'(?:(?P<site>youtube|yt|spotify)\s+' + ON + r'\s+)?(?P<q>.+?)\s+' + V['play'], 'play {q}{site}'),
    (r'(?:(?P<site>google|youtube|yt|steam|amazon|reddit|github|wikipedia|flipkart)\s+' + ON + r'\s+)?(?P<q>.+?)(?:\s+ke\s+baare\s+(?:mein|me|main))?\s+' + V['search'], 'search for {q}{site}'),
    (r'(?P<x>.+?)\s+' + V['delete'], 'delete {x}'),
    (r'(?P<x>.+?)\s+(?:ko\s+)?' + V['open'], 'open {x}'),
    (r'(?P<x>.+?)\s+' + V['close'], 'close this window'),
]
_COMPILED = [(re.compile(pattern + r'[\s.!?]*$', re.I), template) for pattern, template in RULES]
CLAUSE_JOIN = re.compile(r'\s+(?:aur\s+(?:phir|fir)|aur|phir|fir|uske\s+baad|iske\s+baad|then)\s+', re.I)

# Simple Devanagari → Latin for when a multilingual model writes Hindi script.
_VOWELS = {'अ': 'a', 'आ': 'aa', 'इ': 'i', 'ई': 'ee', 'उ': 'u', 'ऊ': 'oo', 'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au', 'ऋ': 'ri'}
_SIGNS = {'ा': 'aa', 'ि': 'i', 'ी': 'ee', 'ु': 'u', 'ू': 'oo', 'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au', 'ृ': 'ri', 'ं': 'n',
          'ँ': 'n', 'ः': 'h', '्': '', '़': ''}
_CONSONANTS = dict(zip('कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह',
                       ['k', 'kh', 'g', 'gh', 'n', 'ch', 'chh', 'j', 'jh', 'n', 't', 'th', 'd', 'dh', 'n', 't', 'th', 'd', 'dh',
                        'n', 'p', 'ph', 'b', 'bh', 'm', 'y', 'r', 'l', 'v', 'sh', 'sh', 's', 'h']))
_DIGITS = dict(zip('०१२३४५६७८९', '0123456789'))


_NUKTA = {'ज': 'z', 'फ': 'f', 'ड': 'd', 'ढ': 'dh', 'क': 'q', 'ख': 'kh', 'ग': 'gh'}  # Hinglish writes ड़/ढ़ as d/dh
_MATRAS = set('ािीुूेैोौृॉॅ')


def transliterate(text: str) -> str:
    """Devanagari → the way Hinglish is usually typed ("कितने बजे हैं" → "kitne baje hain")."""
    if not re.search(r'[\u0900-\u097F]', text):
        return text
    chars = list(text.replace('ॉ', 'ो').replace('ॅ', 'े'))
    is_deva = lambda c: bool(c) and '\u0900' <= c <= '\u097F'
    out, i, prev_vowel = [], 0, False
    while i < len(chars):
        ch = chars[i]
        nxt = chars[i + 1] if i + 1 < len(chars) else ''
        if ch in _CONSONANTS:
            if nxt == '़':
                out.append(_NUKTA.get(ch, _CONSONANTS[ch]))
                i += 1
                nxt = chars[i + 1] if i + 1 < len(chars) else ''
            else:
                out.append(_CONSONANTS[ch])
            after = chars[i + 2] if i + 2 < len(chars) else ''
            if nxt in ('ं', 'ँ'):
                out.append('a')          # नं → "nan", not "nn"
                prev_vowel = True
            elif nxt in _CONSONANTS:
                # Hindi drops the inherent "a" between a vowel and a consonant that has its own vowel.
                silent = prev_vowel and after in _MATRAS
                if not silent:
                    out.append('a')
                prev_vowel = not silent
            else:
                prev_vowel = nxt not in ('्', '')
        elif ch in ('ं', 'ँ'):
            out.append('m' if nxt in ('प', 'फ', 'ब', 'भ', 'म') else 'n')   # नंबर → "nambar"
            prev_vowel = False
        elif ch in _SIGNS:
            out.append(_SIGNS[ch])
            prev_vowel = ch not in ('्', '़')
        elif ch in _VOWELS:
            out.append(_VOWELS[ch])
            prev_vowel = True
        elif ch in _DIGITS:
            out.append(_DIGITS[ch])
        else:
            out.append('.' if ch == '।' else ch)
            prev_vowel = False
        i += 1
    latin = ''.join(out)
    latin = latin.replace('ee', 'i')                         # "arijeet" → "arijit"
    latin = re.sub(r'aa\b', 'a', latin)                    # "kyaa" → "kya", "gaanaa" → "gaana"
    latin = re.sub(r'aao\b', 'ao', latin)                  # "lagaao" → "lagao"
    return re.sub(r'\ba+va+z\b', 'awaaz', latin)          # "aavaaz" → "awaaz"


# English loanwords as they come out of Devanagari ("यूट्यूब" → "yootyoob" → "youtube").
LOANWORDS = [
    (r'\by[ou]+t[yu]+[ou]+b\b', 'youtube'), (r'\bsp[ou]+t[ie]+ph?[ae]*[iy]\b', 'spotify'), (r'\bg[ou]+g[ae]*l\b', 'google'),
    (r'\bv[ao]l[yi]*[ou]+m\b', 'volume'), (r'\bs?k?r[ie]+nsh[ao]+t\b', 'screenshot'), (r'\bbr[ae]+[iy]+tn[ae]+s\b', 'brightness'),
    (r'\bt[ae]+rm[ie]+n[ae]+l\b', 'terminal'), (r'\bph?[ao]+l?d[ae]+r\b', 'folder'), (r'\bd[ae]+[uo]+nl[oa]+[dt]+s?\b', 'downloads'),
    (r'\bv[ie]+d[ie]+y?o\b', 'video'), (r'\bs[ae]+r?ch\b', 'search'), (r'\bkl[ie]+k\b', 'click'), (r'\bnambar\b', 'number'), (r'\bsk?r[ao]+l+\b', 'scroll'),
    (r'\bstiim\b|\bsteem\b', 'steam'), (r'\bvh?[ao]+tsa+p\b', 'whatsapp'), (r'\bb[aei]+t[ae]*r[ie]+\b', 'battery'),
]


def _loanwords(text: str) -> str:
    for pattern, word in LOANWORDS:
        text = re.sub(pattern, word, text, flags=re.I)
    return text


def _site(name: str | None) -> str:
    if not name:
        return ''
    return ' on ' + {'yt': 'youtube'}.get(name.lower(), name.lower())


def _clause(text: str) -> str | None:
    t = FILLER_END.sub('', FILLER_START.sub('', text.strip(' ,.!?'))).strip(' ,.!?')
    t = re.sub(r'\b(?:hain|he|hei|hey)$', 'hai', t, flags=re.I)   # "kya tarik hain" → "… hai"
    for pattern, template in _COMPILED:
        m = pattern.fullmatch(t)
        if not m:
            continue
        groups = {k: v for k, v in m.groupdict().items() if v}
        if template == 'press {0}':
            return 'press ' + t.split()[0].lower()
        if 'n2' in groups:
            groups['n'] = groups.pop('n2')
        if 'name2' in groups:
            groups['name'] = groups.pop('name2')
        if 'n' in groups:
            groups['n'] = _num(groups['n'])
        site = _site(groups.pop('site', None))
        filled = template.replace('{site}', site)
        for key, value in groups.items():
            filled = filled.replace('{' + key + '}', re.sub(r'^(?:ye|yeh|is|iss|wo|woh|mera|meri|mere)\s+', '', value.strip(), flags=re.I))
        return filled
    return None


def is_hinglish(text: str) -> bool:
    return bool(re.search(r'[ऀ-ॿ]', text)) or bool(MARKER.search(text))


def translate(text: str) -> str | None:
    """English for a Hinglish command, or None when the text isn't Hinglish."""
    if re.search(r'[\u0900-\u097F]', text):
        text = _loanwords(transliterate(text))
    if not is_hinglish(text):
        return None
    # One command unless "aur/phir" joins two; "X left mein aur Y right mein" is still one.
    one_command = not CLAUSE_JOIN.search(text) or re.search(
        r'\b(?:left|baayein|baaye|bayen)\b.+\b(?:right|daayein|daaye|dayen)\b', text, re.I)
    whole = _clause(text) if one_command else None
    if whole:
        return whole
    clauses = CLAUSE_JOIN.split(text.strip())
    english = [_clause(c) for c in clauses]
    if not any(english):
        return None
    # Untranslated clauses stay as said, so Laya can still try them.
    return ' and then '.join(e or c.strip(' ,.!?') for e, c in zip(english, clauses))


# --- Replies in Hindi (Devanagari), spoken by Kokoro's Hindi voices ------------------
# Kokoro's Hindi mode garbles Latin words, so every word of a reply is Devanagari.
NAMES = {
    'youtube': 'यूट्यूब', 'spotify': 'स्पॉटिफ़ाई', 'google': 'गूगल', 'github': 'गिटहब', 'terminal': 'टर्मिनल',
    'browser': 'ब्राउज़र', 'files': 'फ़ाइल्स', 'file': 'फ़ाइल', 'downloads': 'डाउनलोड्स', 'download': 'डाउनलोड',
    'folder': 'फ़ोल्डर', 'documents': 'डॉक्यूमेंट्स', 'pictures': 'पिक्चर्स', 'music': 'म्यूज़िक', 'videos': 'वीडियोज़',
    'video': 'वीडियो', 'notes': 'नोट्स', 'note': 'नोट', 'camera': 'कैमरा', 'screenshot': 'स्क्रीनशॉट', 'volume': 'वॉल्यूम',
    'brightness': 'ब्राइटनेस', 'battery': 'बैटरी', 'steam': 'स्टीम', 'reddit': 'रेडिट', 'netflix': 'नेटफ्लिक्स',
    'instagram': 'इंस्टाग्राम', 'whatsapp': 'व्हाट्सऐप', 'gmail': 'जीमेल', 'amazon': 'अमेज़न', 'window': 'विंडो',
    'workspace': 'वर्कस्पेस', 'theme': 'थीम', 'minecraft': 'माइनक्राफ्ट', 'halloween': 'हैलोवीन', 'diwali': 'दिवाली',
    'omarchy': 'ओमार्ची', 'liquid': 'लिक्विड', 'song': 'सॉन्ग', 'songs': 'सॉन्ग्स', 'tab': 'टैब', 'code': 'कोड',
    'obsidian': 'ऑब्सिडियन', 'chrome': 'क्रोम', 'brave': 'ब्रेव', 'search': 'सर्च', 'page': 'पेज', 'numbers': 'नंबर्स',
    'number': 'नंबर', 'wallpaper': 'वॉलपेपर', 'timer': 'टाइमर', 'trash': 'ट्रैश', 'pdf': 'पीडीएफ़', 'wikipedia': 'विकिपीडिया',
    'subscribe': 'सब्सक्राइब', 'next': 'नेक्स्ट', 'button': 'बटन', 'link': 'लिंक', 'blok': 'ब्लॉक', 'block': 'ब्लॉक',
    'pewdiepie': 'प्यूडीपाई', 'coding': 'कोडिंग', 'gaming': 'गेमिंग', 'work': 'वर्क', 'study': 'स्टडी', 'focus': 'फ़ोकस',
    'layout': 'लेआउट', 'discord': 'डिस्कॉर्ड', 'slack': 'स्लैक', 'telegram': 'टेलीग्राम', 'firefox': 'फ़ायरफ़ॉक्स', 'the': 'द', 'on': 'ऑन', 'of': 'ऑफ़', 'and': 'एंड', 'my': 'माय', 'new': 'न्यू', 'tab': 'टैब',
}
_VOWEL_SIGNS = [('aa', 'ा', 'आ'), ('ai', 'ै', 'ऐ'), ('au', 'ौ', 'औ'), ('ee', 'ी', 'ई'), ('oo', 'ू', 'ऊ'), ('ou', 'ौ', 'औ'),
                ('a', '', 'अ'), ('i', 'ि', 'इ'), ('u', 'ु', 'उ'), ('e', 'े', 'ए'), ('o', 'ो', 'ओ'), ('y', 'ी', 'ई')]
_CONS = [('chh', 'छ'), ('kh', 'ख'), ('gh', 'घ'), ('ch', 'च'), ('jh', 'झ'), ('th', 'थ'), ('dh', 'ध'), ('ph', 'फ'), ('bh', 'भ'),
         ('sh', 'श'), ('ck', 'क'), ('k', 'क'), ('g', 'ग'), ('c', 'क'), ('j', 'ज'), ('t', 'त'), ('d', 'द'), ('n', 'न'),
         ('p', 'प'), ('b', 'ब'), ('m', 'म'), ('y', 'य'), ('r', 'र'), ('l', 'ल'), ('v', 'व'), ('w', 'व'), ('s', 'स'),
         ('h', 'ह'), ('f', 'फ़'), ('z', 'ज़'), ('q', 'क'), ('x', 'क्स')]


def to_devanagari(word: str) -> str:
    """Sound-based Latin → Devanagari for names ("Arijit" → "अरिजित"); known English words use NAMES."""
    if not re.search(r'[A-Za-z]', word):
        return word
    known = NAMES.get(word.lower())
    if known:
        return known
    w, out, i = word.lower(), [], 0
    suffix = ''
    if w.endswith('ngh'):                                   # "singh" → सिंह
        w, suffix = w[:-3], 'ंह'
    while i < len(w):
        # An "n" before another consonant inside a word is the nasal dot: Ganga → गंगा.
        if w[i] == 'n' and 0 < i < len(w) - 1 and w[i + 1] not in 'aeiouy' and out:
            out.append('ं')
            i += 1
            continue
        cons = next(((latin, deva) for latin, deva in _CONS if w.startswith(latin, i)), None)
        if cons and not (cons[0] == 'y' and i > 0 and i + 1 == len(w)):
            i += len(cons[0])
            vowel = next(((latin, sign) for latin, sign, _ in _VOWEL_SIGNS if latin != 'y' and w.startswith(latin, i)), None)
            if vowel:
                sign = vowel[1]
                if i + len(vowel[0]) == len(w) and vowel[0] in ('a', 'i') and not suffix:
                    sign = {'a': 'ा', 'i': 'ी'}[vowel[0]]      # final a/i are long: Shreya → श्रेया, Hi → ही
                out.append(cons[1] + sign)
                i += len(vowel[0])
            elif i < len(w) and w[i].isalpha():
                out.append(cons[1] + '्')      # consonant cluster
            else:
                out.append(cons[1])            # word end: Hindi drops the final "a"
            continue
        vowel = next(((latin, full) for latin, _, full in _VOWEL_SIGNS if w.startswith(latin, i)), None)
        if vowel:
            out.append(vowel[1])
            i += len(vowel[0])
        else:
            out.append(w[i])
            i += 1
    return ''.join(out) + suffix


# Romanized Hindi words that aren't everyday English. A phrase with one of these is Hindi, spelled out.
ROMAN_HINDI = re.compile(r"\b(?:hai|hain|nahi|nahin|kya|kaise|kyun|kaun|mein|mera|meri|tum|tumhara|tera|teri|aap|aapka|hum|yeh|woh|aur|lekin|bahut|"
                         r"accha|achha|theek|gaana|gaane|chala|chalao|diya|kiya|karo|kar|kardo|pe|par|ka|ke|ki|ko|se|bhi|abhi|aaj|kal|ho|gaya|gayi|raha|rahi|"
                         r"dil|pyaar|pyar|ishq|zindagi|sanam|jaan|mere|tere|hi)\b", re.I)
IPA_VOWELS = [('eɪ', 'ए', 'े'), ('aɪ', 'आइ', 'ाइ'), ('ɔɪ', 'ऑय', 'ॉय'), ('aʊ', 'आउ', 'ाउ'), ('oʊ', 'ओ', 'ो'), ('iː', 'ई', 'ी'), ('uː', 'ऊ', 'ू'),
              ('ɑː', 'आ', 'ा'), ('ɔː', 'ऑ', 'ॉ'), ('ɜː', 'अर', 'र'), ('ɪ', 'इ', 'ि'), ('ᵻ', 'इ', 'ि'), ('i', 'ई', 'ी'), ('ʊ', 'उ', 'ु'), ('u', 'ऊ', 'ू'),
              ('ɛ', 'ए', 'े'), ('æ', 'ऐ', 'ै'), ('ʌ', 'अ', ''), ('ɐ', 'अ', ''), ('ə', 'अ', ''), ('ɚ', 'अर', 'र'), ('ɑ', 'आ', 'ा'), ('ɔ', 'ऑ', 'ॉ'), ('o', 'ओ', 'ो')]
IPA_CONSONANTS = [('tʃ', 'च'), ('dʒ', 'ज'), ('p', 'प'), ('b', 'ब'), ('t', 'ट'), ('d', 'ड'), ('k', 'क'), ('ɡ', 'ग'), ('f', 'फ़'), ('v', 'व'), ('θ', 'थ'),
                  ('ð', 'द'), ('s', 'स'), ('z', 'ज़'), ('ʃ', 'श'), ('ʒ', 'ज़'), ('h', 'ह'), ('m', 'म'), ('n', 'न'), ('ŋ', 'ंग'), ('l', 'ल'), ('ɹ', 'र'), ('r', 'र'),
                  ('j', 'य'), ('w', 'व'), ('ɾ', 'ड')]
HALANT = '्'


def _from_ipa(ipa: str) -> str:
    """English pronunciation, written in Hindi script: /seɪv/ → सेव."""
    ipa = re.sub(r'[ˈˌ\s]', '', ipa)
    out, i, after_consonant = '', 0, False
    while i < len(ipa):
        vowel = next((v for v in IPA_VOWELS if ipa.startswith(v[0], i)), None)
        if vowel:
            out += vowel[2] if after_consonant else vowel[1]
            i += len(vowel[0])
            after_consonant = False
            continue
        consonant = next((c for c in IPA_CONSONANTS if ipa.startswith(c[0], i)), None)
        if consonant:
            if after_consonant and not consonant[1].startswith('ं'):
                out += HALANT
            out += consonant[1]
            i += len(consonant[0])
            after_consonant = not consonant[1].startswith('ं')
            continue
        i += 1      # a mark this table doesn't need
    return out


@functools.lru_cache(maxsize=512)
def _english_word(word: str) -> str | None:
    """How an English word really sounds, in Hindi script; None if espeak-ng can't say."""
    if not shutil.which('espeak-ng'):
        return None
    try:
        ipa = subprocess.run(['espeak-ng', '-q', '--ipa', '-v', 'en-us', word], capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return _from_ipa(ipa) or None


# Spellings English uses and romanized Hindi doesn't: silent e, -ing, c without h, -es, and so on.
ENGLISH_SPELLING = re.compile(r"[aeiou][bcdfgklmnprstvz]e$|ings?$|tion|ght|gn$|ck|^wh|x|q|c(?!h)|[^aeiou]es$|ea|oa|ou|ay$|ows?$|ew$|oo[kmn]$|(?:en|ch|ll|ss|pp|tt|rr)ed$", re.I)


def devanagari_text(text: str, roman: bool | None = None) -> str:
    """Latin letters → Hindi script. Hindi and Indian names are spelled out; English goes by how it sounds.

    `roman=True` says the text is romanized Hindi. Otherwise a phrase with a Hindi word in it is
    Hindi, and each other word is judged by its spelling ("Save" → सेव, "Arijit" → अरिजित).
    """
    hindi = bool(ROMAN_HINDI.search(text)) if roman is None else roman

    def word(found):
        said = found.group(0)
        if hindi or said.lower() in NAMES or not ENGLISH_SPELLING.search(said):
            return to_devanagari(said)
        return _english_word(said) or to_devanagari(said)
    return re.sub(r"[A-Za-z][A-Za-z']*", word, text)


WEEKDAYS = {'Monday': 'सोमवार', 'Tuesday': 'मंगलवार', 'Wednesday': 'बुधवार', 'Thursday': 'गुरुवार', 'Friday': 'शुक्रवार',
            'Saturday': 'शनिवार', 'Sunday': 'रविवार'}
MONTHS = {'January': 'जनवरी', 'February': 'फ़रवरी', 'March': 'मार्च', 'April': 'अप्रैल', 'May': 'मई', 'June': 'जून',
          'July': 'जुलाई', 'August': 'अगस्त', 'September': 'सितंबर', 'October': 'अक्टूबर', 'November': 'नवंबर', 'December': 'दिसंबर'}


def _name(text: str) -> str:
    text = re.sub(r'~/(?:[^\s/]+/)*', '', text.strip(' .'))             # "~/Downloads" → "Downloads"
    return devanagari_text(re.sub(r'https?://(?:www\.)?([^/\s]+)\S*', r'\1', text).replace('.com', ''))


REPLIES = [
    (r'Opened (?P<x>.+?) in a new tab', lambda m: f'{_name(m["x"])} नए टैब में खोल दिया'),
    (r'Opened (?P<x>.+)', lambda m: f'{_name(m["x"])} खोल दिया'),
    (r'Requested (?P<x>.+)', lambda m: f'{_name(m["x"])} खोल रहा हूँ'),
    (r'Playing (?P<x>.+?)(?: on \w+)?', lambda m: f'{_name(m["x"])} चला दिया'),
    (r'Searched (?P<site>\S+) for (?P<q>.+)', lambda m: f'{_name(m["site"])} पर {_name(m["q"])} सर्च कर दिया'),
    (r'Volume (?P<n>\d+)%', lambda m: f'आवाज़ {m["n"]} प्रतिशत'),
    (r'Brightness (?P<n>\d+)%', lambda m: f'ब्राइटनेस {m["n"]} प्रतिशत'),
    (r'Sound muted', lambda m: 'आवाज़ बंद कर दी'),
    (r'Sound unmuted', lambda m: 'आवाज़ चालू कर दी'),
    (r'It is (?P<h>\d+):(?P<m>\d+) (?:AM|PM)\.', lambda m: f'अभी {int(m["h"])} बजकर {int(m["m"])} मिनट हुए हैं'),
    (r'Today is (?P<d>\w+), (?P<mo>\w+) (?P<n>\d+), (?P<y>\d+)\.',
     lambda m: f'आज {WEEKDAYS.get(m["d"], m["d"])}, {m["n"]} {MONTHS.get(m["mo"], m["mo"])} {m["y"]} है'),
    (r'Battery is at (?P<n>\d+)% and (?P<s>\w+)\.', lambda m: f'बैटरी {m["n"]} प्रतिशत है' + (', और चार्ज हो रही है' if m['s'] == 'charging' else '')),
    (r'Closed (?P<x>.+)', lambda m: f'{_name(m["x"])} बंद कर दिया'),
    (r'Screenshot taken', lambda m: 'स्क्रीनशॉट ले लिया'),
    (r'Clicked (?P<x>.+)', lambda m: f'{_name(m["x"])} पर क्लिक कर दिया'),
    (r'Scrolled (?P<d>down|up|top|bottom)', lambda m: {'down': 'नीचे', 'up': 'ऊपर', 'top': 'सबसे ऊपर', 'bottom': 'सबसे नीचे'}[m['d']] + ' स्क्रॉल कर दिया'),
    (r'Showing (?P<n>\d+) numbers', lambda m: f'{m["n"]} नंबर दिखा दिए'),
    (r'Hid the numbers', lambda m: 'नंबर हटा दिए'),
    (r'(?P<x>\w+) theme', lambda m: f'{_name(m["x"])} थीम लगा दी'),
    (r'Typed (?P<x>.+)', lambda m: 'लिख दिया'),
    (r'Hands-free is on\..*', lambda m: 'हैंड्स फ़्री चालू है। ब्लॉक बोलकर कुछ भी कहिए'),
    (r'Hands-free is off\.', lambda m: 'हैंड्स फ़्री बंद कर दिया'),
    (r'Yes\?', lambda m: 'जी?'),
    (r'Okay\.?', lambda m: 'ठीक है'),
    (r'I can see "(?P<x>[^"]+)" in (?P<n>\d+) places.*', lambda m: f'{_name(m["x"])} {m["n"]} जगह दिख रहा है, इसलिए क्लिक नहीं किया। पूरा नाम बोलिए'),
    (r'I can\'t see "(?P<x>[^"]+)".*', lambda m: f'{_name(m["x"])} नहीं दिख रहा'),
    (r'No visible control named (?P<x>.+?)\.(?: Closest:.*)?', lambda m: f'{_name(m["x"])} नहीं मिला'),
    (r'Which one: .*', lambda m: 'कौन सा? स्क्रीन पर देखिए'),
    (r'This page has no search box\. Searched (?P<site>\S+) for (?P<q>.+)', lambda m: f'इस पेज पर सर्च नहीं है, इसलिए {_name(m["site"])} पर {_name(m["q"])} सर्च कर दिया'),
    (r'Speaking Hindi now\.?', lambda m: 'अब मैं हिंदी में बोलूँगा'),
    (r'Answering in the language you speak\.?', lambda m: 'अब आप जिस भाषा में बोलेंगे, उसी में जवाब दूँगा'),
    (r'Watching\..*', lambda m: 'देख रहा हूँ। एक बार करके दिखाइए, फिर बोलिए इसका नाम क्या रखूँ'),
    (r'Got it, (?P<n>\d+) steps\..*', lambda m: f'{m["n"]} स्टेप देख लिए। इसका नाम क्या रखूँ?'),
    (r'Learned "(?P<x>[^"]+)".*', lambda m: f'सीख लिया: {_name(m["x"])}'),
    (r'Done: (?P<x>.+)', lambda m: f'{_name(m["x"])} हो गया'),
    (r'Focus mode on: .*', lambda m: 'फ़ोकस मोड चालू है, नोटिफ़िकेशन बंद कर दिए'),
    (r'Focus (?:mode off|time is over) after (?P<n>\d+) minutes\..*', lambda m: f'फ़ोकस मोड बंद, {m["n"]} मिनट हुए'),
    (r'Saved (?P<n>\d+) windows? as (?P<x>.+)', lambda m: f'{m["n"]} विंडो {_name(m["x"])} नाम से सेव कर दीं'),
    (r'Restored (?P<x>[^:]+):.*', lambda m: f'{_name(m["x"])} लेआउट लगा दिया'),
    (r'(?P<a>\S+) on the left, (?P<b>\S+) on the right.*', lambda m: f'{_name(m["a"])} बाईं तरफ़, {_name(m["b"])} दाईं तरफ़'),
]


EFFECTS = [
    (r'opened a new tab', lambda m: 'नया टैब खुल गया'),
    (r'opened a new window', lambda m: 'नई विंडो खुल गई'),
    (r'the page changed', lambda m: 'पेज बदल गया'),
    (r'the window changed', lambda m: 'विंडो बदल गई'),
    (r'nothing visibly changed', lambda m: 'पर कुछ बदला नहीं दिखा'),
    (r'focus moved to another window', lambda m: 'दूसरी विंडो पर आ गए'),
    (r'downloading (?P<x>.+)', lambda m: f'{_name(m["x"])} डाउनलोड हो रहा है'),
]


def feminine(text: str) -> str:
    """The same reply for a female voice: the replies are written in the masculine."""
    for masculine, female in (('रहा हूँ', 'रही हूँ'), ('बोलूँगा', 'बोलूँगी'), ('दूँगा', 'दूँगी'), ('रखूँगा', 'रखूँगी'), ('रहता हूँ', 'रहती हूँ'), ('चलता हूँ', 'चलती हूँ'),
                              ('सकता हूँ', 'सकती हूँ'), ('देता हूँ', 'देती हूँ'), ('जाता हूँ', 'जाती हूँ'), ('देता,', 'देती,'), ('देता ', 'देती '), ('भूल गया', 'भूल गई'), ('किया।', 'किया।')):
        text = text.replace(masculine, female)
    return text


def _match(rules, text: str) -> str | None:
    for pattern, build in rules:
        m = re.fullmatch(pattern, text)
        if m:
            return build(m)
    return None


def reply(message: str, error: bool = False, strict: bool = False) -> str | None:
    """The reply in Hindi (Devanagari) for Kokoro's Hindi mode; the overlay keeps the English details."""
    text = re.sub(r'\s*·\s*result not verified', '', message.strip())
    head, *notes = [part.strip() for part in text.split(' · ')]     # "Clicked Save · the page changed"
    said = _match(REPLIES, head)
    if said:
        extra = [_match(EFFECTS, note) for note in notes]
        return '। '.join([said] + [e for e in extra if e])
    if strict:
        return None
    return 'माफ़ कीजिए, यह नहीं हो पाया' if error else 'हो गया'
