import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from blok import browser, skills
from blok.backend import Backend
from blok.nlu import resolve_intent

RECORDED = [{'op': 'navigate', 'url': 'https://expenses.example.org/new'},
            {'op': 'fill', 'name': 'Amount', 'role': 'textbox', 'value': '450'},
            {'op': 'click', 'name': 'Travel', 'role': 'button'},
            {'op': 'fill', 'name': 'Note', 'role': 'textbox', 'value': 'lunch'},
            {'op': 'click', 'name': 'Submit', 'role': 'button'},
            {'op': 'bogus', 'name': 'x'}, {'op': 'click', 'name': ''}]


class SkillStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        p = patch.object(skills, 'SKILLS', Path(self.temp.name)); p.start(); self.addCleanup(p.stop)

    def test_save_keeps_valid_steps_and_finds_fields(self):
        skill = skills.save('File an expense', RECORDED)
        self.assertEqual(len(skill['steps']), 5)
        self.assertEqual(skill['fields'], [{'name': 'Amount', 'default': '450'}, {'name': 'Note', 'default': 'lunch'}])
        with self.assertRaises(RuntimeError):
            skills.save('Nothing', [RECORDED[0]])

    def test_spoken_values(self):
        skills.save('File an expense', RECORDED)
        skill, values = skills.match('file an expense, amount 900, note team dinner')
        self.assertEqual(values, {'Amount': '900', 'Note': 'team dinner'})
        self.assertEqual(skills.match('run file an expense with amount 120')[1], {'Amount': '120'})
        self.assertEqual(skills.match('file an expense')[1], {})
        self.assertIsNone(skills.match('file a complaint'))
        steps = skills.replay_steps(skill, {'amount': '900'})
        self.assertEqual([s.get('value') for s in steps if s['op'] == 'fill'], ['900', 'lunch'])

    def test_single_field_takes_the_rest(self):
        skills.save('Order chai', [RECORDED[0], {'op': 'fill', 'name': 'Quantity', 'role': 'textbox', 'value': '1'},
                                    {'op': 'click', 'name': 'Buy now', 'role': 'button'}])
        self.assertEqual(skills.match('order chai, 3')[1], {'Quantity': '3'})
        self.assertEqual(skills.risky(skills.all_skills()['order-chai']['steps']), ['Buy now'])

    def test_rules(self):
        skills.save('File an expense', RECORDED)
        self.assertEqual(json.loads(resolve_intent('file an expense, amount 900').action_value),
                         {'tool': 'skill_run', 'name': 'File an expense', 'values': {'Amount': '900'}})
        self.assertEqual(json.loads(resolve_intent('watch me').action_value), {'tool': 'watch', 'on': True})
        self.assertEqual(json.loads(resolve_intent('dekho main kaise karta hun').action_value), {'tool': 'watch', 'on': True})


class SkillFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        p = patch.object(skills, 'SKILLS', Path(self.temp.name)); p.start(); self.addCleanup(p.stop)
        self.backend = Backend()
        self.backend.emit = Mock()
        self.calls = []
        def request(payload, **_):
            self.calls.append(payload)
            return {'watch_start': {'verified': True}, 'watch_stop': {'steps': RECORDED},
                    'replay': {'verified': True, 'message': 'Did all steps'}}[payload['action']]
        for target, kwargs in ((browser, dict(new=Mock(side_effect=request))),):
            p = patch.object(target, 'request', **kwargs); p.start(); self.addCleanup(p.stop)
        p = patch.object(Backend, 'require_extension'); p.start(); self.addCleanup(p.stop)
        p = patch.object(Backend, 'browser_in_front', return_value=True); p.start(); self.addCleanup(p.stop)

    def test_watch_name_and_run(self):
        self.assertIn('Watching', self.backend.run_tool({'tool': 'watch', 'on': True}))
        self.assertTrue(self.backend.context.watching)
        self.assertEqual(resolve_intent("i'm done", self.backend.context).action_value, json.dumps({'tool': 'watch', 'on': False}))
        self.assertIn('4 steps', self.backend.run_tool({'tool': 'watch', 'on': False}))
        self.assertIn('Learned "File an expense"', self.backend.run_tool({'tool': 'skill_save', 'name': 'File an expense'}))
        self.backend.request_approval = Mock(return_value=True)
        self.assertEqual(self.backend.run_tool({'tool': 'skill_run', 'name': 'File an expense', 'values': {'Amount': '900'}}),
                         'Done: File an expense')
        replay = self.calls[-1]
        self.assertEqual([s.get('value') for s in replay['steps'] if s['op'] == 'fill'], ['900', 'lunch'])
        self.backend.request_approval.assert_called_once()   # "Submit" is a risky click

    def test_rejected_risky_skill_never_replays(self):
        skills.save('File an expense', RECORDED)
        self.backend.request_approval = Mock(return_value=False)
        with self.assertRaises(RuntimeError):
            self.backend.run_tool({'tool': 'skill_run', 'name': 'File an expense', 'values': {}})
        self.assertNotIn('replay', [c['action'] for c in self.calls])

    def test_nothing_to_save(self):
        with self.assertRaisesRegex(RuntimeError, 'watch me'):
            self.backend.run_tool({'tool': 'skill_save', 'name': 'x'})


if __name__ == '__main__':
    unittest.main()
