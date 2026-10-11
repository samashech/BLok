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
        self.assertEqual(json.loads(parse('click the search bar')[0].value),dict(action='click',target='Search',role='field'))
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

    def test_reported_compound_requests(self):
        for phrase,action in [
            ('play a justin bieber song','play'),
            ('play a song by adele','play'),
            ('open a new tab','new_tab'),
            ('search for bbs in youtube and play the second video','sequence'),
            ('open github and go to my repositories and find clickyAI and open it','github_repo')]:
            parsed=parse(phrase)
            self.assertEqual(len(parsed),1,phrase)
            self.assertEqual(parsed[0].kind,'web_task')
            self.assertEqual(json.loads(parsed[0].value)['action'],action)
        artist=json.loads(parse('play a justin bieber song')[0].value)
        self.assertEqual((artist['query'],artist['mode']),('justin bieber','artist'))
        steps=json.loads(parse('search for bbs in youtube and play the second video')[0].value)['steps']
        self.assertEqual(steps,[{'action':'search','site':'youtube','query':'bbs'},{'action':'result','index':2,'play':True}])

    def test_obsidian_content_is_not_a_title_or_destination(self):
        action=parse('create a note saying hello in obsidian')[0]
        self.assertEqual(action.kind,'obsidian_note')
        self.assertEqual(json.loads(action.value),{'content':'hello'})
        backend=Backend();backend.emit=Mock()
        with patch('hyprash.desktop.create_obsidian_note',return_value='hello') as create:
            backend.execute(action)
            create.assert_called_once_with('hello')
        self.assertEqual(backend.notes_target,'obsidian')

    def test_negated_compound_request_does_not_execute(self):
        self.assertEqual(parse("don't search for bbs in youtube and play the second video"),[])

    def test_obsidian_uri_uses_percent_encoded_spaces(self):
        from hyprash import desktop
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def launched(args):
                self.assertIn('name=hello%20world',args[1])
                self.assertIn('content=hello%20there',args[1])
                (root/'hello world.md').write_text('hello there')
            with patch.object(desktop,'obsidian_vault',return_value=('vault',root)),patch.object(desktop,'start_app',side_effect=launched):
                self.assertEqual(desktop.new_obsidian_note('hello world','hello there'),'hello world')
