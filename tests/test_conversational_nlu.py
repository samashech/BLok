"""Comprehensive tests for conversational natural language understanding in Hyprash.

Tests 40+ conversational variations across:
1. Casual slang & phrasal verbs
2. Conversational filler stripping with entity preservation
3. Speech disfluencies and mid-sentence repairs / self-corrections
4. Multi-clause compound utterances
5. Contextual follow-up resolution & working memory continuity
6. Empty speech guards & ASR quirks
"""
import unittest
from unittest.mock import patch

from hyprash.nlu import (
    ConversationContext,
    ResolvedIntent,
    normalize_utterance,
    repair_self_corrections,
    resolve_intent,
)
from hyprash.plans import proposals


class ConversationalNLUTests(unittest.TestCase):
    def setUp(self):
        self.context = ConversationContext()

    # --- 1. Casual Slang & Phrasal Verbs (10 tests) ---
    def test_slang_fire_up_terminal(self):
        intent = resolve_intent("fire up foot", self.context)
        self.assertEqual(intent.intent_type, "open_app")
        self.assertEqual(intent.slots.get("app"), "terminal")

    def test_slang_spin_up_app(self):
        intent = resolve_intent("spin up code", self.context)
        self.assertEqual(intent.intent_type, "open_app")
        self.assertEqual(intent.slots.get("app"), "code")

    def test_slang_hop_over_to_site(self):
        intent = resolve_intent("hop over to youtube", self.context)
        self.assertEqual(intent.intent_type, "navigate")
        self.assertEqual(intent.slots.get("url"), "https://www.youtube.com")

    def test_slang_pull_up_app(self):
        intent = resolve_intent("pull up nautilus", self.context)
        self.assertEqual(intent.intent_type, "open_app")
        self.assertEqual(intent.slots.get("app"), "files")

    def test_slang_pop_open_notes(self):
        intent = resolve_intent("pop open notes", self.context)
        self.assertEqual(intent.intent_type, "open_app")
        self.assertEqual(intent.slots.get("app"), "notes")

    def test_slang_look_up_search(self):
        intent = resolve_intent("look up rust tutorials", self.context)
        self.assertEqual(intent.intent_type, "search")
        self.assertEqual(intent.slots.get("query"), "rust tutorials")

    def test_slang_check_out_search(self):
        intent = resolve_intent("check out arch linux wiki", self.context)
        self.assertEqual(intent.intent_type, "search")
        self.assertEqual(intent.slots.get("query"), "arch linux wiki")

    def test_slang_blast_media(self):
        intent = resolve_intent("blast bohemian rhapsody on spotify", self.context)
        self.assertEqual(intent.intent_type, "play")
        self.assertEqual(intent.slots.get("site"), "spotify")
        self.assertEqual(intent.slots.get("query"), "bohemian rhapsody")

    def test_slang_throw_on_media(self):
        intent = resolve_intent("throw on lo-fi beats on youtube", self.context)
        self.assertEqual(intent.intent_type, "play")
        self.assertEqual(intent.slots.get("site"), "youtube")
        self.assertEqual(intent.slots.get("query"), "lo-fi beats")

    def test_slang_bare_tab_variants(self):
        for phrase in ("tab", "tabs", "open a tab", "gimme a tab", "fresh tab", "another tab"):
            intent = resolve_intent(phrase, self.context)
            self.assertEqual(intent.intent_type, "new_tab", f"Failed on phrase: '{phrase}'")

    # --- 2. Conversational Filler Stripping with Entity Preservation (8 tests) ---
    def test_filler_stripping_yo_bro_can_you(self):
        intent = resolve_intent("yo bro can you please fire up foot right now", self.context)
        self.assertEqual(intent.intent_type, "open_app")
        self.assertEqual(intent.slots.get("app"), "terminal")

    def test_filler_stripping_dude_for_me(self):
        intent = resolve_intent("dude search for arch hyprland for me", self.context)
        self.assertEqual(intent.intent_type, "search")
        self.assertEqual(intent.slots.get("query"), "arch hyprland")

    def test_filler_stripping_i_wanna(self):
        intent = resolve_intent("i wanna look up python async tutorials", self.context)
        self.assertEqual(intent.intent_type, "search")
        self.assertEqual(intent.slots.get("query"), "python async tutorials")

    def test_filler_stripping_real_quick(self):
        intent = resolve_intent("open notes real quick", self.context)
        self.assertEqual(intent.intent_type, "open_app")
        self.assertEqual(intent.slots.get("app"), "notes")

    def test_entity_preservation_hey_jude(self):
        intent = resolve_intent("play hey jude on youtube", self.context)
        self.assertEqual(intent.intent_type, "play")
        self.assertEqual(intent.slots.get("query"), "hey jude")

    def test_entity_preservation_query_with_please(self):
        intent = resolve_intent("search for help me please on google", self.context)
        self.assertEqual(intent.intent_type, "search")
        self.assertEqual(intent.slots.get("query"), "help me please")

    def test_entity_preservation_quoted_message(self):
        steps = proposals('create a note saying "can you please help me right now" in obsidian')
        self.assertEqual(steps[0][1].value, '{"content": "can you please help me right now"}')

    def test_filler_stripping_with_routine_proposal(self):
        intent = resolve_intent("could you please run routine morning_flow right now", self.context)
        self.assertEqual(intent.intent_type, "routine")
        self.assertEqual(intent.slots.get("name"), "morning_flow")

    # --- 3. Speech Disfluencies & Mid-Sentence Repairs (8 tests) ---
    def test_repair_app_no_wait(self):
        text = repair_self_corrections("open spotify—no wait, open youtube")
        self.assertEqual(text, "open youtube")
        intent = resolve_intent("open spotify—no wait, open youtube", self.context)
        self.assertEqual(intent.intent_type, "navigate")
        self.assertEqual(intent.slots.get("url"), "https://www.youtube.com")

    def test_repair_search_actually(self):
        text = repair_self_corrections("search for cats actually dogs")
        self.assertEqual(text, "search for dogs")
        intent = resolve_intent("search for cats actually dogs", self.context)
        self.assertEqual(intent.intent_type, "search")
        self.assertEqual(intent.slots.get("query"), "dogs")

    def test_repair_app_scratch_that(self):
        text = repair_self_corrections("fire up foot scratch that open nautilus")
        self.assertEqual(text, "open nautilus")
        intent = resolve_intent("fire up foot scratch that open nautilus", self.context)
        self.assertEqual(intent.intent_type, "open_app")
        self.assertEqual(intent.slots.get("app"), "files")

    def test_repair_app_wait_no(self):
        text = repair_self_corrections("open code wait no open notes")
        self.assertEqual(text, "open notes")
        intent = resolve_intent("open code wait no open notes", self.context)
        self.assertEqual(intent.intent_type, "open_app")
        self.assertEqual(intent.slots.get("app"), "notes")

    def test_repair_media_i_mean(self):
        text = repair_self_corrections("play despacito on youtube i mean lofi on spotify")
        self.assertEqual(text, "play lofi on spotify")

    def test_repair_tab_no_actually(self):
        intent = resolve_intent("open terminal no wait open a new tab", self.context)
        self.assertEqual(intent.intent_type, "new_tab")

    def test_cancellation_veto_not_triggered_by_repair(self):
        intent = resolve_intent("open foot actually nautilus", self.context)
        self.assertNotEqual(intent.intent_type, "cancel")
        self.assertEqual(intent.intent_type, "open_app")
        self.assertEqual(intent.slots.get("app"), "files")

    def test_genuine_cancellation_veto_still_works(self):
        intent = resolve_intent("never mind cancel that", self.context)
        self.assertEqual(intent.intent_type, "cancel")

    # --- 4. Multi-Clause Compound Utterances (6 tests) ---
    def test_compound_tab_and_search(self):
        steps = proposals("open a tab and look up arch linux", self.context)
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0][1].kind, "web_task")
        self.assertEqual(steps[1][1].kind, "web_task")

    def test_compound_open_app_and_write_note(self):
        steps = proposals("open notes and write buy milk", self.context)
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0][1].kind, "open")
        self.assertEqual(steps[1][1].kind, "write")
        self.assertEqual(steps[1][1].value, "buy milk")

    def test_compound_slang_with_and(self):
        steps = proposals("fire up foot and open notes", self.context)
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0][1].kind, "open")
        self.assertEqual(steps[0][1].value, "terminal")
        self.assertEqual(steps[1][1].kind, "open")
        self.assertEqual(steps[1][1].value, "notes")

    def test_compound_then_conjunction(self):
        steps = proposals("open a tab then look up games", self.context)
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0][1].kind, "web_task")
        self.assertEqual(steps[1][1].kind, "web_task")

    def test_compound_tab_id_continuity_contract(self):
        steps = proposals("open a tab and search for weather on google", self.context)
        step1 = steps[0][1]
        step2 = steps[1][1]
        self.assertEqual(getattr(step1, "output_binding", None), "tab_id")
        self.assertIn("target_tab_id", getattr(step2, "input_bindings_dict", {}))

    @patch("hyprash.routines.get_routine")
    def test_compound_routine_proposal(self, mock_get_routine):
        from hyprash.routines import Routine
        mock_get_routine.return_value = Routine("morning_flow", "Morning flow", [], [{"kind": "open", "value": "notes"}])
        steps = proposals("run routine morning_flow and open code", self.context)
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0][1].kind, "routine")
        self.assertEqual(steps[1][1].kind, "open")

    # --- 5. Contextual Follow-up Resolution (5 tests) ---
    def test_contextual_result_selection_first(self):
        self.context.set_search_context(tab_id=12, url="https://youtube.com/results?search_query=lofi", site="youtube", query="lofi")
        intent = resolve_intent("play the first one", self.context)
        self.assertEqual(intent.intent_type, "result")
        self.assertEqual(intent.action_kind, "web_task")
        self.assertEqual(intent.slots.get("target_tab_id"), 12)
        self.assertEqual(intent.slots.get("index"), 1)

    def test_contextual_result_selection_second(self):
        self.context.set_search_context(tab_id=42, url="https://google.com/search?q=hyprland", site="google", query="hyprland")
        intent = resolve_intent("click the second result", self.context)
        self.assertEqual(intent.intent_type, "result")
        self.assertEqual(intent.action_kind, "web_task")
        self.assertEqual(intent.slots.get("target_tab_id"), 42)
        self.assertEqual(intent.slots.get("index"), 2)

    def test_context_active_tab_inherited(self):
        self.context.update_tab(tab_id=99, url="https://news.ycombinator.com", site="news.ycombinator.com")
        self.assertEqual(self.context.active_tab_id, 99)
        self.assertEqual(self.context.active_domain, "news.ycombinator.com")

    def test_context_expiration_check(self):
        self.context.set_search_context(tab_id=5, url="https://google.com/search?q=test", site="google", query="test")
        self.assertTrue(self.context.is_search_context_valid())
        self.context.search_context["created_at"] = 0  # simulate expiration past TTL
        self.assertFalse(self.context.is_search_context_valid())

    def test_context_cleared_on_explicit_new_search(self):
        self.context.set_search_context(tab_id=5, url="https://google.com/search?q=test", site="google", query="test")
        self.context.clear_search_context()
        self.assertIsNone(self.context.search_context)

    # --- 6. Empty Speech Guards & ASR Transcription Quirks (4 tests) ---
    def test_empty_speech_guard_dot(self):
        intent = resolve_intent(" .", self.context)
        self.assertEqual(intent.intent_type, "empty")

    def test_empty_speech_guard_whitespace(self):
        intent = resolve_intent("   ", self.context)
        self.assertEqual(intent.intent_type, "empty")

    def test_empty_speech_guard_dots_and_commas(self):
        intent = resolve_intent("...,", self.context)
        self.assertEqual(intent.intent_type, "empty")

    def test_empty_speech_guard_bare_empty(self):
        intent = resolve_intent("", self.context)
        self.assertEqual(intent.intent_type, "empty")


if __name__ == "__main__":
    unittest.main()
