"""Seeing the screen without a GPU: page text from the browser extension, OCR elsewhere.

Answers use the local Qwen model through Ollama when it's running; otherwise
they're extractive (the most relevant sentences, plus patterns for prices,
dates, emails and phone numbers). Captures live in a private runtime folder
and are deleted immediately; screen text is never stored.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unicodedata
from difflib import SequenceMatcher

from blok import browser

STOP = set('a an the is are was were be been of to in on for and or but with this that these those it its at by from as '
           'what whats which who whom how when where why do does did can could should would will i me my you your we our they '
           'their there here page article site screen about please tell show give find'.split())


# ---------------------------------------------------------------- capture + OCR
def _run(args, timeout=20, **kw):
    return subprocess.run(args, capture_output=True, timeout=timeout, **kw)


def active_window() -> dict:
    return json.loads(_run(['hyprctl', '-j', 'activewindow'], text=True).stdout or '{}')


def ocr_window(window: dict | None = None, hide_overlay=None) -> dict:
    """OCR the focused window. Returns {'text', 'words': [{text, x, y, w, h, conf}], 'window'}.

    `hide_overlay(hidden)` hides BLoK's own overlay during the capture, so its text
    (often the very question being asked) isn't read as the window's.
    """
    if not (shutil.which('grim') and shutil.which('tesseract') and shutil.which('magick')):
        raise RuntimeError('Reading other apps needs grim, tesseract and imagemagick.')
    window = window or active_window()
    if not window.get('size'):
        raise RuntimeError('No window is focused.')
    (x, y), (w, h) = window['at'], window['size']
    with tempfile.TemporaryDirectory(prefix='blok-screen-', dir=os.environ.get('XDG_RUNTIME_DIR')) as folder:
        shot = Path(folder) / 'window.png'
        if hide_overlay:
            hide_overlay(True)
        try:
            captured = _run(['grim', '-g', f'{x},{y} {w}x{h}', str(shot)]).returncode == 0
        finally:
            if hide_overlay:
                hide_overlay(False)
        if not captured:
            raise RuntimeError('Could not capture the window.')
        mean = float(_run(['magick', str(shot), '-colorspace', 'Gray', '-format', '%[fx:mean]', 'info:'], text=True).stdout or 0.5)
        # Light text on a dark (often translucent) background: a low threshold keeps the
        # glyphs and drops the wallpaper; dark-on-light themes use a high one. Keep the best.
        variants = ([['-threshold', '35%', '-negate'], ['-threshold', '45%', '-negate'], ['-negate']] if mean < 0.5
                    else [['-threshold', '60%'], ['-threshold', '75%'], []])
        best = None
        for i, steps in enumerate(variants):
            prepared = Path(folder) / f'prep{i}.png'
            _run(['magick', str(shot), '-colorspace', 'Gray', '-resize', '200%', *steps, str(prepared)])
            result = _tesseract(prepared)
            if best is None or result['score'] > best['score']:
                best = result
            if best['score'] > 85:
                break
    best['window'] = window
    return best


def _tesseract(path: Path) -> dict:
    tsv = _run(['tesseract', str(path), '-', '--psm', '6', 'tsv'], text=True).stdout
    words, lines = [], {}
    for row in tsv.splitlines()[1:]:
        cols = row.split('\t')
        if len(cols) < 12 or not cols[11].strip():
            continue
        conf = float(cols[10])
        if conf < 0:
            continue
        word = {'text': unicodedata.normalize('NFKC', cols[11]), 'x': int(cols[6]) // 2, 'y': int(cols[7]) // 2, 'w': int(cols[8]) // 2,
                'h': int(cols[9]) // 2, 'conf': conf}
        words.append(word)
        lines.setdefault((cols[2], cols[3], cols[4]), []).append(word['text'])
    good = [w['conf'] for w in words if re.search(r'[A-Za-z]{2}', w['text'])]
    score = sum(good) / len(good) if good else 0.0
    return {'text': '\n'.join(' '.join(v) for v in lines.values()), 'words': words, 'score': score}


# ---------------------------------------------------------------- what's on screen
def read_screen(in_browser: bool, hide_overlay=None) -> dict:
    """{'source', 'title', 'text', 'selection'} for whatever is in front."""
    if in_browser:
        page = browser.request({'action': 'read_page'})
        return {'source': 'page', 'title': page.get('title', ''), 'text': page.get('text', ''),
                'selection': page.get('selection', ''), 'url': page.get('url', '')}
    seen = ocr_window(hide_overlay=hide_overlay)
    window = seen['window']
    return {'source': 'ocr', 'title': window.get('title') or window.get('class', ''), 'text': seen['text'], 'selection': ''}


# ---------------------------------------------------------------- understanding text
def sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[.!?])\s+|\n{1,}', text)
    return [p.strip() for p in parts if len(p.strip()) > 25 and re.search(r'[a-z]{3}', p)]


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in STOP and len(w) > 2]


def summarize(text: str, count: int = 3) -> str:
    """A few sentences: from Qwen when available, else the most central sentences in order."""
    llm = _llm('Summarize this in two or three short sentences for someone listening, plain words, no lists.', text)
    if llm:
        return llm
    found = sentences(text)
    if not found:
        return text.strip()[:300] or 'There is no readable text here.'
    freq = {}
    for w in _words(text):
        freq[w] = freq.get(w, 0) + 1
    scored = sorted(range(len(found)), key=lambda i: -sum(freq.get(w, 0) for w in set(_words(found[i]))) / (len(_words(found[i])) ** 0.5 + 1)
                    - (2 if i < 3 else 0))
    keep = sorted(scored[:count])
    return ' '.join(found[i] for i in keep)


PATTERNS = {
    'price': r'(?:₹|rs\.?|inr|\$|usd|€|£)\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?(?:rupees|dollars|usd|inr)',
    'cost': None, 'email': r'[\w.+-]+@[\w-]+\.[\w.]+', 'phone': r'\+?\d[\d\s()-]{8,}\d',
    'date': r'\b(?:\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{2,4}|'
            r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{2,4}|\d{4}-\d{2}-\d{2})\b',
}
PATTERNS['cost'] = PATTERNS['price']
PATTERNS['deadline'] = PATTERNS['date']


def answer(question: str, text: str) -> str:
    llm = _llm('Answer the question using only the text. One short sentence. If the text does not say, reply "It doesn\'t say."',
               f'Question: {question}\n\nText:\n{text}')
    if llm:
        return llm
    for key, pattern in PATTERNS.items():
        if re.search(rf'\b{key}\b', question, re.I):
            hits = list(dict.fromkeys(m.group(0).strip() for m in re.finditer(pattern, text, re.I)))
            if hits:
                return f'The {key} here is {hits[0]}' + (f' (also {", ".join(hits[1:3])})' if len(hits) > 1 else '')
    asked = set(_words(question))
    best = max(sentences(text), key=lambda s: len(asked & set(_words(s))), default='')
    return best if best and asked & set(_words(best)) else "I couldn't find that here."


ERROR = re.compile(r'error|exception|traceback|failed|failure|fatal|not found|denied|refused|cannot|can\'t|unable|'
                   r'no such|undefined|invalid|panic|segmentation', re.I)


def explain_error(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    hits = [i for i, l in enumerate(lines) if ERROR.search(l)]
    if not hits:
        return "I don't see an error on screen."
    last = lines[hits[-1]]
    context = '\n'.join(lines[max(0, hits[0] - 3):hits[-1] + 2])
    llm = _llm('Explain this error to a developer in one or two short spoken sentences: what went wrong and the most likely fix.', context)
    return llm or f'The error says: {last}'


def _llm(instruction: str, text: str) -> str | None:
    """Local Qwen through Ollama, when it's running; never required."""
    from blok import rephrase
    model = rephrase.model_name()
    if not model or not text.strip():
        return None
    import urllib.request
    payload = {'model': model, 'stream': False, 'keep_alive': '30m', 'options': {'temperature': 0.2, 'num_predict': 160, 'num_ctx': 4096},
               'messages': [{'role': 'system', 'content': instruction}, {'role': 'user', 'content': text[:6000]}]}
    try:
        request = urllib.request.Request(rephrase.HOST + '/api/chat', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=25) as response:
            reply = json.loads(response.read())['message']['content'].strip()
        return reply or None
    except (OSError, ValueError, KeyError):
        return None


def find_word(words: list[dict], target: str) -> dict | None:
    """The on-screen box for a label (one or more words), most confident first."""
    target = re.sub(r'\s+(?:button|link|tab|icon|option|menu|field)$', '', target.strip(), flags=re.I)
    wanted = [w for w in re.findall(r'\w+', target.lower()) if w not in STOP] or re.findall(r'\w+', target.lower())
    if not wanted:
        return None
    # OCR misreads a letter now and then ("ﬁodule"), so words match when they're nearly equal.
    same = lambda seen, want: seen == want or (len(want) > 3 and SequenceMatcher(None, seen, want).ratio() >= 0.8)
    best = None
    for i, word in enumerate(words):
        if not same(re.sub(r'\W', '', word['text'].lower()), wanted[0]):
            continue
        run = words[i:i + len(wanted)]
        if len(run) == len(wanted) and all(same(re.sub(r'\W', '', w['text'].lower()), want) for w, want in zip(run, wanted)):
            box = {'x': run[0]['x'], 'y': min(w['y'] for w in run), 'w': run[-1]['x'] + run[-1]['w'] - run[0]['x'],
                   'h': max(w['h'] for w in run), 'conf': min(w['conf'] for w in run)}
            if best is None or box['conf'] > best['conf']:
                best = box
    return best


# ---------------------------------------------------------------- what people say
def intent(text: str) -> dict | None:
    t = text.strip().strip('.!?')
    if re.fullmatch(r"(?:read|read out|read aloud)(?: me)? (?:this|it|the page|this page|the article|this article|the screen|"
                    r"what'?s on (?:the|my) screen|this to me|the selection|the selected text|what i selected|this out)"
                    r"(?: (?:out|aloud|to me|for me))*", t, re.I):
        return {'tool': 'screen', 'ask': 'read'}
    if re.fullmatch(r"(?:summari[sz]e|sum up|give me a summary of|tl;?dr|tldr)(?: (?:this|it|the page|this page|the article|this article|"
                    r"the screen|this video))?|what(?:'s| is) (?:this|the) (?:page|article|site|website|video|screen|document|email) about|"
                    r"what am i looking at|what does (?:this|the) (?:page|article) say", t, re.I):
        return {'tool': 'screen', 'ask': 'summary'}
    if re.fullmatch(r"(?:what(?:'s| is| does) (?:this|the) error(?: mean| say)?|explain (?:this|the) error|summari[sz]e (?:this|the) error|"
                    r"what went wrong|why did (?:this|it|that) (?:fail|crash|break))(?: (?:in|on) (?:my|the|this) (?:terminal|screen|editor))?", t, re.I):
        return {'tool': 'screen', 'ask': 'error'}
    m = re.fullmatch(r"(?:on this page,? |according to this page,? |here,? )?((?:what(?:'s| is| are)|how much (?:is|does)|when (?:is|does)|who (?:is|wrote)|"
                     r"where (?:is|do)|how many) .+?)(?: (?:here|on this page|on the page|in this|on screen|on the screen))", t, re.I) \
        or re.fullmatch(r"(?:on this page|according to this page|on screen),? (.+)", t, re.I)
    if m:
        return {'tool': 'screen', 'ask': 'question', 'question': m[1]}
    m = re.fullmatch(r"(?:what(?:'s| is) the|how much is the) (price|cost|deadline|email|phone number|address)", t, re.I)
    if m:
        return {'tool': 'screen', 'ask': 'question', 'question': t}
    return None
