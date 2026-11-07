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


def ocr_window(window: dict | None = None, hide_overlay=None, sparse: bool = False, wanted: str | None = None) -> dict:
    """OCR the focused window. Returns {'text', 'words': [{text, x, y, w, h, conf}], 'window'}.

    `hide_overlay(hidden)` hides BLoK's own overlay during the capture, so its text
    (often the very question being asked) isn't read as the window's. `sparse` looks for
    scattered labels: reading a page as one block of text finds no buttons at all. With
    `wanted`, reading stops as soon as that label is clearly found.
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
        if sparse:
            # Doubling helps small interface text, but makes large text unreadable: read both sizes.
            prepared = Path(folder) / 'actual.png'
            _run(['magick', str(shot), '-colorspace', 'Gray', *(['-negate'] if mean < 0.5 else []), str(prepared)])
            best = _tesseract(prepared, sparse, zoom=1)
        sure = lambda: wanted and any(box['conf'] >= 70 for box in find_words(best['words'], wanted))
        for i, steps in enumerate(variants):
            if sparse and sure():
                break
            prepared = Path(folder) / f'prep{i}.png'
            _run(['magick', str(shot), '-colorspace', 'Gray', '-resize', '200%', *steps, str(prepared)])
            result = _tesseract(prepared, sparse)
            if sparse:
                # Each treatment can drop a different word, so looking for a label keeps them all.
                best = _merge(best, result)
                continue
            if best is None or result['score'] > best['score']:
                best = result
            if best['score'] > 85:
                break
        # On a scaled display the capture has more pixels than the window has positions.
        pixels = _run(['magick', 'identify', '-format', '%w', str(shot)], text=True).stdout
        factor = int(pixels) / w if str(pixels).strip().isdigit() and w else 1.0
        image = _gray(shot) if sparse else None
    if image is not None:
        best['image'], best['factor'], best['dark'] = image, factor, mean < 0.5
    if factor != 1.0:
        for word in best['words']:
            for key in ('x', 'y', 'w', 'h'):
                word[key] = round(word[key] / factor)
    best['window'] = window
    return best


def _gray(path) -> "numpy.ndarray | None":
    """An image as a grid of 0–255 brightness values."""
    import numpy
    size = _run(['magick', 'identify', '-format', '%w %h', str(path)], text=True).stdout
    raw = _run(['magick', str(path), '-colorspace', 'Gray', '-depth', '8', 'gray:-']).stdout
    try:
        width, height = map(int, str(size).split())
        return numpy.frombuffer(raw, numpy.uint8).reshape(height, width)
    except (TypeError, ValueError):
        return None


def capture_gray(window: dict):
    """A fresh look at a window, for comparing before and after. None if it can't be taken."""
    (x, y), (w, h) = window['at'], window['size']
    with tempfile.TemporaryDirectory(prefix='blok-screen-', dir=os.environ.get('XDG_RUNTIME_DIR')) as folder:
        shot = Path(folder) / 'window.png'
        if _run(['grim', '-g', f'{x},{y} {w}x{h}', str(shot)]).returncode:
            return None
        return _gray(shot)


def changed_share(before, after) -> float:
    """How much of a window visibly differs between two looks, 0–1. Tiny shifts don't count."""
    import numpy
    if before is None or after is None or before.shape != after.shape:
        return 0.0
    return float((numpy.abs(before.astype(numpy.int16) - after.astype(numpy.int16)) > 24).mean())


def clients() -> set[str]:
    """The addresses of all open windows."""
    return {c.get('address') for c in json.loads(_run(['hyprctl', '-j', 'clients'], text=True).stdout or '[]')}


def _long_runs(mask, length: int):
    """Which cells belong to a horizontal run at least this long."""
    import numpy
    found = numpy.zeros_like(mask)
    for i, row in enumerate(mask):
        edges = numpy.diff(numpy.concatenate(([0], row.astype(numpy.int8), [0])))
        for start, end in zip(numpy.where(edges == 1)[0], numpy.where(edges == -1)[0]):
            if end - start >= length:
                found[i, start:end] = True
    return found


def text_blobs(image) -> list[tuple[int, int, int, int]]:
    """Where text-like shapes are, as (left, top, right, bottom). Works from the image alone.

    Button borders are what confuse Tesseract, so straight lines are erased, then pixels that
    stand out from their neighbourhood are joined into words.
    """
    import numpy
    a = image.astype(numpy.int32)
    up, down, left, right = numpy.roll(a, 2, 0), numpy.roll(a, -2, 0), numpy.roll(a, 2, 1), numpy.roll(a, -2, 1)
    across, along = (up + down) // 2, (left + right) // 2
    flat = a.copy()
    lines = _long_runs(numpy.abs(a - across) > 12, 40)
    flat[lines] = across[lines]
    lines = _long_runs((numpy.abs(a - along) > 12).T, 40).T
    flat[lines] = along[lines]
    size = 15
    table = numpy.pad(numpy.pad(flat, size, mode='edge').astype(numpy.int64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    span = 2 * size + 1
    local = (table[span:, span:] - table[:-span, span:] - table[span:, :-span] + table[:-span, :-span]) / span ** 2
    ink = numpy.abs(flat - local) > 18
    joined = ink.copy()
    for i in numpy.where(ink.any(axis=1))[0]:
        cells = numpy.where(ink[i])[0]
        for start, end in zip(cells[:-1], cells[1:]):
            if 1 < end - start <= 8:
                joined[i, start:end] = True
    return _components(joined)


def _components(mask) -> list[tuple[int, int, int, int]]:
    """Bounding boxes of joined regions, keeping only those shaped like words."""
    import numpy
    labels = numpy.zeros(mask.shape, numpy.int32)
    parent = [0]

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for y, x in zip(*numpy.nonzero(mask)):
        near = [v for v in (labels[y, x - 1] if x else 0, labels[y - 1, x] if y else 0) if v]
        if near:
            labels[y, x] = root(near[0])
            if len(near) > 1:
                parent[root(near[1])] = root(near[0])
        else:
            parent.append(len(parent))
            labels[y, x] = len(parent) - 1
    boxes: dict[int, list[int]] = {}
    for y, x in zip(*numpy.nonzero(labels)):
        box = boxes.setdefault(root(labels[y, x]), [x, y, x + 1, y + 1])
        box[0], box[1], box[2], box[3] = min(box[0], x), min(box[1], y), max(box[2], x + 1), max(box[3], y + 1)
    return [tuple(int(v) for v in b) for b in boxes.values() if 6 <= b[3] - b[1] <= 70 and 8 <= b[2] - b[0] <= 500]


def read_blobs(seen: dict, label: str, limit: int = 120) -> list[dict]:
    """Read text-like shapes one at a time. Slower, but it reads small dim text whole-window OCR misses.

    A shape about as long as the label comes first, so a page full of text stays quick.
    """
    from concurrent.futures import ThreadPoolExecutor
    import numpy
    image = seen.get('image')
    if image is None:
        return []
    gray = (255 - image) if seen.get('dark') else image
    letters = max(1, len(label.strip()))

    def likeness(box):
        fit = (box[2] - box[0]) / max(1, box[3] - box[1]) / letters
        return abs(fit - 0.55)
    blobs = sorted(text_blobs(gray), key=likeness)[:limit]
    factor = seen.get('factor') or 1.0

    def read(box):
        left, top, right, bottom = box
        x0, y0 = max(left - 10, 0), max(top - 4, 0)
        crop = gray[y0:bottom + 4, x0:right + 10]
        zoom = max(100, min(600, 100 * 48 // max(bottom - top, 1)))
        with tempfile.TemporaryDirectory(prefix='blok-blob-', dir=os.environ.get('XDG_RUNTIME_DIR')) as folder:
            path = Path(folder) / 'blob.png'
            height, width = crop.shape
            _run(['magick', '-size', f'{width}x{height}', '-depth', '8', 'gray:-', '-filter', 'Lanczos', '-resize', f'{zoom}%',
                  '-bordercolor', f'gray({int(numpy.median(crop))})', '-border', '16', str(path)], input=crop.astype(numpy.uint8).tobytes())
            tsv = _run(['tesseract', str(path), '-', '--psm', '7', 'tsv'], text=True).stdout
        words = []
        for row in tsv.splitlines()[1:]:
            cols = row.split('\t')
            if len(cols) < 12 or not cols[11].strip() or float(cols[10]) < 0:
                continue
            scale = 100 / zoom
            words.append({'text': unicodedata.normalize('NFKC', cols[11]), 'conf': float(cols[10]),
                          'x': round((x0 + (int(cols[6]) - 16) * scale) / factor), 'y': round((y0 + (int(cols[7]) - 16) * scale) / factor),
                          'w': round(int(cols[8]) * scale / factor), 'h': round(int(cols[9]) * scale / factor)})
        return words
    with ThreadPoolExecutor(8) as pool:
        return [word for words in pool.map(read, blobs) for word in words]


def lookalikes(seen: dict, box: dict) -> int:
    """How many other places look like this word, comparing pixels, so a copy OCR misread still counts.

    A close match inside a different word the OCR read clearly ("Save" in "Saved") doesn't count.
    """
    import numpy
    image, factor = seen.get('image'), seen.get('factor') or 1.0
    if image is None:
        return 0
    x, y = round(box['x'] * factor), round(box['y'] * factor)
    w, h = max(1, round(box['w'] * factor)), max(1, round(box['h'] * factor))
    template = image[max(y, 0):y + h, max(x, 0):x + w].astype(numpy.float64)
    if template.size == 0 or template.std() < 8 or template.shape[0] > image.shape[0] or template.shape[1] > image.shape[1]:
        return 0
    h, w = template.shape
    a = image.astype(numpy.float64)
    t = template - template.mean()
    shape = (a.shape[0] + h, a.shape[1] + w)
    top = numpy.fft.irfft2(numpy.fft.rfft2(a, shape) * numpy.fft.rfft2(t[::-1, ::-1], shape), shape)[h - 1:a.shape[0], w - 1:a.shape[1]]

    def windowed(values):
        table = numpy.pad(values.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
        return table[h:, w:] - table[:-h, w:] - table[h:, :-w] + table[:-h, :-w]
    spread = windowed(a * a) - windowed(a) ** 2 / (h * w)
    score = numpy.zeros_like(top)
    usable = spread > (8 ** 2) * h * w
    score[usable] = numpy.abs(top[usable]) / numpy.sqrt(spread[usable] * (t * t).sum())
    others = 0
    ys, xs = numpy.where(score >= 0.88)
    taken = [(x, y)]
    for py, px in sorted(zip(ys.tolist(), xs.tolist()), key=lambda p: -score[p[0], p[1]]):
        if any(abs(px - ox) < w and abs(py - oy) < h for ox, oy in taken):
            continue
        taken.append((px, py))
        cx, cy = (px + w / 2) / factor, (py + h / 2) / factor
        inside = next((word for word in seen['words'] if word['conf'] >= 60 and word['x'] <= cx <= word['x'] + word['w']
                       and word['y'] <= cy <= word['y'] + word['h']), None)
        wide = inside is not None and inside['w'] > (box['w']) * 1.15
        if not wide:
            others += 1
    return others


def _merge(seen: dict | None, more: dict) -> dict:
    """Add the words only `more` found. The same word in the same spot counts once, at its best confidence."""
    if seen is None:
        return more
    center = lambda w: (w['x'] + w['w'] / 2, w['y'] + w['h'] / 2)
    for word in more['words']:
        cx, cy = center(word)
        same = next((w for w in seen['words'] if w['text'].lower() == word['text'].lower()
                     and abs(center(w)[0] - cx) <= 10 and abs(center(w)[1] - cy) <= 10), None)
        if same is None:
            seen['words'].append(word)
        elif word['conf'] > same['conf']:
            same.update(word)
    seen['words'].sort(key=lambda w: (round(w['y'] / 12), w['x']))      # reading order, so labels stay in sequence
    seen['text'] = ' '.join(w['text'] for w in seen['words'])
    seen['score'] = max(seen['score'], more['score'])
    return seen


def _tesseract(path: Path, sparse: bool = False, zoom: int = 2) -> dict:
    tsv = _run(['tesseract', str(path), '-', '--psm', '11' if sparse else '6', 'tsv'], text=True).stdout
    words, lines = [], {}
    for row in tsv.splitlines()[1:]:
        cols = row.split('\t')
        if len(cols) < 12 or not cols[11].strip():
            continue
        conf = float(cols[10])
        if conf < 0:
            continue
        word = {'text': unicodedata.normalize('NFKC', cols[11]), 'x': int(cols[6]) // zoom, 'y': int(cols[7]) // zoom, 'w': int(cols[8]) // zoom,
                'h': int(cols[9]) // zoom, 'conf': conf}
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
    return max(find_words(words, target), key=lambda box: box['conf'], default=None)


def find_words(words: list[dict], target: str) -> list[dict]:
    """Every on-screen box for a label (one or more words)."""
    target = re.sub(r'\s+(?:button|link|tab|icon|option|menu|field)$', '', target.strip(), flags=re.I)
    wanted = [w for w in re.findall(r'\w+', target.lower()) if w not in STOP] or re.findall(r'\w+', target.lower())
    if not wanted:
        return []
    # OCR misreads a letter now and then ("ﬁodule"), so words match when they're nearly equal.
    same = lambda seen, want: seen == want or (len(want) > 3 and SequenceMatcher(None, seen, want).ratio() >= 0.8)
    found = []
    for i, word in enumerate(words):
        if not same(re.sub(r'\W', '', word['text'].lower()), wanted[0]):
            continue
        run = words[i:i + len(wanted)]
        if len(run) == len(wanted) and all(same(re.sub(r'\W', '', w['text'].lower()), want) for w, want in zip(run, wanted)):
            found.append({'x': run[0]['x'], 'y': min(w['y'] for w in run), 'w': run[-1]['x'] + run[-1]['w'] - run[0]['x'],
                          'h': max(w['h'] for w in run), 'conf': min(w['conf'] for w in run)})
    # Reading the screen several ways finds one word several times: overlapping boxes are one place.
    places = []
    for box in sorted(found, key=lambda b: -b['conf']):
        if not any(box['x'] < p['x'] + p['w'] and p['x'] < box['x'] + box['w'] and box['y'] < p['y'] + p['h'] and p['y'] < box['y'] + box['h']
                   for p in places):
            places.append(box)
    return places


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
