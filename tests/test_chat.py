import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from blok import backend as backend_module, chat
from blok.backend import Backend
from blok.nlu import ConversationContext, resolve_intent
from blok.voice import DEVANAGARI, LATIN, language_parts


def topic(text, **kw):
    reply = chat.respond(text, **kw)
    return reply and reply.name


class TopicTests(unittest.TestCase):
    def test_everyday_english(self):
        for said, name in (("What's your name?", 'name'), ('who are you', 'name'), ('how are you', 'how_are_you'), ('hello', 'hello'), ('hi there', 'hello'),
                           ('tell me a joke', 'joke'), ('another joke', 'joke'), ('what can you do', 'abilities'), ('who made you', 'maker'), ('are you a robot', 'robot'),
                           ('good morning', 'morning'), ('good night', 'night'), ('i love you', 'love'), ('you are stupid', 'insult'), ("you're awesome", 'praise'),
                           ('thank you', 'thanks'), ('thanks a lot', 'thanks'), ('sing a song', 'sing'), ("what's up", 'up_to'), ("I'm bored", 'bored'), ('bye', 'bye'),
                           ("what's your favorite color", 'favorite'), ('what is the meaning of life', 'meaning'), ('haha', 'agree'), ('sorry', 'sorry')):
            self.assertEqual(topic(said), name, said)

    def test_everyday_hinglish_answers_in_hindi(self):
        for said, name in (('tumhara naam kya hai', 'name'), ('aap kaun ho', 'name'), ('kaise ho', 'how_are_you'), ('kya haal hai', 'how_are_you'), ('namaste', 'hello'),
                           ('ek joke sunao', 'joke'), ('chutkula sunao', 'joke'), ('kya kar rahe ho', 'up_to'), ('shukriya', 'thanks'), ('tumhe kisne banaya', 'maker'),
                           ('tum pagal ho', 'insult'), ('shabash', 'praise'), ('main bor ho raha hoon', 'bored'), ('mujhe bhook lagi hai', 'hungry'), ('phir milenge', 'bye')):
            reply = chat.respond(said)
            self.assertEqual(reply and reply.name, name, said)
            self.assertTrue(reply.hindi, said)

    def test_fillers_and_the_name_around_it_are_ignored(self):
        for said in ('hey block, what is your name', 'bro what is your name please', 'what is your name, block?', 'yaar tumhara naam kya hai'):
            self.assertEqual(topic(said), 'name', said)

    def test_its_name_is_blok_in_both_languages(self):
        self.assertIn('BLoK', chat.respond('what is your name').text)
        self.assertIn('ब्लॉक', chat.respond('tumhara naam kya hai').text)

    def test_commands_are_never_mistaken_for_chat(self):
        for said in ('play a joke podcast', 'search for jokes', 'open youtube', 'search for hello', 'tell me the time', 'what time is it', 'what is the date today',
                     'stop', 'open the name folder', 'click thank you', 'play hello by adele', 'how are you search on google', 'youtube pe gaana chalao', 'volume up', 'next page',
                     'go to help', 'click help', 'search for good morning images', 'open bye', 'type i love you', 'scroll down', 'go back', 'nothing', 'never mind', 'bas'):
            self.assertIsNone(chat.respond(said), said)

    def test_long_sentences_are_not_chat(self):
        self.assertIsNone(chat.respond('hello ' * 40))


class ToneTests(unittest.TestCase):
    def test_a_serious_moment_gets_no_jokes(self):
        for said in ('i want to kill myself', 'I want to die', "i don't want to live anymore", 'mujhe marna hai', 'main khud ko maar dunga'):
            reply = chat.respond(said)
            self.assertEqual(reply and reply.name, 'crisis', said)
            self.assertIn('14416', reply.text)
            remembered = []
            chat.respond(said, remember=remembered.append)
            self.assertEqual(remembered, [])       # "mujhe marna hai" is not a name
        for said in ("I'm sad", 'i feel lonely', 'having a bad day' if False else "i'm having a bad day", 'main bahut udaas hoon'):
            self.assertEqual(topic(said), 'sad', said)
        for name in ('crisis', 'sad'):
            for _ in range(10):
                said = {'crisis': 'i want to die', 'sad': "i'm sad"}[name]
                self.assertNotRegex(chat.respond(said).text.lower(), r'joke|laptop|tabs|electricity|rupee')

    def test_no_repeat_in_a_row(self):
        for said in ('tell me a joke', 'ek joke sunao', 'hello', 'thank you'):
            replies = [chat.respond(said).text for _ in range(30)]
            self.assertTrue(all(a != b for a, b in zip(replies, replies[1:])), said)

    def test_goodbye_and_thanks_end_the_conversation_but_chat_keeps_it_going(self):
        for said in ('bye', 'good night', 'thank you', 'i want to die'):
            self.assertTrue(chat.respond(said).ends, said)
        for said in ('hello', 'tell me a joke', 'how are you', "i'm sad"):
            self.assertFalse(chat.respond(said).ends, said)

    def test_morning_is_time_aware(self):
        with patch.object(chat.time, 'localtime', return_value=Mock(tm_hour=23)), patch.object(chat.time, 'strftime', return_value='11 PM'):
            self.assertIn('11 PM', chat.respond('good morning').text)


class VoiceSafetyTests(unittest.TestCase):
    def test_every_english_reply_is_pure_english_and_hindi_pure_hindi(self):
        for name, _, _, english, hindi, _ in chat.TOPICS:
            for reply in english:
                self.assertFalse(DEVANAGARI.search(reply), reply)
                self.assertEqual({lang for lang, _ in language_parts(reply)}, {'en'}, reply)
            for reply in hindi:
                self.assertFalse(LATIN.search(reply), reply)
                self.assertEqual({lang for lang, _ in language_parts(reply)}, {'hi'}, reply)
        for reply in chat.CONFUSED_HINDI:
            self.assertFalse(LATIN.search(reply), reply)

    def test_the_voice_says_blok_as_a_word(self):
        self.assertEqual(language_parts("I'm BLoK."), [('en', "I'm Block.")])

    def test_hinglish_language_preference_wins(self):
        self.assertTrue(chat.respond('what is your name', language='hindi').hindi)
        self.assertFalse(chat.respond('tumhara naam kya hai', language='english').hindi)

    def test_feminine_grammar_for_female_voice(self):
        with patch.dict(backend_module.os.environ, {'BLOK_HINDI_VOICE': 'hf_alpha'}):
            for _ in range(8):
                self.assertNotIn('रहता हूँ', chat.respond('tumhara naam kya hai').text)


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        patcher = patch.object(backend_module, 'DATA', Path(self.folder.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.backend = Backend()
        self.backend.speaker = Mock()
        self.backend.submit_decision = Mock()
        self.backend.live = False

    def test_chat_is_shown_and_read_in_its_own_voice_and_never_reaches_laya(self):
        self.backend.transcript('what is your name', True, source='voice')
        self.backend.submit_decision.assert_not_called()
        said = self.backend.speaker.read_aloud.call_args.args[0]
        self.assertIn('BLoK', said)
        self.backend.speaker.say.assert_not_called()

    def test_commands_still_reach_the_planner(self):
        self.backend.transcript('open youtube', True, source='voice')
        self.backend.submit_decision.assert_called_once()

    def test_goodbye_stops_listening_but_a_joke_keeps_the_conversation(self):
        self.backend.transcript('tell me a joke', True, source='voice')
        self.assertEqual(self.backend.input_source, 'voice')
        self.backend.transcript('bye', True, source='voice')
        self.assertEqual(self.backend.input_source, 'typed')

    def test_stop_and_never_mind_still_just_stop(self):
        self.backend.transcript('stop', True, source='voice')
        self.assertEqual(self.backend.speaker.say.call_args.args[0], 'Okay.')

    def test_a_pending_approval_or_skill_name_isnt_chat(self):
        self.backend.has_pending_approval = Mock(return_value=True)
        self.assertFalse(self.backend.chat('hello'))
        self.backend.has_pending_approval = Mock(return_value=False)
        self.backend.pending_steps = [{'op': 'click'}]
        self.assertFalse(self.backend.chat('hello'))
        self.backend.pending_steps = None
        self.backend.context.watching = True
        self.assertFalse(self.backend.chat('hello'))

    def test_it_remembers_your_name_on_this_computer(self):
        path = Path(self.folder.name) / 'settings.json'
        path.write_text(json.dumps({'hands_free': True}))
        self.backend.transcript('my name is sameer', True, source='voice')
        self.assertIn('Sameer', self.backend.speaker.read_aloud.call_args.args[0])
        self.assertEqual(json.loads(path.read_text()), {'hands_free': True, 'user_name': 'Sameer'})
        self.backend.transcript("what's my name", True, source='voice')
        self.assertIn('Sameer', self.backend.speaker.read_aloud.call_args.args[0])
        self.backend.transcript('forget my name', True, source='voice')
        self.assertNotIn('user_name', json.loads(path.read_text()))
        self.backend.transcript('mera naam Aarav hai', True, source='voice')
        said = self.backend.speaker.read_aloud.call_args.args[0]
        self.assertFalse(LATIN.search(said))
        self.assertEqual(self.backend.user_name(), 'Aarav')

    def test_not_understood_is_friendly_in_the_language_you_spoke(self):
        self.backend.understood_nothing('flibber the wobble')
        self.assertIn(self.backend.speaker.read_aloud.call_args.args[0], chat.CONFUSED)
        self.backend.understood_nothing('yeh kya hai bhai karo')

    def test_a_question_uses_the_local_model_only_if_its_on(self):
        with patch.object(chat, 'ask_model', return_value='Paris, probably. It is lovely.'):
            self.backend.understood_nothing('what is the capital of france')
            generation, event = self.backend.events.get(timeout=2)
        self.assertEqual(event['reply'].text, 'Paris, probably. It is lovely.')
        with patch.object(chat, 'ask_model', return_value=None):
            self.backend.understood_nothing('what is the capital of france')
            generation, event = self.backend.events.get(timeout=2)
        self.assertIn(event['reply'].text, chat.CONFUSED)

    def test_names_are_only_taken_from_real_introductions(self):
        for said in ('mujhe bhook lagi hai', 'mujhe marna hai', 'mujhe gaana sunna hai', 'mera naam kya hai'):
            remembered = []
            chat.respond(said, remember=remembered.append)
            self.assertEqual(remembered, [], said)
        for said, name in (('my name is sameer', 'Sameer'), ('call me boss', 'Boss'), ('mera naam Aarav hai', 'Aarav'), ('mujhe Sam bulao', 'Sam')):
            remembered = []
            chat.respond(said, remember=remembered.append)
            self.assertEqual(remembered, [name], said)

    def test_a_stopped_request_doesnt_answer_late(self):
        with patch.object(chat, 'ask_model', side_effect=lambda *a: setattr(self.backend, 'generation', self.backend.generation + 1) or 'Too late'):
            self.backend.understood_nothing('what is the capital of france')
            import time
            time.sleep(0.1)
        self.assertTrue(self.backend.events.empty())

    def test_laya_giving_up_goes_to_the_friendly_answer(self):
        self.backend.understood_nothing = Mock()
        decision = Mock(action=None, reason="I'm not sure what you want. Try saying it another way.", intent='none', probability=0.1, elapsed_ms=1)
        self.backend.pending = 1
        with patch.object(backend_module, 'record_trace'):
            self.backend.finish_decision({'type': 'decision', 'decision': decision, 'intent': Mock(raw_text='flibber'), 'timer': Mock()})
        self.backend.understood_nothing.assert_called_once_with('flibber')


if __name__ == '__main__':
    unittest.main()
