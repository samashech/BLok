import json
import os
from pathlib import Path
import tempfile
import unittest
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


class WhisperSessionTests(unittest.TestCase):
    def wav(self, seconds):
        import numpy, soundfile
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name) / 'speech.wav'
        soundfile.write(str(path), numpy.zeros(int(16000 * seconds), dtype='float32'), 16000)
        return path

    def session(self, path):
        from blok.speech import WhisperSession
        with patch('blok.speech.shutil.which', return_value='/usr/bin/pw-record'):
            voice = WhisperSession()
        voice.path = path
        voice.started = 0
        voice.process = Mock()
        voice.process.poll.return_value = 0
        return voice

    def test_finished_recording_is_transcribed_locally(self):
        voice = self.session(self.wav(1.0))
        voice.stopped.set()
        busy = Mock()
        with patch('blok.speech.transcribe', return_value='open the terminal') as transcribe:
            self.assertEqual(voice.wait(lambda: True, busy), 'open the terminal')
        busy.assert_called_once()
        self.assertEqual(transcribe.call_args[0][0].shape, (16000,))

    def test_too_short_or_cancelled_recording_runs_nothing(self):
        voice = self.session(self.wav(0.1))
        voice.stopped.set()
        with patch('blok.speech.transcribe') as transcribe:
            self.assertEqual(voice.wait(lambda: True, Mock()), '')
            voice.cancelled = True
            self.assertIsNone(voice.wait(lambda: True, Mock()))
        transcribe.assert_not_called()

    def test_recorder_command_is_16k_mono(self):
        from blok.speech import WhisperSession
        with patch('blok.speech.shutil.which', return_value='/usr/bin/pw-record'), \
             patch('blok.speech.subprocess.Popen') as popen, patch('blok.speech.time.sleep'):
            popen.return_value.poll.return_value = None
            voice = WhisperSession()
            voice.start()
        args = popen.call_args[0][0]
        self.assertEqual(args[:7], ['/usr/bin/pw-record', '--rate', '16000', '--channels', '1', '--format', 's16'])
        voice.close()

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
