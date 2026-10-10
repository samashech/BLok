import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from hyprash.speech import VoxtypeSession

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
