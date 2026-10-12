# Simular-inspired Hyprash development report

Started: 2026-10-12. This file tracks implementation, evidence, and unfinished work for each phase.

## Requirements

Keep local inference without API keys, Voxtype recognition, the existing signed-in Brave browser, and the Arch/Hyprland/Omarchy interface. Improve task completion and responsiveness before adding broader autonomy. Build from public research and our existing code; do not claim to reproduce Sai's private implementation or benchmark results.

## Phase plan

| Phase | Outcome | Status |
| --- | --- | --- |
| 1 | Observe, act once, verify; report actual progress and failures | Implemented; isolated checks and live new-tab path pass |
| 2 | Explicit multistep plans; stop dependent steps on failure | Planned |
| 3 | Discover current screen controls; choose DOM/accessibility/visual methods | Planned |
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

Status: planned. Build explicit plans from supported browser and desktop actions; show the current step; stop dependent actions on failure. Tests must cover mixed-app plans, unsupported middle clauses, cancellation, and quoted content. General unrestricted model-generated commands are not an acceptance criterion.

## Phase 3 — Current-screen control discovery

Status: planned. Give controls stable identifiers within an observation, preserve app/tab ownership, and select DOM or accessibility controls before considering visual targeting. Measure local visual-model feasibility on this machine; do not assume generic Linux support means Hyprland support.

## Phase 4 — Recovery and follow-up context

Status: planned. Add bounded recovery for stale controls and page transitions, plus short-lived context for commands such as “open the second one.” Never retry an uncertain state-changing action blindly. Validate stale context and manual navigation cases.

## Phase 5 — Reusable routines

Status: planned. Save only explicitly supported, successful task structures and recheck their starting conditions before reuse. Measure whether routines improve recurring tasks without concealing changed interfaces.

## Phase 6 — Responsiveness and motion

Status: planned. Measure recognition, decision, browser/desktop execution and rendering separately. Use those timings to reduce unnecessary work, improve cancellation feedback, and align the existing orb/liquid animation with real activity. Physical shortcut validation remains a separate required check.
