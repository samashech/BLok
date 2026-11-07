import json
import threading
import time
import unittest
from unittest.mock import patch, Mock

from blok.backend import Backend
from blok.nlu import ConversationContext, resolve_intent


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.backend = Backend()
        self.backend.live = True
        self.backend.speaker = Mock()
        self.backend.speaker.speaking.return_value = False
        p = patch('builtins.print'); p.start(); self.addCleanup(p.stop)

    def follow_up_event(self, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                return self.backend.events.get(timeout=0.1)
            except Exception:
                continue
        return None

    def test_spoken_answer_leads_to_listening_again(self):
        self.backend.input_source = 'voice'
        self.backend.emit(type='action', message='Opened a new tab')
        self.assertEqual(self.follow_up_event(), (None, {'command': 'follow_up', 'source': 'voice'}))
        with patch.object(Backend, 'listen') as listen:
            self.backend.start_follow_up('voice')
        listen.assert_called_once_with(follow_up=True)

    def test_hands_free_reopens_its_window_after_answering(self):
        self.backend.input_source = 'hands_free'
        self.backend.hands_free = Mock()
        self.backend.start_follow_up('hands_free')
        self.backend.hands_free.listen_for_follow_up.assert_called_once_with()

    def test_waits_for_blok_to_finish_talking(self):
        self.backend.input_source = 'voice'
        talking = [True]
        self.backend.speaker.speaking.side_effect = lambda: talking[0]
        self.backend.schedule_follow_up()
        self.assertIsNone(self.follow_up_event(timeout=0.8))
        talking[0] = False
        self.assertIsNotNone(self.follow_up_event())

    def test_typed_commands_and_goodbyes_end_the_conversation(self):
        self.backend.input_source = 'typed'
        self.backend.emit(type='action', message='Opened a new tab')
        self.assertIsNone(self.follow_up_event(timeout=0.8))
        self.backend.submit_decision = Mock()
        self.backend.transcript('thanks', True, source='voice')
        self.backend.submit_decision.assert_not_called()
        self.assertEqual(self.backend.input_source, 'typed')
        with patch.object(Backend, 'listen') as listen:
            self.backend.start_follow_up('voice')
        listen.assert_not_called()

    def test_quiet_follow_up_ends_without_complaining(self):
        self.backend.voice = Mock(follow_up=True)
        self.backend.events.put((self.backend.generation, {'type': 'speech_text', 'text': ''}))
        self.backend.events.put((None, {'command': 'quit'}))
        with patch.object(Backend, 'start_decisions'), patch('blok.mcp_bridge.Bridge'):
            self.backend.live = False
            with patch('blok.echo.start', return_value=True):   # never a real audio filter in tests
                self.backend.main()
        errors = [c for c in self.backend.speaker.say.call_args_list if "didn't hear" in str(c)]
        self.assertEqual(errors, [])


class PageNavigationTests(unittest.TestCase):
    def on(self, url):
        context = ConversationContext()
        context.update_tab(3, url=url)
        return context

    def test_go_to_clicks_the_pages_own_link(self):
        github = self.on('https://github.com/samashech')
        self.assertEqual(json.loads(resolve_intent('go to my repositories', github).action_value),
                         {'action': 'click', 'target': 'repositories', 'navigate': True})
        self.assertEqual(json.loads(resolve_intent('next page', github).action_value)['target'], 'Next')

    def test_apps_sites_and_blank_tabs_keep_their_meaning(self):
        github = self.on('https://github.com/samashech')
        self.assertEqual(resolve_intent('open spotify', github).action_kind, 'url')
        self.assertEqual(resolve_intent('open a new tab', github).intent_type, 'new_tab')
        self.assertEqual(resolve_intent('open settings', self.on('brave://newtab/')).intent_type, 'unclassified')
        self.assertEqual(resolve_intent('open settings').intent_type, 'unclassified')


if __name__ == '__main__':
    unittest.main()
