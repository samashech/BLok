import json
import tempfile
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch

from blok import backend as backend_module, browser, game
from blok.backend import Backend
from blok.game import Commentator, Event, Memory, Session, read_state
from blok.voice import DEVANAGARI, LATIN

# Real text from slither.io, captured from a live game.
PLAYING = ('Leaderboard\n24281\n16742\n8844\n8412\n7930\n7063\n5985\n4959\n4819\n4807\n\nC\xa0B\xa0T\xa0R\xa017\nBANGLADESH\npeter\xa0\n\nfahhad|\xa0ammu\xa0fan\xa0^_<\n\n'
           'ARYAN\xa0the\xa0KING\xa0{_J_S_R_}\n78\nMotu\xa0k\xa0dost\xa0Motuuuuu\n?as\n\n#1\n#2\n#3\n#4\n#5\n#6\n#7\n#8\n#9\n#10\n\nYour length: 23\nYour rank: 222 of 340\nserver 8828')
HOME = '\xa0\nEat to grow longer!\n\xa0Play\xa0\nprivacy - terms of service - contact'
DEAD = 'Your final length was 51\n\xa0Play Again\xa0\nprivacy - terms of service - contact'


# Real text from gulper.io, the game inside slithergame.io, including a real death.
GULPER = '1. qqq\t\n30525\n\n2. RAP\t\n11392\n\n3. AYAN\t\n2031\n\n4. Play\t\n1554\n\n9. Guest470\t\n93\n\n12. Guest375\t\n10\nFPS: 60/60\nPing: 78~14\nScore: 10\nRank: 10 of 14'
GULPER_OVER = 'Copy invite link\nGame over...\nFinal score: 35\nTop rank: 10\nSurvived for: 6s\nMain Menu Play Again'
GULPER_HOME = 'Play\nHold left mouse button or Space to accelerate\n© 2026 gulper.io•About•Privacy•v1.5.1b\nAbout the game\nWelcome to gulper.io, a fast-paced game'


def at(length, rank=200, players=300):
    return {'playing': True, 'length': length, 'rank': rank, 'players': players, 'final': None, 'top': 20000}


GONE = {'playing': False, 'length': None, 'rank': None, 'players': None, 'final': None, 'top': None}


def kinds(events):
    return [e.kind for e in events]


class ReadTests(unittest.TestCase):
    def test_reads_the_real_page(self):
        state = read_state(PLAYING)
        self.assertEqual((state['playing'], state['length'], state['rank'], state['players'], state['top']), (True, 23, 222, 340, 24281))

    def test_home_and_death_screens(self):
        self.assertFalse(read_state(HOME)['playing'])
        self.assertEqual(read_state(DEAD)['final'], 51)
        self.assertFalse(read_state(DEAD)['playing'])

    def test_junk_is_not_a_game(self):
        for text in ('', None, 'Your length: lots', 'hello'):
            self.assertFalse(read_state(text)['playing'], text)

    def test_reads_the_game_inside_slithergame(self):
        state = read_state(GULPER)
        self.assertEqual((state['playing'], state['length'], state['rank'], state['players'], state['top']), (True, 10, 10, 14, 30525))

    def test_reads_a_real_death(self):
        state = read_state(GULPER_OVER)
        self.assertEqual((state['playing'], state['final'], state['survived'], state['top_rank']), (False, 35, 6, 10))
        self.assertEqual(read_state('Final score: 900\nSurvived for: 2m 5s')['survived'], 125)
        self.assertFalse(read_state(GULPER_HOME)['playing'])

    def test_a_real_game_from_start_to_death(self):
        session = Session(now=0.0)
        self.assertEqual(kinds(session.feed(read_state(GULPER_HOME), 0)), [])
        self.assertEqual(kinds(session.feed(read_state(GULPER), 1)), ['life_start'])
        died = session.feed(read_state(GULPER_OVER), 40)
        self.assertEqual(kinds(died), ['death'])
        self.assertEqual((died[0].data['final'], died[0].data['seconds'], died[0].data['best_rank']), (35, 6, 10))
        self.assertEqual(session.feed(read_state(GULPER_OVER), 41), [])    # the screen stays up: one death
        self.assertEqual(kinds(session.feed(read_state(GULPER), 50)), ['life_start'])    # Play Again

    def test_only_the_real_site_counts(self):
        for url in ('https://slither.io/', 'http://slither.io/?a', 'https://www.slither.io', 'https://gulper.io/'):
            self.assertTrue(game.is_game_page(url), url)
        for url in ('https://notslither.io/', 'https://slither.io.evil.test/', 'https://example.com/slither.io', 'https://gulper.io.evil.test/', '', None):
            self.assertFalse(game.is_game_page(url), url)


class SessionTests(unittest.TestCase):
    def play(self, session, *lengths, start=0.0, step=10.0):
        found = []
        for i, length in enumerate(lengths):
            found += session.feed(at(length), start + i * step)
        return found

    def test_a_life_starts_grows_and_dies(self):
        session = Session()
        events = self.play(session, 10, 50, 120)
        self.assertEqual(kinds(events), ['life_start', 'length_mark'])
        self.assertEqual(events[1].data['mark'], 100)
        died = session.feed(GONE, 100)
        self.assertEqual(kinds(died), ['death'])
        self.assertEqual((died[0].data['final'], died[0].data['seconds']), (120, 100))
        self.assertEqual(session.lives[0]['number'], 1)

    def test_the_screen_is_trusted_for_the_final_length(self):
        session = Session()
        self.play(session, 10, 50)
        died = session.feed({**GONE, 'final': 57}, 30)
        self.assertEqual(died[0].data['final'], 57)

    def test_nothing_happens_before_playing_or_twice_after_death(self):
        session = Session()
        self.assertEqual(session.feed(GONE, 0), [])
        self.play(session, 10)
        self.assertEqual(kinds(session.feed(GONE, 5)), ['death'])
        self.assertEqual(session.feed(GONE, 6), [])

    def test_marks_are_said_once_per_life_and_again_next_life(self):
        session = Session()
        marks = [e for e in self.play(session, 90, 110, 120, 105, 130) if e.kind == 'length_mark']
        self.assertEqual(len(marks), 1)
        session.feed(GONE, 100)
        marks = [e for e in self.play(session, 10, 110, start=200) if e.kind == 'length_mark']
        self.assertEqual(len(marks), 1)

    def test_joining_big_isnt_an_achievement(self):
        session = Session()
        self.assertEqual(kinds(session.feed(at(600), 0)), ['life_start'])

    def test_a_sudden_jump_means_a_big_meal(self):
        session = Session()
        events = self.play(session, 200, 205, 300, step=2.0)
        self.assertIn('big_jump', kinds(events))
        self.assertEqual(next(e for e in events if e.kind == 'big_jump').data['gained'], 100)

    def test_slow_growth_isnt_a_jump(self):
        session = Session()
        self.assertNotIn('big_jump', kinds(self.play(session, *range(200, 400, 4), step=2.0)))
        self.assertNotIn('big_jump', kinds(self.play(Session(), 10, 12, 30, step=2.0)))    # small numbers

    def test_shrinking_from_boosting(self):
        self.assertIn('shrank', kinds(self.play(Session(), 400, 300)))
        self.assertNotIn('shrank', kinds(self.play(Session(), 400, 390)))

    def test_a_new_best_is_announced_once_and_only_past_the_old_one(self):
        session = Session(best=300)
        events = self.play(session, 100, 299, 301, 400, 500)
        best = [e for e in events if e.kind == 'new_best']
        self.assertEqual(len(best), 1)
        self.assertEqual(best[0].data['old'], 300)
        self.assertTrue(best[0].important)

    def test_a_first_game_has_no_old_best_to_beat(self):
        self.assertNotIn('new_best', kinds(self.play(Session(), 100, 200)))

    def test_rank_marks(self):
        session = Session()
        session.feed(at(10, rank=200), 0)
        events = session.feed(at(20, rank=40), 10)
        self.assertEqual([e.data['mark'] for e in events if e.kind == 'rank_mark'], [100, 50])
        self.assertEqual([e.data['mark'] for e in session.feed(at(30, rank=1), 20) if e.kind == 'rank_mark'], [25, 10, 5, 3, 2, 1])
        self.assertEqual(session.life['best_rank'], 1)

    def test_rank_marks_mean_nothing_on_a_tiny_server(self):
        session = Session()
        session.feed(at(10, rank=14, players=14), 0)
        marks = [e.data['mark'] for e in session.feed(at(20, rank=7, players=14), 10) if e.kind == 'rank_mark']
        self.assertEqual(marks, [])       # not "top 10" of 14
        marks = [e.data['mark'] for e in session.feed(at(30, rank=5, players=14), 20) if e.kind == 'rank_mark']
        self.assertEqual(marks, [5])
        self.assertEqual([e.data['mark'] for e in session.feed(at(40, rank=1, players=14), 30) if e.kind == 'rank_mark'], [3, 2, 1])

    def test_summary(self):
        session = Session()
        self.play(session, 10, 200)
        session.feed(GONE, 30)
        self.play(session, 10, 90, start=100)
        session.feed(GONE, 130)
        self.assertEqual(session.summary(), {'lives': 2, 'best': 200, 'best_rank': 200, 'seconds': 60})


class CommentatorTests(unittest.TestCase):
    def event(self, important=False, now=100.0):
        return Event('length_mark', now, {'mark': 100}, important)

    def test_doesnt_talk_over_itself_or_too_often(self):
        talk = Commentator(0.0)
        self.assertIsNotNone(talk.choose([self.event()], 100, busy=False))
        self.assertIsNone(talk.choose([self.event()], 101, busy=False))
        self.assertIsNone(talk.choose([self.event()], 200, busy=True))
        self.assertIsNotNone(talk.choose([self.event()], 200, busy=False))

    def test_important_things_always_get_said(self):
        talk = Commentator(0.0)
        talk.choose([self.event()], 100, busy=False)
        self.assertIsNotNone(talk.choose([self.event(important=True)], 101, busy=True))

    def test_muted_says_nothing_at_all(self):
        talk = Commentator(0.0)
        talk.muted = True
        self.assertIsNone(talk.choose([self.event(important=True)], 100, busy=False))
        self.assertIsNone(talk.choose([], 1000, busy=False, state=at(50)))

    def test_banter_only_after_a_long_silence_while_playing(self):
        talk = Commentator(0.0)
        self.assertIsNone(talk.choose([], 10, busy=False, state=at(50)))
        self.assertEqual(talk.choose([], 60, busy=False, state=at(50)).kind, 'banter')
        self.assertIsNone(talk.choose([], 70, busy=False, state=at(50)))
        self.assertIsNone(talk.choose([], 1000, busy=False, state=GONE))


class LinesTests(unittest.TestCase):
    def test_every_line_stays_in_its_own_language_and_fills_in(self):
        values = dict(gained=100, lost=50, mark=500, old=300, rank=4, players=300, final=800, duration='2 minutes', length=250, top=9000, name='Samash', name_hi='समाश')
        for kind, (english, hindi) in game.LINES.items():
            for option in english:
                said = game._fill(option, values)
                self.assertFalse(DEVANAGARI.search(said), said)
                self.assertNotIn('{', said)
            for option in hindi:
                said = game._fill(option, {**values, 'duration': '2 मिनट'})
                self.assertFalse(LATIN.search(said), said)
                self.assertNotIn('{', said)

    def test_a_missing_name_leaves_no_gap(self):
        said = game._fill("That's your record, {name}! Everything from here is history.", {})
        self.assertEqual(said, "That's your record! Everything from here is history.")

    def test_banter_skips_lines_it_has_no_numbers_for(self):
        for _ in range(30):
            said = game.line('banter', False, length=50, rank=None, players=None, top=None)
            self.assertNotIn('None', said)

    def test_special_remarks(self):
        best = Event('death', 0, {'final': 900, 'seconds': 120, 'was_best': True})
        self.assertIn('best yet', game.remark(best, False))
        one = Event('rank_mark', 0, {'mark': 1, 'rank': 1, 'players': 300})
        self.assertRegex(game.remark(one, False, name='Samash'), 'umber one')
        self.assertIn('2 minutes', game.remark(Event('death', 0, {'final': 9, 'seconds': 125, 'was_best': False}), False) + '2 minutes')

    def test_duration(self):
        self.assertEqual(game.say_duration(125, False), '2 minutes')
        self.assertEqual(game.say_duration(61, False), '1 minute')
        self.assertEqual(game.say_duration(40, False), '40 seconds')
        self.assertEqual(game.say_duration(125, True), '2 मिनट')


class UnderstandTests(unittest.TestCase):
    def test_commands(self):
        for said, kind in (('start commentary', 'start'), ('hey block, commentate on my game', 'start'), ('watch me play', 'start'), ("let's play slither", 'start'), ('commentary shuru karo', 'start'),
                           ('stop commentary', 'stop'), ('game over', 'stop'), ('commentary band karo', 'stop'), ('be quiet', 'mute'), ('shut up', 'mute'), ('chup raho', 'mute'),
                           ('you can talk again', 'unmute'), ('what happened', 'summary'), ("what's happening", 'summary'), ('tell me about the game', 'summary'), ('what happened in my last game', 'summary'), ('how am i doing', 'summary'), ('kya hua', 'summary'),
                           ("what's my high score", 'best'), ('mera record kya hai', 'best'), ('how many times did i die', 'deaths'), ('kitni baar mara', 'deaths'),
                           ("what's my rank", 'now'), ('how long have i been playing', 'time'), ('who killed me', 'killer')):
            self.assertEqual(game.understand(said)[0], kind, said)

    def test_hindi_is_noticed(self):
        self.assertTrue(game.understand('kya hua')[1])
        self.assertFalse(game.understand('what happened')[1])

    def test_commands_for_other_things_are_left_alone(self):
        for said in ('open slither', 'search for snake game', 'play a song', 'what is your name', 'tell me a joke', 'stop', 'quiet place trailer', 'what happened in 1947', 'open the summary doc'):
            self.assertIsNone(game.understand(said)[0], said)


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.memory = Memory(Path(self.folder.name) / 'games' / 'slither.jsonl')

    def test_survives_a_restart_and_a_damaged_line(self):
        self.memory.add('session_start')
        self.memory.add('death', {'final': 100, 'peak': 120})
        with self.memory.path.open('a') as out:
            out.write('{"at": 1, "kind": "dea')     # the power went out mid-write
        again = Memory(self.memory.path)
        self.assertEqual(again.best(), 120)
        self.assertEqual(len(again.deaths()), 1)

    def test_watching_but_seeing_nothing_says_that_not_no_memory(self):
        for kind in ('summary', 'best', 'now'):
            said = game.answer(kind, self.memory, Session(), False, 0)
            self.assertIn("can't see a score", said, kind)
            self.assertNotIn('any games', said)
            self.assertFalse(LATIN.search(game.answer(kind, self.memory, Session(), True, 0)))

    def test_empty_memory_says_so(self):
        self.assertEqual(self.memory.best(), 0)
        self.assertIn('any games', game.answer('summary', self.memory, None, False, 0))
        self.assertIn('any games', game.answer('best', self.memory, None, False, 0))

    def test_summary_covers_the_last_session_only(self):
        self.memory.add('session_start')
        self.memory.add('death', {'final': 9000, 'peak': 9000, 'seconds': 60, 'best_rank': 1})
        self.memory.add('session_start')
        self.memory.add('death', {'final': 100, 'peak': 120, 'seconds': 90, 'best_rank': 40})
        self.memory.add('death', {'final': 200, 'peak': 210, 'seconds': 30, 'best_rank': 25})
        said = game.answer('summary', self.memory, None, False, 0)
        self.assertIn('2 lives', said)
        self.assertIn('Longest was 210', said)
        self.assertIn('best rank 25', said)
        self.assertIn('ended at 200', said)
        self.assertNotIn('9000', said)
        self.assertIn('9000', game.answer('best', self.memory, None, False, 0))
        self.assertEqual(game.answer('deaths', self.memory, None, False, 0), '2 this session, 3 all time.')

    def test_answers_in_hindi_are_pure_hindi(self):
        self.memory.add('session_start')
        self.memory.add('death', {'final': 100, 'peak': 120, 'seconds': 90, 'best_rank': 40})
        session = Session(now=0.0)
        session.feed(at(50), 0)
        for kind in ('summary', 'best', 'deaths', 'now', 'time', 'killer'):
            said = game.answer(kind, self.memory, session, True, 100)
            self.assertFalse(LATIN.search(said), said)

    def test_it_admits_what_it_cant_know(self):
        self.assertIn("can't see", game.answer('killer', self.memory, None, False, 0))
        between_games = Session()
        between_games.feed(at(50), 0)
        between_games.feed(GONE, 10)
        self.assertIn('not in a game', game.answer('now', self.memory, between_games, False, 0))


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        patcher = patch.object(backend_module, 'DATA', Path(self.folder.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.backend = Backend()
        self.backend.emit = Mock(wraps=self.backend.emit)
        self.backend.speaker = Mock()
        self.backend.speaker.speaking.return_value = False
        self.backend.live = False
        self.backend.game_watch = None
        for name in ('require_extension',):
            setattr(self.backend, name, Mock())
        self.backend.game_tab_in_front = Mock(return_value=True)
        timer = patch.object(backend_module.threading, 'Timer')
        self.timer = timer.start()
        self.addCleanup(timer.stop)
        self.addCleanup(lambda: self.backend.game_watch and self.backend.game_watch['stop'].set())

    def start(self):
        with patch.object(browser, 'request', side_effect=RuntimeError('no browser')):
            self.backend.transcript('start commentary', True, source='voice')
        self.backend.game_watch['stop'].set()
        return self.backend.game_watch

    def test_start_answers_and_stop_summarises(self):
        watch = self.start()
        self.backend.game_tick(watch, at(50), 1000.0)
        self.backend.game_tick(watch, GONE, 1060.0)
        self.backend.transcript('stop commentary', True, source='voice')
        self.assertIsNone(self.backend.game_watch)
        said = self.backend.speaker.read_aloud.call_args.args[0]
        self.assertIn('Commentary off', said)
        self.assertIn('1 life', said)

    def test_every_event_is_remembered_even_when_quiet(self):
        watch = self.start()
        self.backend.transcript('be quiet', True, source='voice')
        self.assertTrue(watch['commentator'].muted)
        self.backend.speaker.say.reset_mock()
        self.backend.game_tick(watch, at(50), 1000.0)
        self.backend.game_tick(watch, GONE, 1060.0)
        self.backend.speaker.say.assert_not_called()
        self.assertEqual(len(self.backend.game_memory().deaths()), 1)
        self.backend.transcript('you can talk again', True, source='voice')
        self.assertFalse(watch['commentator'].muted)

    def test_a_death_is_announced(self):
        watch = self.start()
        self.backend.game_tick(watch, at(50), 1000.0)
        self.backend.speaker.say.reset_mock()
        self.backend.game_tick(watch, GONE, 1060.0)
        self.backend.speaker.say.assert_called_once()

    def test_it_doesnt_talk_while_you_are_speaking_to_it(self):
        watch = self.start()
        self.backend.hands_free = Mock(shown='listening')
        self.backend.game_tick(watch, at(10), 1000.0)
        self.backend.speaker.say.reset_mock()
        self.backend.game_tick(watch, at(120), 2000.0)
        self.backend.speaker.say.assert_not_called()

    def test_commentary_never_opens_the_overlay(self):
        watch = self.start()
        self.backend.emit.reset_mock()
        self.backend.game_tick(watch, at(10), 1000.0)
        self.backend.game_tick(watch, GONE, 1060.0)
        self.backend.emit.assert_not_called()

    def test_the_overlay_leaves_after_an_answer_during_a_game(self):
        self.start()
        self.timer.reset_mock()
        self.backend.transcript('what happened', True, source='voice')
        self.timer.assert_called_once()

    def test_quiet_and_stop_only_count_during_a_game(self):
        self.backend.submit_decision = Mock()
        self.assertFalse(self.backend.game_command('be quiet'))
        self.assertFalse(self.backend.game_command('stop commentary'))

    def test_it_says_so_once_if_it_never_finds_a_score(self):
        watch = {'session': Session(), 'commentator': Commentator(), 'stop': threading.Event(), 'memory': self.backend.game_memory()}
        rounds = iter(range(4))
        watch['stop'].wait = lambda timeout: next(rounds, None) is None
        clock = iter([0.0, 40.0, 41.0, 42.0, 43.0, 44.0])
        with patch.object(browser, 'request', return_value={'found': False}), patch.object(backend_module.time, 'monotonic', side_effect=lambda: next(clock)):
            self.backend.watch_game(watch)
        self.assertEqual(self.backend.speaker.say.call_count, 1)
        self.assertIn("can't see a score", self.backend.speaker.say.call_args.args[0])

    def test_what_happened_with_no_game_on_is_just_a_question(self):
        self.assertFalse(self.backend.game_command('what happened'))
        self.backend.game_memory().add('session_start')
        self.assertTrue(self.backend.game_command('what happened in my last game'))

    def test_answers_work_after_a_restart_with_no_game_running(self):
        self.backend.game_memory().add('death', {'final': 100, 'peak': 450, 'seconds': 90, 'best_rank': 40})
        self.backend.transcript("what's my high score", True, source='voice')
        self.assertIn('450', self.backend.speaker.read_aloud.call_args.args[0])

    def test_old_best_carries_over(self):
        self.backend.game_memory().add('death', {'final': 100, 'peak': 450, 'seconds': 90})
        watch = self.start()
        self.assertEqual(watch['session'].best_before, 450)

    def test_old_extension_says_how_to_update(self):
        self.backend.require_extension = Mock(side_effect=RuntimeError('Game commentary: this needs the updated browser extension.'))
        self.assertTrue(self.backend.game_command('start commentary'))
        self.assertIsNone(self.backend.game_watch)
        said = [c.kwargs.get('message', '') for c in self.backend.emit.call_args_list]
        self.assertTrue(any('updated browser extension' in message for message in said))

    def test_watcher_only_reads_and_ignores_other_tabs(self):
        calls = []

        def request(payload, **_):
            calls.append(payload['action'])
            if len(calls) == 1:
                return {'found': True, 'url': 'https://youtube.com/', 'text': 'Your length: 999'}
            if len(calls) == 2:
                return {'found': True, 'url': 'https://slither.io/', 'text': PLAYING}
            watch['stop'].set()
            raise RuntimeError('gone')
        watch = {'session': Session(), 'commentator': Commentator(), 'stop': threading.Event(), 'memory': self.backend.game_memory()}
        with patch.object(browser, 'request', side_effect=request):
            original = watch['stop'].wait
            watch['stop'].wait = lambda timeout: watch['stop'].is_set()
            self.backend.watch_game(watch)
        self.assertEqual(set(calls), {'game_text'})
        self.assertEqual(watch['session'].life['length'], 23)   # only the game's page counted


if __name__ == '__main__':
    unittest.main()
