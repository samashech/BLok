"""Local Gemma 2B Structured Task Compiler for Hyprash.

Implements a 3-stage local hybrid NLU pipeline:
1. Stage 1 — Fast Deterministic Fast-Path (<2ms) for unambiguous commands.
2. Stage 2 — Local Gemma 2B Structured Task Compiler (temperature 0.0, strict JSON schema via Ollama).
3. Stage 3 — Strict Schema Validation & Fallback to deterministic NLU when Ollama is offline.
"""
from dataclasses import dataclass, field
import json
import logging
import os
import re
import time
from typing import Any, Optional
import urllib.error
import urllib.request

from hyprash.commands import Action
from hyprash.nlu import (
    ConversationContext,
    ResolvedIntent,
    normalize_utterance,
    repair_self_corrections,
    resolve_intent,
    split_compound_utterance,
)
from hyprash.plans import Plan, PlanStep, assess_step_risk, _infer_step_attributes

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.environ.get("HYPRASH_OLLAMA_HOST", "http://127.0.0.1:11434")
GEMMA_MODEL_DEFAULT = os.environ.get("HYPRASH_GEMMA_MODEL", "gemma2:2b")

ALLOWED_DOMAINS = {
    "youtube",
    "spotify",
    "google",
    "brave",
    "obsidian",
    "notes",
    "camera",
    "system",
    "terminal",
    "files",
    "code",
}

ALLOWED_INTENTS = {
    "open_tab",
    "search",
    "play_media",
    "select_result",
    "next_track",
    "open_app",
    "create_note",
    "take_photo",
    "run_routine",
}

SYSTEM_PROMPT = """You are a local desktop task compiler for Hyprash. Convert conversational voice commands into structured subtask JSON.
Allowed domains: youtube, spotify, google, brave, obsidian, notes, camera, system, terminal, files, code.
Allowed intents: open_tab, search, play_media, select_result, next_track, open_app, create_note, take_photo, run_routine.

Output strict JSON with schema:
{
  "understood": true,
  "needs_clarification": false,
  "clarification_question": null,
  "subtasks": [
    {"subtask_id": 1, "domain": "...", "intent": "...", "query": "...", "ordinal": 1, "use_active_tab": false}
  ]
}

Examples:
1. User: "yo fire up a tab and look up some games for me"
Output: {"understood": true, "needs_clarification": false, "clarification_question": null, "subtasks": [{"subtask_id": 1, "domain": "brave", "intent": "open_tab", "query": null, "ordinal": 1, "use_active_tab": false}, {"subtask_id": 2, "domain": "google", "intent": "search", "query": "games", "ordinal": 1, "use_active_tab": true}]}

2. User: "open up youtube and put on justin bieber then hop over to spotify and play chill music"
Output: {"understood": true, "needs_clarification": false, "clarification_question": null, "subtasks": [{"subtask_id": 1, "domain": "youtube", "intent": "play_media", "query": "justin bieber", "ordinal": 1, "use_active_tab": false}, {"subtask_id": 2, "domain": "spotify", "intent": "play_media", "query": "chill music", "ordinal": 1, "use_active_tab": false}]}

3. User: "open the second one" (Context: active_site=youtube)
Output: {"understood": true, "needs_clarification": false, "clarification_question": null, "subtasks": [{"subtask_id": 1, "domain": "youtube", "intent": "select_result", "query": null, "ordinal": 2, "use_active_tab": true}]}
"""


@dataclass
class SubtaskItem:
    subtask_id: int
    domain: str
    intent: str
    query: Optional[str] = None
    ordinal: int = 1
    use_active_tab: bool = False
    raw_action: Optional[str] = None

    def validate(self) -> bool:
        return self.domain in ALLOWED_DOMAINS and self.intent in ALLOWED_INTENTS


@dataclass
class CompiledTask:
    understood: bool = True
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    subtasks: list[SubtaskItem] = field(default_factory=list)
    parser_used: str = "fastpath"  # "fastpath" | "gemma2:2b" | "deterministic_fallback"
    latency_ms: float = 0.0


def detect_gemma_model(host: str = OLLAMA_HOST, timeout: float = 0.8) -> Optional[str]:
    """Check if Ollama is running and has a Gemma 2B model installed."""
    try:
        req = urllib.request.Request(f"{host}/api/tags", headers={"User-Agent": "Hyprash/0.6.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", [])]
            for pref in ("gemma2:2b", "gemma:2b"):
                if pref in models:
                    return pref
            for m in models:
                if "gemma" in m and "2b" in m:
                    return m
            if models and any("gemma" in m for m in models):
                return next(m for m in models if "gemma" in m)
    except Exception:
        pass
    return None


def call_gemma_compiler(
    text: str,
    context: Optional[ConversationContext] = None,
    model: str = GEMMA_MODEL_DEFAULT,
    host: str = OLLAMA_HOST,
    timeout: float = 3.5,
) -> Optional[CompiledTask]:
    """Invoke local Gemma 2B via Ollama with strict JSON formatting."""
    t0 = time.monotonic()
    context_str = ""
    if context:
        ctx_parts = []
        if context.active_site:
            ctx_parts.append(f"active_site={context.active_site}")
        if context.active_tab_id:
            ctx_parts.append(f"active_tab_id={context.active_tab_id}")
        if context.active_app:
            ctx_parts.append(f"active_app={context.active_app}")
        if context.search_context:
            ctx_parts.append(f"last_search_query={context.search_context.get('query')}")
        if ctx_parts:
            context_str = f" (Context: {', '.join(ctx_parts)})"

    prompt = f"{SYSTEM_PROMPT}\nUser: \"{text}\"{context_str}\nOutput:"

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "keep_alive": "60m",
        "options": {
            "temperature": 0.0,
            "num_predict": 256,
        },
    }

    try:
        req = urllib.request.Request(
            f"{host}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "Hyprash/0.6.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            raw_response = res_data.get("response", "{}")
            parsed = json.loads(raw_response)

            subtasks: list[SubtaskItem] = []
            for st in parsed.get("subtasks", []):
                item = SubtaskItem(
                    subtask_id=int(st.get("subtask_id", len(subtasks) + 1)),
                    domain=str(st.get("domain", "")).lower().strip(),
                    intent=str(st.get("intent", "")).lower().strip(),
                    query=st.get("query"),
                    ordinal=int(st.get("ordinal", 1)),
                    use_active_tab=bool(st.get("use_active_tab", False)),
                )
                if item.validate():
                    subtasks.append(item)

            dur_ms = (time.monotonic() - t0) * 1000.0
            return CompiledTask(
                understood=bool(parsed.get("understood", True)),
                needs_clarification=bool(parsed.get("needs_clarification", False)),
                clarification_question=parsed.get("clarification_question"),
                subtasks=subtasks,
                parser_used=model,
                latency_ms=dur_ms,
            )
    except Exception as e:
        logger.debug(f"Gemma 2B compilation fallback triggered: {e}")
        return None


def is_fastpath_eligible(raw_text: str) -> bool:
    """Determine if utterance can be parsed deterministically with <2ms latency."""
    t = repair_self_corrections(raw_text).lower().strip()
    # Single commands without sequencers
    if any(seq in t for seq in (" then ", ", then ", ";", " and then ")):
        return False

    # Check common deterministic fastpath patterns
    fast_patterns = [
        r"^(?:open|create)? ?(?:a )?(?:new )?tabs?$",
        r"^stop(?: listening)?$",
        r"^(?:run|start|execute) (?:the )?[a-z0-9_-]+ routine$",
        r"^(?:open|launch|start) (?:notes|camera|terminal|code|files|obsidian)$",
        r"^take (?:a )?(?:picture|photo|selfie)$",
        r"^(?:next track|skip track)$",
        r"^(?:approve|reject|cancel|yes|no)$",
    ]
    return any(re.match(p, t) for p in fast_patterns)


def compile_task_fallback(
    text: str, context: Optional[ConversationContext] = None
) -> CompiledTask:
    """Deterministic Tier 1 fast-path / fallback compiler."""
    t0 = time.monotonic()
    cleaned = repair_self_corrections(text)
    clauses = split_compound_utterance(cleaned)

    subtasks: list[SubtaskItem] = []
    active_ctx = context or ConversationContext()

    for i, clause in enumerate(clauses, 1):
        intent = resolve_intent(clause, active_ctx)
        domain = "system"
        intent_name = "open_app"
        query = None
        ordinal = 1
        use_active_tab = False

        if intent.intent_type == "new_tab":
            domain = "brave"
            intent_name = "open_tab"
        elif intent.intent_type == "search":
            domain = intent.slots.get("site", "google")
            intent_name = "search"
            query = intent.slots.get("query")
            use_active_tab = bool(i > 1 and subtasks and subtasks[-1].intent == "open_tab")
        elif intent.intent_type == "play":
            domain = intent.slots.get("site", "youtube")
            intent_name = "play_media"
            query = intent.slots.get("query")
        elif intent.intent_type == "select_result":
            domain = intent.slots.get("site", active_ctx.active_site or "google")
            intent_name = "select_result"
            ordinal = int(intent.slots.get("ordinal", 1))
            use_active_tab = True
        elif intent.intent_type == "next_track":
            domain = "spotify"
            intent_name = "next_track"
        elif intent.intent_type == "open_app":
            app = intent.slots.get("app", "app")
            if app in ("notes", "hyprash_notes"):
                domain = "notes"
                intent_name = "open_app"
            elif app == "obsidian":
                domain = "obsidian"
                intent_name = "open_app"
            elif app in ("camera", "hyprash_camera"):
                domain = "camera"
                intent_name = "open_app"
            elif app == "terminal":
                domain = "terminal"
                intent_name = "open_app"
            else:
                domain = "system"
                intent_name = "open_app"
                query = app
        elif intent.intent_type == "create_note":
            domain = "notes"
            intent_name = "create_note"
            query = intent.slots.get("title") or intent.slots.get("content")
        elif intent.intent_type == "take_photo":
            domain = "camera"
            intent_name = "take_photo"
        elif intent.intent_type == "routine":
            domain = "system"
            intent_name = "run_routine"
            query = intent.slots.get("routine")
        elif intent.intent_type == "empty":
            continue
        else:
            # General fallback mapping
            domain = "system"
            intent_name = "open_app"
            query = intent.action_value or clause

        subtasks.append(
            SubtaskItem(
                subtask_id=i,
                domain=domain,
                intent=intent_name,
                query=query,
                ordinal=ordinal,
                use_active_tab=use_active_tab,
            )
        )

    dur_ms = (time.monotonic() - t0) * 1000.0
    return CompiledTask(
        understood=len(subtasks) > 0,
        subtasks=subtasks,
        parser_used="fastpath" if len(clauses) <= 1 and is_fastpath_eligible(text) else "deterministic_fallback",
        latency_ms=dur_ms,
    )


def compile_task(
    text: str,
    context: Optional[ConversationContext] = None,
    allow_llm: bool = True,
    timeout: float = 3.5,
) -> CompiledTask:
    """Compile natural voice utterance into a structured task with Gemma 2B or deterministic fallback."""
    cleaned = repair_self_corrections(text).strip()
    if not cleaned or cleaned in (".", "..", "...", " ."):
        return CompiledTask(understood=False, parser_used="fastpath")

    # Stage 1: Fastpath (<2ms)
    if is_fastpath_eligible(cleaned):
        return compile_task_fallback(cleaned, context)

    # Stage 2: Local Gemma 2B Structured Task Compiler
    if allow_llm:
        gemma_model = detect_gemma_model()
        if gemma_model:
            compiled = call_gemma_compiler(cleaned, context, model=gemma_model, timeout=timeout)
            if compiled and compiled.subtasks:
                return compiled

    # Stage 3: Deterministic fallback
    return compile_task_fallback(cleaned, context)


def compiled_task_to_plan(
    compiled: CompiledTask, context: Optional[ConversationContext] = None
) -> Plan:
    """Convert validated SubtaskItems into bounded PlanSteps with DAG bindings."""
    steps: list[PlanStep] = []
    ctx = context or ConversationContext()

    for idx, st in enumerate(compiled.subtasks, 1):
        step_id = f"step_{idx}"
        subtask_id = f"subtask_{st.subtask_id}"

        # Map to Hyprash Action
        action: Optional[Action] = None
        domain_scope = f"browser:{st.domain}" if st.domain in ("youtube", "spotify", "google", "brave") else f"desktop:{st.domain}"

        if st.intent == "open_tab":
            action = Action("web_task", '{"action": "new_tab"}')
            domain_scope = "browser:general"
        elif st.intent == "search":
            site = st.domain if st.domain in ("google", "youtube", "spotify") else "google"
            action = Action("web_task", json.dumps({"action": "search", "site": site, "query": st.query or ""}))
            domain_scope = f"browser:{site}"
        elif st.intent == "play_media":
            site = st.domain if st.domain in ("youtube", "spotify") else "youtube"
            action = Action("web_task", json.dumps({"action": "play", "site": site, "query": st.query or ""}))
            domain_scope = f"browser:{site}"
        elif st.intent == "select_result":
            site = st.domain if st.domain in ("youtube", "google") else "youtube"
            action = Action("web_task", json.dumps({"action": "result", "index": st.ordinal, "play": (site == "youtube")}))
            domain_scope = f"browser:{site}"
        elif st.intent == "next_track":
            action = Action("web_task", '{"action": "next_track"}')
            domain_scope = "browser:spotify"
        elif st.intent == "open_app":
            action = Action("open", st.query or st.domain)
        elif st.intent == "create_note":
            action = Action("new_note", st.query or "Untitled")
            domain_scope = "desktop:notes"
        elif st.intent == "take_photo":
            action = Action("photo", "camera")
            domain_scope = "desktop:camera"
        elif st.intent == "run_routine":
            action = Action("routine", st.query or "morning")
            domain_scope = "system"

        if not action:
            continue

        domain, idemp, pre, post = _infer_step_attributes(action.kind, action.value)
        risk, req_appr, reason = assess_step_risk(action.kind, action.value)

        deps: list[str] = []
        input_binds: list[tuple[str, str]] = []
        output_bind = None

        if action.kind == "web_task" and '"action": "new_tab"' in action.value:
            output_bind = "tab_id"

        # Tab continuity & output-to-input binding
        if steps and st.use_active_tab:
            prev = steps[-1]
            if prev.output_binding == "tab_id":
                deps.append(prev.step_id)
                input_binds.append(("target_tab_id", f"{prev.step_id}.tab_id"))

        step = PlanStep(
            kind=action.kind,
            value=action.value,
            offset=0,
            step_id=step_id,
            subtask_id=subtask_id,
            domain_scope=domain_scope,
            target_domain=domain_scope,
            depends_on=tuple(deps),
            idempotency=idemp,
            preconditions=tuple(pre),
            postconditions=tuple(post),
            on_failure="ABORT_DEPENDENT",
            target_tab_id=ctx.active_tab_id if (st.use_active_tab and not input_binds) else None,
            output_binding=output_bind,
            input_bindings=tuple(input_binds),
            risk_level=risk,
            requires_approval=req_appr,
            approval_reason=reason,
        )
        steps.append(step)

    return Plan(tuple(steps))
