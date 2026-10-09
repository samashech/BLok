import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from hyprash.commands import parse, StreamPlanner, Action
from hyprash.backend import Backend

class CommandTests(unittest.TestCase):
    def values(self, text, final=True):
        return [(a.kind,a.value) for a in parse(text,final)]

    def test_demo_note_sequence(self):
        self.assertEqual(self.values('can you open up the notes app for me and create a new note and make the title say hello'),
                         [('open','notes'), ('new_note','Untitled'), ('title','hello')])

    def test_search_keeps_full_query(self):
        self.assertEqual(self.values('search for robin williams'), [('url','https://www.google.com/search?q=robin+williams')])
        self.assertEqual(self.values('search for robin', False), [])

    def test_dictation_keeps_command_words_as_content(self):
        self.assertEqual(self.values('write open source software is useful'), [('write','open source software is useful')])
        self.assertEqual(self.values('create a note titled google research'), [('new_note','google research')])

    def test_sites_and_camera(self):
        self.assertEqual(self.values('open up x dot com'), [('url','https://x.com')])
        self.assertEqual(self.values('open photo booth and take a picture of me'), [('open','camera'),('photo','')])

    def test_no_shell_or_negation(self):
        for text in ['open $(touch /tmp/bad)', 'open example.com; touch /tmp/bad', "don't open browser", 'do not take a photo', 'delete all files', 'open browser actually open terminal instead']:
            self.assertEqual(self.values(text), [])

    def test_streaming_no_duplicate(self):
        planner = StreamPlanner()
        self.assertEqual(planner.feed('open browser', False, 0), [])
        self.assertEqual(len(planner.feed('open browser', False, 0.7)), 1)
        self.assertEqual(planner.feed('open browser', False, 1), [])
        self.assertEqual(planner.feed('open browser', True, 2), [])
        self.assertEqual(len(planner.feed('open browser', True, 3)), 1)

    def test_unstable_partial_resets(self):
        planner = StreamPlanner()
        planner.feed('open browser',False,0)
        planner.feed('open',False,0.3)
        self.assertEqual(planner.feed('open browser',False,0.8),[])
        self.assertEqual(len(planner.feed('open browser',False,1.5)),1)

    def test_completed_clause_runs_mid_sentence(self):
        planner=StreamPlanner()
        text='open browser and search for robin'
        planner.feed(text,False,0)
        self.assertEqual([(a.kind,a.value) for a in planner.feed(text,False,0.7)], [('open','browser')])
        self.assertEqual([(a.kind,a.value) for a in planner.feed(text+' williams',True,1)], [('url','https://www.google.com/search?q=robin+williams')])

    def test_note_title_and_workspace(self):
        self.assertEqual(self.values('create a note titled hello'), [('new_note','hello')])
        self.assertEqual(self.values('switch to workspace three'), [('workspace','3')])
        self.assertEqual(self.values('switch to workspace 99'), [])

class BackendTests(unittest.TestCase):
    def setUp(self):
        self.backend=Backend()
        self.events=[]
        self.backend.emit=lambda **e:self.events.append(e)
        self.temp=tempfile.TemporaryDirectory()
        self.data=patch('hyprash.backend.DATA',Path(self.temp.name))
        self.data.start()

    def tearDown(self):
        self.data.stop()
        self.temp.cleanup()

    def test_notes_survive_restart_and_titles_are_not_paths(self):
        self.backend.execute(Action('new_note','../../hello'))
        self.backend.execute(Action('write','a real local note'))
        note_id=self.backend.note['id']
        other=Backend()
        other.ensure_note()
        self.assertEqual(other.note['body'],'a real local note')
        self.assertEqual(other.note['id'],note_id)
        self.assertEqual(len(list(Path(self.temp.name).glob('notes/*.json'))),1)

    def test_launch_uses_argument_list_and_reports_failure(self):
        with patch.object(self.backend,'run_command',side_effect=RuntimeError('launch failed')) as run:
            self.backend.execute(Action('url','https://google.com/search?q=hello'))
        run.assert_called_once_with(['xdg-open','https://google.com/search?q=hello'])
        self.assertTrue(self.events[-1]['error'])

    def test_stale_editor_save_cannot_overwrite_new_note(self):
        self.backend.execute(Action('new_note','first'))
        first=self.backend.note['id']
        self.backend.execute(Action('new_note','second'))
        self.backend.request(dict(command='save_note',id=first,title='stale',body='stale'))
        self.assertEqual(self.backend.note['title'],'second')

if __name__=='__main__': unittest.main()
