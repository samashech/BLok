import json
import unittest
from unittest.mock import patch, Mock

from blok import hinglish
from blok.backend import Backend
from blok.nlu import resolve_intent


class TranslateTests(unittest.TestCase):
    CASES = {
        'YouTube pe Arijit ke gaane chalao': 'play Arijit songs on youtube',
        'bhai zara spotify khol do': 'open spotify',
        'downloads folder kholo': 'open downloads folder',
        'yaar awaaz thoda badhao': 'turn the volume up',
        'volume kam karo na': 'turn the volume down',
        'kitne baje hain': 'what time is it',
        'aaj kya tarik hain?': 'what is the date',
        'Battery kitne hain.': 'how much battery do i have',
        'agla gaana lagao': 'next track',
        'google pe mausam sarj karo': 'search for mausam on google',
        'youtube kholo aur phir minecraft search karo': 'open youtube and then search for minecraft',
        'numbers dikhao': 'show numbers',
        'barah pe click karo': 'click 12',
        'neeche scroll karo': 'scroll down',
        'hello world likho': 'type hello world',
        'screenshot le lo': 'take a screenshot',
        'halloween wala theme lagao': 'switch to the halloween theme',
        'workspace teen pe jao': 'switch to workspace 3',
        'hands free chalu karo': 'hands free on',
    }

    def test_romanized(self):
        for said, english in self.CASES.items():
            self.assertEqual(hinglish.translate(said), english, said)

    def test_devanagari(self):
        self.assertEqual(hinglish.translate('यूट्यूब पे अरिजीत के गाने चलाओ'), 'play arijit songs on youtube')
        self.assertEqual(hinglish.translate('आवाज़ थोड़ी बढ़ाओ'), 'turn the volume up')
        self.assertEqual(hinglish.translate('नीचे स्क्रॉल करो'), 'scroll down')
        self.assertEqual(hinglish.transliterate('कितने बजे हैं'), 'kitne baje hain')

    def test_english_passes_through(self):
        for said in ('open youtube', 'play lo fi music', 'i like turtles', 'what time is it', 'do it'):
            self.assertIsNone(hinglish.translate(said), said)

    def test_rules_understand_hinglish_directly(self):
        self.assertEqual(json.loads(resolve_intent('awaaz thoda badhao').action_value), {'tool': 'volume', 'op': 'up'})
        self.assertEqual(resolve_intent('haan ji').intent_type, 'hitl_approve')
        self.assertEqual(resolve_intent('nahi rehne do').intent_type, 'hitl_reject')

    def test_replies_are_all_devanagari(self):
        self.assertEqual(hinglish.reply('Opened YouTube'), 'यूट्यूब खोल दिया')
        self.assertEqual(hinglish.reply('Volume 40%'), 'आवाज़ 40 प्रतिशत')
        self.assertEqual(hinglish.reply('It is 1:15 AM.'), 'अभी 1 बजकर 15 मिनट हुए हैं')
        self.assertEqual(hinglish.reply('Playing Arijit Singh songs on youtube'), 'अरिजित सिंह सॉन्ग्स चला दिया')
        self.assertEqual(hinglish.reply('Something unusual'), 'हो गया')
        self.assertEqual(hinglish.reply('Something broke', error=True), 'माफ़ कीजिए, यह नहीं हो पाया')
        for message in ('Opened ~/Downloads', 'Searched youtube for pewdiepie', 'Clicked Subscribe', 'Today is Monday, November 2, 2026.'):
            self.assertNotRegex(hinglish.reply(message), r'[A-Za-z]', message)

    def test_names_by_sound(self):
        self.assertEqual([hinglish.to_devanagari(w) for w in ('Arijit', 'Singh', 'Shreya', 'Tum', 'Ganga')],
                         ['अरिजित', 'सिंह', 'श्रेया', 'तुम', 'गंगा'])


class BackendHinglishTests(unittest.TestCase):
    def test_hinglish_command_gets_a_hinglish_reply_in_a_hindi_voice(self):
        backend = Backend()
        backend.speaker = Mock()
        backend.submit_decision = Mock()
        with patch('builtins.print'):
            backend.transcript('youtube kholo', True)
            backend.emit(type='action', message='Opened youtube')
        backend.submit_decision.assert_called_once_with('open youtube')
        call = backend.speaker.say.call_args
        self.assertEqual((call[0][0], call[1]['voice'], call[1]['lang']), ('यूट्यूब खोल दिया', 'hf_alpha', 'hi'))

    def test_english_command_keeps_the_english_voice(self):
        backend = Backend()
        backend.speaker = Mock()
        backend.submit_decision = Mock()
        with patch('builtins.print'):
            backend.transcript('open youtube', True)
            backend.emit(type='action', message='Opened youtube')
        self.assertNotIn('voice', backend.speaker.say.call_args[1])


if __name__ == '__main__':
    unittest.main()
