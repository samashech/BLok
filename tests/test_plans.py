import unittest
from unittest.mock import Mock

from hyprash.backend import Backend
from hyprash.commands import Action
from hyprash.decision import LayaDecision
from hyprash.plans import Plan, proposals, PlanStep


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

    def test_dag_abort_dependent_allows_independent_workflow_to_proceed(self):
        step1 = PlanStep(kind='web_task', value='{"action":"play","site":"youtube","query":"despacito"}',
                         step_id='step_1', target_domain='browser:youtube',
                         on_failure='ABORT_DEPENDENT')
        step2 = PlanStep(kind='web_task', value='{"action":"play","site":"spotify","query":"baby"}',
                         step_id='step_2', target_domain='browser:spotify',
                         on_failure='ABORT_DEPENDENT')
        plan = Plan((step1, step2))

        # step 1 fails, step 2 succeeds
        self.backend.execute = Mock(side_effect=[False, True])
        result = self.backend.execute_plan(plan)
        self.assertFalse(result)
        self.assertEqual(self.backend.execute.call_count, 2)
        report = self.backend.last_execution_report
        self.assertIsNotNone(report)
        self.assertEqual(report.failed_steps, [{'step_id': 'step_1', 'stage': 'act'}])
        self.assertEqual(report.completed_steps, ['step_2'])
        self.assertEqual(report.overall_status, 'partial_failure')

    def test_dag_dependent_step_is_skipped_when_predecessor_fails(self):
        step1 = PlanStep(kind='web_task', value='{"action":"new_tab"}',
                         step_id='step_1', target_domain='browser:tab',
                         on_failure='ABORT_DEPENDENT')
        step2 = PlanStep(kind='web_task', value='{"action":"search","site":"google","query":"hyprland"}',
                         step_id='step_2', target_domain='browser:tab',
                         depends_on=('step_1',), on_failure='ABORT_DEPENDENT')
        step3 = PlanStep(kind='open', value='notes',
                         step_id='step_3', target_domain='desktop:notes',
                         on_failure='ABORT_DEPENDENT')
        plan = Plan((step1, step2, step3))

        # step 1 fails; step 2 depends on step 1 (skipped); step 3 is independent (executed)
        self.backend.execute = Mock(side_effect=[False, True])
        result = self.backend.execute_plan(plan)
        self.assertFalse(result)
        self.assertEqual(self.backend.execute.call_count, 2)
        report = self.backend.last_execution_report
        self.assertEqual(report.skipped_steps, ['step_2'])
        self.assertEqual(report.completed_steps, ['step_3'])

    def test_tab_id_binding_propagates_between_steps(self):
        step1 = PlanStep(kind='web_task', value='{"action":"new_tab"}',
                         step_id='step_1', target_domain='browser:tab',
                         output_binding='tab_id')
        step2 = PlanStep(kind='web_task', value='{"action":"search","site":"google","query":"hyprland"}',
                         step_id='step_2', target_domain='browser:google',
                         input_bindings=(('target_tab_id', 'step_1.tab_id'),))
        plan = Plan((step1, step2))

        executed_actions = []
        def mock_exec(act):
            executed_actions.append(act)
            if act.kind == 'web_task' and 'new_tab' in act.value:
                self.backend.context.update_tab(108)
            return True

        self.backend.execute = Mock(side_effect=mock_exec)
        self.assertTrue(self.backend.execute_plan(plan))
        self.assertEqual(len(executed_actions), 2)
        self.assertEqual(executed_actions[1].target_tab_id, 108)


if __name__ == '__main__':
    unittest.main()
