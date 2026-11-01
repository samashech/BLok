import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from blok import plugins, themes
from blok.backend import Backend
from blok.nlu import resolve_intent


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        patcher = patch.object(plugins, 'SEARCH', [self.folder])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.temp.cleanup)
        plugins._state['signature'] = None

    def test_toml_command_with_quoted_slot(self):
        (self.folder / 'echo.toml').write_text('description = "Say something"\nphrases = ["say {words} [please]"]\n'
                                               'run = "printf %s {words}"\nreply = "Said {words}"\n')
        intent = resolve_intent('hey could you say hello; rm -rf ~ please')
        task = json.loads(intent.action_value)
        self.assertEqual((task['tool'], task['name'], task['args']), ('plugin', 'echo', {'words': 'hello; rm -rf ~'}))
        with patch('blok.plugins.subprocess.run', return_value=Mock(returncode=0)) as run:
            self.assertEqual(plugins.run(plugins.commands()['echo'], task['args']), 'Said hello; rm -rf ~')
        self.assertEqual(run.call_args[0][0], ['bash', '-c', "printf %s 'hello; rm -rf ~'"])

    def test_python_command_and_live_reload(self):
        self.assertIsNone(plugins.match('roll a 20 sided dice'))
        (self.folder / 'dice.py').write_text('from blok.plugins import command\n'
                                             '@command("Roll a dice", phrases=["roll a dice", "roll a {sides} sided dice"])\n'
                                             'def roll(sides="6"):\n    return "rolled d" + sides\n')
        item, args = plugins.match('roll a 20 sided dice')
        self.assertEqual(plugins.run(item, args), 'rolled d20')

    def test_broken_plugin_is_reported_not_fatal(self):
        (self.folder / 'bad.toml').write_text('description = "x"\n')
        (self.folder / 'ok.toml').write_text('description = "Ok"\nphrases = ["ok go"]\nrun = "true"\n')
        self.assertIn('ok', plugins.commands())
        self.assertTrue(any('bad.toml' in e for e in plugins.errors()))

    def test_confirm_flag_shows_approval(self):
        (self.folder / 'off.toml').write_text('description = "Power off"\nphrases = ["power off"]\nrun = "true"\nconfirm = true\n')
        backend = Backend(); backend.emit = Mock(); backend.request_approval = Mock(return_value=False)
        with self.assertRaises(RuntimeError):
            backend.run_tool({'tool': 'plugin', 'name': 'off', 'args': {}})
        backend.request_approval.assert_called_once()

    def test_commands_join_laya_routing(self):
        (self.folder / 'shot.toml').write_text('description = "Take a screenshot"\nphrases = ["take a screenshot"]\nrun = "true"\n')
        from blok import router
        def distribution(text, options, question):
            pick = router.PLUGIN_AREA if router.PLUGIN_AREA in options else 'Take a screenshot'
            return {o: (0.9 if o == pick else 0.01) for o in options}
        result = router.route("capture what's on my display", distribution)
        self.assertEqual(json.loads(result.action.value), {'tool': 'plugin', 'name': 'shot', 'args': {}})


class ThemePackTests(unittest.TestCase):
    def test_user_pack_is_added_and_resolves_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            user = Path(folder) / 'themes' / 'neon'
            user.mkdir(parents=True)
            (user / 'theme.json').write_text(json.dumps({**json.loads((themes.ROOT / 'themes/liquid/theme.json').read_text()),
                                                         'id': 'neon', 'name': 'Neon', 'badge': 'star.svg', 'ring': 'arc'}))
            with patch.object(themes, 'SEARCH', (themes.ROOT / 'themes', Path(folder) / 'themes')):
                self.assertIn('neon', themes.available())
                store = themes.ThemeStore(folder)
                store.select('neon')
                theme = store.current()
        self.assertEqual(theme['assetBase'], user.resolve().as_uri() + '/')
        self.assertEqual(theme['badge'], 'star.svg')


if __name__ == '__main__':
    unittest.main()
