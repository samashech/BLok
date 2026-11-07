"""Spoken replies: ElevenLabs with a key, else local Kokoro-82M, else espeak-ng.

Kokoro (Apache-2.0) runs offline on the CPU from models/kokoro
(scripts/download_kokoro.py). The ElevenLabs key is read from ELEVENLABS_API_KEY
or ~/.config/blok/elevenlabs.key (never the repository); only the reply text
is sent there, streamed into mpv so speech starts before the clip has downloaded.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request

from blok.paths import CONFIG, MODELS
KEY_FILE = CONFIG / 'elevenlabs.key'
API = 'https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream?output_format=mp3_44100_128'
DEFAULT_VOICE = 'JBFqnCBsd6RMkjVDRZzb'  # "George", a premade ElevenLabs voice
DEFAULT_MODEL = 'eleven_flash_v2_5'      # lowest-latency ElevenLabs model
KOKORO_DIR = MODELS / 'kokoro'
# The full model sounds best; the int8 one (scripts/slim.sh --kokoro-int8) is a quarter the size.
KOKORO_FILES = (next((KOKORO_DIR / name for name in ('kokoro-v1.0.onnx', 'kokoro-v1.0.int8.onnx')
                      if (KOKORO_DIR / name).exists()), KOKORO_DIR / 'kokoro-v1.0.onnx'),
                KOKORO_DIR / 'voices-v1.0.bin')
_kokoro = {'engine': None}
_kokoro_lock = threading.Lock()


def kokoro_available() -> bool:
    if not all(path.exists() for path in KOKORO_FILES):
        return False
    try:
        import kokoro_onnx  # noqa: F401
    except ImportError:
        return False
    return True


def kokoro():
    """The Kokoro engine, loaded once (~1 s) and kept for the session."""
    with _kokoro_lock:
        if _kokoro['engine'] is None:
            from kokoro_onnx import Kokoro
            _kokoro['engine'] = Kokoro(*map(str, KOKORO_FILES))
        return _kokoro['engine']


def api_key() -> str | None:
    key = os.environ.get('ELEVENLABS_API_KEY', '').strip()
    if not key:
        try:
            key = KEY_FILE.read_text().strip()
        except OSError:
            return None
    return key or None


def save_key(key: str):
    CONFIG.mkdir(parents=True, exist_ok=True)
    temp = KEY_FILE.with_suffix('.tmp')
    temp.touch(mode=0o600)
    temp.write_text(key.strip() + '\n')
    temp.replace(KEY_FILE)
    KEY_FILE.chmod(0o600)


def spoken(message: str, error: bool = False) -> str:
    """Overlay text → something pleasant to hear."""
    text = re.sub(r'\s*·\s*', ', ', message)
    text = re.sub(r'https?://(?:www\.)?([^/\s]+)\S*', r'\1', text)
    text = re.sub(r'~/([^/\s,;]+)/?(?=[\s,;.]|$)', r'your \1 folder', text)
    text = re.sub(r'~/(?:[^\s,;]+/)*([^/\s,;]+)', r'\1', text)
    text = re.sub(r'\bresult not verified\b', '', text, flags=re.I)
    text = re.sub(r'\s+', ' ', text).strip(' ,')
    if len(text) > 260:
        text = text[:260].rsplit(' ', 1)[0] + '.'
    if error and not re.match(r'(?:sorry|not done|no |i\'m not sure|which|what)', text, re.I):
        text = 'Sorry, ' + text[0].lower() + text[1:]
    return text


HINDI_DEFAULT, ENGLISH_DEFAULT = 'hm_omega', 'af_heart'
DEVANAGARI = re.compile('[\u0900-\u097f]')
LATIN = re.compile('[A-Za-z]')
ENGLISH_WORDS = re.compile(r"\b(?:the|is|are|was|and|of|to|for|in|on|at|you|your|this|that|with|it|an|from|has|have|not|i)\b", re.I)


def hindi_voice(wanted: str | None = None) -> str:
    """A Hindi voice, whatever was asked for. Only hf_ and hm_ voices can speak Hindi."""
    voice = wanted or os.environ.get('BLOK_HINDI_VOICE') or HINDI_DEFAULT
    return voice if voice[:2] in ('hf', 'hm') else HINDI_DEFAULT


def english_voice(wanted: str | None = None) -> str:
    """An English voice, whatever was asked for. Kokoro's a_ and b_ voices are the English ones."""
    voice = wanted or os.environ.get('BLOK_KOKORO_VOICE') or ENGLISH_DEFAULT
    return voice if voice[:1] in ('a', 'b') else ENGLISH_DEFAULT


def _is_roman_hindi(text: str) -> bool:
    words = re.findall(r"[A-Za-z']+", text)
    from blok.hinglish import ROMAN_HINDI
    found = ROMAN_HINDI.findall(text)
    return len({word.lower() for word in found}) >= 2 and len(found) / max(len(words), 1) >= 0.3 and not ENGLISH_WORDS.search(text)


def language_parts(text: str) -> list[tuple[str, str]]:
    """Split text into ('hi', Devanagari only) and ('en', Latin only) pieces, in order.

    This is what keeps the voices apart: the Hindi voice never gets English letters and the
    English voice never gets Hindi. A few English words in a Hindi sentence are usually names,
    so they're written in Hindi script and stay in the sentence. A longer stretch of English
    gets the English voice, and so does anything mostly English around a Hindi phrase.
    """
    from blok.hinglish import devanagari_text
    text = re.sub(r'\bBLoK\b', 'Block', text)     # said as a word, not spelled B-L-O-K
    if not DEVANAGARI.search(text) and _is_roman_hindi(text):
        text = devanagari_text(text, roman=True)
    runs: list[list] = []
    for word in text.split():
        lang = 'hi' if DEVANAGARI.search(word) else 'en' if LATIN.search(word) else None
        if lang is None and runs:
            lang = runs[-1][0]          # digits and punctuation stay with what they follow
        if runs and (runs[-1][0] == lang or runs[-1][0] is None):
            runs[-1][0] = lang
            runs[-1][1].append(word)
        else:
            runs.append([lang, [word]])
    hindi_words = sum(len(words) for lang, words in runs if lang == 'hi')
    latin_words = sum(len(words) for lang, words in runs if lang == 'en')
    parts: list[tuple[str, str]] = []
    for lang, words in runs:
        piece = ' '.join(words)
        if lang == 'en' and hindi_words and hindi_words >= latin_words and len(words) <= 3:
            lang, piece = 'hi', devanagari_text(piece)
        elif lang == 'hi' and LATIN.search(piece):
            piece = devanagari_text(piece)     # one word in both scripts
        lang = lang or 'en'
        if not re.search(r'\w', piece):
            continue
        if parts and parts[-1][0] == lang:
            parts[-1] = (lang, parts[-1][1] + ' ' + piece)
        else:
            parts.append((lang, piece))
    return parts


class Speaker:
    def __init__(self, settings_path: Path | None = None, on_notice=None, enabled=True):
        self.enabled = enabled
        self.settings_path = settings_path
        self.on_notice = on_notice or (lambda message: None)
        self.lock = threading.Lock()
        self.player = None
        self.generation = 0
        self.talking = None         # which reply is still being made or played
        self.warned = False

    def mode(self) -> str:
        if not self.enabled or os.environ.get('BLOK_TTS') == '0':
            return 'off'
        try:
            chosen = json.loads(self.settings_path.read_text()).get('voice') if self.settings_path else None
        except (OSError, ValueError, AttributeError):
            chosen = None
        if chosen in ('off', 'local') or (chosen == 'kokoro' and kokoro_available()) or (chosen == 'elevenlabs' and api_key()):
            return chosen
        return 'elevenlabs' if api_key() else 'kokoro' if kokoro_available() else 'local'

    def read_aloud(self, text: str, voice: str | None = None, lang: str | None = None):
        """Read long text sentence by sentence; any new speech, or stop(), ends it."""
        chunks, current = [], ''
        for part in re.split(r'(?<=[.!?])\s+|\n+', text):
            part = part.strip()
            if not part:
                continue
            if current and len(current) + len(part) > 240:
                chunks.append(current)
                current = part
            else:
                current = (current + ' ' + part).strip()
        if current:
            chunks.append(current)
        self._play(chunks, voice)

    def _play(self, chunks, voice=None):
        """Speak these in order, each piece in the voice for its own language. Any new speech, or stop(), ends it."""
        mode = self.mode()
        if not chunks or mode == 'off':
            return
        self.stop()
        with self.lock:
            generation = self.generation
            self.talking = generation
        def run():
            try:
                for chunk in chunks:
                    for lang, piece in language_parts(chunk):
                        if not self._current(generation):
                            return
                        chosen = hindi_voice(voice if voice and voice[:2] in ('hf', 'hm') else None) if lang == 'hi' \
                            else english_voice(voice if voice and voice[:1] in ('a', 'b') else None)
                        self._speak(piece, mode, generation, chosen, 'hi' if lang == 'hi' else None)
                        player = self.player
                        while player and player.poll() is None and self._current(generation):
                            time.sleep(0.05)
            finally:
                if self.talking == generation:
                    self.talking = None
        threading.Thread(target=run, daemon=True).start()

    def speaking(self) -> bool:
        """True from the moment a reply is asked for, including while its audio is being made."""
        if self.talking is not None and self.talking == self.generation:
            return True
        player = self.player
        return bool(player and player.poll() is None)

    def stop(self):
        with self.lock:
            self.generation += 1
            player, self.player = self.player, None
        if player and player.poll() is None:
            player.terminate()

    def say(self, text: str, voice: str | None = None, lang: str | None = None):
        """Speak `text`. The language of the words picks the voice, so `voice` is only a preference."""
        text = (text or '').strip()
        if text:
            self._play([text], voice)

    def _current(self, generation):
        return generation == self.generation

    def _start(self, args, generation, stdin=None):
        with self.lock:
            if not self._current(generation):
                return None
            self.player = subprocess.Popen(args, stdin=stdin, stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL, start_new_session=True)
            return self.player

    def warm_up(self):
        if self.mode() == 'kokoro':
            threading.Thread(target=lambda: kokoro().create('ready', voice=self.kokoro_voice(), lang='en-us'), daemon=True).start()

    @staticmethod
    def kokoro_voice():
        return english_voice()

    def _speak(self, text, mode, generation, voice=None, lang=None):
        if mode == 'kokoro':
            try:
                self._kokoro(text, generation, voice, lang)
                return
            except Exception as error:
                if not self.warned:
                    self.warned = True
                    self.on_notice('Kokoro voice failed (' + str(error)[:120] + '); using espeak.')
            self._local(text, generation, lang)
            return
        if mode == 'elevenlabs':
            try:
                self._elevenlabs(text, generation)
                return
            except Exception as error:  # network, quota, bad key, missing player
                if not self.warned:
                    self.warned = True
                    self.on_notice('ElevenLabs voice failed (' + str(error)[:120] + '); using the local voice.')
        self._local(text, generation, lang)

    def _local(self, text, generation, lang=None):
        command = os.environ.get('BLOK_TTS_CMD')
        espeak = ['espeak-ng', '-s', '165'] + (['-v', 'hi'] if lang == 'hi' else [])
        args = command.split() + [text] if command else (espeak + [text] if shutil.which('espeak-ng') else None)
        if args:
            self._start(args, generation)

    def _kokoro(self, text, generation, voice=None, lang=None):
        import soundfile
        speed = float(os.environ.get('BLOK_KOKORO_SPEED', '1.05'))
        lang = lang or 'en-us'
        voice = hindi_voice(voice) if lang == 'hi' else english_voice(voice)
        samples, rate = kokoro().create(text, voice=voice, speed=speed if lang == 'en-us' else 1.0, lang=lang)
        if not self._current(generation):
            return
        player = shutil.which('pw-play') or shutil.which('paplay') or shutil.which('aplay')
        if not player:
            raise RuntimeError('no audio player (pw-play, paplay or aplay)')
        handle, path = tempfile.mkstemp(prefix='blok-voice-', suffix='.wav', dir=os.environ.get('XDG_RUNTIME_DIR'))
        os.close(handle)
        soundfile.write(path, samples, rate)
        process = self._start([player, path], generation)
        def cleanup():
            if process:
                process.wait()
            os.unlink(path)
        threading.Thread(target=cleanup, daemon=True).start()

    def _elevenlabs(self, text, generation):
        player_args = (['mpv', '--no-video', '--really-quiet', '--no-terminal', '-'] if shutil.which('mpv')
                       else ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet', '-'] if shutil.which('ffplay') else None)
        if not player_args:
            raise RuntimeError('install mpv to play ElevenLabs audio')
        voice = os.environ.get('BLOK_ELEVENLABS_VOICE', DEFAULT_VOICE)
        body = json.dumps({'text': text, 'model_id': os.environ.get('BLOK_ELEVENLABS_MODEL', DEFAULT_MODEL),
                           'voice_settings': {'stability': 0.45, 'similarity_boost': 0.8}}).encode()
        request = urllib.request.Request(API.format(voice=voice), data=body, method='POST', headers={
            'xi-api-key': api_key() or '', 'Content-Type': 'application/json', 'Accept': 'audio/mpeg'})
        try:
            response = urllib.request.urlopen(request, timeout=8)
        except urllib.error.HTTPError as error:
            detail = error.read(300).decode(errors='replace')
            raise RuntimeError(f'HTTP {error.code}: {detail}') from error
        with response:
            player = None
            while True:
                chunk = response.read(16384)
                if not chunk or not self._current(generation):
                    break
                if player is None:
                    player = self._start(player_args, generation, stdin=subprocess.PIPE)
                    if player is None:
                        return
                try:
                    player.stdin.write(chunk)
                except (BrokenPipeError, OSError):
                    return
            if player and player.stdin:
                try:
                    player.stdin.close()
                except OSError:
                    pass
            if player is None and self._current(generation):
                raise RuntimeError('ElevenLabs returned no audio')
