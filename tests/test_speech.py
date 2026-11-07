import json
import os
from pathlib import Path
import tempfile
import unittest
import numpy
from unittest.mock import patch, Mock
from blok.speech import VoxtypeSession

class VoxtypeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        root=Path(self.temp.name)
        (root/'voxtype').mkdir()
        (root/'voxtype/config.toml').write_text('engine="whisper"\n[whisper]\nmodel="base.en"\nmode="local"\n')
        self.env=patch.dict(os.environ,XDG_CONFIG_HOME=str(root),XDG_RUNTIME_DIR=str(root))
        self.env.start()

    def tearDown(self):
        self.env.stop(); self.temp.cleanup()

    def test_existing_f9_recording_is_not_hijacked(self):
        voice=VoxtypeSession(); voice.run=Mock(return_value=json.dumps({'class':'recording'}))
        with self.assertRaises(RuntimeError): voice.start()
        voice.run.assert_called_once_with('status','--format','json','--extended')
        self.assertFalse(voice.owned)

    def test_file_override_is_private_and_cancellation_acknowledged(self):
        voice=VoxtypeSession();voice.run=Mock(return_value=json.dumps({'class':'idle','model':'base.en'}))
        voice.state=Mock(return_value='recording')
        voice.start()
        path=voice.path
        self.assertEqual(path.parent.stat().st_mode & 0o077,0)
        args=voice.run.call_args.args
        self.assertIn('--file='+str(path),args)
        self.assertIn('--no-auto-submit',args)
        voice.state.side_effect=['recording','idle']
        voice.cancel()
        self.assertFalse(voice.owned)
        voice.close()
        self.assertFalse(path.parent.exists())

    def test_unowned_session_never_cancels_normal_dictation(self):
        voice=VoxtypeSession();voice.run=Mock()
        voice.cancel();voice.close()
        voice.run.assert_not_called()


class EchoRemovalTests(unittest.TestCase):
    def setUp(self):
        from blok import echo
        self.assertFalse(echo.active(), 'a test left a real echo filter running')

    def tearDown(self):
        from blok import echo
        echo._process = None

    def running(self):
        from blok import echo
        echo._process = Mock(poll=Mock(return_value=None))

    def test_records_the_filtered_mic_while_it_runs(self):
        from blok import echo, speech
        self.running()
        self.assertEqual(speech.microphone(), ['--target', echo.SOURCE])

    def test_uses_the_plain_mic_when_it_is_not_running(self):
        from blok import echo, speech
        with patch.dict(os.environ, {'BLOK_MIC': 'mic1'}):
            self.assertEqual(speech.microphone(), ['--target', 'mic1'])
            echo._process = Mock(poll=Mock(return_value=1))   # it died: back to the plain mic
            self.assertEqual(speech.microphone(), ['--target', 'mic1'])

    def test_can_be_turned_off_and_never_starts_without_a_mic(self):
        from blok import echo
        with patch('blok.echo.subprocess.Popen') as popen:
            with patch.dict(os.environ, {'BLOK_ECHO_CANCEL': '0'}):
                self.assertFalse(echo.start('mic1'))
            with patch.dict(os.environ, {'BLOK_ECHO_CANCEL': ''}):
                self.assertFalse(echo.start(''))
        popen.assert_not_called()

    def test_gives_up_cleanly_if_the_filter_exits(self):
        from blok import echo
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'XDG_RUNTIME_DIR': folder, 'BLOK_ECHO_CANCEL': ''}), \
             patch('blok.echo.shutil.which', return_value='/usr/bin/x'), \
             patch('blok.echo.subprocess.Popen', return_value=Mock(poll=Mock(return_value=1))), patch('blok.echo.atexit.register'):
            self.assertFalse(echo.start('mic1'))
        self.assertFalse(echo.active())

    def test_config_filters_the_named_mic_and_leaves_defaults_alone(self):
        from blok import echo
        config = echo.CONFIG % ('mic1', echo.SOURCE)
        self.assertIn('target.object = "mic1"', config)
        self.assertIn('monitor.mode = true', config)        # reference only: playback isn't rerouted
        self.assertIn('priority.session = 0', config)       # never becomes the default mic

    def test_soft_voice_only_passes_the_voice_check_with_the_filter_on(self):
        from blok import speech
        audio = numpy.zeros(16000, dtype='float32')
        with patch.object(speech, 'voiced', return_value=True), patch.object(speech, 'whisper') as model:
            model.return_value.transcribe.return_value = ([Mock(text='scroll down')], None)
            self.assertEqual(speech.transcribe(audio), '')
            self.running()
            self.assertEqual(speech.transcribe(audio), 'scroll down')


class VoiceMeterTests(unittest.TestCase):
    def settle(self, meter, level, frames=100):
        for _ in range(frames):
            value = meter(level)
        return value

    def test_a_noisy_room_reads_as_silence(self):
        from blok.speech import LevelMeter
        self.assertEqual(self.settle(LevelMeter(), 0.015), 0.0)

    def test_voice_is_measured_above_the_room(self):
        from blok.speech import LevelMeter
        noisy, quiet = LevelMeter(), LevelMeter()
        self.settle(noisy, 0.015)
        self.settle(quiet, 0.0005)
        self.assertGreater(quiet(0.1), noisy(0.1))           # same voice stands out more in a quiet room
        self.assertGreater(noisy(0.1), 0.25)                 # and still reads as good speech in a noisy one

    def test_silence_does_not_crash_and_talking_is_not_learned_as_noise(self):
        from blok.speech import LevelMeter
        meter = LevelMeter()
        self.settle(meter, 0.0)
        self.settle(meter, 0.015)
        self.assertGreater(self.settle(LevelMeter(), 0.015, 1), -1)
        meter = LevelMeter()
        self.settle(meter, 0.015)
        self.assertGreater(self.settle(meter, 0.1, 150), 0.1)   # ~5 s of talking still shows


class WhisperSessionTests(unittest.TestCase):
    """Tap-to-talk with automatic end-of-speech, on synthetic audio."""

    def setUp(self):
        # These streams use tones for "voice", which Silero rightly rejects: test the shared logic on loudness.
        for patcher in (patch.dict(os.environ, {'BLOK_VAD': 'loudness'}), patch('blok.speech.transcribe', return_value='')):
            patcher.start()
            self.addCleanup(patcher.stop)

    def stream(self, *parts):
        import numpy
        rng = numpy.random.default_rng(0)
        audio = []
        for kind, seconds in parts:
            n = int(16000 * seconds)
            audio.append(numpy.sin(numpy.arange(n) / 6) * 0.2 if kind == 'voice' else rng.standard_normal(n) * 0.001)
        return (numpy.concatenate(audio) * 32767).astype('<i2').tobytes()

    def session(self, data, **kw):
        import io
        from blok.speech import WhisperSession
        with patch('blok.speech.shutil.which', return_value='/usr/bin/pw-record'):
            voice = WhisperSession(**kw)
        voice.process = Mock(stdout=io.BytesIO(data))
        voice.process.poll.return_value = None
        voice.started = __import__('time').monotonic()
        return voice

    def test_stops_by_itself_when_you_pause(self):
        voice = self.session(self.stream(('noise', 0.5), ('voice', 1.0), ('noise', 2.0), ('voice', 1.0)))
        voice._read()
        self.assertTrue(voice.stopped.is_set() and voice.auto_stopped and voice.heard_speech)
        seconds = len(voice.frames) * 0.032
        self.assertAlmostEqual(seconds, 0.5 + 1.0 + 1.0, delta=0.2)   # the later speech isn't included

    def test_gives_up_when_nothing_is_said(self):
        voice = self.session(self.stream(('noise', 3.0)))
        voice.NO_SPEECH_SECONDS = 0.0
        voice._read()
        self.assertTrue(voice.stopped.is_set())
        self.assertFalse(voice.heard_speech)
        with patch('blok.speech.transcribe') as transcribe:
            self.assertEqual(voice.wait(lambda: True, Mock()), '')
        transcribe.assert_not_called()

    def test_a_tap_before_speaking_keeps_listening(self):
        voice = self.session(self.stream(('noise', 0.5), ('voice', 1.0), ('noise', 1.2)))
        voice.finish()                          # Ctrl+. released before saying anything
        self.assertFalse(voice.stopped.is_set())
        voice._read()
        self.assertTrue(voice.auto_stopped and voice.heard_speech)

    def test_manual_stop_keeps_a_short_tail(self):
        voice = self.session(self.stream(('voice', 0.5), ('voice', 2.0)))
        voice.heard_speech = True
        voice.finish()
        voice.tail_until = float('inf')         # read everything that's left
        voice._read()
        self.assertFalse(voice.auto_stopped)
        self.assertAlmostEqual(len(voice.frames) * 0.032, 2.5, delta=0.1)

    def test_transcribes_what_was_heard_and_reports_levels(self):
        levels = []
        voice = self.session(self.stream(('noise', 0.3), ('voice', 1.0), ('noise', 1.2)), on_level=levels.append)
        busy = Mock()
        with patch('blok.speech.transcribe', return_value='open the terminal') as transcribe:
            voice._read()
            self.assertEqual(voice.wait(lambda: True, busy), 'open the terminal')
        busy.assert_called_once()
        self.assertGreater(len(transcribe.call_args[0][0]), 16000)
        self.assertTrue(levels and max(levels) > 0.5)

    def test_cancelled_recording_runs_nothing(self):
        voice = self.session(self.stream(('voice', 1.0), ('noise', 1.2)))
        voice._read()
        voice.cancel()
        with patch('blok.speech.transcribe') as transcribe:
            self.assertIsNone(voice.wait(lambda: True, Mock()))
        transcribe.assert_not_called()

    def test_recorder_streams_16k_mono_to_memory(self):
        from blok.speech import WhisperSession
        with patch('blok.speech.shutil.which', return_value='/usr/bin/pw-record'), \
             patch.dict(os.environ, {'BLOK_MIC': 'mic1'}), \
             patch('blok.speech.subprocess.Popen') as popen, patch('blok.speech.time.sleep'), \
             patch('blok.speech.threading.Thread'):
            popen.return_value.poll.return_value = None
            voice = WhisperSession()
            voice.start()
        self.assertEqual(popen.call_args[0][0],
                         ['/usr/bin/pw-record', '--target', 'mic1', '--rate', '16000', '--channels', '1', '--format', 's16', '-'])

    def test_records_from_the_default_mic_by_name(self):
        # PipeWire's automatic routing picked a silent input; the configured default is asked for by name.
        from blok import speech
        info = Mock(stdout='id 63, type PipeWire:Interface:Node\n  * node.name = "alsa_input.Mic1__source"\n')
        with patch.dict(os.environ, {'BLOK_MIC': ''}), patch('blok.speech.subprocess.run', return_value=info):
            self.assertEqual(speech.microphone(), ['--target', 'alsa_input.Mic1__source'])
        with patch.dict(os.environ, {'BLOK_MIC': 'my.usb.mic'}):
            self.assertEqual(speech.microphone(), ['--target', 'my.usb.mic'])
        with patch.dict(os.environ, {'BLOK_MIC': ''}), patch('blok.speech.subprocess.run', side_effect=OSError):
            self.assertEqual(speech.microphone(), [])

    def test_voxtype_only_when_chosen(self):
        from blok import speech
        with patch.dict(os.environ, {'BLOK_STT': ''}), patch('blok.speech.shutil.which', return_value='/usr/bin/pw-record'):
            self.assertIsInstance(speech.new_session(), speech.WhisperSession)


class WhisperTuningTests(unittest.TestCase):
    def test_loudness_check_separates_voice_from_room_noise(self):
        import numpy
        from blok.speech import has_speech
        rng = numpy.random.default_rng(0)
        noise = (rng.standard_normal(32000) * 0.0015).astype('float32')
        voice = noise.copy()
        voice[8000:20000] += (numpy.sin(numpy.arange(12000) / 8) * 0.05).astype('float32')
        self.assertFalse(has_speech(noise))
        self.assertTrue(has_speech(voice))

    def test_silence_never_reaches_whisper(self):
        import numpy
        from blok import speech
        with patch.object(speech, 'whisper') as model:
            self.assertEqual(speech.transcribe(numpy.zeros(32000, dtype='float32')), '')
        model.assert_not_called()

    def test_personal_words_extend_the_hint(self):
        from blok import speech
        with tempfile.TemporaryDirectory() as folder:
            words = Path(folder) / 'words.txt'
            words.write_text('Arijit Singh\n# comment\nPhantom Blade\n')
            with patch.object(speech, 'WORDS_FILE', words):
                hint = speech.vocabulary()
        self.assertIn('Arijit Singh, Phantom Blade', hint)
        self.assertNotIn('comment', hint)


class PromptEchoTests(unittest.TestCase):
    def test_recited_hints_are_dropped_but_real_commands_kept(self):
        from blok import speech
        self.assertTrue(speech.echoes_prompt('YouTube pe gaane chalao, snapshot lo, neeche scroll karo, screenshot lo, neeche scroll karo'))
        self.assertTrue(speech.echoes_prompt('BLoK, Laya, Omarchy, Hyprland, YouTube, Spotify'))
        self.assertFalse(speech.echoes_prompt('open youtube and search for minecraft speedruns'))
        self.assertFalse(speech.echoes_prompt('YouTube pe Arijit ke gaane chalao'))
        self.assertFalse(speech.echoes_prompt('open spotify'))
