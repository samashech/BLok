"""Tests for Hyprash Natural Language Understanding (NLU) pipeline.

Validates conversational normalization, deterministic intent resolution,
slot extraction, entity preservation, contextual continuations, and TTL expiration.
"""
import json
import time
import unittest

from hyprash.nlu import (
    ConversationContext,
    ResolvedIntent,
    normalize_utterance,
    resolve_intent,
    split_compound_utterance,
)


class ConversationalNormalizationTests(unittest.TestCase):
    def test_strip_conversational_prefixes(self):
        cases = [
            ("can you please open a new tab", "open a new tab"),
            ("could you open Spotify", "open Spotify"),
            ("hey Hyprash, open terminal", "open terminal"),
            ("okay please search for games", "search for games"),
            ("i want you to search for weather", "search for weather"),
            ("let's play God's Plan on Spotify", "play God's Plan on Spotify"),
            ("go ahead and take a picture", "take a picture"),
            ("just reload the page", "reload the page"),
            ("now please open code", "open code"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_utterance(raw).lower(), expected.lower())

    def test_strip_conversational_suffixes(self):
        cases = [
            ("open a new tab for me please", "open a new tab"),
            ("search for games right now", "search for games"),
            ("take a photo for me", "take a photo"),
            ("open code please", "open code"),
            ("skip this song thanks", "skip this song"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_utterance(raw).lower(), expected.lower())

    def test_preserves_conjunctions_in_entities(self):
        cases = [
            "search for rock and roll",
            "search for dungeons and dragons",
            "search for bread and butter",
            "search for peace and love",
        ]
        for raw in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_utterance(raw).lower(), raw.lower())

    def test_preserves_quoted_strings(self):
        raw = 'create a note saying "hello and welcome to my world" in obsidian'
        norm = normalize_utterance(raw)
        self.assertIn('"hello and welcome to my world"', norm)


class CompoundUtteranceSplittingTests(unittest.TestCase):
    def test_splits_multi_step_compound_requests(self):
        text = "Open YouTube and play a Justin Bieber song, then open Spotify and play something new"
        chunks = split_compound_utterance(text)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0], "Open YouTube and play a Justin Bieber song")
        self.assertEqual(chunks[1], "open Spotify and play something new")

    def test_splits_tab_and_search_sequence(self):
        text = "open a new tab and search for games"
        chunks = split_compound_utterance(text)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0], "open a new tab")
        self.assertEqual(chunks[1], "search for games")

    def test_does_not_split_inside_entity_names(self):
        cases = [
            "search for dungeons and dragons",
            "search for rock and roll",
            'create a note saying "buy milk and eggs" in obsidian',
        ]
        for query in cases:
            with self.subTest(query=query):
                chunks = split_compound_utterance(query)
                self.assertEqual(len(chunks), 1)


class IntentResolutionTableTests(unittest.TestCase):
    def test_table_driven_intent_resolution(self):
        table = [
            # 1. Tab creation variations
            ("open a tab", "new_tab", "web_task", {"action": "new_tab"}),
            ("open a new tab", "new_tab", "web_task", {"action": "new_tab"}),
            ("open tab", "new_tab", "web_task", {"action": "new_tab"}),
            ("create a tab", "new_tab", "web_task", {"action": "new_tab"}),
            ("launch a new browser tab", "new_tab", "web_task", {"action": "new_tab"}),
            ("can you open another tab for me?", "new_tab", "web_task", {"action": "new_tab"}),

            # 2. Search variations
            ("search for games", "search", "web_task", {"action": "search", "site": "google", "query": "games"}),
            ("can you look up games for me?", "search", "web_task", {"action": "search", "site": "google", "query": "games"}),
            ("google games", "search", "web_task", {"action": "search", "site": "google", "query": "games"}),
            ("google search arch linux", "search", "web_task", {"action": "search", "site": "google", "query": "arch linux"}),
            ("find games online", "search", "web_task", {"action": "search", "site": "google", "query": "games"}),
            ("search for rock and roll", "search", "web_task", {"action": "search", "site": "google", "query": "rock and roll"}),

            # 3. Direct URL navigation vs search
            ("go to github.com", "navigate", "url", "https://github.com"),
            ("visit youtube.com", "navigate", "url", "https://www.youtube.com"),
            ("open archlinux.org", "navigate", "url", "https://archlinux.org"),
            ("open wikipedia", "navigate", "url", "https://www.wikipedia.org"),

            # 4. Music playback & specific sites
            ("play despacito on youtube", "play", "web_task", {"action": "play", "site": "youtube", "query": "despacito"}),
            ("play God's Plan on Spotify", "play", "web_task", {"action": "play", "site": "spotify", "query": "God's Plan"}),
            ("play a Justin Bieber song on Spotify", "play", "web_task", {"action": "play", "site": "spotify", "query": "Justin Bieber", "mode": "artist"}),
            ("search for lofi on youtube", "search", "web_task", {"action": "search", "site": "youtube", "query": "lofi"}),

            # 5. Result selection follow-ups
            ("open the first result", "result", "web_task", {"action": "result", "index": 1}),
            ("play the second video", "result", "web_task", {"action": "result", "index": 2, "play": True}),
            ("click the third link that showed up", "result", "web_task", {"action": "result", "index": 3}),

            # 6. Browser controls & Address bar
            ("focus the address bar", "address", "address", ""),
            ("press enter", "browser_key", "browser_key", "enter"),
            ("hit enter", "browser_key", "browser_key", "enter"),
            ("go back", "browser_key", "browser_key", "back"),
            ("reload the page", "browser_key", "browser_key", "reload"),

            # 7. Desktop applications
            ("open terminal", "open_app", "open", "terminal"),
            ("launch visual studio code", "open_app", "open", "code"),
            ("open code", "open_app", "open", "code"),
            ("open files", "open_app", "open", "files"),

            # 8. Notes & camera
            ("create a note titled meeting notes", "new_note", "new_note", "meeting notes"),
            ("take a selfie", "photo", "photo", ""),
            ("take a picture of me", "photo", "photo", ""),
            ("create a note saying hello in obsidian", "obsidian_note", "obsidian_note", '{"content": "hello"}'),

            # 9. Stop commands
            ("stop listening", "stop", "stop", ""),
            ("stop", "stop", "stop", ""),
        ]

        for text, exp_intent, exp_kind, exp_val in table:
            with self.subTest(text=text):
                res = resolve_intent(text)
                self.assertEqual(res.intent_type, exp_intent, f"Failed intent for: {text}")
                self.assertEqual(res.action_kind, exp_kind, f"Failed kind for: {text}")
                if isinstance(exp_val, dict):
                    actual_dict = json.loads(res.action_value)
                    for k, v in exp_val.items():
                        self.assertEqual(actual_dict.get(k), v, f"Failed key {k} in {text}")
                else:
                    self.assertEqual(res.action_value, exp_val, f"Failed value for: {text}")

    def test_negation_and_cancellation(self):
        cases = [
            "cancel that",
            "don't open notes",
            "do not search for games",
            "never mind",
        ]
        for c in cases:
            with self.subTest(case=c):
                res = resolve_intent(c)
                self.assertEqual(res.intent_type, "cancel")
                self.assertIsNone(res.action_tuple)

    def test_safety_rejection_for_unsupported_verbs(self):
        cases = [
            "delete all files",
            "erase the disk",
            "format drive c",
            "shut down computer",
            "reboot now",
            "drop database users",
        ]
        for c in cases:
            with self.subTest(case=c):
                res = resolve_intent(c)
                self.assertEqual(res.intent_type, "unsupported")
                self.assertEqual(res.confidence, 0.0)
                self.assertIn("Nothing was run", res.ambiguity_reason)

    def test_under_specified_queries_require_clarification(self):
        # Bare "search" or "play" without payload requires clarification
        res = resolve_intent("search")
        self.assertTrue(res.requires_clarification)
        self.assertEqual(res.intent_type, "clarify")

        res_play = resolve_intent("play")
        self.assertTrue(res_play.requires_clarification)
        self.assertEqual(res_play.intent_type, "clarify")

        # "play something else" without active media context requires clarification
        res_other = resolve_intent("play something else", context=None)
        self.assertTrue(res_other.requires_clarification)
        self.assertEqual(res_other.intent_type, "clarify")


class ContextualContinuationTests(unittest.TestCase):
    def test_follow_up_search_inherits_active_tab_id(self):
        ctx = ConversationContext()
        ctx.update_tab(tab_id=142, site="google")

        res = resolve_intent("search for arch linux", context=ctx)
        self.assertEqual(res.intent_type, "search")
        val = json.loads(res.action_value)
        self.assertEqual(val.get("target_tab_id"), 142)

    def test_spotify_next_track_succeeds_with_active_spotify_context(self):
        ctx = ConversationContext(active_site="spotify")
        res = resolve_intent("skip this song", context=ctx)
        self.assertEqual(res.intent_type, "next_track")
        val = json.loads(res.action_value)
        self.assertEqual(val.get("action"), "next_track")
        self.assertEqual(val.get("site"), "spotify")

    def test_search_context_ttl_enforcement(self):
        ctx = ConversationContext()
        ctx.set_search_context(tab_id=200, url="https://www.google.com/search?q=hyprland", site="google", query="hyprland")

        # Immediately valid
        self.assertTrue(ctx.is_search_context_valid(ttl_seconds=300))

        # Manually backdate created_at to 301 seconds ago
        ctx.search_context["created_at"] = time.monotonic() - 301
        self.assertFalse(ctx.is_search_context_valid(ttl_seconds=300))

        # Clear search context
        ctx.clear_search_context()
        self.assertFalse(ctx.is_search_context_valid())


if __name__ == "__main__":
    unittest.main()
