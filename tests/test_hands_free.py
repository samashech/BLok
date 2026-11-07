import io
import json
import time
import unittest
from unittest.mock import patch, Mock

import numpy

from blok import browser, speech
from blok.backend import Backend
from blok.speech import WAKE, HandsFreeListener


def tone(seconds):
    return numpy.sin(numpy.arange(int(16000 * seconds)) / 6) * 0.2


def noise(seconds):
    return numpy.random.default_rng(0).standard_normal(int(16000 * seconds)) * 0.001


class WakeTests(unittest.TestCase):
    def test_wake_variants(self):
        for said in ('Hey Block, open YouTube.', 'okay blok scroll down', 'Block, numbers', 'Hey black, what time is it?'):
            self.assertTrue(WAKE.match(said), said)
        for said in ('I blocked him', 'the black cat', 'open youtube', 'roadblock ahead'):
            self.assertFalse(WAKE.match(said), said)


class VoiceDetectorTests(unittest.TestCase):
    def test_endpointer_keeps_going_on_a_lower_bar_than_it_starts(self):
        probabilities = iter([0.4] * 5 + [0.6] * 3 + [0.4] * 5 + [0.1] * 3)
        pointer = speech.Endpointer(0.096, detector=lambda frame: next(probabilities))
        events = [pointer.feed(numpy.zeros(speech.FRAME)) for _ in range(16)]
        self.assertEqual([i for i, event in enumerate(events) if event == 'start'], [7])   # 0.4 can't start speech
        self.assertEqual([i for i, event in enumerate(events) if event == 'end'], [15])    # but it doesn't end it

    def test_silero_ignores_loud_noise(self):
        detector = speech.voice_detector()
        if detector is None:
            self.skipTest('Silero VAD is not available')
        pointer = speech.Endpointer(1.0, detector)
        loud = (numpy.random.default_rng(0).standard_normal(16000 * 3) * 0.05).astype('float32')
        events = [pointer.feed(loud[i:i + speech.FRAME]) for i in range(0, len(loud) - speech.FRAME, speech.FRAME)]
        self.assertNotIn('start', events)

    def test_falls_back_to_loudness_when_asked(self):
        with patch.dict('os.environ', {'BLOK_VAD': 'loudness'}):
            self.assertIsNone(speech.voice_detector())


class ListenerTests(unittest.TestCase):
    def setUp(self):
        # These streams use tones for "voice", which Silero rightly rejects: test the shared logic on loudness.
        patcher = patch.dict('os.environ', {'BLOK_VAD': 'loudness'})
        patcher.start()
        self.addCleanup(patcher.stop)

    def listener(self):
        self.commands, self.wakes = [], []
        return HandsFreeListener(self.commands.append, lambda early=False: self.wakes.append(early))

    def test_wake_command_and_follow_ups(self):
        heard = self.listener()
        with patch.object(speech, 'transcribe', side_effect=['Hey Block, show numbers.', 'twelve', 'nice weather today', 'okay']):
            heard.handle(numpy.zeros(1))
            heard.listen_for_follow_up()    # BLoK answered: the next command needs no name
            heard.handle(numpy.zeros(1))
            heard.handle(numpy.zeros(1))    # the window closes after one follow-up until BLoK answers again
            heard.listen_for_follow_up(); heard.follow_until = 0   # …or when it runs out
            heard.handle(numpy.zeros(1))
        self.assertEqual(self.commands, ['show numbers', 'twelve'])
        self.assertEqual([h['acted'] for h in heard.heard], [True, True, False, False])

    def test_name_alone_wakes(self):
        heard = self.listener()
        with patch.object(speech, 'transcribe', return_value='Hey block.'):
            heard.handle(numpy.zeros(1))
        self.assertEqual((self.commands, self.wakes), ([], [False]))

    def test_repeated_names_and_junk_are_not_a_command(self):
        heard = self.listener()
        with patch.object(speech, 'transcribe', side_effect=['Hey Block! 639, OK. Hey Block! Hey Block!',
                                                             'Hey Block, hey block, open YouTube']):
            heard.handle(numpy.zeros(1))
            heard.handle(numpy.zeros(1))
        self.assertEqual(self.wakes, [False])               # the first was just the name: wait for the command
        self.assertEqual(self.commands, ['open YouTube'])

    def test_fast_check_counts_even_if_the_full_transcript_misspells_it(self):
        heard = self.listener()
        with patch.object(speech, 'spot_wake', return_value=True):
            heard._spot(numpy.zeros(1))
            import time as _t; _t.sleep(0.1)
        self.assertEqual(self.wakes, [True])                # overlay opened while still talking
        with patch.object(speech, 'transcribe', return_value='Heyblok open the terminal'):
            heard.handle(numpy.zeros(1))
        self.assertEqual(self.commands, ['open the terminal'])

    def run_stream(self, heard, *parts, paused=None):
        """Run the listener over audio; returns the length in seconds of each utterance sent to Whisper."""
        stream = numpy.concatenate(parts)
        heard.process = Mock(stdout=io.BytesIO((stream * 32767).astype('<i2').tobytes()))
        heard.running = True
        if paused:
            heard.paused = paused
        with patch.object(speech, 'transcribe', side_effect=lambda audio: len(audio) / 16000):
            heard._loop()
            lengths = []
            while not heard.queue.empty():
                item = heard.queue.get_nowait()[0]
                lengths.append(item.result() if hasattr(item, 'result') else len(item) / 16000)
        return lengths

    def test_segmenter_cuts_one_utterance_from_a_stream(self):
        lengths = self.run_stream(self.listener(), noise(1.0), tone(1.0), noise(1.5))
        self.assertEqual(len(lengths), 1)
        self.assertAlmostEqual(lengths[0], 1.0 + 0.25 + 0.3, delta=0.2)  # voice + early-transcript tail + pre-roll

    def test_carrying_on_talking_drops_the_early_transcript(self):
        lengths = self.run_stream(self.listener(), noise(0.5), tone(1.0), noise(0.6), tone(1.0), noise(1.5))
        self.assertEqual(len(lengths), 1)
        self.assertGreater(lengths[0], 2.6)   # the whole thing, not just the part before the short pause

    def test_paused_while_speaking(self):
        heard = self.listener()
        heard.paused = lambda: True
        heard.process = Mock(stdout=io.BytesIO((numpy.sin(numpy.arange(32000) / 6) * 0.2 * 32767).astype('<i2').tobytes()
                                               + b'\x00' * 32000))
        heard.running = True
        heard._loop()
        self.assertTrue(heard.queue.empty())

    def test_own_voice_is_not_glued_to_the_next_command(self):
        # BLoK's reply runs straight into your command; only the command reaches Whisper.
        flags = [True] * round(1.0 * 16000 / HandsFreeListener.FRAME)
        lengths = self.run_stream(self.listener(), tone(1.0), tone(1.0), numpy.zeros(int(16000 * 1.3)),
                                  paused=lambda: flags.pop() if flags else False)
        self.assertEqual(len(lengths), 1)
        self.assertLess(lengths[0], 1.5)

    def test_name_anywhere_in_the_utterance(self):
        heard = self.listener()
        with patch.object(speech, 'transcribe', side_effect=["It doesn't work. Hey Block.", 'blah, hey block, open YouTube']):
            heard.handle(numpy.zeros(1))
            heard.handle(numpy.zeros(1))
        self.assertEqual((self.wakes, self.commands), ([False], ['open YouTube']))


class HandsFreeToolTests(unittest.TestCase):
    def setUp(self):
        self.backend = Backend()
        self.backend.emit = Mock()

    def test_numbers_then_click_confirms_risky_labels(self):
        calls = []
        def request(payload, **_):
            calls.append(payload['action'])
            if payload['action'] == 'hints':
                return {'message': 'Showing 9 numbers', 'count': 9}
            return {'name': 'Delete repository', 'control': {'id': 'c'}, 'page': 'p', 'editable': False}
        self.backend.request_approval = Mock(return_value=False)
        with patch.object(Backend, 'browser_in_front', return_value=True), \
             patch.object(browser, 'ping', return_value={'version': 'phase9-v1'}), patch.object(browser, 'request', side_effect=request):
            self.assertEqual(self.backend.run_tool({'tool': 'hints', 'show': True}), 'Showing 9 numbers')
            self.assertGreater(self.backend.context.hints_until, time.monotonic())
            with self.assertRaises(RuntimeError):
                self.backend.run_tool({'tool': 'hint', 'n': 3})
        self.assertEqual(calls, ['hints', 'hint'])   # rejected: never clicked

    def test_scroll_outside_the_browser_uses_keys(self):
        with patch.object(Backend, 'browser_in_front', return_value=False), patch('blok.system.press') as press:
            self.backend.run_tool({'tool': 'scroll', 'direction': 'down', 'amount': 'page'})
        press.assert_called_once_with('Next', 1)

    def test_typing_needs_a_selected_field_in_the_browser(self):
        with patch.object(Backend, 'browser_in_front', return_value=True), \
             patch.object(browser, 'ping', return_value={'version': 'phase9-v1'}), \
             patch.object(browser, 'request', return_value={'editable': False}), patch('blok.system.type_text') as typed:
            with self.assertRaisesRegex(RuntimeError, 'show numbers'):
                self.backend.run_tool({'tool': 'type', 'text': 'hello'})
        typed.assert_not_called()


if __name__ == '__main__':
    unittest.main()
