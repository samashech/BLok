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
| 4 | Bounded recovery and context-aware follow-up commands | Planned |
| 5 | Reusable routines with state validation | Planned |
| 6 | Measure latency, improve interruption and coordinate UI motion | Planned |

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

Status: planned. Add bounded recovery for stale controls and page transitions, plus short-lived context for commands such as “open the second one.” Never retry an uncertain state-changing action blindly. Validate stale context and manual navigation cases.

## Phase 5 — Reusable routines

Status: planned. Save only explicitly supported, successful task structures and recheck their starting conditions before reuse. Measure whether routines improve recurring tasks without concealing changed interfaces.

## Phase 6 — Responsiveness and motion

Status: planned. Measure recognition, decision, browser/desktop execution and rendering separately. Use those timings to reduce unnecessary work, improve cancellation feedback, and align the existing orb/liquid animation with real activity. Physical shortcut validation remains a separate required check.
