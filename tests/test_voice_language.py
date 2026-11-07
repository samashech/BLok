import json
import re
import tempfile
import threading
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from blok import backend as backend_module, hinglish, voice
from blok.backend import Backend
from blok.voice import DEVANAGARI, LATIN, Speaker, language_parts


def spoken_by(say, *args, **kw):
    """Everything the real Speaker sends to the Kokoro engine, as (voice, lang, text)."""
    calls = []

    def create(text, voice, speed, lang):
        calls.append((voice, lang, text))
        return [0.0], 24000
    speaker = Speaker(enabled=True)
    done = threading.Event()
    with patch.object(voice, 'kokoro', return_value=Mock(create=create)), patch.object(voice, 'kokoro_available', return_value=True), \
         patch.object(voice, 'api_key', return_value=None), patch('soundfile.write'), patch.object(voice.os, 'unlink'), \
         patch.object(voice.shutil, 'which', return_value='/usr/bin/pw-play'), \
         patch.object(Speaker, '_start', return_value=Mock(poll=Mock(return_value=0), wait=Mock())), \
         patch.object(voice.tempfile, 'mkstemp', return_value=(0, '/tmp/x')), patch.object(voice.os, 'close'), \
         patch.object(hinglish, '_english_word', return_value='ओपन'):     # no real subprocess while os.close is replaced
        getattr(speaker, say)(*args, **kw)
        for _ in range(400):
            if not speaker.speaking():
                break
            done.wait(0.01)
        assert not speaker.speaking(), 'the speaker never finished'
    return calls


class PartsTests(unittest.TestCase):
    def test_pure_text_is_one_part(self):
        self.assertEqual(language_parts('Opened YouTube.'), [('en', 'Opened YouTube.')])
        self.assertEqual(language_parts('यूट्यूब खोल दिया'), [('hi', 'यूट्यूब खोल दिया')])

    def test_a_name_in_a_hindi_sentence_is_written_in_hindi(self):
        (lang, text), = language_parts('Steam खोल दिया')
        self.assertEqual(lang, 'hi')
        self.assertFalse(LATIN.search(text))

    def test_a_hindi_phrase_in_english_gets_its_own_voice(self):
        self.assertEqual([lang for lang, _ in language_parts('Now playing तुम ही हो on Spotify')], ['en', 'hi', 'en'])

    def test_a_long_english_stretch_in_hindi_keeps_the_english_voice(self):
        parts = language_parts('यह पेज कहता है the quick brown fox jumps over the lazy dog और कुछ नहीं')
        self.assertEqual([lang for lang, _ in parts], ['hi', 'en', 'hi'])

    def test_romanized_hindi_is_never_read_as_english(self):
        for said in ('YouTube pe gaana chala diya', 'aap kaise ho', 'yeh gaana bahut accha hai'):
            self.assertEqual([lang for lang, _ in language_parts(said)], ['hi'], said)

    def test_english_with_look_alike_words_stays_english(self):
        for said in ('Hi, how are you?', 'The car is on the road', 'Do it now', 'Opened Kal in a new tab', 'Go to page 2', 'Karma is a song', 'Ho Ho Ho', 'par for the course'):
            self.assertEqual([lang for lang, _ in language_parts(said)], ['en'], said)

    def test_numbers_and_punctuation_stay_with_their_sentence(self):
        self.assertEqual(language_parts('अभी 3 बजे हैं।'), [('hi', 'अभी 3 बजे हैं।')])
        self.assertEqual(language_parts('It is 3:45 PM.'), [('en', 'It is 3:45 PM.')])
        self.assertEqual(language_parts('... ?'), [])

    def test_the_rule_holds_for_every_kind_of_text(self):
        samples = ['Opened YouTube', 'यूट्यूब खोल दिया', 'Steam खोल दिया', 'Now playing तुम ही हो on Spotify', 'gaana chala diya hai',
                   'Bhairav12 है', 'यहabc मिला', 'a b c d e f ग', 'ग a b c d e f', '१२ बजे 3 PM', '', '   ', 'सर्च Google पर 5', '"तुम" and "you"',
                   'Hindi: नमस्ते. English: hello there my good friend.']
        for text in samples:
            for lang, piece in language_parts(text):
                if lang == 'hi':
                    self.assertFalse(LATIN.search(piece), (text, piece))
                else:
                    self.assertFalse(DEVANAGARI.search(piece), (text, piece))


@unittest.skipUnless(voice.shutil.which('espeak-ng'), 'needs espeak-ng')
class EnglishNamesInHindiTests(unittest.TestCase):
    def test_english_words_go_by_how_they_sound(self):
        for word, sound in (('Save', 'सेव'), ('games', 'गेम्ज़'), ('Settings', 'सेटिंग्ज़'), ('Cancel', 'कैन्सअल'), ('search', 'सर')):
            written = hinglish.devanagari_text(word)
            self.assertFalse(LATIN.search(written))
            self.assertTrue(written.startswith(sound[:2]), (word, written))
        self.assertEqual(hinglish.devanagari_text('Save'), 'सेव')    # not सवे, letter by letter

    def test_indian_names_are_spelled_out(self):
        for name in ('Arijit', 'Singh', 'Shreya', 'Ghoshal', 'Bhairav', 'Sanam', 'Mumbai'):
            self.assertEqual(hinglish.devanagari_text(name), hinglish.to_devanagari(name), name)

    def test_known_names_keep_their_spelling(self):
        self.assertEqual(hinglish.devanagari_text('YouTube'), hinglish.to_devanagari('YouTube'))

    def test_hindi_titles_are_spelled_out_not_pronounced_as_english(self):
        self.assertEqual(hinglish.devanagari_text('tum hi ho'), ' '.join(hinglish.to_devanagari(w) for w in ('tum', 'hi', 'ho')))

    def test_without_espeak_it_still_gives_hindi_script(self):
        hinglish._english_word.cache_clear()
        with patch.object(hinglish.shutil, 'which', return_value=None):
            written = hinglish.devanagari_text('Walrus')
        hinglish._english_word.cache_clear()
        self.assertFalse(LATIN.search(written))
        self.assertTrue(DEVANAGARI.search(written))


class VoiceChoiceTests(unittest.TestCase):
    def test_a_wrong_voice_setting_cant_break_the_rule(self):
        with patch.dict(voice.os.environ, {'BLOK_HINDI_VOICE': 'af_heart', 'BLOK_KOKORO_VOICE': 'hf_alpha'}):
            self.assertEqual(voice.hindi_voice(), 'hm_omega')
            self.assertEqual(voice.english_voice(), 'af_heart')
        with patch.dict(voice.os.environ, {'BLOK_HINDI_VOICE': 'hf_beta', 'BLOK_KOKORO_VOICE': 'bm_george'}):
            self.assertEqual((voice.hindi_voice(), voice.english_voice()), ('hf_beta', 'bm_george'))

    def assertNeverMixed(self, calls):
        self.assertTrue(calls)
        for chosen, lang, text in calls:
            if chosen[:2] in ('hf', 'hm'):
                self.assertEqual(lang, 'hi')
                self.assertFalse(LATIN.search(text), calls)
            else:
                self.assertEqual(lang, 'en-us')
                self.assertFalse(DEVANAGARI.search(text), calls)

    def test_the_engine_never_gets_the_wrong_language(self):
        for args in (('Opened YouTube',), ('यूट्यूब खोल दिया',), ('Opened तुम ही हो on Spotify',), ('gaana chala diya hai',)):
            self.assertNeverMixed(spoken_by('say', *args))

    def test_asking_for_the_wrong_voice_is_ignored(self):
        calls = spoken_by('say', 'Opened YouTube', voice='hf_alpha', lang='hi')
        self.assertEqual(calls, [('af_heart', 'en-us', 'Opened YouTube')])
        calls = spoken_by('say', 'यूट्यूब खोल दिया', voice='af_heart')
        self.assertEqual(calls, [('hm_omega', 'hi', 'यूट्यूब खोल दिया')])

    def test_reading_a_page_splits_by_language(self):
        calls = spoken_by('read_aloud', 'This is English. यह हिंदी है। And this is English again.')
        self.assertNeverMixed(calls)
        self.assertEqual([c[1] for c in calls], ['en-us', 'hi', 'en-us'])

    def test_it_counts_as_speaking_while_the_audio_is_being_made(self):
        speaker = Speaker(enabled=True)
        release = threading.Event()
        seen = []
        with patch.object(Speaker, 'mode', return_value='kokoro'), patch.object(Speaker, '_speak', side_effect=lambda *a, **k: (seen.append(1), release.wait(1))):
            speaker.say('Opened YouTube')
            for _ in range(100):
                if seen:
                    break
                threading.Event().wait(0.005)
            self.assertTrue(speaker.speaking())    # the mic must stay paused, or BLoK hears itself
            release.set()
            for _ in range(100):
                if not speaker.speaking():
                    break
                threading.Event().wait(0.005)
        self.assertFalse(speaker.speaking())


class ReplyTests(unittest.TestCase):
    MESSAGES = ['Opened YouTube', 'Opened Steam in a new tab', 'Requested steam', 'Playing Tum Hi Ho on Spotify', 'Searched google for games', 'Volume 50%', 'Brightness 20%',
                'Sound muted', 'Sound unmuted', 'It is 3:45 PM.', 'Today is Monday, November 2, 2026.', 'Battery is at 80% and charging.', 'Closed Brave', 'Screenshot taken',
                'Clicked Save', 'Clicked Save · result not verified', 'Clicked Save · the page changed', 'Clicked Save · opened a new tab', 'Clicked Save · downloading game.zip',
                'Clicked Save · nothing visibly changed', 'Clicked Save · the window changed', 'Clicked Save · opened a new window', 'Scrolled down', 'Showing 12 numbers',
                'Hid the numbers', 'minecraft theme', 'Typed hello', 'Okay.', 'Speaking Hindi now.', 'Answering in the language you speak.',
                'I can see "Save" in 2 places here, so I didn\'t click. Say more of its label.', 'I can\'t see "Save" in this window.',
                'No visible control named launch. Closest: "Pricing".', 'Which one: "Save draft", or "Save copy"?',
                'This page has no search box. Searched google for games']

    def test_every_hindi_reply_has_no_english_letters(self):
        for message in self.MESSAGES:
            said = hinglish.reply(message, strict=True)
            self.assertIsNotNone(said, message)
            self.assertFalse(LATIN.search(said), (message, said))

    def test_click_reports_read_naturally(self):
        self.assertEqual(hinglish.reply('Clicked Save · the page changed', strict=True).split('। ')[1], 'पेज बदल गया')
        self.assertNotIn('verified', hinglish.reply('Clicked Save · result not verified', strict=True))


class ReplyLanguageTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        for patcher in (patch.object(backend_module, 'DATA', Path(self.folder.name)),):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.backend = Backend()
        self.backend.emit = Mock()
        self.backend.speaker = Mock()

    def heard(self):
        return self.backend.speaker.say.call_args

    def test_auto_answers_in_the_language_you_spoke(self):
        self.backend.reply_hinglish = True
        self.backend.say_result('Opened YouTube')
        self.assertEqual(self.heard().kwargs['lang'], 'hi')
        self.backend.reply_hinglish = False
        self.backend.say_result('Opened YouTube')
        self.assertEqual(self.heard().args[0], 'Opened YouTube')
        self.assertNotIn('lang', self.heard().kwargs)

    def test_always_hindi_and_always_english(self):
        self.backend.set_reply_language('hindi')
        self.backend.reply_hinglish = False
        self.backend.say_result('Opened YouTube')
        self.assertEqual(self.heard().kwargs['lang'], 'hi')
        self.backend.set_reply_language('english')
        self.backend.reply_hinglish = True
        self.backend.say_result('Opened YouTube')
        self.assertEqual(self.heard().args[0], 'Opened YouTube')

    def test_the_choice_survives_a_restart_and_keeps_other_settings(self):
        path = Path(self.folder.name) / 'settings.json'
        path.write_text(json.dumps({'hands_free': True}))
        self.backend.set_reply_language('hindi')
        self.assertEqual(Backend().reply_language(), 'hindi')
        self.assertTrue(json.loads(path.read_text())['hands_free'])

    def test_a_long_english_answer_stays_english_in_the_english_voice(self):
        self.backend.set_reply_language('hindi')
        answer = 'The article says the company was founded in 1998 and now has offices in many countries around the world.'
        self.backend.say_result(answer)
        self.assertNotIn('lang', self.heard().kwargs)

    def test_a_long_error_in_hindi_mode_is_still_hindi(self):
        self.backend.reply_hinglish = True
        self.backend.say_result('Something very long went wrong with this thing and it could not be finished right now.', error=True)
        self.assertEqual(self.heard().kwargs['lang'], 'hi')

    def test_a_female_voice_gets_feminine_grammar(self):
        self.backend.reply_hinglish = True
        with patch.dict(voice.os.environ, {'BLOK_HINDI_VOICE': 'hf_alpha'}):
            self.backend.say_result('Requested steam')
        self.assertIn('रही हूँ', self.heard().args[0])
        self.backend.say_result('Requested steam')
        self.assertIn('रहा हूँ', self.heard().args[0])

    def test_saying_stop_in_hindi_is_answered_in_hindi(self):
        self.backend.live = False
        self.backend.transcript('bas', True, source='voice')
        self.assertEqual(self.heard().args[0], 'ठीक है')

    def test_voice_commands_choose_the_language(self):
        for said, language in (('speak in hindi', 'hindi'), ('Hindi mein bolo.', 'hindi'), ('use the hindi voice', 'hindi'), ('talk to me in Hindi', 'hindi'),
                               ('speak english', 'english'), ('english mein baat karo', 'english'), ('switch to english', 'english'),
                               ('match my language', 'auto'), ('speak in auto', 'auto')):
            self.assertEqual(Backend.ASK_LANGUAGE(said), language, said)
        for said in ('search for hindi songs', 'open english dictionary', 'play hindi music', 'what is hindi'):
            self.assertIsNone(Backend.ASK_LANGUAGE(said), said)


if __name__ == '__main__':
    unittest.main()
