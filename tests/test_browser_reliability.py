"""Tests for Brave browser state reliability, Tab-ID contract, and extension handshake.

Phase 6 verification for:
1. Version capability handshake (phase6-v1 with graceful fallback to phase1).
2. Explicit tab binding (target_tab_id lifecycle contract across Python and extension).
3. Contextual tab reuse on follow-up commands (no duplicate tabs).
4. Closed tab error handling.
5. Search result context 5-minute TTL and active tab/URL validation.
6. Uncertain state and timeout handling without duplicate mutations.
"""
import json
import time
import unittest
from unittest.mock import Mock, patch

from hyprash.backend import Backend
from hyprash.browser import BrowserTaskError, ping
import hyprash.browser as browser_mod
from hyprash.commands import Action
from hyprash.nlu import ConversationContext, resolve_intent
from hyprash.plans import Plan, PlanStep


class BrowserHandshakeTests(unittest.TestCase):
    def test_version_handshake_phase6(self):
        with patch.object(browser_mod, 'request', return_value={'version': 'phase6-v1', 'message': 'Hyprash extension ready'}):
            status = ping()
            self.assertTrue(status['connected'])
            self.assertEqual(status['version'], 'phase6-v1')

    def test_version_handshake_fallback_phase1(self):
        # Gracefully handle live extension that still reports phase1-observe-act-verify
        with patch.object(browser_mod, 'request', return_value={'version': 'phase1-observe-act-verify', 'message': 'Legacy live session'}):
            status = ping()
            self.assertTrue(status['connected'])
            self.assertEqual(status['version'], 'phase1-observe-act-verify')

    def test_ping_when_disconnected(self):
        with patch.object(browser_mod, 'request', side_effect=RuntimeError('Brave control is disconnected')):
            status = ping()
            self.assertFalse(status['connected'])
            self.assertEqual(status['version'], 'disconnected')


class TabBindingAndLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.backend = Backend()
        self.backend.emit = Mock()
        self.backend.worker_context.generation = self.backend.generation

    def test_new_tab_updates_backend_active_tab_id(self):
        mock_result = {
            'verified': True,
            'tab_id': 77,
            'url': 'chrome://newtab/',
            'status': 'complete',
            'message': 'Opened a new tab',
            'trace': [{'kind': 'act', 'status': 'complete'}]
        }
        with patch.object(browser_mod, 'request', return_value=mock_result):
            msg = self.backend.browser_task({'action': 'new_tab'})
            self.assertEqual(msg, 'Opened a new tab')
            self.assertEqual(self.backend.context.active_tab_id, 77)

    def test_sequential_plan_binds_output_tab_id_to_input(self):
        """In open_tab -> search, the tab created in step 1 is passed to step 2."""
        step1 = PlanStep(
            kind='web_task',
            value=json.dumps({'action': 'new_tab'}),
            step_id='step_1',
            target_domain='browser:tab',
            output_binding='tab_id'
        )
        step2 = PlanStep(
            kind='web_task',
            value=json.dumps({'action': 'search', 'site': 'google', 'query': 'games'}),
            step_id='step_2',
            target_domain='browser:google',
            input_bindings=(('target_tab_id', 'step_1.tab_id'),)
        )
        plan = Plan((step1, step2))

        recorded_tasks = []
        def mock_request(task, on_progress=None):
            recorded_tasks.append(task)
            if task.get('action') == 'new_tab':
                return {'verified': True, 'tab_id': 105, 'url': 'chrome://newtab/', 'message': 'Opened a new tab'}
            return {'verified': True, 'tab_id': task.get('target_tab_id'), 'message': 'Searched games'}

        with patch.object(browser_mod, 'request', side_effect=mock_request):
            success = self.backend.execute_plan(plan)
            self.assertTrue(success)
            self.assertEqual(len(recorded_tasks), 2)
            # Step 2 received step 1's created tab_id: 105
            self.assertEqual(recorded_tasks[1].get('target_tab_id'), 105)

    def test_follow_up_command_targets_created_tab_without_duplicate(self):
        """Command 1 ('open a tab') followed by Command 2 ('search for games') targets tab 88."""
        # Step 1: Open a tab
        with patch.object(browser_mod, 'request', return_value={'verified': True, 'tab_id': 88, 'url': 'chrome://newtab/', 'message': 'Opened a new tab'}):
            self.backend.browser_task({'action': 'new_tab'})
            self.assertEqual(self.backend.context.active_tab_id, 88)

        # Step 2: Follow-up command "search for games" resolves with active_tab_id
        resolved = resolve_intent("search for games", context=self.backend.context)
        task = json.loads(resolved.action_value)
        self.assertEqual(task.get('target_tab_id'), 88)
        self.assertEqual(task.get('query'), 'games')

    def test_closed_tab_rejection_emits_failure_gracefully(self):
        """When targeted tab is closed or invalid, BrowserTaskError is handled cleanly."""
        err = BrowserTaskError('The targeted tab 999 was closed or no longer exists.', trace=[])
        with patch.object(browser_mod, 'request', side_effect=err):
            success = self.backend.execute(Action('web_task', json.dumps({'action': 'search', 'site': 'google', 'query': 'games', 'target_tab_id': 999})))
            self.assertFalse(success)
            # Verify backend emitted execution error
            self.assertTrue(any(call.kwargs.get('type') == 'action' and call.kwargs.get('error') for call in self.backend.emit.call_args_list))


class SearchContextTtlAndValidationTests(unittest.TestCase):
    def setUp(self):
        self.backend = Backend()
        self.backend.emit = Mock()
        self.backend.worker_context.generation = self.backend.generation

    def test_search_context_valid_within_5_minutes(self):
        # Seed search context
        self.backend.browser_context = {
            'tabId': 12,
            'url': 'https://www.google.com/search?q=arch',
            'site': 'google',
            'query': 'arch',
            'created_at': time.monotonic()
        }
        # Tab inspection confirms same tab and URL
        with patch.object(browser_mod, 'request', return_value={'tabId': 12, 'url': 'https://www.google.com/search?q=arch'}):
            ctx = self.backend.require_browser_context()
            self.assertEqual(ctx['tabId'], 12)
            self.assertEqual(ctx['site'], 'google')

    def test_search_context_expires_after_5_minutes(self):
        # Seed search context older than 300 seconds
        self.backend.browser_context = {
            'tabId': 12,
            'url': 'https://www.google.com/search?q=arch',
            'site': 'google',
            'query': 'arch',
            'created_at': time.monotonic() - 301
        }
        with self.assertRaisesRegex(RuntimeError, 'No current search results'):
            self.backend.require_browser_context()
        self.assertIsNone(self.backend.browser_context)

    def test_search_context_invalidated_when_tab_navigates(self):
        # Search was on Google, but user navigated to another site
        self.backend.browser_context = {
            'tabId': 12,
            'url': 'https://www.google.com/search?q=arch',
            'site': 'google',
            'query': 'arch',
            'created_at': time.monotonic()
        }
        with patch.object(browser_mod, 'request', return_value={'tabId': 12, 'url': 'https://archlinux.org'}):
            with self.assertRaisesRegex(RuntimeError, 'no longer current'):
                self.backend.require_browser_context()
            self.assertIsNone(self.backend.browser_context)


class StateContinuityAndRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.backend = Backend()
        self.backend.emit = Mock()
        self.backend.worker_context.generation = self.backend.generation

    def test_blank_tab_reused_without_spawning_duplicate(self):
        """When the current active tab is blank, search navigates inside it instead of spawning a new tab."""
        self.backend.context.update_tab(tab_id=303, url='chrome://newtab/')

        recorded_tasks = []
        def mock_request(task, on_progress=None):
            recorded_tasks.append(task)
            return {'verified': True, 'tab_id': 303, 'message': 'Searched Google for games'}

        with patch.object(browser_mod, 'request', side_effect=mock_request):
            resolved = resolve_intent("search for games", context=self.backend.context)
            self.assertEqual(json.loads(resolved.action_value).get('target_tab_id'), 303)
            self.backend.execute(Action(resolved.action_kind, resolved.action_value))
            self.assertEqual(len(recorded_tasks), 1)
            self.assertEqual(recorded_tasks[0].get('target_tab_id'), 303)

    def test_uncertain_state_does_not_repeat_non_idempotent_actions(self):
        """A timeout or lost ACK in a step marks failure and does not repeat mutations."""
        step1 = PlanStep(
            kind='web_task',
            value=json.dumps({'action': 'play', 'site': 'spotify', 'query': 'baby'}),
            step_id='step_1',
            target_domain='browser:spotify',
            idempotency='NON_IDEMPOTENT',
            on_failure='ABORT_ALL'
        )
        step2 = PlanStep(
            kind='open',
            value='terminal',
            step_id='step_2',
            target_domain='desktop:terminal'
        )
        plan = Plan((step1, step2))

        # First step raises a timeout (lost ACK)
        call_count = [0]
        def mock_exec(act):
            call_count[0] += 1
            return False

        self.backend.execute = Mock(side_effect=mock_exec)
        result = self.backend.execute_plan(plan)
        self.assertFalse(result)
        # Verify non-idempotent action was executed once and halted
        self.assertEqual(call_count[0], 1)
        self.assertEqual(self.backend.last_execution_report.overall_status, 'failed')
        self.assertEqual(self.backend.last_execution_report.failed_steps, [{'step_id': 'step_1', 'stage': 'act'}])


if __name__ == '__main__':
    unittest.main()
