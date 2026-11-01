import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from hyprash import files, router, system
from hyprash.backend import Backend
from hyprash.nlu import resolve_intent
from hyprash.plans import proposals


class SandboxHome(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name).resolve()
        (self.home / 'Documents').mkdir()
        (self.home / 'Downloads').mkdir()
        (self.home / '.secret').mkdir()
        (self.home / 'Documents' / 'todo.txt').write_text('eggs\n')
        (self.home / 'Downloads' / 'report.pdf').write_bytes(b'%PDF')
        patcher = patch.object(files, 'HOME', self.home)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        dirs = {'home': self.home, 'documents': self.home / 'Documents', 'download': self.home / 'Downloads',
                'downloads': self.home / 'Downloads'}
        dirs_patch = patch.object(files, 'user_dirs', return_value=dirs)
        dirs_patch.start()
        self.addCleanup(dirs_patch.stop)


class FileToolTests(SandboxHome):
    def test_find_and_known_folders(self):
        self.assertEqual(files.find('my downloads folder'), [self.home / 'Downloads'])
        self.assertEqual(files.find('todo'), [self.home / 'Documents' / 'todo.txt'])
        self.assertEqual(files.find('report pdf'), [self.home / 'Downloads' / 'report.pdf'])

    def test_append_keeps_existing_text(self):
        files.append_text(self.home / 'Documents' / 'todo.txt', 'Buy Milk')
        self.assertEqual((self.home / 'Documents' / 'todo.txt').read_text(), 'eggs\nBuy Milk\n')

    def test_append_refuses_binary_and_hidden(self):
        with self.assertRaises(files.FileError):
            files.append_text(self.home / 'Downloads' / 'report.pdf', 'x')
        (self.home / '.secret' / 'a.txt').write_text('')
        with self.assertRaises(files.FileError):
            files.append_text(self.home / '.secret' / 'a.txt', 'x')

    def test_paths_outside_home_are_refused(self):
        with self.assertRaises(files.FileError):
            files.inside_home(Path('/etc/passwd'))
        with self.assertRaises(files.FileError):
            files.inside_home(self.home / '..' / 'escape.txt')

    def test_create_rename_move_copy_never_overwrite(self):
        path = files.create_file('ideas', content='a GPU')
        self.assertEqual(path, self.home / 'Documents' / 'ideas.txt')
        with self.assertRaises(files.FileError):
            files.create_file('ideas')
        files.rename(path, 'plans')
        self.assertTrue((self.home / 'Documents' / 'plans.txt').exists())
        files.move(self.home / 'Documents' / 'plans.txt', self.home / 'Downloads', copy=True)
        self.assertTrue((self.home / 'Downloads' / 'plans.txt').exists())
        with self.assertRaises(files.FileError):
            files.move(self.home / 'Documents' / 'plans.txt', self.home / 'Downloads')

    def test_trash_uses_gio_and_protects_main_folders(self):
        with self.assertRaises(files.FileError):
            files.trash(self.home / 'Documents')
        target = self.home / 'Downloads' / 'report.pdf'
        def fake_trash(args, **_):
            Path(args[2]).unlink()
            return Mock(returncode=0, stderr='')
        with patch('hyprash.files.subprocess.run', side_effect=fake_trash) as run:
            files.trash(target)
        self.assertEqual(run.call_args[0][0][:2], ['gio', 'trash'])


class BackendToolTests(SandboxHome):
    def setUp(self):
        super().setUp()
        self.backend = Backend()
        self.backend.emit = Mock()

    def test_append_through_backend(self):
        message = self.backend.run_tool({'tool': 'file_append', 'text': 'milk', 'query': 'todo'})
        self.assertIn('milk', (self.home / 'Documents' / 'todo.txt').read_text())
        self.assertIn('Added', message)

    def test_rejected_approval_changes_nothing(self):
        self.backend.request_approval = Mock(return_value=False)
        with self.assertRaises(RuntimeError):
            self.backend.run_tool({'tool': 'file_rename', 'query': 'report pdf', 'name': 'old'})
        self.assertTrue((self.home / 'Downloads' / 'report.pdf').exists())
        self.assertIn('report.pdf', self.backend.request_approval.call_args[0][0])

    def test_find_then_open_it(self):
        self.backend.run_tool({'tool': 'file_find', 'query': 'todo'})
        with patch('hyprash.files.subprocess.Popen') as popen:
            self.backend.run_tool({'tool': 'file_pick', 'index': 1})
        self.assertEqual(popen.call_args[0][0], ['xdg-open', str(self.home / 'Documents' / 'todo.txt')])

    def test_ambiguous_match_lists_choices_without_laya(self):
        (self.home / 'Downloads' / 'todo.md').write_text('')
        with self.assertRaises(files.FileError) as raised:
            self.backend.resolve_path('todo')
        self.assertIn('Several match', str(raised.exception))


class RuleTests(unittest.TestCase):
    def tool(self, text):
        intent = resolve_intent(text)
        return json.loads(intent.action_value) if intent.action_kind == 'tool' else (intent.action_kind, intent.action_value)

    def test_desktop_rules(self):
        self.assertEqual(self.tool('turn the volume up'), {'tool': 'volume', 'op': 'up'})
        self.assertEqual(self.tool('set the volume to forty five'), {'tool': 'volume', 'op': 'set', 'level': 45})
        self.assertEqual(self.tool('close this window'), {'tool': 'window', 'op': 'close'})
        self.assertEqual(self.tool('move this window to workspace three'), {'tool': 'window', 'op': 'move', 'workspace': '3'})
        self.assertEqual(self.tool('what time is it'), {'tool': 'answer', 'topic': 'time'})
        self.assertEqual(self.tool('pause the music'), {'tool': 'media', 'op': 'toggle'})

    def test_file_rules_need_file_like_targets(self):
        self.assertEqual(self.tool('open my downloads folder')['tool'], 'file_open')
        self.assertEqual(self.tool('find my resume'), {'tool': 'file_find', 'query': 'resume'})
        self.assertEqual(self.tool('open files'), ('open', 'files'))
        self.assertEqual(self.tool('open youtube'), ('url', 'https://www.youtube.com'))
        self.assertEqual(self.tool('open archlinux.org'), ('url', 'https://archlinux.org'))
        self.assertEqual(json.loads(self.tool('find cats online')[1])['site'], 'google')

    def test_search_youtube_for(self):
        kind, value = self.tool('search youtube for elden ring gameplay')
        self.assertEqual(json.loads(value), {'action': 'search', 'site': 'youtube', 'query': 'elden ring gameplay'})

    def test_download_and_file_verbs_are_no_longer_rejected(self):
        for text in ('download minecraft from the browser', 'rename report.pdf to old.pdf', 'delete old.txt'):
            steps = proposals(text)
            self.assertEqual(steps[0][1].kind, 'tool', text)
        with self.assertRaises(ValueError):
            proposals('shut down the computer')

    def test_unknown_clause_is_left_for_laya(self):
        steps = proposals('open youtube and make it a bit louder')
        self.assertEqual(steps[0][1].kind, 'url')
        self.assertIsNone(steps[1][1])

    def test_case_is_preserved_for_file_text(self):
        self.assertEqual(self.tool('add Buy Milk to my todo file')['text'], 'Buy Milk')


class RouterTests(unittest.TestCase):
    def test_route_picks_best_of_two_areas(self):
        answers = {
            "Which area is the user's request about?": {'Web browser and websites': .46, 'Files and folders': .40},
        }
        def distribution(text, options, question):
            if question in answers:
                return {o: answers[question].get(o, .01) for o in options}
            if 'Open a file or folder' in options:
                return {o: (.9 if o == 'Open a file or folder' else .01) for o in options}
            return {o: (.4 if o == 'Download something' else .1) for o in options}
        result = router.route('open my downloads folder', distribution)
        self.assertEqual(json.loads(result.action.value)['tool'], 'file_open')

    def test_missing_slot_asks_instead_of_guessing(self):
        result = router.route('change the volume', lambda t, options, q: {o: (.9 if o in ('Volume, brightness and system', 'Set the volume to a level') else .01) for o in options})
        self.assertIsNone(result.action)
        self.assertIn('volume level', result.reason)


class SystemTests(unittest.TestCase):
    def test_window_close_uses_lua_dispatcher(self):
        calls = []
        def run(args, timeout=8):
            calls.append(args)
            return json.dumps({'address': '0x1', 'class': 'foot'}) if args[1] == '-j' else 'ok'
        with patch.object(system, 'run', side_effect=run):
            self.assertEqual(system.window('close'), 'Closed foot')
        self.assertEqual(calls[-1], ['hyprctl', 'dispatch', 'hl.dsp.window.close()'])

    def test_answer_battery_without_battery(self):
        with patch('hyprash.system.Path.glob', return_value=[]):
            self.assertIn('No battery', system.answer('battery'))



class VoiceTests(unittest.TestCase):
    def test_spoken_form_is_friendly(self):
        from hyprash.voice import spoken
        self.assertEqual(spoken('Opened ~/Downloads'), 'Opened your Downloads folder')
        self.assertEqual(spoken('Saved note · Hello'), 'Saved note, Hello')
        self.assertEqual(spoken('No installed app named "x".', error=True), 'No installed app named "x".')
        self.assertEqual(spoken('Browser task timed out', error=True), 'Sorry, browser task timed out')

    def test_mode_prefers_elevenlabs_only_with_a_key(self):
        from hyprash import voice
        speaker = voice.Speaker()
        with patch.dict(os.environ, {'ELEVENLABS_API_KEY': ''}), patch.object(voice, 'KEY_FILE', Path('/nonexistent/key')):
            with patch.object(voice, 'kokoro_available', return_value=True):
                self.assertEqual(speaker.mode(), 'kokoro')
            with patch.object(voice, 'kokoro_available', return_value=False):
                self.assertEqual(speaker.mode(), 'local')
        with patch.dict(os.environ, {'ELEVENLABS_API_KEY': 'k'}):
            self.assertEqual(speaker.mode(), 'elevenlabs')
        with patch.dict(os.environ, {'HYPRASH_TTS': '0'}):
            self.assertEqual(speaker.mode(), 'off')

    def test_elevenlabs_failure_falls_back_to_local_voice(self):
        from hyprash import voice
        notices = []
        speaker = voice.Speaker(on_notice=notices.append)
        with patch.object(voice.Speaker, '_elevenlabs', side_effect=RuntimeError('HTTP 401')), \
             patch.object(voice.Speaker, '_local') as local:
            speaker._speak('hello', 'elevenlabs', speaker.generation)
        local.assert_called_once()
        self.assertIn('HTTP 401', notices[0])

    def test_kokoro_failure_falls_back_to_espeak(self):
        from hyprash import voice
        notices = []
        speaker = voice.Speaker(on_notice=notices.append)
        with patch.object(voice.Speaker, '_kokoro', side_effect=RuntimeError('model missing')), \
             patch.object(voice.Speaker, '_local') as local:
            speaker._speak('hello', 'kokoro', speaker.generation)
        local.assert_called_once()
        self.assertIn('Kokoro', notices[0])

    def test_kokoro_plays_synthesised_wav(self):
        from hyprash import voice
        import numpy
        engine = Mock(); engine.create.return_value = (numpy.zeros(2400, dtype='float32'), 24000)
        player = Mock(); player.wait.return_value = 0
        with patch.object(voice, 'kokoro', return_value=engine), \
             patch('hyprash.voice.subprocess.Popen', return_value=player) as popen, \
             patch('hyprash.voice.shutil.which', return_value='/usr/bin/pw-play'):
            speaker = voice.Speaker()
            speaker._kokoro('Opened Spotify', speaker.generation)
        self.assertEqual(engine.create.call_args[0][0], 'Opened Spotify')
        self.assertEqual(popen.call_args[0][0][0], '/usr/bin/pw-play')
        self.assertTrue(popen.call_args[0][0][1].endswith('.wav'))

    def test_elevenlabs_streams_audio_to_player(self):
        from hyprash import voice
        speaker = voice.Speaker()
        response = Mock(); response.read.side_effect = [b'ID3audio', b'']
        response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False)
        player = Mock(); player.poll.return_value = None
        with patch.dict(os.environ, {'ELEVENLABS_API_KEY': 'secret'}), \
             patch('hyprash.voice.urllib.request.urlopen', return_value=response) as urlopen, \
             patch('hyprash.voice.subprocess.Popen', return_value=player), \
             patch('hyprash.voice.shutil.which', return_value='/usr/bin/mpv'):
            speaker._elevenlabs('Opened Spotify', speaker.generation)
        request = urlopen.call_args[0][0]
        self.assertEqual(request.get_header('Xi-api-key'), 'secret')
        self.assertEqual(json.loads(request.data)['text'], 'Opened Spotify')
        player.stdin.write.assert_called_once_with(b'ID3audio')

    def test_backend_speaks_results_but_summarises_plans(self):
        backend = Backend()
        backend.speaker = Mock()
        with patch('builtins.print'):
            backend.emit(type='action', message='Opened ~/Downloads')
        backend.speaker.say.assert_called_once_with('Opened your Downloads folder')


if __name__ == '__main__':
    unittest.main()
