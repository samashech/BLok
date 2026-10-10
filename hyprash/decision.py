"""Local Laya selects intents; Python validates the bounded action arguments."""
import os
import json
import math
import re
import time
from pathlib import Path
from urllib.parse import quote_plus
from dataclasses import dataclass

from hyprash.commands import Action, parse

ROOT = Path(__file__).resolve().parent.parent
MODEL_ID = "convaiinnovations/laya"
REVISION = "55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851"
# Readable labels matter to this decision checkpoint. Unknown requests are
# classified against concrete supported actions, rather than vague "open/edit" buckets.
APP_LABELS = {"Open browser":"browser", "Open terminal":"terminal", "Open files":"files",
    "Open code editor":"code", "Open notes":"notes", "Open camera":"camera"}
ROUTES = {**{k:("open",v) for k,v in APP_LABELS.items()},
    "Search the web":("search",""), "Create a new note":("new_note",""),
    "Change note title":("title",""), "Write in note":("write",""),
    "Take photo":("photo",""), "Switch workspace":("workspace",""),
    "Stop listening":("stop",""), "No action":("none","")}


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

    def load(self):
        if self.agent is not None: return
        os.environ.setdefault("HF_HOME", str(ROOT / "models/huggingface"))
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

    def choose(self, text, criteria, instructions):
        answer = self.agent.predict(text, {"decision": {"type":"choice",
            "instructions":instructions, "criteria":criteria}})
        usage = answer.get("usage", {})
        if usage.get("truncated") or usage.get("truncated_questions"):
            raise ValueError("Request is too long for the local decision model. Use a shorter command.")
        result = answer["answers"]["decision"]
        values = sorted(result["probabilities"].values(), reverse=True)
        probability = float(result["probabilities"].get(result["choice"], 0))
        margin = probability - (values[1] if len(values) > 1 else 0)
        if not math.isfinite(probability) or not math.isfinite(margin):
            raise ValueError("Laya returned an invalid decision score")
        return result["choice"], probability, margin

    def decide(self, text):
        self.load()
        started = time.monotonic()
        parsed = parse(text)
        # The grammar extracts literal arguments and shortlists valid actions.
        # Laya must accept the proposal; rejection never falls back to execution.
        if len(parsed) == 1:
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
            if proposed.kind in ('web_task','ui_control'):
                task=json.loads(proposed.value)
                label=("Play " + task['query'] + " on Spotify" if task['action']=='play' else
                       "Search " + task.get('site','the current site') + " for " + task.get('query','') if task['action']=='search' else
                       "Open search result " + str(task['index']) if task['action']=='result' else
                       "Click " + task.get('target','') if task['action']=='click' else
                       "Fill the " + task.get('target','') + " field with " + task.get('text',''))
            else:
                label = labels[proposed.kind]
            # Explicit alternative prevents opening Notes from becoming a new note.
            criteria = {label:"", "Do nothing":""}
            choice, probability, margin = self.choose(text, criteria, "Choose the action requested by the user.")
            action = proposed if choice == label else None
            intent = proposed.kind if action else "none"
        else:
            choice, probability, margin = self.choose(text, dict.fromkeys(ROUTES, ""),
                "Choose the action requested by the user.")
            intent, value = ROUTES.get(choice, ("none", ""))
            action = None
            if intent == "open": action = Action("open", value)
            elif intent in ("photo", "stop"): action = Action(intent)
            elif intent == "search":
                match = re.search(r"\b(?:look up|look online for|find(?: online)?|search(?: the web)?(?: for)?)\s+(.+)", text, re.I)
                if match: action = Action("url", "https://www.google.com/search?q="+quote_plus(match[1].strip(" .?!")))
            # Note modifications require explicit literal arguments, never guessed text.
        reason = ""
        if re.search(r"\b(?:don't|do not|never|cancel|actually|instead)\b", text, re.I):
            action = None
            reason = "Request cancelled; no action taken"
        elif probability < 0.60 or margin < 0.15 or action is None:
            action = None
            reason = "I’m not sure which action you want. Try a shorter request."
        return Decision(action, intent, probability, round((time.monotonic()-started)*1000), reason)
