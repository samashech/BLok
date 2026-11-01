"""Local Laya selects intents; Python validates the bounded action arguments."""
import os
import json
import math
import re
import threading
import time
from pathlib import Path
from dataclasses import dataclass

from blok.commands import Action, parse
from blok.paths import MODELS
from blok.workflows import task_label

ROOT = Path(__file__).resolve().parent.parent
MODEL_ID = "convaiinnovations/laya"
REVISION = "55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851"


@dataclass
class Decision:
    action: Action | None
    intent: str
    probability: float
    elapsed_ms: int
    reason: str = ""

class LayaDecision:
    def __init__(self, agent=None):
        self.agent = agent
        # The decision worker and the action worker (file/link picking) share one model.
        self.lock = threading.Lock()

    def load(self):
        with self.lock:
            if self.agent is not None: return
            os.environ.setdefault("HF_HOME", str(MODELS / "huggingface"))
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            os.environ["USE_TF"] = "0"
            os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
            os.environ["TOKENIZERS_PARALLELISM"] = "false"
            import laya
            import torch
            torch.set_num_threads(4)
            self.agent = laya.load(MODEL_ID, device="cpu", revision=REVISION)

    def distribution(self, text, options, instructions):
        """Laya's probability for each option of one bounded choice question."""
        self.load()
        with self.lock:
            answer = self.agent.predict(text, {"decision": {"type":"choice",
                "instructions":instructions, "criteria":dict.fromkeys(options, "")}})
        usage = answer.get("usage", {})
        if usage.get("truncated") or usage.get("truncated_questions"):
            raise ValueError("Request is too long for the local decision model. Use a shorter command.")
        result = answer["answers"]["decision"]
        probabilities = {option: float(result["probabilities"].get(option, 0.0)) for option in options}
        if not all(math.isfinite(p) for p in probabilities.values()):
            raise ValueError("Laya returned an invalid decision score")
        return probabilities

    def choose(self, text, criteria, instructions):
        probabilities = self.distribution(text, list(criteria), instructions)
        ranked = sorted(probabilities.items(), key=lambda kv: -kv[1])
        choice, probability = ranked[0]
        margin = probability - (ranked[1][1] if len(ranked) > 1 else 0)
        return choice, probability, margin

    def pick(self, text, options, instructions, threshold=0.5):
        """Choose one of ≤9 concrete candidates (files, links), or None when unsure."""
        from blok.router import NONE
        probabilities = self.distribution(text, list(options)[:9] + [NONE], instructions)
        choice, probability = max(probabilities.items(), key=lambda kv: kv[1])
        return (choice, probability) if choice != NONE and probability >= threshold else (None, probability)

    def plan(self, text, context=None):
        from blok.plans import Plan, proposals
        candidates = proposals(text, context)
        decisions = [self.route(clause) if action is None else self.decide(clause, proposed=action)
                     for clause, action in candidates]
        rejected = next((d for d in decisions if d.action is None), None)
        if rejected:
            return Decision(None, 'plan', rejected.probability,
                            sum(d.elapsed_ms for d in decisions), rejected.reason + ' Nothing was run.')
        return Decision(Plan(tuple(d.action for d in decisions)), 'plan',
                        min(d.probability for d in decisions), sum(d.elapsed_ms for d in decisions))

    def route(self, text):
        """Two-stage Laya routing for a clause no rule understood."""
        from blok.nlu import repair_self_corrections, normalize_utterance
        from blok.plans import PlanStep
        from blok import router
        started = time.monotonic()
        text_clean = normalize_utterance(repair_self_corrections(text))
        if re.search(r"\b(?:don't|do not|never|cancel(?: that)?)\b", text_clean, re.I):
            return Decision(None, "none", 1.0, 0, "Request cancelled; no action taken")
        result = router.route(text_clean, self.distribution)
        action = None
        if result.action is not None:
            action = PlanStep.from_action(result.action)
            if result.needs_approval:
                from dataclasses import replace
                action = replace(action, requires_approval=True,
                                 approval_reason=f"{self.action_label(result.action)}? ({round(result.probability*100)}% sure)")
        return Decision(action, result.intent, result.probability,
                        round((time.monotonic()-started)*1000), result.reason)

    @staticmethod
    def action_label(action):
        from blok import router
        if action.kind == "tool":
            return router.label(json.loads(action.value))
        if action.kind in ("web_task", "ui_control"):
            return task_label(json.loads(action.value))
        return (action.kind + " " + action.value).strip()

    def decide(self, text, proposed=None):
        from blok.nlu import repair_self_corrections
        started = time.monotonic()
        text_clean = repair_self_corrections(text)
        parsed = [proposed] if proposed is not None else parse(text_clean)
        if len(parsed) != 1:
            return self.route(text)
        # The grammar extracts literal arguments and shortlists valid actions.
        # Laya must accept the proposal; rejection never falls back to execution.
        proposed = parsed[0]
        labels = {
            "address": "Focus the browser address bar",
            "browser_type": "Type " + proposed.value + " in the browser address bar",
            "browser_key": "Browser: " + proposed.value,
            "open": "Open " + proposed.value.replace("_", " "),
            "new_note": "Create a new note titled " + proposed.value,
            "title": "Change the note title to " + proposed.value,
            "write": "Write " + proposed.value,
            "photo": "Take photo",
            "workspace": "Switch to workspace " + proposed.value,
            "stop": "Stop listening",
            "url": ("Search the web" if "/search?q=" in proposed.value else "Open the website " + proposed.value.removeprefix("https://")),
        }
        if proposed.kind in ('web_task','ui_control','tool'):
            label = self.action_label(proposed)
        elif proposed.kind=='obsidian_note':
            label='Create a note saying '+json.loads(proposed.value)['content']+' in Obsidian'
        elif proposed.kind=='routine':
            from blok.routines import get_routine
            routine = get_routine(proposed.value)
            name = routine.name.replace('_', ' ') if routine else proposed.value.replace('_', ' ')
            label = f"Run the {name} routine"
        else:
            label = labels[proposed.kind]
        # Explicit alternative prevents opening Notes from becoming a new note.
        criteria = {label:"", "Do nothing":""}
        choice, probability, margin = self.choose(text_clean, criteria, "Choose the action requested by the user.")
        action = proposed if choice == label else None
        intent = proposed.kind if action else "none"
        reason = ""
        if re.search(r"\b(?:don't|do not|never|cancel(?: that)?)\b", text_clean, re.I):
            action = None
            reason = "Request cancelled; no action taken"
        elif probability < 0.60 or margin < 0.15 or action is None:
            action = None
            reason = "I’m not sure which action you want. Try a shorter request."
        return Decision(action, intent, probability, round((time.monotonic()-started)*1000), reason)
