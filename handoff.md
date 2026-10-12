# Hyprash project handoff

## Initial target

Hyprash is a fully local, voice-first assistant for Arch Linux, Omarchy, and
Hyprland. It was visually inspired by `jevaiass.mp4`, but is not based on Jev
AI and does not use it. The product replaces any hosted assistant dependency
with local Voxtype speech recognition and the local Laya model.

The intended experience is a polished top-screen assistant overlay with
thinking orbs, a liquid animation that appears to originate near the camera
space, and an Omarchy-compatible box theme. It should control existing,
signed-in Brave tabs and desktop applications using natural commands, including
Google search, YouTube search and playback, Spotify search and playback,
GitHub navigation, Obsidian notes, Notes, and Camera.

No cloud API or API key is required.

## Architecture

```mermaid
flowchart TD
    User["Voice / Ctrl+. hold-to-talk / typed command"] --> UI["Quickshell QML overlay"]
    UI --> Backend["Python backend"]

    Backend --> Speech["Voxtype local transcription"]
    Backend --> Intent["Rules + local Laya decision"]
    Intent --> Plans["Bounded plan builder"]

    Plans --> Browser["Browser workflow layer"]
    Plans --> Desktop["Desktop workflow layer"]

    Browser --> Socket["Local Unix socket"]
    Socket --> Host["Native messaging host"]
    Host --> Extension["Brave MV3 extension"]
    Extension --> Page["Existing signed-in Brave tab"]

    Desktop --> Hyprland["Hyprland / gtk-launch"]
    Desktop --> ATSPI["AT-SPI accessibility tree"]
    ATSPI --> Apps["Obsidian, Camera, Notes, other desktop apps"]

    Backend --> UI
```

The assistant uses bounded execution. Local Laya chooses from known tasks and
plans; it does not produce unrestricted shell commands or arbitrary desktop
actions.

Browser execution follows observe, act once, and verify. Desktop execution uses
Hyprland window information and AT-SPI controls, such as named buttons, text
fields, links, and menus.

## Workflow

1. The user holds `Ctrl+.` to speak and releases it to execute.
2. Voxtype transcribes speech locally.
3. The backend normalizes the utterance, identifies a supported workflow, and
   has local Laya approve or reject its bounded action.
4. The complete plan is validated before any side effect begins.
5. Each step observes state, targets a specific control or workflow, acts once,
   and verifies the expected outcome.
6. Progress, errors, cancellation, and execution state return to the QML UI.

This prevents the earlier failure mode of guessing page elements, repeating
clicks, or continuing after a failed first step.

## Folder structure

```text
hyprash/
├── hyprash.sh                 Launcher
├── README.md                  Setup and usage documentation
├── simular-similar.md         Simular-inspired phased capability report
├── handoff.md                 This document
├── requirements.txt           Python dependencies
├── jevaiass.mp4               Original visual reference
│
├── hyprash/                   Core Python application
│   ├── backend.py             Main orchestration and event loop
│   ├── speech.py              Voxtype transcription integration
│   ├── decision.py            Local Laya decision gate
│   ├── commands.py            Command normalization and routing
│   ├── workflows.py           Known browser/desktop workflows
│   ├── plans.py               Multi-step plan validation/execution
│   ├── browser.py             Browser bridge client
│   ├── desktop.py             Desktop control layer
│   └── themes.py              Theme loading
│
├── ui/                        Quickshell/QML interface
│   ├── shell.qml              Main assistant overlay
│   ├── LiquidSurface.qml      Liquid/camera-origin animation
│   ├── ThinkingOrb.qml        Individual thinking orb
│   ├── ThinkingOrbs.js        Orb animation logic
│   ├── Notes.qml              Embedded notes view
│   ├── CameraWindow.qml       Camera view
│   └── shaders/               Liquid and glow shaders
│
├── browser-extension/         Brave/Chrome Manifest V3 extension
│   ├── manifest.json
│   ├── background.js          Native bridge and tab coordination
│   ├── page.js                Semantic page observation/control
│   └── execution.js           Observe → act → verify behavior
│
├── scripts/
│   ├── browser_host.py        Native messaging host
│   ├── accessibility.py       AT-SPI desktop accessibility bridge
│   ├── ptt.py                 Push-to-talk support
│   └── check_*.py             Focused live checks
│
├── tests/
│   ├── test_*.py              Python unit and workflow tests
│   ├── browser_controls.mjs   Browser control integration tests
│   ├── browser_workflows.mjs  Browser workflow tests
│   └── execution.mjs          Extension execution tests
│
├── themes/
│   ├── omarchy.json           Main box-like Omarchy theme
│   └── liquid.json            Liquid visual variant
│
├── vendor/
│   ├── thinking-orbs/         Orbs implementation/adaptation
│   └── liquid-gooey/          Liquid visual assets
│
└── data/                      Local settings, notes, and vault selection
```

## Technology stack

| Area | Technology |
|---|---|
| Desktop environment | Arch Linux, Omarchy, Hyprland |
| Main backend | Python 3.12 |
| Speech recognition | Voxtype and a local speech model |
| Intent decisions | Laya 0.4.1, local CPU inference |
| UI | Quickshell, Qt Quick, QML, Qt Multimedia |
| Visual effects | QML Canvas, shaders, Gaussian/threshold goo effect |
| Browser integration | Brave Origin, Manifest V3 extension |
| Browser bridge | Native messaging and local Unix socket |
| Desktop controls | Hyprland `hyprctl`, `gtk-launch`, Linux AT-SPI |
| Browser tests | Node.js and Playwright |
| Python tests | `unittest` |

The visual system has the requested camera-space liquid reveal: it begins near
the camera/top origin, expands through liquid drops and gooey blending, and
settles into the assistant box. Thinking orbs are integrated into the top UI.

## Current progress

| Phase | Status | Delivered work |
|---|---|---|
| Core assistant | Complete | QML overlay, local transcription, Laya routing, themes, liquid motion, orbs, Ctrl+. interaction, browser and desktop foundations |
| Phase 1: reliable single actions | Complete | Browser observe → act → verify flow, trace output, cancellation, safer tab handling, known Google/YouTube/Spotify/GitHub workflows |
| Phase 2: multi-step plans | Complete | Whole-command validation before side effects, sequential execution, local Laya decision per step, stop on failure/cancel |
| Phase 3: current-screen semantic control | Implemented locally; Brave reload pending | Safer page controls, shadow-DOM discovery, stale-control protection, desktop control identity and owner-window checks |
| Phase 4: context and recovery | Remaining | References such as “open the second one,” controlled retries, stale page/window recovery |
| Phase 5: routines | Remaining | User-approved reusable workflows with precondition checks |
| Phase 6: polish and measurement | Remaining | Timing metrics, cancellation refinements, physical shortcut validation, motion tied to real execution state |

Phases 1 and 2 are documented in `simular-similar.md`.

## Implemented capabilities

- Local voice-to-command flow and typed commands.
- Local Laya decision gating without cloud services.
- Control of existing signed-in Brave tabs.
- Google searches and result opening.
- YouTube search plus first/second-result workflows.
- Spotify search/play workflows when Spotify exposes the needed controls.
- GitHub navigation workflows.
- Dedicated local Obsidian vault and note creation flow.
- Notes and Camera application launching.
- Omarchy and Liquid themes.
- Thinking orbs and liquid UI animation.
- Multi-step plans, validated before actions begin.

Phase 2 verification included 58 Python tests, browser execution and workflow
tests, browser-control checks, and offline Laya plan fixtures.

## Phase 3 checkpoint

Phase 3 is implemented locally and has passed its isolated test gate. Its
browser source is not active in the existing Brave session until the unpacked
extension receives a non-disruptive reload. Its changes include:

- Browser controls receive short-lived semantic identities based on name, role,
  editability, disabled state, and page identity.
- Open shadow-DOM controls can be discovered.
- A stale or replaced control fails safely instead of clicking a similar new
  target.
- Generic browser clicks and fills require fresh observation first.
- Desktop controls are tied to their owning window address, PID, title, and
  class.
- A selected desktop control is checked again before activation, preventing an
  action after the user changes windows.

The current Phase 3 test checkpoint passed 61 Python tests, extension execution
tests, browser workflow tests, browser control tests in headless Brave,
JavaScript syntax checks, and Python compilation checks. The first sandboxed
Playwright launch was blocked by Brave's crashpad socket restriction; the same
isolated fixture passed when run outside that sandbox.

Live checks exposed two current desktop constraints:

- Obsidian exposes only its top-level frame through AT-SPI on this machine, so
  arbitrary in-app controls cannot yet be safely automated through
  accessibility. Its direct note-creation workflow remains available.
- Camera exposes controls including “Take Picture,” but they are disabled in
  the current state, likely because the camera device or app state is
  unavailable. Hyprash correctly refuses to activate disabled controls.

The installed extension ping currently reports `phase1-observe-act-verify`, so
the running Brave service has not loaded Phase 3 yet. No user tab was navigated
solely to reload it.

## Remaining work

1. Activate the already tested Phase 3 extension source without disrupting
   current Brave tabs, then run a read-only live browser inspection.
2. Improve AT-SPI support for applications that expose useful accessibility
   trees.
3. Build Phase 4 contextual actions, such as “open the second one” and “play
   that result,” with strict page/tab/window validation.
4. Add safe recovery that re-observes after navigation but never blindly
   retries clicks or playback actions.
5. Add saved routines only after successful workflows establish reliable
   structure and preconditions.
6. Improve Voxtype recognition separately from browser and desktop control.
   Transcription quality is distinct from Laya’s task decision quality.
7. Measure the full command path from speech capture through action completion,
   then refine cancellation and UI animation timing.

## Product boundary and risks

Hyprash is not yet unrestricted visual automation. It is designed around
semantic browser controls, known workflows, and AT-SPI desktop controls. This
keeps it from blindly interacting with changed pages and wrong windows.

Spotify and YouTube may change their UI, and signed-in account state can alter
available controls. Desktop control quality depends on each application’s
AT-SPI support. A later visual-selector capability should only be considered
after local feasibility and reliability testing.
