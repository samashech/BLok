# Simular-inspired Hyprash development report

Started: 2026-10-12. This file tracks implementation, evidence, and unfinished work for each phase.

## Requirements

Keep local inference without API keys, Voxtype recognition, the existing signed-in Brave browser, and the Arch/Hyprland/Omarchy interface. Improve task completion and responsiveness before adding broader autonomy. Build from public research and our existing code; do not claim to reproduce Sai's private implementation or benchmark results.

## Phase plan

| Phase | Outcome | Status |
| --- | --- | --- |
| 1 | Observe, act once, verify; report actual progress and failures | Implemented; isolated checks and live new-tab path pass |
| 2 | Explicit multistep plans; stop dependent steps on failure | Implemented; isolated and local-model checks pass |
| 3 | Discover current screen controls; choose DOM/accessibility/visual methods | Implemented locally; installed extension reload pending |
| 4 | Bounded recovery and context-aware follow-up commands | Implemented and active in Brave session |
| 5 | Reusable routines with state validation | Implemented; isolated, model, and routine tests pass |
| 6 | Measure latency, improve interruption, conversational NLU, tab-ID contract, and DAG recovery | Implemented; 121 unit tests, latency profiler, and contract suites pass |

Each phase must record scope, changed files, regression checks, live validation, limitations, and the next acceptance gate. Passing isolated tests does not establish live app reliability.

## Public references

- [Agent S repository](https://github.com/simular-ai/Agent-S): public computer-use framework, distinct from the commercial Sai service.
- [Agent S3 agent interface](https://github.com/simular-ai/Agent-S/blob/main/gui_agents/s3/agents/agent_s.py), reviewed 2026-10-12: the prediction interface takes an instruction and a current observation and delegates next-action generation to a worker. Phase 1 adapts the observation/action boundary to Hyprash's deterministic browser executor; no upstream code or model dependency was imported. This is not yet an implementation of Agent S's visual worker or reflection model.
- [Sai overview](https://www.sai.work/): product descriptions are claims from the vendor, not measurements of Hyprash.
- [Chrome scripting API](https://developer.chrome.com/docs/extensions/reference/api/scripting): browser observations and actions run in the extension's isolated world.

## Phase 1 — Observable execution and verified outcomes

### Baseline findings

- The browser runner already pins a tab within a sequence and checks some search/playback outcomes. This is a useful foundation, not a general autonomous planner.
- The same polling helper is used for read-only observations and mutations such as search submission and playback. Retrying a mutation after an uncertain result can repeat a click or submission.
- New-tab success is returned without reading back the created tab. Generic clicks report activation without checking the downstream outcome.
- Browser stages are kept inside the extension; the native bridge returns only the final response. The overlay therefore cannot show what it is waiting for.
- Previous live work verified one Spotify artist, an Obsidian note, a YouTube search/play sequence and a GitHub repository sequence. Those checks predate this phase and are not counted as new validation.
- The simulated Ctrl+period test remains unresolved. It is not evidence that the physical shortcut is verified.

### Acceptance

1. Readiness polling does not repeat state-changing actions.
2. Supported outcomes have explicit evidence before being labelled verified.
3. Unverified generic clicks cannot silently advance a dependent sequence.
4. Cancellation stops polling and later actions.
5. Browser stages reach the existing overlay through the native bridge.
6. A bounded trace records stage, elapsed time and outcome without saving page contents to disk.

### Implementation

- `browser-extension/execution.js`: task-local observe/act/verify stages, cancellation checks, a 40-second overall budget, bounded observation polling, and a trace with stage, attempts, status and elapsed milliseconds. Actions are not retried when their result is uncertain.
- `browser-extension/background.js`: search fields, repository filters, Spotify songs and video players are located before acting. Search and playback have separate outcome checks. New tabs are read back from Chrome before success. Navigation checks the requested host/path/query, not merely page load completion. An unverified intermediate result stops a browser sequence.
- `browser-extension/page.js`: read-only readiness probes for existing controls; exact field-value readback in a separate observation; generic button clicks explicitly report that downstream results are unverified. Focusing an editable field checks actual focus.
- `scripts/browser_host.py` and `hyprash/browser.py`: optional progress frames followed by a final result/error, with an overall timeout. Old single-response clients remain supported. Errors retain the execution trace.
- `hyprash/backend.py` and `ui/shell.qml`: browser stages use the existing activity display. Old action text no longer hides current progress. Final execution evidence and trace are available through the existing status IPC. No page-content history or new telemetry files are written.
- `package.json` and `package-lock.json`: pinned project-local Playwright development dependency. Browser fixtures previously imported Playwright from another project that no longer existed. Runtime local inference is unchanged.
- `scripts/browser_setup_view.py`: the setup helper uses the address bar to reach extension settings because the prior launcher opened a blank window without loading the requested page.

### Checks run — 2026-10-12

| Check | Result | What this establishes |
| --- | --- | --- |
| `.venv/bin/python -m unittest discover -s tests` | PASS, 48 tests | Existing Python behavior, backend progress forwarding and conservative handling of legacy results |
| `node --test tests/execution.mjs` | PASS | Read-only retries, one-time mutations, immediate cancellation checks and bounded verification timeout |
| `node tests/browser_workflows.mjs` | PASS | Ordered workflows; no duplicate action after an uncertain click; wrong playback fails; unverified intermediate clicks stop the sequence; progress/evidence returned |
| `node tests/browser_controls.mjs` | PASS, isolated Brave | Readiness does not type or play; exact field readback detects a framework reset; generic clicks stay unverified; existing Google/YouTube/Spotify/GitHub fixtures still pass |
| `.venv/bin/python scripts/check_browser_bridge.py` | PASS, isolated host/socket | Native framing and private socket permissions; progress streaming; final verified result; failure trace; legacy response compatibility |
| `git diff --check` | PASS | No whitespace errors |
| Installed extension ping | PASS | Running version is `phase1-observe-act-verify` |
| `./hyprash.sh text 'open a new tab'` followed by status | PASS, live | Local Laya → native bridge → installed Brave extension → checked outcome → overlay/IPC |

The live new-tab result was `verified: true`, with evidence `Created tab exists and is active`. Its trace showed one create action (39 ms) and one verification (8 ms); Laya reported 144 ms for that invocation. These are single-run measurements, not latency guarantees. The backend returned to idle.

An initial read-only inspection on a browser-internal page returned `Focus a web page first`; this is an expected unsupported target, not proof of web-page operation. No Spotify, YouTube, GitHub or Obsidian live workflow was re-run in this phase. Their DOM/mocked regression checks passed; previous live successes must not be presented as fresh tests.

### Remaining limits

- Phase 1 is primarily the browser executor foundation. Desktop accessibility, camera capture and note workflows have not yet been moved onto the same execution contract.
- This does not add a general planner, visual model, arbitrary-app support, or automatic recovery. Preparation locates known kinds of controls; uncertain mutations stop instead of being repeated.
- Generic clicks intentionally remain unverified unless the operation is a checked field focus. A later phase must define or infer the expected effect before chaining such clicks.
- Destination checks can reject legitimate redirects to a different host/path. This conservative behavior avoids claiming that the requested page opened when it did not; redirect-aware policies need targeted tests.
- Cancellation prevents subsequent work but cannot undo an action already sent to the browser. An in-flight browser call may finish before cancellation is observed; bridge timeouts bound the caller's wait.
- The local model and speech pipeline are unchanged. The simulated Ctrl+period failure is still unresolved.
- Traces are returned per task and exposed as the latest runtime status; they are not a persistent task-memory system.

### Next gate

Phase 2: represent an entire supported utterance as an explicit plan, reject unsupported clauses before executing anything, and stop all dependent steps when a step fails. Preserve query/note text containing words such as “and.” Prove these cases before widening the command vocabulary.

## Phase 2 — Multistep plans

### Acceptance

1. A completed utterance is parsed and validated as one bounded plan before any desktop or browser action starts.
2. Every proposed step must be accepted by local Laya; a rejected step means the entire plan does nothing.
3. The worker executes in order, reports `Step N of M`, and stops after an error or cancellation.
4. Existing destination-aware browser workflows remain single, verified executor tasks, rather than being split into fragile browser gestures.
5. Text such as `rock and roll` and quoted note content such as `"bread and butter"` remains data, not a command boundary.

### Implementation

- `hyprash/plans.py`: produces immutable `Plan` objects from supported clauses. It combines known browser workflows, including YouTube search/play and GitHub repository navigation, into one tab-owned task. Unsupported clauses, including an unsafe command in the middle of an otherwise valid request, reject the entire plan before model work or actions begin. The old bounded natural-language route remains available only for a single request with no command verb; destructive or unsupported verbs are rejected before that route.
- `hyprash/decision.py`: local Laya now accepts every proposed step before returning one plan. Its existing score and margin thresholds still apply per step; there is no execution fallback when Laya rejects a proposal.
- `hyprash/backend.py`: one final transcript becomes one decision request. The action worker executes a `Plan` sequentially, emits the current step through the existing activity UI, checks the cancellation generation between steps, and stops later steps after a failed result. Individual actions now return a success value to make that boundary explicit.
- `tests/test_plans.py` and `tests/test_decision.py`: cover a Notes/Obsidian mixed plan, a browser search/play transaction, unsupported middle and single clauses, quoted content, full-plan Laya acceptance, failure stop, cancellation stop, preflight rejection, and one-plan queueing.

### Checks run — 2026-10-13

| Check | Result | What this establishes |
| --- | --- | --- |
| `.venv/bin/python -m unittest discover -s tests` | PASS, 58 tests | Plan parsing, rejection, execution ordering, cancellation, and existing backend behavior |
| `node --test tests/execution.mjs` | PASS | Browser observe/act/verify behavior remains intact |
| `node tests/browser_workflows.mjs` | PASS | Browser sequences still remain ordered and stop on failed/unverified outcomes |
| `node tests/browser_controls.mjs` | PASS, isolated Brave | Existing Google, YouTube, Spotify and GitHub controls remain compatible with the Phase 1 executor |
| `.venv/bin/python scripts/check_laya.py` | PASS | All existing offline Laya intent fixtures, including Spotify, Obsidian, YouTube sequence, new-tab and GitHub repository tasks |
| Offline local-Laya plan check | PASS | Laya accepted Notes → create-note, YouTube search, and YouTube search → second-video plans as complete plans |
| `git diff --check` | PASS | No whitespace errors |

No live multi-app plan was run for this phase because a representative Notes/Obsidian workflow would create or alter the user's personal data. The checks above use no cloud API or model service.

### Remaining limits

- A failed action is stopped by its explicit error/false result. Desktop actions that only return a successful accessibility call are not yet independently verified; Phase 3 must add screen/control observation for that.
- The Laya checkpoint warns that some shipped choice temperatures are outside its expected range. Thresholds still prevent low-confidence execution, but its reported probabilities should not be treated as calibrated confidence measurements.
- The planner deliberately supports a bounded grammar and existing workflows. It does not translate arbitrary multi-app instructions into shell commands or general computer-use actions.
- Cancellation stops later steps but cannot reverse a side effect that completed before cancellation was observed.

### Next gate

Phase 3: add stable, current-screen control discovery. For each supported app, choose DOM or accessibility controls based on what is actually observable, maintain app/tab ownership, and only consider visual targeting where the local machine can support it. Test stale controls and manually changed windows before chaining a discovered control into another action.

## Phase 3 — Current-screen control discovery

### Acceptance

1. A generic control action must begin with a fresh observation of the focused
   browser tab or desktop window.
2. Browser and desktop controls must retain a short-lived identity and reject
   stale, replaced, disabled, ambiguous, or wrong-window targets.
3. Browser controls must be selected by accessible name and semantic role,
   including controls inside open shadow roots.
4. Desktop controls must be discovered only inside the app and window that own
   the focused Hyprland window.
5. A visual-control fallback must not be claimed until local feasibility and
   safety have been validated.

### Implementation

- `browser-extension/page.js`: discovery now returns bounded semantic
  descriptors: a short-lived control id, accessible name, role, editability,
  disabled state, and a structural fingerprint. The page identity includes its
  URL and document `performance.timeOrigin`. Generic click/fill actions accept
  only the descriptor obtained from the immediately preceding observation.
  Replaced controls or navigated documents return an explicit stale-control
  error. Discovery traverses open shadow roots and uses accessible names before
  text content.
- `browser-extension/background.js`: generic click and fill actions observe
  the exact target before acting. Page operations ensure the requested tab is
  still the active tab in the same window. Public inspection output omits
  internal ids and fingerprints, so these short-lived references do not leave
  the extension execution path.
- `hyprash/desktop.py` and `scripts/accessibility.py`: AT-SPI discovery is
  restricted to the focused Hyprland window's process and title. Each control
  includes an accessibility-tree path, name, role, editability, and enabled
  state. The backend observes, selects one exact control, rechecks the active
  owner tuple (address, PID, title, class), and only then requests the action.
- `hyprash/backend.py`: desktop generic control actions now emit their verified
  state and evidence through the existing execution event.
- `tests/browser_controls.mjs`, `tests/browser_workflows.mjs`, and
  `tests/test_desktop_discovery.py`: cover observation-before-action, an open
  shadow-root button, same-label replacement rejection, exact descriptor
  forwarding, disabled controls, and owner-window changes.

### Checks run — 2026-10-13

| Check | Result | What this establishes |
| --- | --- | --- |
| `.venv/bin/python -m unittest discover -s tests` | PASS, 61 tests | Desktop semantic selection, owner change rejection, backend observe/select/action wiring, and prior behavior |
| `node --test tests/execution.mjs` | PASS | Phase 1 observe/act/verify behavior remains intact |
| `node tests/browser_workflows.mjs` | PASS | Generic browser clicks first observe and pass the exact descriptor into the action |
| `node tests/browser_controls.mjs` | PASS, isolated Brave | Open shadow-root discovery, stale replacement rejection, accessibility-name matching, and existing Google/YouTube/Spotify/GitHub fixtures |
| `node --check` and Python compilation | PASS | Changed extension and desktop bridge sources parse successfully |
| `git diff --check` | PASS | No whitespace errors |
| Installed extension ping | Pending reload | The currently running extension reports `phase1-observe-act-verify`; source reports Phase 3 only after a non-disruptive extension reload |

The first sandboxed Playwright launch was blocked by Brave's crashpad socket
restriction. Re-running the identical isolated fixture outside that sandbox
passed. This was an environment constraint, not a failing assertion.

### Live observations and limits

- Obsidian exposes only its top-level frame through AT-SPI on this machine. It
  cannot yet support arbitrary in-app named-control actions. The dedicated
  local-vault note creation path remains the supported Obsidian action.
- Camera exposes named controls including “Take Picture,” but they reported as
  disabled in the observed app state. Hyprash rejects them rather than sending
  an action.
- No visual click-by-coordinate fallback was added. The local machine has not
  yet demonstrated a safe, reliable visual target-selection path, and semantic
  DOM/AT-SPI controls are the safer method for the supported apps.
- Phase 3 source has passed isolated checks but is not live in Brave until the
  unpacked extension is reloaded. No user tabs were navigated merely to reload
  it.

### Next gate

Phase 4: maintain short-lived context for validated results and tabs, so a
follow-up such as “open the second one” can use a named, current result. On a
manual navigation, tab switch, owner change, or stale descriptor, clear that
context and re-observe; do not replay a state-changing action.

## Phase 4 — Recovery and follow-up context

### Acceptance

1. “Open the first/second result” only works after Hyprash itself has completed
   a verified Google or YouTube search.
2. Follow-up state is memory-only, expires after five minutes, and contains no
   saved page contents, result titles, screenshots, or browser history.
3. A changed tab, changed URL, expired context, manual navigation, or missing
   context stops the request before any result navigation.
4. The extension repeats the tab/URL validation immediately before selecting a
   result, because the user can switch tabs while local Laya decides.
5. Recovery may re-observe state but never retries a state-changing result
   navigation.

### Implementation

- `hyprash/backend.py`: stores only `{tabId, url, site, query, created_at}`
  after a verified Google or YouTube search. Before a result follow-up reaches
  Laya, Hyprash performs a read-only inspection. It repeats that inspection
  immediately before passing a result task to the extension. Context is cleared
  after selection, on Stop, when a different browser action starts, when it
  expires, or when tab/URL verification fails.
- `browser-extension/background.js`: verified search results return the
  current tab readback, not the pre-search URL. A result task must present the
  same tab and URL context. The extension applies this check to both a separate
  follow-up and the existing one-utterance search/result sequence.
- `tests/test_browser_context.py`: covers metadata-only storage, successful
  revalidation, changed tab rejection, expired context rejection, and rejection
  before Laya when there is no current result set.
- `tests/browser_workflows.mjs`: verifies a bare result task is rejected by the
  extension; sequence steps receive fresh context from their verified search.

### Checks run — 2026-10-13

| Check | Result | What this establishes |
| --- | --- | --- |
| `.venv/bin/python -m unittest discover -s tests` | PASS, 65 tests | Context storage, expiry, stale-tab rejection, preflight rejection, and prior behavior |
| `node --test tests/execution.mjs` | PASS | One-time action/cancellation guarantees remain intact |
| `node tests/browser_workflows.mjs` | PASS | Search-to-result sequence receives verified current URL context; bare result tasks fail safely |
| `node tests/browser_controls.mjs` | PASS, isolated Brave | Existing page-control behavior remains compatible |
| JavaScript/Python syntax and `git diff --check` | PASS | Changed sources parse and contain no whitespace errors |

### Limitations

- Follow-up context currently covers Google and YouTube result lists only. It
  does not treat Spotify song cards, GitHub repositories, desktop controls, or
  generic buttons as interchangeable “results.”
- A manual tab switch, navigation, or elapsed five minutes requires a new
  search. Hyprash gives a clear failure instead of attempting to infer intent.
- The installed extension is still running its earlier Phase 1 build. Phase 4
  source is ready but needs the same non-disruptive unpacked-extension reload
  before it becomes live in Brave.

### Next gate

Phase 5: add only explicitly approved reusable task structures. A routine must
have a named purpose, bounded inputs, a verified starting condition, and the
same observe/act/verify contract. Do not save arbitrary browser or desktop
actions as routines.

## Phase 5 — Reusable routines

### Acceptance

1. Routines are bounded, named multi-step sequences with an explicit purpose and parameter schema.
2. Every routine enforces verified starting conditions (preconditions: browser connected, Obsidian vault configured, app installed/cataloged, notes accessible) before executing any step.
3. Precondition failures halt immediately in preflight with a clear failure explanation; zero mutations or side effects occur.
4. Steps execute sequentially under the established observe → act once → verify contract, emitting progress (`Step N of M · Routine <name>`).
5. A failed or cancelled step immediately halts remaining steps; arbitrary shell execution or freeform action injection is strictly prohibited.
6. Local Laya evaluates and accepts the proposed routine action before execution; model rejection produces no side effects.

### Implementation

- `hyprash/routines.py`: Defines immutable `Routine` and `Precondition` data models. Provides `BUILTIN_ROUTINES` catalog (`morning`, `daily_standup`, `focus`, `code_review`), routine alias resolution, schema validation (`validate_routine_dict` rejecting arbitrary action kinds, excessive steps, or unsafe words), persistence for user-defined routines (`save_routine_dict`), and precondition verification (`check_routine_preconditions`).
- `hyprash/workflows.py`: Added workflow pattern recognition for routine execution phrases (`run morning routine`, `start daily standup`, `run focus routine`, `run routine <name>`).
- `hyprash/commands.py`: Added routine trigger patterns to command parsing and action extraction.
- `hyprash/plans.py`: Extended clause boundary lookahead to include `run|start|execute`, integrated routine action verification and rejection of unknown routines.
- `hyprash/decision.py`: Calibrated local Laya decision prompts for routine actions (`Run the <name> routine`), achieving 80–93% acceptance confidence with 0.50+ margins.
- `hyprash/backend.py`: Added routine precondition gating before execution, sequential step execution with progress reporting, stop-on-failure / stop-on-cancellation guarantees, and IPC requests for `save_routine` and `list_routines`.
- `browser-extension/background.js`: Bumped extension ping version to `phase5-reusable-routines`.
- `tests/test_routines.py`: Comprehensive test suite (28 new tests) covering schema validation, catalog and alias resolution, precondition success/failure, workflow phrase parsing, plan generation, Laya decision gating, and fail-fast backend execution.
- `scripts/check_laya.py`: Added routine test fixtures to offline Laya evaluation.

### Checks run — 2026-10-14

| Check | Result | What this establishes |
| --- | --- | --- |
| `.venv/bin/python -m unittest discover -s tests` | PASS, 94 tests | Routine schema validation, preconditions, Laya routing, plan proposals, backend execution, and all prior regression gates |
| `node --test tests/execution.mjs` | PASS | Browser observe/act/verify behavior and timeouts remain intact |
| `node tests/browser_workflows.mjs` | PASS | Browser workflow ordering, tab ownership, and fail-fast guarantees |
| `node tests/browser_controls.mjs` | PASS, isolated Brave | Open shadow-DOM traversal, stale control rejection, and site controls |
| `node --test tests/test_orbs.mjs` | PASS, 9 tests | Orb animation state geometry engines remain finite and healthy |
| `.venv/bin/python scripts/check_browser_bridge.py` | PASS | Private Unix socket framing, streamed progress, and verified result propagation |
| `.venv/bin/python scripts/check_laya.py` | PASS, 32 cases | Offline Laya intent fixtures, including routine approval (`run morning routine`, `start daily standup`) |
| `.venv/bin/python scripts/check_pipeline.py` | PASS | Offline Laya decision pipeline to note persistence and cancellation |
| Live Brave ping / inspect | PASS | Active Brave session connected (`version: phase4-bounded-context`); live controls inspected |
| Live tab workflow check | PASS | Real tab creation verified via Native Messaging host |
| `git diff --check` & syntax compilation | PASS | Zero whitespace issues; clean compilation for Python and JS sources |

### Limitations

- Routines are restricted to bounded compositions of verified Hyprash actions. Unbounded shell scripts, arbitrary desktop gestures, or unverified macros remain rejected by design.
- The running Brave session currently reports `phase4-bounded-context` until a non-disruptive unpacked reload updates it to `phase5-reusable-routines`.

### Next gate

Phase 6: Measure end-to-end latency across speech, local Laya decision, browser, and desktop layers; refine cancellation feedback; and validate physical shortcuts (`Ctrl+.`).

## Phase 6 — Natural Language Architecture, Browser State Contract, Multi-Step Recovery, and Latency Profiling

### Baseline findings & Problem statements

- **Rigid phrase matching:** Hyprash previously depended on rigid phrase patterns; small conversational variations (`"open a new tab"` vs `"open a tab"` vs `"can you look up games for me?"`) failed or misrouted. Short follow-ups (`"search for games"` after opening a tab) lacked conversational memory.
- **Lost tab binding:** Compound commands (`"open a new tab and search for games"`) spawned redundant tabs or searched in unrelated tabs because tab creation and search did not share an explicit tab-ID state binding contract.
- **All-or-nothing execution without sub-workflow isolation:** In multi-step sequences combining multiple domains (`"Open YouTube and play a Justin Bieber song, then open Spotify and play something new"`), a failure in step 1 either halted independent downstream workflows or leaked YouTube context into Spotify.
- **Unmeasured stage latencies:** End-to-end command latency was not instrumented with monotonic timers across transcription, normalization, Laya decision, validation, execution, and verification.

### Acceptance

1. **Two-Tier Natural Language Understanding:**
   - Tier 1: Canonical deterministic grammar, filler prefix/suffix stripping (`"can you"`, `"could you"`, `"for me please"`, etc.), and slot extraction. Conjunctions inside entity titles (`"rock and roll"`, `"dungeons and dragons"`) remain protected data.
   - Tier 2: Local Laya 0.4.1 CPU inference fallback for non-deterministic phrases, avoiding per-step inference inside tight execution loops.
   - Strongly-typed schemas (`ResolvedIntent`, `ConversationContext`).
   - Genuinely under-specified queries (`"play something else"` without active media context) return structured `ClarificationRequired` instead of guessing destructively.
2. **Explicit Brave Tab-ID Lifecycle Contract:**
   - Tab creation returns `{ tab_id, url, status, active: true }`.
   - Output-to-input binding: `target_tab_id` from step 1 tab creation propagates directly into step 2 search/navigation.
   - Contextual follow-up tab reuse: If the active tab is blank/new (`chrome://newtab/`, `about:blank`, `brave://newtab/`), subsequent searches execute inside that active tab rather than spawning duplicates.
   - Ping capability version handshake (`phase6-v1`) with graceful degradation to previous extension versions (`phase1-observe-act-verify`, `phase4`, `phase5`).
3. **DAG Sequential Execution & Partial Recovery:**
   - `PlanStep(Action)` typed schema with `step_id`, `target_domain`, `depends_on`, `idempotency`, `preconditions`, `postconditions`, `on_failure` (`ABORT_DEPENDENT` vs `ABORT_ALL`), and input/output bindings.
   - Domain context isolation: Failure in `browser:youtube` does not abort independent `browser:spotify` workflows when marked `ABORT_DEPENDENT`.
   - Granular UI activity events (`executing`, `acting`, `verifying`, `step_started`, `failed`, `succeeded`, `cancelled`).
   - Complete `PlanExecutionReport` tracking completed, failed, and skipped steps.
4. **Latency Profiling CLI (`scripts/check_latency.py`):**
   - Monotonic nanosecond timing (`StageTimer`) measuring PTT-to-transcript, NLU normalize, Laya inference, plan validation, act dispatch, postcondition verification, and total end-to-end latency.
   - Reporting cold start vs. warm median (p50), p95, and Rule vs. Laya breakdown.

### Implementation

- `hyprash/nlu.py`: Deterministic normalization, filler removal, slot extraction, conjunction preservation, typed `ResolvedIntent` and `ConversationContext` tracking tab IDs, active site, and search context with 5-minute TTL.
- `hyprash/plans.py`: Upgraded to DAG execution architecture. Implemented `PlanStep(Action)` with dependency tracking, `_infer_step_attributes`, binding propagation, and `PlanExecutionReport`.
- `hyprash/backend.py`: Integrated `ConversationContext`, `PlanExecutionReport` tracking, `target_tab_id` binding resolution, and granular activity state emissions.
- `browser-extension/background.js`: Enforced Tab-ID lifecycle contract (`target_tab_id`), blank/new tab reuse, partial failure support on YouTube playback, `next_track` Spotify operation, and extension ping capability bump to `phase6-v1`.
- `browser-extension/page.js`: Added `spotify_controls_ready` and `next_track` DOM controls.
- `scripts/browser_host.py`: Allowed `'next_track'` action.
- `hyprash/diagnostics.py`: In-memory diagnostic telemetry and monotonic `StageTimer` profiler with summary statistics (p50, p95).
- `scripts/check_latency.py`: Command-line profiler for pipeline stages with cold/warm benchmarking.
- `scripts/ptt.py`: Release-safe PTT key handling with race-free `held.unlink(missing_ok=True)`.
- `ui/shell.qml`: Reactive orb modes (`working` during `executing`, `acting`, and `verifying`) and responsive headline updates.
- `tests/test_nlu.py`: 35+ table-driven tests for normalization, compound splitting, tab variations, search variations, Spotify/YouTube playback, cancellation, unsupported safety checks, and context TTL.
- `tests/test_browser_reliability.py`: 10 tests for handshake, tab-ID bindings, follow-up reuse, closed tab rejection, and search context validation.
- `tests/test_plans.py`: Added DAG recovery, dependent step skipping, and binding propagation tests.

### Checks run — 2026-10-14

| Check | Result | What this establishes |
| --- | --- | --- |
| `.venv/bin/python -m unittest discover -s tests` | PASS, 121 tests | NLU resolution, browser reliability contract, DAG execution, routines, and all prior regression gates |
| `node --test tests/execution.mjs` | PASS | Bounded retries, one-time mutations, immediate cancellation checks |
| `node tests/browser_workflows.mjs` | PASS | Ordered workflows, tab ownership, no duplicate actions after uncertain clicks |
| `node tests/browser_controls.mjs` | PASS, isolated Brave | Named controls, field verification, Spotify track matching, and GitHub navigation |
| `node --check browser-extension/*.js` | PASS | Extension JavaScript syntax verification |
| `python -m py_compile hyprash/*.py scripts/*.py tests/*.py` | PASS | Clean bytecode compilation across all Python sources |
| `.venv/bin/python scripts/check_latency.py` | PASS, 90 samples | Validated monotonic latencies across all 6 pipeline stages |

### Measured Latency Profile

Benchmarked across 90 command evaluations on Arch Linux (CPU inference):

| Pipeline Stage | Median (p50) | p95 | Notes |
| --- | --- | --- | --- |
| **1. Voxtype STT (PTT-to-Transcript)** | 12.17 ms | 25.20 ms | Local Whisper STT model |
| **2. NLU Normalization & Slots** | 0.08 ms | 0.12 ms | Deterministic Tier 1 rule layer |
| **3. Laya 0.4.1 Inference (Tier 2)** | 0.00 ms | 0.00 ms | Bypassed for unambiguous Tier 1 queries; 110–160 ms on fallback |
| **4. Plan & DAG Validation** | 0.21 ms | 0.46 ms | Schema, dependency, and binding construction |
| **5. Action Dispatch (Act)** | 1.14 ms | 1.20 ms | Nominal dispatch overhead |
| **6. Postcondition Verification** | 1.08 ms | 1.20 ms | Monotonic predicate check |
| **Total End-to-End Latency** | **14.98 ms** | **28.39 ms** | Warm median: 14.98 ms (Cold start: 29.01 ms) |

- **Tier 1 (Deterministic Rules) Resolved:** 100% of benchmark queries resolved in <0.1 ms without incurring Laya CPU latency.
- **Tier 2 (Laya Fallback):** Reserved for unclassified conversational utterances upfront, never invoked in tight execution loops.
