import unittest
from unittest.mock import patch, Mock

from blok import screen
from blok.backend import Backend
from blok.nlu import resolve_intent

ARTICLE = """Solar panels turn sunlight into electricity using photovoltaic cells.
Most home panels are made of silicon and last for about twenty five years.
A typical home system costs ₹2,40,000 and pays for itself in about six years.
Cookie settings. Subscribe to our newsletter.
Installers recommend south-facing roofs for the most electricity from sunlight."""


class UnderstandingTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(screen, '_llm', return_value=None)   # the extractive path, no Ollama
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_summary_keeps_central_sentences_in_order(self):
        summary = screen.summarize(ARTICLE, count=2)
        self.assertIn('photovoltaic', summary)
        self.assertNotIn('newsletter', summary)

    def test_answers_prices_and_facts(self):
        self.assertEqual(screen.answer('what is the price', ARTICLE), 'The price here is ₹2,40,000')
        self.assertIn('twenty five years', screen.answer('how long do the panels last', ARTICLE))
        self.assertEqual(screen.answer('who is the author', ARTICLE), "I couldn't find that here.")

    def test_error_explanation_reads_the_error_line(self):
        terminal = '$ python app.py\nTraceback (most recent call last):\n  File "app.py", line 3\nModuleNotFoundError: No module named requests\n$'
        self.assertEqual(screen.explain_error(terminal), 'The error says: ModuleNotFoundError: No module named requests')
        self.assertEqual(screen.explain_error('all good\n$'), "I don't see an error on screen.")

    def test_find_word_matches_multi_word_labels(self):
        words = [{'text': t, 'x': i * 50, 'y': 10, 'w': 40, 'h': 12, 'conf': 90} for i, t in enumerate(['File', 'Save', 'As...', 'Cancel'])]
        self.assertEqual(screen.find_word(words, 'save as')['x'], 50)
        self.assertEqual(screen.find_word(words, 'Cancel button')['x'], 150)
        self.assertIsNone(screen.find_word(words, 'Delete'))

    def test_qwen_answers_when_available(self):
        with patch.object(screen, '_llm', return_value='It costs 2.4 lakh rupees.'):
            self.assertEqual(screen.answer('what does it cost', ARTICLE), 'It costs 2.4 lakh rupees.')


class ScreenToolTests(unittest.TestCase):
    def setUp(self):
        self.backend = Backend()
        self.backend.speaker = Mock()

    def run_tool(self, ask, **extra):
        seen = {'source': 'page', 'title': 'Solar', 'text': ARTICLE, 'selection': '', 'url': 'https://x.test'}
        with patch.object(Backend, 'browser_in_front', return_value=True), patch.object(Backend, 'require_extension'), \
             patch.object(screen, 'read_screen', return_value=seen), patch.object(screen, '_llm', return_value=None), \
             patch('builtins.print'):
            return self.backend.run_tool({'tool': 'screen', 'ask': ask, **extra})

    def test_read_aloud_speaks_the_text_not_the_status(self):
        message = self.run_tool('read')
        self.assertEqual(message, 'Reading Solar')
        with patch('builtins.print'):
            self.backend.emit(type='action', message=message)
        self.backend.speaker.read_aloud.assert_called_once_with(ARTICLE)
        self.backend.speaker.say.assert_not_called()

    def test_summary_and_question(self):
        self.assertIn('photovoltaic', self.run_tool('summary'))
        self.assertEqual(self.run_tool('question', question='what is the price'), 'The price here is ₹2,40,000')

    def test_routing_keeps_old_meanings(self):
        self.assertEqual(resolve_intent('what is the date').intent_type, 'tool:ask_date')
        self.assertEqual(resolve_intent('read my readme file').intent_type, 'tool:file_read')
        self.assertEqual(resolve_intent('ye page kis baare mein hai').intent_type, 'screen:summary')


if __name__ == '__main__':
    unittest.main()
