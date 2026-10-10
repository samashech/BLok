import unittest
from unittest.mock import patch, Mock
from hyprash.commands import parse
from hyprash.backend import Backend
from hyprash import browser

class BrowserTests(unittest.TestCase):
    def test_browser_sequence(self):
        actions=parse('Go to the address bar and type weather in Delhi and press enter.')
        self.assertEqual([(a.kind,a.value) for a in actions], [('address',''),('browser_type','weather in delhi'),('browser_key','enter')])

    def test_search_aliases(self):
        for text in ['look up weather in Delhi', 'look online for weather in Delhi', 'search for weather in Delhi']:
            self.assertEqual(parse(text)[0].value, 'https://www.google.com/search?q=weather+in+delhi')

    def test_query_keeps_conjunctions(self):
        self.assertEqual(parse("search for rock and roll")[0].value, "https://www.google.com/search?q=rock+and+roll")

    def test_partial_speech_never_executes(self):
        backend=Backend()
        backend.emit=Mock(); backend.submit_decision=Mock()
        backend.transcript('open browser', False)
        backend.submit_decision.assert_not_called()

    def test_browser_focus_is_required_before_typing(self):
        with patch.object(browser,'focus',side_effect=RuntimeError('No browser')), patch.object(browser,'run') as run:
            with self.assertRaises(RuntimeError): browser.control('browser_type','hello')
            run.assert_not_called()

    def test_typed_text_cannot_be_wtype_options(self):
        with patch.object(browser,'focus'), patch.object(browser,'run') as run:
            browser.control('browser_type','-k Return')
            self.assertEqual(run.call_args.args[0][-2:], ['--','-k Return'])

    def test_control_characters_are_rejected(self):
        with patch.object(browser,'focus'), patch.object(browser,'run') as run:
            with self.assertRaises(ValueError): browser.control('browser_type','hello\nworld')
            run.assert_not_called()

    def test_finish_does_not_cancel_transcription(self):
        backend=Backend(); backend.emit=Mock(); backend.voice=Mock();backend.listening=True
        backend.finish_recording()
        backend.voice.finish.assert_called_once()
        backend.voice.cancel.assert_not_called()
        self.assertFalse(backend.listening)
