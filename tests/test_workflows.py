import json
import unittest
from unittest.mock import Mock, patch
from hyprash.commands import parse,Action
from hyprash.backend import Backend

class WorkflowTests(unittest.TestCase):
    def test_destinations_stay_attached_to_queries(self):
        for text,site,query,verb in [
            ('google search games','google','games','search'),
            ('open youtube and search for games','youtube','games','search'),
            ('open youtube.com and search for bbs','youtube','bbs','search'),
            ("open spotify and play god's plan",'spotify',"god's plan",'play'),
            ('search for rock and roll on youtube','youtube','rock and roll','search')]:
            actions=parse(text)
            self.assertEqual(len(actions),1)
            self.assertEqual(actions[0].kind,'web_task')
            self.assertEqual(json.loads(actions[0].value),dict(action=verb,site=site,query=query))
    def test_first_result_is_a_followup(self):
        self.assertEqual(json.loads(parse('open the first link that showed up')[0].value),dict(action='result',index=1))
    def test_named_fields_are_not_address_bar_shortcuts(self):
        self.assertEqual(json.loads(parse('click the search bar')[0].value),dict(action='click',target='Search'))
        self.assertEqual(parse('go to the address bar')[0].kind,'address')
    def test_one_complete_task_reaches_laya(self):
        b=Backend();b.emit=Mock();b.submit_decision=Mock()
        b.transcript('open youtube and search for games',True)
        b.submit_decision.assert_called_once_with('open youtube and search for games')
    def test_cancelled_workflow_never_reaches_browser(self):
        self.assertEqual(parse("don't open spotify and play music"),[])
    def test_builtin_apps_can_be_explicit(self):
        self.assertEqual(parse('open hyprash notes')[0].value,'hyprash_notes')
        self.assertEqual(parse('open hyprash camera')[0].value,'hyprash_camera')
    def test_installed_notes_selected_when_present(self):
        b=Backend();b.emit=Mock()
        with patch('hyprash.desktop.launch',return_value=True):b.execute(Action('open','notes'))
        self.assertEqual(b.notes_target,'obsidian')
    def test_builtin_notes_fallback(self):
        b=Backend();b.emit=Mock();b.publish_note=Mock();b.ensure_note=Mock()
        with patch('hyprash.desktop.launch',return_value=False):b.execute(Action('open','notes'))
        self.assertEqual(b.notes_target,'hyprash');b.publish_note.assert_called_once()
