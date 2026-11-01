import json
import unittest
from unittest.mock import patch, Mock

from blok import rephrase
from blok.backend import Backend
from blok.decision import Decision


def ollama_reply(command, question=''):
    response = Mock()
    response.read.return_value = json.dumps({'message': {'content': json.dumps({'command': command, 'question': question})}}).encode()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    return response


class RephraseTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(rephrase, 'model_name', return_value='qwen2.5:3b')
        patcher.start()
        self.addCleanup(patcher.stop)

    def rewrite(self, said, command, question=''):
        with patch('blok.rephrase.urllib.request.urlopen', return_value=ollama_reply(command, question)) as urlopen:
            result = rephrase.rewrite(said)
        self.request = json.loads(urlopen.call_args[0][0].data)
        return result

    def test_grounded_rewrite_is_kept(self):
        result = self.rewrite("dude it's way too loud bring it down", 'turn the volume down')
        self.assertEqual(result.command, 'turn the volume down')
        self.assertEqual(self.request['model'], 'qwen2.5:3b')
        self.assertEqual(self.request['options']['temperature'], 0)

    def test_invented_names_are_rejected(self):
        self.assertIsNone(self.rewrite('open that music thing', 'open spotify'))
        self.assertIsNone(self.rewrite('find my invoice', 'find my tax receipt pdf'))

    def test_close_spoken_names_may_expand(self):
        self.assertEqual(self.rewrite('can you open insta', 'open instagram').command, 'open instagram')

    def test_placeholders_and_vague_targets_are_rejected(self):
        self.assertIsNone(self.rewrite('open this app or something', 'switch to this app'))
        self.assertIsNone(self.rewrite('put it on workspace 3', 'switch to <app>'))

    def test_question_is_kept_when_nothing_to_do(self):
        result = self.rewrite('hmm what was i gonna say', '', 'What would you like me to do?')
        self.assertEqual((result.command, result.question), ('', 'What would you like me to do?'))

    def test_no_model_installed_skips_stage(self):
        with patch.object(rephrase, 'model_name', return_value=None):
            self.assertIsNone(rephrase.rewrite('anything'))


class ModelChoiceTests(unittest.TestCase):
    def tags(self, *names):
        response = Mock(); response.read.return_value = json.dumps({'models': [{'name': n} for n in names]}).encode()
        response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False)
        return response

    def choose(self, *names):
        rephrase._models.update(checked=0.0, name=None)
        with patch('blok.rephrase.urllib.request.urlopen', return_value=self.tags(*names)):
            return rephrase.model_name()

    def test_prefers_installed_qwen_then_gemma_never_vision(self):
        self.assertEqual(self.choose('moondream:latest', 'gemma2:2b', 'qwen2.5:3b'), 'qwen2.5:3b')
        self.assertEqual(self.choose('moondream:latest', 'gemma2:2b'), 'gemma2:2b')
        self.assertIsNone(self.choose('moondream:latest'))


class BackendRephraseTests(unittest.TestCase):
    def setUp(self):
        self.backend = Backend()
        self.backend.emit = Mock()
        self.model = Mock()

    def run_with(self, rewrite, plans):
        self.model.plan.side_effect = plans
        with patch('blok.rephrase.rewrite', return_value=rewrite):
            return self.backend.plan_with_rephrase(self.model, self.backend.generation, 'yo turn it down man', None)

    def test_rewrite_plan_is_used(self):
        ok = Decision(Mock(), 'plan', .9, 1)
        decision = self.run_with(rephrase.Rewrite('turn the volume down', '', 'qwen2.5:3b', 200), [ok])
        self.assertIs(decision, ok)
        self.assertEqual(self.model.plan.call_args[0][0], 'turn the volume down')

    def test_failed_rewrite_falls_back_to_original_wording(self):
        failed = Decision(None, 'plan', .1, 1, 'not sure')
        self.assertIsNone(self.run_with(rephrase.Rewrite('turn the volume down', '', 'q', 200), [failed]))

    def test_question_only_when_original_also_fails(self):
        failed = Decision(None, 'plan', .1, 1, 'not sure')
        decision = self.run_with(rephrase.Rewrite('', 'Which app?', 'q', 200), [failed])
        self.assertEqual(decision.reason, 'Which app?')


if __name__ == '__main__':
    unittest.main()
