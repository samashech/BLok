import unittest
from unittest.mock import Mock

from hyprash.backend import Backend
from hyprash.commands import Action
from hyprash.decision import LayaDecision
from hyprash.plans import Plan, proposals


class ProposalTests(unittest.TestCase):
    def test_mixed_desktop_plan_has_ordered_steps(self):
        steps = proposals('open notes and create a note saying hello in obsidian')
        self.assertEqual([action.kind for _, action in steps], ['open', 'obsidian_note'])

    def test_browser_workflow_remains_one_tab_owned_step(self):
        steps = proposals('search for bbs in youtube and play the second video')
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0][1].kind, 'web_task')

    def test_unsupported_middle_clause_rejects_entire_plan(self):
        with self.assertRaisesRegex(ValueError, 'Nothing was run'):
            proposals('open notes and delete all files and open browser')

    def test_unsupported_single_request_never_uses_natural_language_fallback(self):
        with self.assertRaisesRegex(ValueError, 'Nothing was run'):
            proposals('delete all files')

    def test_quoted_content_keeps_and_as_data(self):
        steps = proposals('create a note saying "delete all files and move on" in obsidian')
        self.assertEqual(steps[0][1].value, '{"content": "delete all files and move on"}')

    def test_bounded_model_accepts_every_plan_step(self):
        agent = Mock()
        def predict(_, request):
            criteria = request['decision']['criteria']
            choice = next(label for label in criteria if label not in ('Do nothing', 'No action'))
            return {'answers': {'decision': {'choice': choice,
                    'probabilities': {choice: .95, 'Do nothing': .05}}}}
        agent.predict.side_effect = predict
        decision = LayaDecision(agent).plan('open notes and create a note titled hello')
        self.assertIsInstance(decision.action, Plan)
        self.assertEqual(decision.action.steps, (Action('open', 'notes'), Action('new_note', 'hello')))


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.backend = Backend()
        self.backend.emit = Mock()
        self.backend.worker_context.generation = self.backend.generation

    def test_failure_stops_later_steps(self):
        self.backend.execute = Mock(side_effect=[False, True])
        plan = Plan((Action('open', 'notes'), Action('open', 'browser')))
        self.assertFalse(self.backend.execute_plan(plan))
        self.backend.execute.assert_called_once_with(Action('open', 'notes'))
        self.assertTrue(any(call.kwargs.get('error') and 'later steps' in call.kwargs.get('message', '')
                            for call in self.backend.emit.call_args_list))

    def test_cancellation_stops_later_steps(self):
        def cancel_after_first(_):
            self.backend.generation += 1
            return True
        self.backend.execute = Mock(side_effect=cancel_after_first)
        plan = Plan((Action('open', 'notes'), Action('open', 'browser')))
        self.assertFalse(self.backend.execute_plan(plan))
        self.backend.execute.assert_called_once_with(Action('open', 'notes'))

    def test_invalid_plan_is_rejected_before_model_or_actions(self):
        self.backend.start_decisions = Mock()
        self.backend.transcript('open notes and delete all files and open browser', True)
        self.backend.start_decisions.assert_not_called()
        self.assertTrue(any(call.kwargs.get('error') and 'Nothing was run' in call.kwargs.get('message', '')
                            for call in self.backend.emit.call_args_list))


if __name__ == '__main__':
    unittest.main()
