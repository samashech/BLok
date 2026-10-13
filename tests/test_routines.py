import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from hyprash.backend import Backend
from hyprash.commands import Action, parse
from hyprash.decision import LayaDecision
from hyprash.plans import proposals
from hyprash.routines import (
    BUILTIN_ROUTINES,
    Precondition,
    Routine,
    check_precondition,
    check_routine_preconditions,
    get_routine,
    list_routines,
    save_routine_dict,
    validate_routine_dict,
)
from hyprash.workflows import workflow


class RoutineDefinitionTests(unittest.TestCase):
    def test_validate_valid_routine(self):
        raw = {
            'name': 'quick_check',
            'description': 'Quick system and notes check',
            'preconditions': [{'kind': 'notes'}],
            'steps': [{'kind': 'open', 'value': 'notes'}],
        }
        routine = validate_routine_dict(raw)
        self.assertEqual(routine.name, 'quick_check')
        self.assertEqual(routine.description, 'Quick system and notes check')
        self.assertEqual(len(routine.preconditions), 1)
        self.assertEqual(routine.preconditions[0].kind, 'notes')
        self.assertEqual(len(routine.steps), 1)
        self.assertEqual(routine.steps[0].kind, 'open')

    def test_reject_invalid_name(self):
        for bad_name in ['', 'Bad Name!', 'foo/bar', 'a' * 65]:
            with self.assertRaises(ValueError):
                validate_routine_dict({
                    'name': bad_name,
                    'description': 'desc',
                    'steps': [{'kind': 'open', 'value': 'notes'}],
                })

    def test_reject_empty_or_excessive_steps(self):
        with self.assertRaises(ValueError):
            validate_routine_dict({'name': 'empty', 'description': 'desc', 'steps': []})
        with self.assertRaises(ValueError):
            validate_routine_dict({
                'name': 'too_many',
                'description': 'desc',
                'steps': [{'kind': 'open', 'value': 'notes'}] * 9,
            })

    def test_reject_unsupported_action_kind(self):
        with self.assertRaises(ValueError):
            validate_routine_dict({
                'name': 'bad_kind',
                'description': 'desc',
                'steps': [{'kind': 'shell_exec', 'value': 'ls'}],
            })

    def test_reject_unsafe_content(self):
        with self.assertRaises(ValueError):
            validate_routine_dict({
                'name': 'unsafe',
                'description': 'desc',
                'steps': [{'kind': 'write', 'value': 'delete all records'}],
            })

    def test_reject_unsupported_precondition(self):
        with self.assertRaises(ValueError):
            validate_routine_dict({
                'name': 'bad_precon',
                'description': 'desc',
                'preconditions': [{'kind': 'root_access'}],
                'steps': [{'kind': 'open', 'value': 'notes'}],
            })


class RoutineCatalogTests(unittest.TestCase):
    def test_builtins_present(self):
        routines = list_routines()
        for name in ('morning', 'daily_standup', 'focus', 'code_review'):
            self.assertIn(name, routines)

    def test_aliases_resolve(self):
        self.assertEqual(get_routine('morning routine').name, 'morning')
        self.assertEqual(get_routine('daily standup').name, 'daily_standup')
        self.assertEqual(get_routine('focus session').name, 'focus')
        self.assertEqual(get_routine('code review').name, 'code_review')

    def test_user_routine_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            data = {
                'name': 'custom_work',
                'description': 'Open code and terminal',
                'preconditions': [{'kind': 'app', 'target': 'terminal'}],
                'steps': [
                    {'kind': 'open', 'value': 'code'},
                    {'kind': 'open', 'value': 'terminal'},
                ],
            }
            saved = save_routine_dict(data, tmp_path)
            self.assertEqual(saved.name, 'custom_work')
            loaded = get_routine('custom_work', tmp_path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.description, 'Open code and terminal')
            self.assertEqual(len(loaded.steps), 2)


class PreconditionCheckTests(unittest.TestCase):
    def test_browser_precondition_success(self):
        with patch('hyprash.browser.request', return_value={'message': 'Brave connected'}):
            ok, reason = check_precondition(Precondition('browser'))
            self.assertTrue(ok)
            self.assertEqual(reason, '')

    def test_browser_precondition_failure(self):
        with patch('hyprash.browser.request', return_value={'message': 'Not connected'}):
            ok, reason = check_precondition(Precondition('browser'))
            self.assertFalse(ok)
            self.assertIn('not connected', reason)

    def test_vault_precondition_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch('hyprash.desktop.obsidian_vault', return_value=('vault_id', Path(tmp))):
                ok, reason = check_precondition(Precondition('vault'))
                self.assertTrue(ok)

    def test_vault_precondition_failure(self):
        with patch('hyprash.desktop.obsidian_vault', return_value=None):
            ok, reason = check_precondition(Precondition('vault'))
            self.assertFalse(ok)
            self.assertIn('No configured Obsidian vault', reason)

    def test_app_precondition_success(self):
        with patch('hyprash.desktop.catalog', return_value=['gedit', 'terminal']):
            ok, reason = check_precondition(Precondition('app', 'terminal'))
            self.assertTrue(ok)

    def test_app_precondition_failure(self):
        with patch('hyprash.desktop.catalog', return_value=['gedit']):
            ok, reason = check_precondition(Precondition('app', 'nonexistent_tool'))
            self.assertFalse(ok)
            self.assertIn('not installed', reason)

    def test_routine_preconditions_all_pass(self):
        routine = Routine(
            name='test_pass',
            description='desc',
            preconditions=(Precondition('notes'),),
            steps=(Action('open', 'notes'),),
        )
        ok, reason = check_routine_preconditions(routine)
        self.assertTrue(ok)
        self.assertEqual(reason, '')

    def test_routine_preconditions_one_fails(self):
        routine = Routine(
            name='test_fail',
            description='desc',
            preconditions=(Precondition('notes'), Precondition('vault')),
            steps=(Action('open', 'notes'),),
        )
        with patch('hyprash.desktop.obsidian_vault', return_value=None):
            ok, reason = check_routine_preconditions(routine)
            self.assertFalse(ok)
            self.assertIn('Obsidian vault', reason)


class WorkflowAndPlanTests(unittest.TestCase):
    def test_workflow_matches_routine_phrases(self):
        self.assertEqual(workflow('run morning routine'), ('routine', 'morning'))
        self.assertEqual(workflow('start daily standup'), ('routine', 'daily_standup'))
        self.assertEqual(workflow('run the focus routine'), ('routine', 'focus'))
        self.assertEqual(workflow('run code review routine'), ('routine', 'code_review'))

    def test_parse_routine(self):
        actions = parse('run morning routine')
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, 'routine')
        self.assertEqual(actions[0].value, 'morning')

    def test_proposals_single_routine(self):
        steps = proposals('run morning routine')
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0][1].kind, 'routine')
        self.assertEqual(steps[0][1].value, 'morning')

    def test_proposals_compound_routine(self):
        steps = proposals('run morning routine and then take a picture')
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0][1].kind, 'routine')
        self.assertEqual(steps[0][1].value, 'morning')
        self.assertEqual(steps[1][1].kind, 'photo')

    def test_unknown_routine_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown routine'):
            proposals('run routine mysterious_ghost_action')


class DecisionTests(unittest.TestCase):
    def test_laya_accepts_routine(self):
        agent = Mock()
        def predict(_, req):
            criteria = req['decision']['criteria']
            choice = next(k for k in criteria if k != 'Do nothing')
            return {'answers': {'decision': {'choice': choice, 'probabilities': {choice: 0.95, 'Do nothing': 0.05}}}}
        agent.predict.side_effect = predict

        decision = LayaDecision(agent).decide('run morning routine')
        self.assertIsNotNone(decision.action)
        self.assertEqual(decision.action.kind, 'routine')
        self.assertEqual(decision.action.value, 'morning')

    def test_laya_rejects_routine(self):
        agent = Mock()
        agent.predict.return_value = {
            'answers': {'decision': {'choice': 'Do nothing', 'probabilities': {'Do nothing': 0.95}}}
        }
        decision = LayaDecision(agent).decide('run morning routine')
        self.assertIsNone(decision.action)


class BackendExecutionTests(unittest.TestCase):
    def setUp(self):
        self.backend = Backend()
        self.backend.emit = Mock()
        self.backend.worker_context.generation = self.backend.generation

    def test_precondition_failure_stops_before_any_step(self):
        routine = Routine(
            name='mock_browser_routine',
            description='desc',
            preconditions=(Precondition('browser'),),
            steps=(Action('open', 'notes'), Action('photo', '')),
        )
        with patch('hyprash.routines.get_routine', return_value=routine), \
             patch('hyprash.routines.check_routine_preconditions', return_value=(False, 'Brave is closed')):
            success = self.backend.execute(Action('routine', 'mock_browser_routine'))
            self.assertFalse(success)
            # Precondition failure is emitted as an error action
            self.assertTrue(any(call.kwargs.get('error') and 'Precondition failed' in call.kwargs.get('message', '')
                                for call in self.backend.emit.call_args_list))

    def test_routine_executes_all_steps_sequentially(self):
        executed_steps = []
        def fake_execute(step):
            if step.kind == 'routine':
                return Backend.execute(self.backend, step)
            executed_steps.append(step)
            return True

        self.backend.execute = Mock(side_effect=fake_execute)
        success = self.backend.execute(Action('routine', 'daily_standup'))
        self.assertTrue(success)
        self.assertEqual([s.kind for s in executed_steps], ['open', 'new_note'])
        # Confirms activity messages reported progress for steps
        activity_messages = [call.kwargs.get('message', '') for call in self.backend.emit.call_args_list
                             if call.kwargs.get('type') == 'activity']
        self.assertTrue(any('Step 1 of 2' in msg for msg in activity_messages))
        self.assertTrue(any('Step 2 of 2' in msg for msg in activity_messages))

    def test_step_failure_stops_remaining_steps(self):
        executed_steps = []
        def fake_execute(step):
            if step.kind == 'routine':
                return Backend.execute(self.backend, step)
            executed_steps.append(step)
            return False  # First step fails!

        self.backend.execute = Mock(side_effect=fake_execute)
        success = self.backend.execute(Action('routine', 'daily_standup'))
        self.assertFalse(success)
        self.assertEqual(len(executed_steps), 1)
        self.assertTrue(any(call.kwargs.get('error') and 'stopped at step 1 of 2' in call.kwargs.get('message', '')
                            for call in self.backend.emit.call_args_list))

    def test_cancellation_stops_routine(self):
        executed_steps = []
        def fake_execute(step):
            if step.kind == 'routine':
                return Backend.execute(self.backend, step)
            executed_steps.append(step)
            self.backend.generation += 1  # User cancelled!
            return True

        self.backend.execute = Mock(side_effect=fake_execute)
        success = self.backend.execute(Action('routine', 'daily_standup'))
        self.assertFalse(success)
        self.assertEqual(len(executed_steps), 1)


if __name__ == '__main__':
    unittest.main()
