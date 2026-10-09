import unittest
from unittest.mock import patch, Mock
from hyprash.decision import LayaDecision, Decision
from hyprash.backend import Backend
from hyprash.commands import Action

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

    def test_natural_language_is_routed_by_model(self):
        model=self.engine('Open terminal',{'Open terminal':0.98,'No action':0.02})
        self.assertEqual(model.decide('I need my terminal').action,Action('open','terminal'))

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

    def test_stop_bypasses_slow_model_and_invalidates_pending(self):
        self.b.pending=3
        generation=self.b.generation
        self.b.transcript('stop listening',True)
        self.assertGreater(self.b.generation,generation)
        self.assertEqual(self.b.pending,0)
        self.b.submit_decision.assert_not_called()

    def test_multi_clause_passes_each_literal_clause_to_model(self):
        self.b.transcript('open notes and create a note titled hello',True)
        self.assertEqual([c.args[0] for c in self.b.submit_decision.call_args_list],
                         ['open notes','create a note titled hello'])
        self.b.execute.assert_not_called()

    def test_no_parser_bypass_on_model_failure(self):
        self.b.pending=1
        self.b.finish_decision({'type':'decision_error','message':'model missing'})
        self.b.execute.assert_not_called()
        self.assertEqual(self.b.pending,0)

    def test_model_result_executes_only_accepted_action(self):
        self.b.pending=1
        self.b.finish_decision({'type':'decision','decision':Decision(Action('open','notes'),'open',0.9,123)})
        self.b.execute.assert_called_once_with(Action('open','notes'))
        self.assertEqual(self.b.pending,0)

    def test_typed_request_stops_concurrent_voice_turn(self):
        self.b.listening=True
        generation=self.b.generation
        self.b.request({'command':'text','text':'open notes'})
        self.assertFalse(self.b.listening)
        self.assertGreater(self.b.generation,generation)

if __name__=='__main__': unittest.main()
