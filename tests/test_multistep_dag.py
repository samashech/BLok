"""Tests for Multi-Level Subtask DAG and Fault Isolation in Hyprash.

Tests:
1. Dynamic Tab-ID binding and runtime propagation between DAG nodes.
2. Fault isolation: independent subtask execution when predecessor fails under ABORT_DEPENDENT.
3. Strict dependency abortion when predecessor fails under ABORT_ALL or explicit depends_on.
4. DAG decomposition and clause segmentation with domain scope.
5. Risk level assessment (SAFE_READ, SAFE_NAVIGATE, STATE_MUTATING, SENSITIVE_DESTRUCTIVE).
6. Blank tab reuse and continuity.
"""
import json
import unittest
from unittest.mock import Mock

from hyprash.backend import Backend
from hyprash.commands import Action
from hyprash.nlu import ConversationContext
from hyprash.plans import (
    Plan,
    PlanStep,
    assess_step_risk,
    proposals,
    split_compound_utterance,
)


class MultiStepDAGTests(unittest.TestCase):
    def setUp(self):
        self.backend = Backend()
        self.backend.emit = Mock()
        self.backend.worker_context.generation = self.backend.generation
        self.context = ConversationContext()

    def test_assess_step_risk_classification(self):
        # SAFE_READ
        read_step = Action("web_task", json.dumps({"action": "inspect"}))
        self.assertEqual(assess_step_risk(read_step)[0], "SAFE_READ")

        # SAFE_NAVIGATE
        nav_step = Action("url", "https://news.ycombinator.com")
        self.assertEqual(assess_step_risk(nav_step)[0], "SAFE_NAVIGATE")
        tab_step = Action("web_task", json.dumps({"action": "new_tab"}))
        self.assertEqual(assess_step_risk(tab_step)[0], "SAFE_NAVIGATE")

        # STATE_MUTATING
        note_step = Action("write", "meeting notes")
        self.assertEqual(assess_step_risk(note_step)[0], "STATE_MUTATING")
        play_step = Action("web_task", json.dumps({"action": "play", "query": "lofi"}))
        self.assertEqual(assess_step_risk(play_step)[0], "STATE_MUTATING")

        # SENSITIVE_DESTRUCTIVE
        del_step = Action("ui_control", json.dumps({"action": "click", "target": "Delete note"}))
        self.assertEqual(assess_step_risk(del_step)[0], "SENSITIVE_DESTRUCTIVE")
        checkout_step = Action("ui_control", json.dumps({"action": "click", "target": "Checkout and Pay"}))
        self.assertEqual(assess_step_risk(checkout_step)[0], "SENSITIVE_DESTRUCTIVE")

    def test_dag_decomposition_subtask_ids(self):
        chunks = split_compound_utterance("open notes and fire up terminal and search for arch linux")
        self.assertEqual(len(chunks), 3)

        steps = proposals("open notes and search for weather on google", self.context)
        self.assertEqual(len(steps), 2)
        step1 = steps[0][1]
        step2 = steps[1][1]

        self.assertTrue(hasattr(step1, "subtask_id"))
        self.assertTrue(hasattr(step2, "subtask_id"))
        self.assertNotEqual(step1.subtask_id, step2.subtask_id)

    def test_runtime_tab_id_propagation_between_subtasks(self):
        # Step 1 produces tab_id=77, Step 2 consumes target_tab_id from Step 1
        step1 = PlanStep(
            kind="web_task",
            value='{"action":"new_tab"}',
            step_id="step_1",
            subtask_id="subtask_1",
            target_domain="browser:tab",
            output_binding="tab_id",
            on_failure="ABORT_DEPENDENT",
        )
        step2 = PlanStep(
            kind="web_task",
            value='{"action":"search","site":"google","query":"hyprland"}',
            step_id="step_2",
            subtask_id="subtask_2",
            target_domain="browser:google",
            input_bindings={"target_tab_id": "step_1.tab_id"},
            on_failure="ABORT_DEPENDENT",
        )
        plan = Plan((step1, step2))

        executed_actions = []

        def mock_execute(action):
            executed_actions.append(action)
            if action.kind == "web_task" and "new_tab" in action.value:
                self.backend.context.update_tab(tab_id=77, url="chrome://newtab", site="newtab")
            return True

        self.backend.execute = Mock(side_effect=mock_execute)
        success = self.backend.execute_plan(plan)

        self.assertTrue(success)
        self.assertEqual(len(executed_actions), 2)
        # Step 2 must have received target_tab_id=77 injected from Step 1!
        self.assertEqual(getattr(executed_actions[1], "target_tab_id", None), 77)

    def test_fault_isolation_independent_subtasks_proceed(self):
        # Subtask 1 in browser:youtube fails, but Subtask 2 in desktop:notes succeeds
        step1 = PlanStep(
            kind="web_task",
            value='{"action":"play","site":"youtube","query":"song"}',
            step_id="step_1",
            subtask_id="subtask_1",
            target_domain="browser:youtube",
            on_failure="ABORT_DEPENDENT",
        )
        step2 = PlanStep(
            kind="open",
            value="notes",
            step_id="step_2",
            subtask_id="subtask_2",
            target_domain="desktop:notes",
            on_failure="ABORT_DEPENDENT",
        )
        plan = Plan((step1, step2))

        self.backend.execute = Mock(side_effect=[False, True])
        result = self.backend.execute_plan(plan)

        self.assertFalse(result)  # Partial failure overall
        self.assertEqual(self.backend.execute.call_count, 2)
        report = self.backend.last_execution_report
        self.assertIsNotNone(report)
        self.assertEqual(report.failed_steps, [{"step_id": "step_1", "stage": "act"}])
        self.assertEqual(report.completed_steps, ["step_2"])
        self.assertEqual(report.overall_status, "partial_failure")

    def test_fault_isolation_dependent_subtask_is_skipped(self):
        # Step 1 fails; Step 2 depends on step 1 (skipped); Step 3 is independent (executed)
        step1 = PlanStep(
            kind="web_task",
            value='{"action":"new_tab"}',
            step_id="step_1",
            subtask_id="subtask_1",
            target_domain="browser:tab",
            on_failure="ABORT_DEPENDENT",
        )
        step2 = PlanStep(
            kind="web_task",
            value='{"action":"search","site":"google","query":"hyprland"}',
            step_id="step_2",
            subtask_id="subtask_2",
            target_domain="browser:tab",
            depends_on=("step_1",),
            on_failure="ABORT_DEPENDENT",
        )
        step3 = PlanStep(
            kind="open",
            value="notes",
            step_id="step_3",
            subtask_id="subtask_3",
            target_domain="desktop:notes",
            on_failure="ABORT_DEPENDENT",
        )
        plan = Plan((step1, step2, step3))

        self.backend.execute = Mock(side_effect=[False, True])
        result = self.backend.execute_plan(plan)

        self.assertFalse(result)
        self.assertEqual(self.backend.execute.call_count, 2)  # step 1 and step 3 run, step 2 skipped
        report = self.backend.last_execution_report
        self.assertIn("step_2", report.skipped_steps)
        self.assertTrue(any(f["step_id"] == "step_1" for f in report.failed_steps))
        self.assertEqual(report.completed_steps, ["step_3"])

    def test_abort_all_policy_stops_even_independent_steps(self):
        # If on_failure is ABORT_ALL, any failure terminates the plan immediately
        step1 = PlanStep(
            kind="open",
            value="terminal",
            step_id="step_1",
            target_domain="desktop:terminal",
            on_failure="ABORT_ALL",
        )
        step2 = PlanStep(
            kind="open",
            value="notes",
            step_id="step_2",
            target_domain="desktop:notes",
            on_failure="ABORT_ALL",
        )
        plan = Plan((step1, step2))

        self.backend.execute = Mock(side_effect=[False, True])
        result = self.backend.execute_plan(plan)

        self.assertFalse(result)
        self.assertEqual(self.backend.execute.call_count, 1)
        report = self.backend.last_execution_report
        self.assertEqual(report.overall_status, "failed")
        self.assertEqual(report.completed_steps, [])

    def test_blank_tab_reuse_across_clauses(self):
        # When creating a tab then searching in the same compound command,
        # the search step inherits the active tab binding.
        steps = proposals("open a tab and search for rust tutorials on google", self.context)
        self.assertEqual(len(steps), 2)
        step_tab = steps[0][1]
        step_search = steps[1][1]
        self.assertEqual(step_tab.output_binding, "tab_id")
        self.assertIn("target_tab_id", step_search.input_bindings_dict)


if __name__ == "__main__":
    unittest.main()
