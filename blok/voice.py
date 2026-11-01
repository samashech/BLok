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


class Speaker:
    def __init__(self, settings_path: Path | None = None, on_notice=None, enabled=True):
        self.enabled = enabled
        self.settings_path = settings_path
        self.on_notice = on_notice or (lambda message: None)
        self.lock = threading.Lock()
        self.player = None
        self.generation = 0
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
        if not chunks or self.mode() == 'off':
            return
        self.stop()
        with self.lock:
            generation = self.generation
        def run():
            for chunk in chunks:
                if not self._current(generation):
                    return
                self.next_voice, self.next_lang = voice, lang
                self._speak(chunk, self.mode(), generation)
                player = self.player
                while player and player.poll() is None and self._current(generation):
                    time.sleep(0.05)
        threading.Thread(target=run, daemon=True).start()

    def speaking(self) -> bool:
        player = self.player
        return bool(player and player.poll() is None)

    def stop(self):
        with self.lock:
            self.generation += 1
            player, self.player = self.player, None
        if player and player.poll() is None:
            player.terminate()

    def say(self, text: str, voice: str | None = None, lang: str | None = None):
        """Speak `text`; `voice`/`lang` apply to this reply only (Hindi replies: an hf_/hm_ voice and lang 'hi')."""
        self.next_voice, self.next_lang = voice, lang
        text = (text or '').strip()
        mode = self.mode()
        if not text or mode == 'off':
            return
        self.stop()
        with self.lock:
            generation = self.generation
        threading.Thread(target=self._speak, args=(text, mode, generation), daemon=True).start()

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
        return os.environ.get('BLOK_KOKORO_VOICE', 'af_heart')

    def _speak(self, text, mode, generation):
        if mode == 'kokoro':
            try:
                self._kokoro(text, generation)
                return
            except Exception as error:
                if not self.warned:
                    self.warned = True
                    self.on_notice('Kokoro voice failed (' + str(error)[:120] + '); using espeak.')
            self._local(text, generation)
            return
        if mode == 'elevenlabs':
            try:
                self._elevenlabs(text, generation)
                return
            except Exception as error:  # network, quota, bad key, missing player
                if not self.warned:
                    self.warned = True
                    self.on_notice('ElevenLabs voice failed (' + str(error)[:120] + '); using the local voice.')
        self._local(text, generation)

    def _local(self, text, generation):
        command = os.environ.get('BLOK_TTS_CMD')
        espeak = ['espeak-ng', '-s', '165'] + (['-v', 'hi'] if getattr(self, 'next_lang', None) == 'hi' else [])
        args = command.split() + [text] if command else (espeak + [text] if shutil.which('espeak-ng') else None)
        if args:
            self._start(args, generation)

    def _kokoro(self, text, generation):
        import soundfile
        speed = float(os.environ.get('BLOK_KOKORO_SPEED', '1.05'))
        voice = getattr(self, 'next_voice', None) or self.kokoro_voice()
        lang = getattr(self, 'next_lang', None) or 'en-us'
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
