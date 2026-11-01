import json
import unittest

from hyprash.nlu import resolve_intent, tidy_speech
from hyprash.plans import proposals
from hyprash.themes import ThemeStore, THEMES


class TidySpeechTests(unittest.TestCase):
    def test_hesitations_stutters_and_tails(self):
        cases = {
            "yo uh open the uh terminal": "open the terminal",
            "open the open the browser": "open the browser",
            "search for search for minecraft mods": "search for minecraft mods",
            "hey man open spotify or something": "open spotify",
            "can you open the, uh, what's it called, files": "can you open the files",
            "can u open yt": "can you open youtube",
            "look up youtube": "look up youtube",
        }
        for spoken, plain in cases.items():
            self.assertEqual(tidy_speech(spoken), plain, spoken)

    def test_meaningful_like_and_quotes_survive(self):
        self.assertEqual(tidy_speech("i like turtles"), "i like turtles")
        self.assertEqual(tidy_speech("play like a prayer"), "play like a prayer")
        self.assertEqual(tidy_speech('write "uh uh hello" please'), 'write "uh uh hello"')


class EverydayIntentTests(unittest.TestCase):
    def action(self, text):
        intent = resolve_intent(text)
        return intent.action_kind, (json.loads(intent.action_value) if intent.action_value.startswith('{') else intent.action_value)

    def test_look_up_a_site_opens_it(self):
        self.assertEqual(self.action("hey can you look up reddit for me"), ('url', 'https://www.reddit.com'))
        self.assertEqual(self.action("hey can you look up github.com for me"), ('url', 'https://github.com'))
        self.assertEqual(self.action("i need to check my mail"), ('url', 'https://mail.google.com'))

    def test_look_up_a_question_searches_google(self):
        kind, task = self.action("can you look up how to cook pasta for me")
        self.assertEqual((task['site'], task['query']), ('google', 'how to cook pasta'))
        kind, task = self.action("hey can you like google weather in delhi for me")
        self.assertEqual(task['query'], 'weather in delhi')

    def test_media_phrasing(self):
        self.assertEqual(self.action("i wanna see some cat videos on youtube")[1],
                         {'action': 'search', 'site': 'youtube', 'query': 'cat videos'})
        self.assertEqual(self.action("i want to listen to arijit singh")[1]['query'], 'arijit singh')
        self.assertEqual(self.action("put on some lofi")[1]['query'], 'lofi')

    def test_vague_request_asks(self):
        intent = resolve_intent("hey man, open this app or something")
        self.assertTrue(intent.requires_clarification)
        self.assertEqual(intent.ambiguity_reason, "Which app should I open?")

    def test_casual_desktop_requests(self):
        self.assertEqual(self.action("bro can you uh make it louder")[1], {'tool': 'volume', 'op': 'up'})
        self.assertEqual(self.action("what's up with my battery")[1], {'tool': 'answer', 'topic': 'battery'})
        self.assertEqual(self.action("so like, can you, uh, find that resume thing i had")[1], {'tool': 'file_find', 'query': 'resume'})
        self.assertEqual(self.action("find me some funny videos")[0], 'web_task')

    def test_unrouted_clause_after_rule_clause_does_not_crash(self):
        steps = proposals("open youtube and do the thing with the stuff and turn the volume up")
        self.assertIsNone(steps[1][1])
        self.assertEqual(json.loads(steps[2][1].value), {'tool': 'volume', 'op': 'up'})


class SeasonalThemeTests(unittest.TestCase):
    def test_themes_cycle_and_voice(self):
        import tempfile
        self.assertEqual(THEMES[:4], ('omarchy', 'liquid', 'halloween', 'diwali'))
        store = ThemeStore(tempfile.mkdtemp())
        for expected in ('liquid', 'halloween', 'diwali', 'omarchy'):
            store.select('next')
            self.assertEqual(store.selected, expected)
        self.assertEqual(json.loads(resolve_intent("make it spooky").action_value), {'tool': 'theme', 'name': 'halloween'})
        self.assertEqual(json.loads(resolve_intent("switch to the diwali theme").action_value), {'tool': 'theme', 'name': 'diwali'})


if __name__ == '__main__':
    unittest.main()
