import json
import unittest
from unittest.mock import Mock, patch

from blok import browser, everyday, hinglish, system
from blok.backend import Backend
from blok.nlu import ConversationContext
from blok.plans import proposals


def plan(text, url='https://www.youtube.com/watch?v=x'):
    context = ConversationContext()
    context.update_tab(7, url=url)
    text = hinglish.translate(text) or text
    return [(action.kind, json.loads(action.value) if str(action.value).startswith('{') else action.value) for _, action in proposals(text, context)]


def tool(text, **kw):
    (kind, value), = plan(text, **kw)
    return value


class UnderstandingTests(unittest.TestCase):
    def test_tabs_are_never_opened_by_mistake(self):
        for said, name in (('close this tab', 'close_tab'), ('close the tab', 'close_tab'), ('reopen the closed tab', 'reopen_tab'),
                           ('next tab', 'next_tab'), ('previous tab', 'previous_tab'), ('refresh the page', 'refresh'), ('reload', 'refresh'),
                           ('zoom in', 'zoom_in'), ('zoom out', 'zoom_out'), ('reset zoom', 'zoom_reset'), ('bookmark this page', 'bookmark'),
                           ('tab band karo', 'close_tab'), ('agla tab', 'next_tab'), ('page refresh karo', 'refresh')):
            self.assertEqual(tool(said), {'tool': 'shortcut', 'name': name}, said)
        self.assertEqual(tool('switch to the github tab'), {'tool': 'switch_tab', 'query': 'github'})
        self.assertEqual(plan('naya tab kholo'), [('web_task', {'action': 'new_tab'})])

    def test_editing_keys(self):
        for said, name in (('copy this', 'copy'), ('copy', 'copy'), ('paste', 'paste'), ('cut this', 'cut'), ('undo', 'undo'), ('redo', 'redo'),
                           ('select all', 'select_all'), ('copy karo', 'copy')):
            self.assertEqual(tool(said), {'tool': 'shortcut', 'name': name}, said)

    def test_say_exactly_what_you_mean_no_toggles(self):
        self.assertEqual(tool('mute'), {'tool': 'volume', 'op': 'mute_on'})
        self.assertEqual(tool('unmute'), {'tool': 'volume', 'op': 'mute_off'})
        self.assertEqual(tool('pause'), {'tool': 'media', 'op': 'pause'})
        self.assertEqual(tool('resume'), {'tool': 'media', 'op': 'play'})
        self.assertEqual(tool('skip this song'), {'tool': 'media', 'op': 'next'})
        self.assertEqual(tool('set brightness to 50 percent'), {'tool': 'brightness', 'op': 'set', 'level': 50})

    def test_closing_an_app_by_name_closes_that_app(self):
        self.assertEqual(tool('close brave'), {'tool': 'window', 'op': 'close', 'app': 'brave'})
        self.assertEqual(tool('brave band karo'), {'tool': 'window', 'op': 'close', 'app': 'brave'})
        self.assertEqual(tool('close this window'), {'tool': 'window', 'op': 'close'})
        for said in ('close it', 'close the tab', 'close this tab'):
            self.assertNotIn('app', tool(said), said)

    def test_system(self):
        self.assertEqual(tool('turn on wifi'), {'tool': 'radio', 'radio': 'wifi', 'on': True})
        self.assertEqual(tool('turn off bluetooth'), {'tool': 'radio', 'radio': 'bluetooth', 'on': False})
        self.assertEqual(tool('wifi band karo'), {'tool': 'radio', 'radio': 'wifi', 'on': False})
        self.assertEqual(tool('go to sleep'), {'tool': 'power', 'op': 'suspend'})
        self.assertEqual(tool('shut down'), {'tool': 'power', 'op': 'poweroff'})
        self.assertEqual(tool('restart the computer'), {'tool': 'power', 'op': 'reboot'})
        self.assertEqual(tool('computer band karo'), {'tool': 'power', 'op': 'poweroff'})
        self.assertEqual(tool('screenshot this window'), {'tool': 'screenshot_window'})
        self.assertEqual(tool('minimize this'), {'tool': 'window', 'op': 'minimize'})

    def test_other_risky_verbs_stay_blocked(self):
        for said in ('restart chrome', 'shut down the server', 'format the disk', 'uninstall steam', 'send it'):
            with self.assertRaises(ValueError, msg=said):
                plan(said)

    def test_weather_is_a_search(self):
        self.assertEqual(plan("what's the weather"), [('web_task', {'action': 'search', 'site': 'google', 'query': 'weather'})])
        self.assertEqual(plan('what is the weather in delhi')[0][1]['query'], 'weather in delhi')

    def test_named_site_wins_over_the_tab_you_are_on(self):
        self.assertEqual(plan('play shape of you on spotify')[0][1]['site'], 'spotify')
        self.assertEqual(plan('play lofi')[0][1]['site'], 'youtube')

    def test_notes_text_is_only_what_you_dictate(self):
        self.assertEqual(plan('add milk to my notes'), [('write', 'milk')])

    def test_real_commands_are_left_alone(self):
        self.assertEqual(plan('click sign in')[0][0], 'ui_control')
        self.assertEqual(plan('copy report.txt to documents')[0][1]['tool'], 'file_copy')
        self.assertIsNone(everyday.intent('close the first result'))
        self.assertIsNone(everyday.intent('open the downloads folder'))
        self.assertIsNone(everyday.intent('switch to a new tab'))


class ActionTests(unittest.TestCase):
    def test_shortcut_keys(self):
        with patch.object(system, 'run') as run, patch.object(browser, 'focus') as focus:
            self.assertEqual(system.shortcut('previous_tab'), 'Previous tab')
            focus.assert_called_once()
            self.assertEqual(run.call_args.args[0], ['wtype', '-M', 'ctrl', '-M', 'shift', '-k', 'Tab', '-m', 'shift', '-m', 'ctrl'])
            focus.reset_mock()
            system.shortcut('paste')
            focus.assert_not_called()           # editing keys go to whatever is in front
            self.assertEqual(run.call_args.args[0], ['wtype', '-M', 'ctrl', '-k', 'v', '-m', 'ctrl'])
            system.shortcut('refresh')
            self.assertEqual(run.call_args.args[0], ['wtype', '-k', 'F5'])

    def test_mute_and_unmute_are_explicit(self):
        with patch.object(system, 'run') as run:
            self.assertEqual(system.volume('mute_on'), 'Sound muted')
            self.assertEqual(run.call_args.args[0], ['wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', '1'])
            self.assertEqual(system.volume('mute_off'), 'Sound unmuted')
            self.assertEqual(run.call_args.args[0][-1], '0')

    def test_close_by_name_closes_only_that_apps_windows(self):
        clients = [{'address': '0xa1', 'class': 'brave-browser', 'mapped': True}, {'address': '0xb2', 'class': 'foot', 'mapped': True},
                   {'address': '0xa3', 'class': 'brave-browser', 'mapped': True}]
        with patch.object(system, 'run', return_value=json.dumps(clients)), patch.object(system, 'dispatch') as dispatch:
            self.assertEqual(system.window('close', app='brave'), 'Closed brave-browser (2 windows)')
        self.assertEqual([c.args[0] for c in dispatch.call_args_list],
                         ['hl.dsp.window.close({ window = "address:0xa1" })', 'hl.dsp.window.close({ window = "address:0xa3" })'])
        with patch.object(system, 'run', return_value=json.dumps(clients)), patch.object(system, 'dispatch') as dispatch:
            with self.assertRaisesRegex(RuntimeError, 'No open window'):
                system.window('close', app='spotify')
        dispatch.assert_not_called()

    def test_minimize_explains_itself(self):
        with self.assertRaisesRegex(RuntimeError, 'no minimize'):
            system.window('minimize')

    def test_radio(self):
        with patch.object(system, 'run') as run, patch.object(system.shutil, 'which', return_value='/usr/bin/x'):
            self.assertEqual(system.radio('wifi', False), 'Wi-Fi off')
            self.assertEqual(run.call_args.args[0], ['nmcli', 'radio', 'wifi', 'off'])
            self.assertEqual(system.radio('bluetooth', True), 'Bluetooth on')
            self.assertEqual(run.call_args.args[0], ['bluetoothctl', 'power', 'on'])


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.backend = Backend()
        self.backend.emit = Mock()

    def test_power_always_asks_first(self):
        self.backend.request_approval = Mock(return_value=False)
        with patch.object(system, 'power') as power:
            with self.assertRaisesRegex(RuntimeError, 'Shut down'):
                self.backend.run_tool({'tool': 'power', 'op': 'poweroff'})
        power.assert_not_called()
        self.backend.request_approval = Mock(return_value=True)
        with patch.object(system, 'power', return_value='Shutting down') as power:
            self.assertEqual(self.backend.run_tool({'tool': 'power', 'op': 'poweroff'}), 'Shutting down')
        power.assert_called_once_with('poweroff')

    def test_closing_a_site_by_name_closes_its_tab(self):
        with patch.object(system, 'window', side_effect=RuntimeError('No open window belongs to "youtube".')), \
             patch.object(browser, 'ping', return_value={'version': 'phase15-v1'}), \
             patch.object(browser, 'request', return_value={'message': 'Switched to YouTube', 'tabId': 3}) as request, \
             patch.object(system, 'shortcut') as shortcut:
            self.assertEqual(self.backend.run_tool({'tool': 'window', 'op': 'close', 'app': 'youtube'}), 'Closed the YouTube tab')
        self.assertEqual(request.call_args.args[0], {'action': 'switch_tab', 'query': 'youtube'})
        shortcut.assert_called_once_with('close_tab')

    def test_nothing_by_that_name_closes_nothing(self):
        with patch.object(system, 'window', side_effect=RuntimeError('No open window belongs to "zebra".')), \
             patch.object(browser, 'ping', return_value={'version': 'phase15-v1'}), \
             patch.object(browser, 'request', side_effect=browser.BrowserTaskError('No open tab matches "zebra".')), \
             patch.object(system, 'shortcut') as shortcut:
            with self.assertRaisesRegex(RuntimeError, 'No open window'):
                self.backend.run_tool({'tool': 'window', 'op': 'close', 'app': 'zebra'})
        shortcut.assert_not_called()

    def test_switch_tab_follows_you(self):
        with patch.object(browser, 'ping', return_value={'version': 'phase15-v1'}), \
             patch.object(browser, 'request', return_value={'message': 'Switched to GitHub', 'tabId': 4, 'url': 'https://github.com/'}):
            self.assertEqual(self.backend.run_tool({'tool': 'switch_tab', 'query': 'github'}), 'Switched to GitHub')
        self.assertEqual((self.backend.context.active_tab_id, self.backend.context.active_site), (4, 'github'))


if __name__ == '__main__':
    unittest.main()
