"""Tests for Ported Simular AI Features:
1. Action Timeline / Live Execution Trace (`timeline_update` stream)
2. Human-in-the-Loop (HITL) Approval Gate
3. Auto-Recording User & Assistant Actions into Reusable Routines
"""
import json
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from hyprash.backend import Backend
from hyprash.commands import Action
from hyprash.plans import Plan, PlanStep
from hyprash.recording import SessionActionRecorder, compile_routine, infer_routine_preconditions
from hyprash.routines import get_routine, list_routines


class SimularFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir)
        (self.data_dir / "routines").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "notes").mkdir(parents=True, exist_ok=True)

        self.backend = Backend()
        self.backend.emit = Mock()
        self.backend.worker_context.generation = self.backend.generation

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # --- 1. Action Timeline / Live Execution Trace ---
    def test_timeline_update_stream_lifecycle(self):
        step1 = PlanStep(
            kind="open",
            value="notes",
            step_id="step_1",
            subtask_id="subtask_1",
            target_domain="desktop:notes",
        )
        step2 = PlanStep(
            kind="open",
            value="terminal",
            step_id="step_2",
            subtask_id="subtask_2",
            target_domain="desktop:terminal",
        )
        plan = Plan((step1, step2))

        self.backend.execute = Mock(return_value=True)
        success = self.backend.execute_plan(plan)
        self.assertTrue(success)

        # Collect timeline_update events
        timeline_events = [
            call.kwargs for call in self.backend.emit.call_args_list
            if call.kwargs.get("type") == "timeline_update"
        ]

        self.assertGreaterEqual(len(timeline_events), 3)

        # First event: status "running", steps pending
        first = timeline_events[0]
        self.assertEqual(first["status"], "running")
        self.assertEqual(len(first["steps"]), 2)
        self.assertEqual(first["steps"][0]["step_id"], "step_1")
        self.assertEqual(first["steps"][0]["status"], "pending")

        # Last event: status "completed", both steps verified
        last = timeline_events[-1]
        self.assertEqual(last["status"], "completed")
        self.assertEqual(last["steps"][0]["status"], "verified")
        self.assertEqual(last["steps"][1]["status"], "verified")
        self.assertIn("duration_ms", last["steps"][0])

    def test_timeline_update_on_failure(self):
        step1 = PlanStep(kind="open", value="notes", step_id="step_1", on_failure="ABORT_ALL")
        step2 = PlanStep(kind="open", value="terminal", step_id="step_2", on_failure="ABORT_ALL")
        plan = Plan((step1, step2))

        self.backend.execute = Mock(return_value=False)
        success = self.backend.execute_plan(plan)
        self.assertFalse(success)

        timeline_events = [
            call.kwargs for call in self.backend.emit.call_args_list
            if call.kwargs.get("type") == "timeline_update"
        ]
        last = timeline_events[-1]
        self.assertEqual(last["status"], "failed")
        self.assertEqual(last["steps"][0]["status"], "failed")

    # --- 2. Human-in-the-Loop (HITL) Approval Gate ---
    def test_hitl_approval_granted_resumes_and_executes(self):
        step1 = PlanStep(
            kind="ui_control",
            value='{"action":"click","target":"Delete database"}',
            step_id="step_1",
            risk_level="SENSITIVE_DESTRUCTIVE",
            requires_approval=True,
            approval_reason="Deleting database requires explicit user confirmation",
        )
        plan = Plan((step1,))

        self.backend.execute = Mock(return_value=True)

        # Simulate user approving in a background thread after approval_request is emitted
        def approve_when_ready():
            for _ in range(50):
                if self.backend.has_pending_approval():
                    self.backend.resolve_latest_approval(approved=True)
                    return
                time.sleep(0.01)

        t = threading.Thread(target=approve_when_ready)
        t.start()

        success = self.backend.execute_plan(plan)
        t.join()

        self.assertTrue(success)
        self.assertEqual(self.backend.execute.call_count, 1)

        # Verify approval_request was emitted
        req_events = [
            c.kwargs for c in self.backend.emit.call_args_list
            if c.kwargs.get("type") == "approval_request"
        ]
        self.assertEqual(len(req_events), 1)
        self.assertEqual(req_events[0]["risk_level"], "SENSITIVE_DESTRUCTIVE")
        self.assertIn("Deleting database", req_events[0]["reason"])

    def test_hitl_approval_rejected_aborts_action(self):
        step1 = PlanStep(
            kind="ui_control",
            value='{"action":"click","target":"Format drive"}',
            step_id="step_1",
            risk_level="SENSITIVE_DESTRUCTIVE",
            requires_approval=True,
            approval_reason="Drive format requires confirmation",
        )
        plan = Plan((step1,))

        self.backend.execute = Mock(return_value=True)

        # Simulate user rejecting
        def reject_when_ready():
            for _ in range(50):
                if self.backend.has_pending_approval():
                    self.backend.resolve_latest_approval(approved=False)
                    return
                time.sleep(0.01)

        t = threading.Thread(target=reject_when_ready)
        t.start()

        success = self.backend.execute_plan(plan)
        t.join()

        self.assertFalse(success)
        self.assertEqual(self.backend.execute.call_count, 0)  # Action was never executed!
        report = self.backend.last_execution_report
        self.assertEqual(report.overall_status, "failed")

    def test_hitl_approval_voice_resolution(self):
        # Verify transcript routing when approval is pending
        approval_id = "test_appr_123"
        self.backend.approval_events[approval_id] = threading.Event()
        self.backend.approval_results[approval_id] = False

        self.assertTrue(self.backend.has_pending_approval())
        self.backend.transcript("yes go ahead", final=True)

        self.assertTrue(self.backend.approval_events[approval_id].is_set())
        self.assertTrue(self.backend.approval_results[approval_id])

    def test_hitl_rejection_voice_resolution(self):
        approval_id = "test_appr_456"
        self.backend.approval_events[approval_id] = threading.Event()
        self.backend.approval_results[approval_id] = False

        self.assertTrue(self.backend.has_pending_approval())
        self.backend.transcript("no cancel that", final=True)

        self.assertTrue(self.backend.approval_events[approval_id].is_set())
        self.assertFalse(self.backend.approval_results[approval_id])

    # --- 3. Routine Auto-Recording & Immediate Execution ---
    def test_infer_routine_preconditions(self):
        steps = [
            Action("web_task", '{"action":"new_tab"}'),
            Action("open", "notes"),
            Action("open", "code"),
        ]
        preconditions = infer_routine_preconditions(steps)
        pre_types = {p.type for p in preconditions}
        self.assertIn("browser", pre_types)
        self.assertIn("notes", pre_types)
        self.assertIn("app", pre_types)

    def test_session_action_recorder_ring_buffer(self):
        recorder = SessionActionRecorder(maxlen=3)
        recorder.record(Action("open", "notes"))
        recorder.record(Action("open", "terminal"))
        recorder.record(Action("open", "code"))
        recorder.record(Action("open", "files"))  # evicts notes

        recent = recorder.get_last_n(3)
        self.assertEqual(len(recent), 3)
        self.assertEqual([a.value for a in recent], ["terminal", "code", "files"])

    def test_compile_routine_and_persist(self):
        steps = [
            Action("open", "notes"),
            Action("write", "standup notes"),
        ]
        routine = compile_routine("daily_standup", steps, data_dir=self.data_dir)
        self.assertEqual(routine.name, "daily_standup")
        self.assertEqual(len(routine.steps), 2)

        # Check it exists on disk and is loadable
        saved = get_routine("daily_standup", data_dir=self.data_dir)
        self.assertIsNotNone(saved)
        self.assertEqual(saved.name, "daily_standup")

    def test_voice_driven_routine_recording_workflow(self):
        with patch("hyprash.backend.DATA", self.data_dir):
            # 1. Start recording
            self.backend.transcript("start recording routine morning_coffee", final=True)
            self.assertEqual(self.backend.recording_routine_name, "morning_coffee")

            # 2. Execute two actions while recording is active
            self.backend.execute = Mock(side_effect=lambda a: self.backend._record_executed_action(a) or True)
            self.backend.execute(Action("open", "notes"))
            self.backend.execute(Action("open", "terminal"))

            self.assertEqual(len(self.backend.recorded_routine_steps), 2)

            # 3. Stop recording
            self.backend.transcript("stop recording routine", final=True)
            self.assertIsNone(self.backend.recording_routine_name)

            # 4. Verify routine was saved
            saved_routines = list_routines(self.data_dir)
            self.assertIn("morning_coffee", saved_routines)
            routine = saved_routines["morning_coffee"]
            self.assertEqual(len(routine.steps), 2)

    def test_save_recent_actions_as_routine(self):
        with patch("hyprash.backend.DATA", self.data_dir):
            # Execute some actions
            self.backend.action_recorder.record(Action("open", "code"), label="Open code")
            self.backend.action_recorder.record(Action("open", "terminal"), label="Open terminal")

            self.backend.transcript("save that as my dev routine", final=True)

            saved_routines = list_routines(self.data_dir)
            self.assertIn("dev", saved_routines)
            routine = saved_routines["dev"]
            self.assertEqual(len(routine.steps), 2)


if __name__ == "__main__":
    unittest.main()
