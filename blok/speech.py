"""Speech to text, fully local.

Default: BLoK records the microphone with PipeWire (`pw-record`) and transcribes
with open-source Whisper (faster-whisper, models/whisper-small.en) in-process, so
no daemon has to be running. `BLOK_STT=voxtype` uses the Voxtype daemon instead.
"""
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time
import threading
import tomllib

class VoxtypeSession:
    def __init__(self):
        self.lock = threading.RLock()
        self.directory = None
        self.path = None
        self.owned = False
        config_path = Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'voxtype/config.toml'
        config = tomllib.loads(config_path.read_text())
        self.model = str(config.get('whisper', {}).get('model', 'base.en'))
        self.engine = config.get('engine', 'whisper')
        if self.engine == 'soniox' or config.get('whisper', {}).get('mode', 'local') == 'remote':
            raise RuntimeError('BLoK requires local Voxtype recognition; this configuration uses a remote service.')
        state = config.get('state_file', 'auto')
        self.state_path = (Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))/'voxtype/state'
                           if state == 'auto' else Path(state).expanduser())

    def run(self, *args):
        result = subprocess.run(['voxtype', *args], capture_output=True, text=True, timeout=8)
        if result.returncode:
            raise RuntimeError(result.stderr.strip()[:240] or 'Voxtype command failed')
        return result.stdout

    def state(self):
        try:
            return self.state_path.read_text().strip()
        except FileNotFoundError:
            return 'stopped'

    def start(self):
        status = json.loads(self.run('status', '--format', 'json', '--extended'))
        if status.get('class') == 'stopped':
            raise RuntimeError('Voxtype is not running. Start it once with: systemctl --user enable --now voxtype')
        if status.get('class') != 'idle':
            raise RuntimeError('Voxtype is busy. Finish your F9 dictation first.')
        self.model = status.get('model', self.model)
        self.directory = tempfile.TemporaryDirectory(prefix='blok-voice-', dir=os.environ.get('XDG_RUNTIME_DIR', '/tmp'))
        self.path = Path(self.directory.name)/'transcript.txt'
        model = os.environ.get('BLOK_VOXTYPE_MODEL')
        try:
            # `--file` is Voxtype's file output mode: it neither types into the
            # focused window nor touches the clipboard (and rejects `--clipboard`).
            self.run('record', 'start', '--file='+str(self.path), '--no-auto-submit', '--no-smart-auto-submit', '--no-osd',
                     *(['--model', model] if model else []))
            self.owned = True
            for _ in range(30):
                if self.state() == 'recording':
                    return
                time.sleep(.05)
            raise RuntimeError('Voxtype did not start recording')
        except Exception:
            self.cancel()
            raise

    def finish(self):
        if self.owned and self.state() == 'recording':
            self.run('record', 'stop')

    def cancel(self):
        with self.lock:
            if self.owned:
                self.run('record', 'cancel')
                for _ in range(60):
                    if self.state() in ('idle', 'stopped'):
                        self.owned = False
                        return
                    time.sleep(.05)
                raise RuntimeError('Voxtype has not confirmed cancellation')

    def close(self):
        with self.lock:
            self.cancel()
            if self.directory:
                self.directory.cleanup()
                self.directory = None

    def wait(self, alive, on_busy):
        """Block until Voxtype has written the transcript; None if cancelled."""
        started = time.monotonic()
        busy = False
        while alive():
            state = self.state()
            if state == 'transcribing' and not busy:
                busy = True
                on_busy()
            if state == 'idle':
                # State and output are separate writes; tolerate their ordering.
                for _ in range(10):
                    if self.path.exists():
                        break
                    time.sleep(.05)
                text = self.path.read_text().strip() if self.path.exists() else ''
                self.owned = False
                return text
            if state == 'stopped' or time.monotonic() - started > 180:
                raise RuntimeError('Voxtype stopped or timed out')
            time.sleep(.1)
        return None


ROOT = Path(__file__).resolve().parent.parent
# Names Whisper should spell the way BLoK expects.
VOCABULARY = ('Hey Block, BLoK, Laya, Omarchy, Hyprland, YouTube, Spotify, Steam, GitHub, Obsidian, Reddit, '
              'PewDiePie, Brave, VS Code, Nautilus, workspace, open, search, play.')
WORDS_FILE = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'blok' / 'words.txt'


def vocabulary() -> str:
    """Built-in names plus the user's own (one per line in ~/.config/blok/words.txt)."""
    try:
        extra = [w.strip() for w in WORDS_FILE.read_text().splitlines() if w.strip() and not w.startswith('#')]
    except OSError:
        extra = []
    hint = VOCABULARY.rstrip('.') + (', ' + ', '.join(extra[:60]) if extra else '') + '.'
    return hint + ' ' + HINGLISH_HINTS if multilingual() else hint


_whisper = {'model': None}
_whisper_lock = threading.Lock()


# Multilingual models first: installed for Hindi/Hinglish, and almost as good at English.
WHISPER_SIZES = ('small', 'medium', 'base', 'small.en', 'base.en', 'medium.en', 'tiny.en', 'large-v3-turbo')
# Romanized Hinglish in the prompt keeps a multilingual model writing Hindi words in Latin letters.
# Kept short: on unclear audio Whisper sometimes just recites its prompt back.
HINGLISH_HINTS = 'YouTube pe gaana chalao.'


def multilingual() -> bool:
    try:
        return not Path(whisper_model_path()).name.endswith('.en')
    except RuntimeError:
        return False


def whisper_model_path() -> str:
    """BLOK_WHISPER_MODEL, else the installed model (multilingual small preferred, then small.en)."""
    from blok.paths import MODELS
    configured = os.environ.get('BLOK_WHISPER_MODEL')
    if configured:
        return configured
    for size in WHISPER_SIZES:
        local = MODELS / f'whisper-{size}'
        if (local / 'model.bin').exists():
            return str(local)
    raise RuntimeError('No speech model installed. Run ./install.sh (or scripts/download_whisper.py small.en).')


def whisper():
    """The Whisper model, loaded once (~1 s) and kept for the session."""
    with _whisper_lock:
        if _whisper['model'] is None:
            from faster_whisper import WhisperModel
            _whisper['model'] = WhisperModel(whisper_model_path(), device='cpu', compute_type='int8',
                                             cpu_threads=int(os.environ.get('BLOK_WHISPER_THREADS', '4')))
        return _whisper['model']


def normalize(audio):
    """Bring quiet microphones up to a usable level (silence stays silence)."""
    import numpy
    peak = float(numpy.abs(audio).max()) if len(audio) else 0.0
    if 0.002 < peak < 0.5:
        audio = audio * (0.7 / peak)
    return audio.astype('float32')


def has_speech(audio) -> bool:
    """Loudness check: some 30 ms frames stand clearly above the room's noise floor.

    Used instead of Whisper's VAD filter, which trimmed quiet and accented words.
    """
    import numpy
    frame = 480
    usable = len(audio) // frame * frame
    if not usable:
        return False
    levels = numpy.sqrt((audio[:usable].reshape(-1, frame) ** 2).mean(axis=1))
    floor = float(numpy.percentile(levels, 20))
    loud = levels > max(floor * 3, 0.004)
    return int(loud.sum()) >= 6  # at least ~0.2 s of voice


_spotter = {'model': None, 'checked': False}


def spotter():
    """A small English model for hearing "hey block" quickly; falls back to the main model."""
    from blok.paths import MODELS
    with _whisper_lock:
        if not _spotter['checked']:
            _spotter['checked'] = True
            for size in ('tiny.en', 'base.en'):
                if (MODELS / f'whisper-{size}' / 'model.bin').exists():
                    from faster_whisper import WhisperModel
                    # More threads: ~0.5 s instead of ~1.2 s per check, since Whisper always encodes a 30 s window.
                    _spotter['model'] = WhisperModel(str(MODELS / f'whisper-{size}'), device='cpu', compute_type='int8',
                                                     cpu_threads=max(2, min(8, (os.cpu_count() or 4) // 2)))
                    break
    return _spotter['model'] or whisper()


def spot_wake(audio) -> bool:
    """Fast check of the first moments of speech: does it start with "hey block"?"""
    audio = normalize(audio - audio.mean())
    segments, _ = spotter().transcribe(audio, language='en', beam_size=1, vad_filter=False, condition_on_previous_text=False,
                                       without_timestamps=True, initial_prompt='Hey Block.')
    return wake(' '.join(segment.text.strip() for segment in segments))[0]


def transcribe(audio) -> str:
    audio = audio - audio.mean()
    if not has_speech(audio):
        return ''
    audio = normalize(audio)
    # Beam search 5 without the VAD trim: 0% word errors on accented test commands
    # versus mangled names with greedy decoding, at the same speed on this CPU.
    segments, _ = whisper().transcribe(audio, language='en', beam_size=5, vad_filter=False,
                                       initial_prompt=vocabulary(), condition_on_previous_text=False)
    text = ' '.join(segment.text.strip() for segment in segments).strip()
    # Whisper's well-known inventions on silence or room noise.
    if re.fullmatch(r"(?:thanks? (?:you )?for watching|thank you|you|bye|please subscribe|subtitles by .*|\.+)[.!]?", text, re.I):
        return ''
    return '' if echoes_prompt(text) else text


def echoes_prompt(text: str) -> bool:
    """True when a transcript is just the hint prompt recited back (Whisper does this on unclear audio)."""
    said = re.findall(r"[a-z']+", text.lower())
    prompt = set(re.findall(r"[a-z']+", (vocabulary() + ' ' + HINGLISH_HINTS + ' ' +
                                        'YouTube pe gaane chalao, awaaz badhao, kitne baje hain, folder kholo, screenshot lo, neeche scroll karo').lower()))
    content = [w for w in said if w not in ('hey', 'block', 'blok', 'a', 'the', 'and', 'ok', 'okay')]
    # Recitals come out as comma-separated lists of hint words; real commands rarely do.
    return len(content) >= 4 and text.count(',') >= 2 and sum(w in prompt for w in content) / len(content) >= 0.8


def warm_up():
    def run():
        try:
            import numpy
            transcribe(numpy.zeros(16000, dtype='float32'))
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


def microphone() -> list[str]:
    """pw-record arguments that pick the microphone explicitly.

    PipeWire's automatic routing can connect to a different (sometimes silent)
    input than the one your sound settings call the default, so BLoK asks for
    the default source by name. BLOK_MIC overrides it with a node name.
    """
    name = os.environ.get('BLOK_MIC', '').strip()
    if not name:
        try:
            info = subprocess.run(['wpctl', 'inspect', '@DEFAULT_AUDIO_SOURCE@'], capture_output=True, text=True, timeout=3).stdout
            found = re.search(r'node\.name = "([^"]+)"', info)
            name = found[1] if found else ''
        except (OSError, subprocess.SubprocessError):
            name = ''
    return ['--target', name] if name else []


def record_command(destination: str = '-') -> list[str]:
    recorder = shutil.which('pw-record')
    if not recorder:
        raise RuntimeError('pw-record (PipeWire) is needed to use the microphone.')
    return [recorder, *microphone(), '--rate', '16000', '--channels', '1', '--format', 's16', destination]


class Endpointer:
    """Frame by frame (30 ms), decides when speech starts and when it has ended.

    It follows the room's noise floor slowly, counts a run of loud frames as the
    start of speech, and a run of quiet frames after that as its end, like a
    phone assistant that stops listening when you pause.
    """
    FRAME_SECONDS = 0.03

    def __init__(self, end_seconds: float = 0.7):
        self.floor = 0.002
        self.level = 0.0
        self.end_frames = max(1, round(end_seconds / self.FRAME_SECONDS))
        self.reset()

    def reset(self):
        self.speaking, self.voiced, self.silent = False, 0, 0

    def feed(self, frame) -> str:
        """'start' when speech begins, 'end' when it has ended, '' otherwise."""
        import numpy
        self.level = float(numpy.sqrt((frame ** 2).mean()))
        loud = self.level > max(self.floor * 3, 0.004)
        if not loud:
            self.floor = self.floor * 0.995 + self.level * 0.005
        if not self.speaking:
            self.voiced = self.voiced + 1 if loud else 0
            if self.voiced >= 3:
                self.speaking, self.silent = True, 0
                return 'start'
            return ''
        self.silent = 0 if loud else self.silent + 1
        if self.silent >= self.end_frames:
            self.reset()
            return 'end'
        return ''


class WhisperSession:
    """Listen from a tap (or while Ctrl+. is held) and stop by itself when you pause.

    PipeWire streams 16 kHz audio into memory; the endpointer ends the recording
    about a second after you stop talking, gives up if nothing is said, and a
    manual stop still works. Nothing is written to disk.
    """
    FRAME = 480
    MAX_SECONDS = 60
    NO_SPEECH_SECONDS = 7.0
    TAIL_SECONDS = 0.3

    def __init__(self, on_level=None):
        self.lock = threading.RLock()
        self.process = None
        self.frames = []
        self.stopped = threading.Event()
        self.reader_done = threading.Event()
        self.cancelled = False
        self.heard_speech = False
        self.auto_stopped = False
        self.tail_until = 0.0
        self.on_level = on_level
        self.end_silence = float(os.environ.get('BLOK_END_SILENCE', '1.0'))
        try:
            self.model = 'Whisper ' + Path(whisper_model_path()).name.removeprefix('whisper-')
        except RuntimeError:
            self.model = 'Whisper'
        self.command = record_command()

    def start(self):
        self.started = time.monotonic()
        self.process = subprocess.Popen(self.command,
                                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(.1)
        if self.process.poll() is not None:
            error = self.process.stderr.read().decode(errors='replace').strip()[:200]
            raise RuntimeError('The microphone could not start: ' + (error or 'pw-record exited'))
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        import numpy
        endpointer = Endpointer(self.end_silence)
        try:
            while True:
                chunk = self.process.stdout.read(self.FRAME * 2)
                if len(chunk) < self.FRAME * 2:
                    break
                frame = numpy.frombuffer(chunk, dtype='<i2').astype('float32') / 32768.0
                self.frames.append(frame)
                event = endpointer.feed(frame)
                now = time.monotonic()
                if self.on_level and len(self.frames) % 3 == 0:   # about 11 updates a second
                    self.on_level(min(1.0, endpointer.level * 8))
                if event == 'start':
                    self.heard_speech = True
                if self.stopped.is_set():
                    if now >= self.tail_until:   # a manual stop keeps a short tail
                        break
                    continue
                if event == 'end' and self.heard_speech:
                    self.auto_stopped = True     # you paused: that's the end of the command
                    self.stopped.set()
                    break
                if (not self.heard_speech and now - self.started > self.NO_SPEECH_SECONDS) or now - self.started > self.MAX_SECONDS:
                    self.stopped.set()
                    break
        finally:
            self.reader_done.set()

    def state(self):
        return 'recording' if self.process is not None and not self.stopped.is_set() and self.process.poll() is None else 'idle'

    def finish(self):
        # Releasing Ctrl+. (or tapping the mic) before speaking means "tap to talk":
        # keep listening and stop on the pause. After speech, it stops now, with a
        # short tail so a word cut mid-syllable isn't lost. × cancels either way.
        if not self.heard_speech:
            return
        self.tail_until = time.monotonic() + self.TAIL_SECONDS
        self.stopped.set()

    def cancel(self):
        with self.lock:
            self.cancelled = True
            self._kill()
            self.stopped.set()

    def _kill(self):
        if self.process and self.process.poll() is None:
            self.process.kill()
            self.process.wait()

    def wait(self, alive, on_busy):
        """Block until you pause (or stop), then return the transcript; None if cancelled."""
        while not self.stopped.wait(.1):
            if not alive():
                return None
            if self.process.poll() is not None:
                break  # recorder died (device unplugged): transcribe what we have
        if self.cancelled or not alive():
            return None
        self.reader_done.wait(timeout=self.TAIL_SECONDS + 1)
        with self.lock:
            if self.cancelled:
                return None
            self._kill()
        if not self.heard_speech:
            return ''
        on_busy()
        import numpy
        audio = numpy.concatenate(self.frames) if self.frames else numpy.zeros(0, dtype='float32')
        if os.environ.get('BLOK_KEEP_AUDIO') == '1':
            import soundfile
            soundfile.write(str(Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp')) / 'blok-last.wav'), audio, 16000)
        if len(audio) < 16000 * 0.3:
            return ''
        return transcribe(audio)

    def close(self):
        with self.lock:
            self._kill()


def new_session(on_level=None):
    return VoxtypeSession() if os.environ.get('BLOK_STT') == 'voxtype' else WhisperSession(on_level=on_level)


# Whisper's spellings of "BLoK"; the bare name must open the utterance.
WAKE = re.compile(r"^\W*(?:(?:hey|hi|okay|ok|yo)[\s,]+(?:block|blok|bloc|blog|bloke|black|blocks)|block|blok)\b[\s,.!?]*", re.I)
GREETINGS = {'hey', 'hi', 'hay', 'he', 'a', 'ok', 'okay', 'yo', 'hello', 'hei', 'heyy', 'oye', 'arey', 'are'}
NAMES = {'block', 'blok', 'bloc', 'blog', 'bloke', 'blocks', 'blox', 'blokk', 'bloch', 'blogg'}
NEAR_NAMES = NAMES | {'black', 'brock', 'glock', 'plock', 'flock', 'clock', 'blake', 'blob', 'bloque', 'block.'}


def clean_command(rest: str) -> str:
    """What follows the name, minus repeated "hey block"s; '' if nothing real is left."""
    rest = re.sub(r"\b(?:(?:hey|hi|ok|okay|a|yo)[\s,]+)?(?:block|blok|bloc|blog|bloke|black|brock)\b[\s,.!?]*", ' ', rest, flags=re.I)
    rest = re.sub(r"^(?:\s*(?:ok(?:ay)?|um+|uh+|so|and|yeah|hmm+)[\s,.!?]+)+", '', rest.strip(' ,.!?'), flags=re.I)
    rest = re.sub(r"\s+", ' ', rest).strip(' ,.!?')
    words = re.findall(r"[^\W\d_]{3,}", rest)
    return rest if words else ''


def wake(text: str) -> tuple[bool, str]:
    """Did the utterance address BLoK? Returns (woke, the command after the name).

    Whisper spells the name many ways ("Hey Blok", "hey, bloc", "A block", "Hey black"),
    so after a greeting a near spelling counts; a bare "block" only counts as the very
    first word. With people talking nearby, the name often lands mid-utterance
    ("… it doesn't work. Hey Block, open YouTube"), so the whole utterance is searched
    and only what follows the name is the command.
    """
    from difflib import SequenceMatcher
    words = list(re.finditer(r"[\w']+", text))
    for i, word in enumerate(words):
        token = word.group(0).lower()
        greeted = i > 0 and words[i - 1].group(0).lower() in GREETINGS
        close = token in NEAR_NAMES or SequenceMatcher(None, token, 'block').ratio() >= 0.75
        if (token in NAMES and i == 0) or (greeted and (token in NAMES or close)):
            return True, clean_command(text[word.end():])
    return False, text


class HandsFreeListener:
    """Always-on listening for "hey block …", with an 8 s window for follow-ups.

    PipeWire streams 16 kHz audio into memory; an adaptive loudness gate cuts it
    into utterances and only those are transcribed. Nothing is written to disk,
    and audio that doesn't address BLoK is dropped immediately.
    """
    FRAME = 480                 # 30 ms
    FOLLOW_UP_SECONDS = 20.0    # after BLoK has finished acting and talking

    def __init__(self, on_command, on_wake=None, paused=lambda: False):
        self.on_command = on_command
        self.on_wake = on_wake or (lambda early=False: None)
        self.addressed = False
        self.paused = paused
        self.process = None
        self.thread = None
        self.running = False
        self.follow_until = 0.0
        import queue
        self.queue = queue.Queue()
        # What hands-free heard lately, in memory only, for "blok heard".
        import collections
        self.heard = collections.deque(maxlen=12)

    def start(self):
        command = record_command()
        self.running = True
        self.process = subprocess.Popen(command,
                                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self):
        while self.running:
            item = self.queue.get()
            if item is None:
                return
            audio, addressed = item
            try:
                self.handle(audio, addressed)
            except Exception:
                pass

    def stop(self):
        self.running = False
        self.queue.put(None)
        if self.process and self.process.poll() is None:
            self.process.kill()
            self.process.wait()

    def _loop(self):
        import collections
        import numpy
        pre_roll = collections.deque(maxlen=10)          # 300 ms before speech starts
        endpointer, segment = Endpointer(0.7), None
        while self.running:
            chunk = self.process.stdout.read(self.FRAME * 2)
            if len(chunk) < self.FRAME * 2:
                break
            frame = numpy.frombuffer(chunk, dtype='<i2').astype('float32') / 32768.0
            event = endpointer.feed(frame)
            if self.paused():
                # BLoK is talking (or a tap recording owns the mic): drop what the mic hears, so its
                # own voice never sticks to the front of your next command.
                segment = None
                pre_roll.clear()
                endpointer.reset()
                continue
            if segment is None:
                pre_roll.append(frame)
                if event == 'start':
                    segment = list(pre_roll)
                continue
            segment.append(frame)
            if len(segment) == 35:   # ~1 s in (with pre-roll): is this "hey block"?
                self._spot(numpy.concatenate(segment))
            if event == 'end' or len(segment) >= 400:  # 0.7 s pause, or 12 s at most
                audio = numpy.concatenate(segment)
                segment = None
                pre_roll.clear()
                endpointer.reset()
                # Transcribe on another thread: the mic pipe holds ~2 s, and a command said right
                # after "hey block" must not be lost while Whisper works on the name.
                self.queue.put((audio, self.addressed))
                self.addressed = False

    def _spot(self, audio):
        """React to the name while you're still talking: the overlay opens right away."""
        def run():
            try:
                if spot_wake(audio):
                    self.addressed = True
                    self.on_wake(early=True)
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()

    def handle(self, audio, addressed=None):
        text = transcribe(audio)
        if not text:
            return
        now = time.monotonic()
        woke, command = wake(text)
        if not woke and (self.addressed if addressed is None else addressed):
            # The fast check heard the name even if the full transcript spells it oddly.
            woke, command = True, clean_command(' '.join(text.split()[1:]) if len(text.split()) > 1 else '')
        following = now < self.follow_until
        self.heard.append({'at': time.strftime('%H:%M:%S'), 'text': text, 'acted': woke or following,
                           'command': command if woke else (text if following else '')})
        if woke:
            self.follow_until = 0.0         # reopened once BLoK has answered
            if command:
                self.on_command(command)
            else:
                self.follow_until = now + self.FOLLOW_UP_SECONDS
                self.on_wake(early=False)
        elif following:
            self.follow_until = 0.0
            self.on_command(text.strip(' ,.!?'))

    def listen_for_follow_up(self, seconds: float | None = None):
        """Accept the next command without the name for a while (called once BLoK has answered)."""
        self.follow_until = time.monotonic() + (seconds or self.FOLLOW_UP_SECONDS)
