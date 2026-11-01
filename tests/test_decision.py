import json
import unittest
from unittest.mock import patch, Mock
from hyprash.decision import LayaDecision, Decision
from hyprash.backend import Backend
from hyprash.commands import Action
from hyprash.plans import Plan

class DecisionTests(unittest.TestCase):
    def engine(self,choice,probabilities):
        agent=Mock()
        agent.predict.return_value={'answers':{'decision':{'choice':choice,'probabilities':probabilities}}}
        return LayaDecision(agent)

    def test_model_rejection_prevents_valid_parsed_command(self):
        model=self.engine('Do nothing',{'Open browser':0.1,'Do nothing':0.9})
        self.assertIsNone(model.decide('open browser').action)
        model.agent.predict.assert_called_once()

    def test_low_score_cannot_execute(self):
        model=self.engine('Open browser',{'Open browser':0.55,'Do nothing':0.45})
        self.assertIsNone(model.decide('open browser').action)

    def test_negation_veto_even_when_model_is_wrong(self):
        model=self.engine('Open browser',{'Open browser':0.99,'No action':0.01})
        self.assertIsNone(model.decide("don't open browser").action)

    def routed(self, answers):
        """Fake Laya answering each question by its first option found in `answers`."""
        agent=Mock()
        def predict(_, request):
            criteria=request['decision']['criteria']
            choice=next((a for a in answers if a in criteria), 'None of these')
            probabilities={k:0.02 for k in criteria}; probabilities[choice]=answers.get(choice,0.9)
            return {'answers':{'decision':{'choice':choice,'probabilities':probabilities}}}
        agent.predict.side_effect=predict
        return LayaDecision(agent)

    def test_natural_language_is_routed_by_model(self):
        model=self.routed({'App windows and workspaces':0.9,'Open an app':0.95})
        self.assertEqual(model.route('I need my terminal').action,Action('open','terminal'))

    def test_two_stage_routing_extracts_file_slots(self):
        model=self.routed({'Files and folders':0.8,'Add text to a file':0.97})
        action=model.route('could you stick buy milk onto my todo list').action
        self.assertIsNone(action)  # "stick" is not an extraction verb: ask, never guess
        action=model.route('put buy milk into my todo file').action
        self.assertEqual(json.loads(action.value),{'tool':'file_append','text':'buy milk','query':'todo'})

    def test_routed_risky_tool_needs_approval_when_unsure(self):
        model=self.routed({'Files and folders':0.8,'Delete a file':0.7})
        action=model.route('get rid of old report').action
        self.assertTrue(action.requires_approval)

    def test_routing_none_of_these_runs_nothing(self):
        model=self.routed({'Web browser and websites':0.6})
        self.assertIsNone(model.route('i like turtles').action)

    def test_unknown_clause_in_plan_goes_to_router(self):
        model=self.routed({'Volume, brightness and system':0.9,'Volume up':0.95,'Open the website www.youtube.com':0.95})
        decision=model.plan('open youtube and make it a bit louder')
        self.assertEqual(json.loads(decision.action.steps[1].value),{'tool':'volume','op':'up'})

    def test_missing_arguments_not_invented(self):
        model=self.engine('Change note title',{'Change note title':0.99,'No action':0.01})
        self.assertIsNone(model.decide('rename it').action)

    def test_truncated_model_input_never_executes(self):
        model=self.engine('Open browser',{'Open browser':0.99,'No action':0.01})
        model.agent.predict.return_value['usage']={'truncated':True}
        with self.assertRaises(ValueError): model.decide('open browser')

class QueueTests(unittest.TestCase):
    def setUp(self):
        self.b=Backend()
        self.b.emit=Mock()
        self.b.submit_decision=Mock()
        self.b.execute=Mock()
        self.b.enqueue_action=Mock()

    def test_stop_bypasses_slow_model_and_invalidates_pending(self):
        self.b.pending=3
        generation=self.b.generation
        self.b.transcript('stop listening',True)
        self.assertGreater(self.b.generation,generation)
        self.assertEqual(self.b.pending,0)
        self.b.submit_decision.assert_not_called()

    def test_multi_clause_is_submitted_as_one_plan(self):
        self.b.transcript('open notes and create a note titled hello',True)
        self.assertEqual([c.args[0] for c in self.b.submit_decision.call_args_list],
                         ['open notes and create a note titled hello'])
        self.b.execute.assert_not_called()

    def test_no_parser_bypass_on_model_failure(self):
        self.b.pending=1
        self.b.finish_decision({'type':'decision_error','message':'model missing'})
        self.b.execute.assert_not_called()
        self.assertEqual(self.b.pending,0)

    def test_model_result_executes_only_accepted_action(self):
        self.b.pending=1
        self.b.finish_decision({'type':'decision','decision':Decision(Action('open','notes'),'open',0.9,123)})
        self.b.enqueue_action.assert_called_once_with(Action('open','notes'))
        self.assertEqual(self.b.pending,0)

    def test_model_result_queues_one_complete_plan(self):
        self.b.pending=1
        plan=Plan((Action('open','notes'),Action('new_note','hello')))
        self.b.finish_decision({'type':'decision','decision':Decision(plan,'plan',0.9,123)})
        self.b.enqueue_action.assert_called_once_with(plan)

    def test_typed_request_stops_concurrent_voice_turn(self):
        self.b.listening=True
        generation=self.b.generation
        self.b.request({'command':'text','text':'open notes'})
        self.assertFalse(self.b.listening)
        self.assertGreater(self.b.generation,generation)

if __name__=='__main__': unittest.main()
