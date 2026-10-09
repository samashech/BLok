# Hyprash

A native, local voice assistant for Arch Linux + Hyprland/Omarchy. It uses **Vosk for speech recognition** and **Laya for desktop action decisions**. It has never used Jev or a hosted inference API.

The top-center surface emerges from the webcam position as a small connected drop, spreads into an island, and reveals its content after expanding. Dismissal contracts it back to the same point. The thinking orb uses the original [Libraries.dev thinking-orbs](https://libraries.dev/orbs) geometry and presets, compiled for native Qt Quick Canvas; it is not a lookalike spinner or a webview.

## Use

Press **Super+Shift+J** to open and listen; press again to stop and retract the panel. You can also launch **Hyprash** from the application launcher or run `./hyprash.sh`. Click the circular mic control to listen/stop, **Aa** to type, and **×** to retract. Saying **stop listening** stops immediately without waiting for the model. Typing a command stops a simultaneous microphone session so the two inputs cannot duplicate one another.

Try:

1. “Open notes and create a new note and make the title say hello.”
2. “Write this is my first local voice note.”
3. “Open browser and search for Robin Williams.”
4. “Open x dot com.”
5. “Open camera.” Then: “Take a picture of me.”

Also: “Can you bring up my terminal?”, “open files”, “open code”, “open github”, “visit example.com”, and “switch to workspace three”.

**Orb states follow real work:** breathing when idle, connecting while loading, listening with microphone activity, solving during Laya inference, working during action dispatch. No fabricated model reasoning is shown. Set `HYPRASH_REDUCED_MOTION=1` before launch to disable reveal and particle animation.

## How decisions work

`convaiinnovations/laya` is an independent Apache-2.0 decision model, not Jev's weights or a speech-to-text model. Vosk is still needed to turn audio into text. Laya chooses among typed action options; it does not generate conversation or arbitrary code.

For explicit commands, a grammar extracts literal titles, URLs, queries, and workspace numbers, then Laya accepts or rejects the proposed action. For other phrasing, Laya selects among the supported concrete desktop actions. Model rejection/failure never bypasses to the old parser. Unknown arguments and uncertain decisions result in no action. A negative/cancel phrase is a hard veto.

The action threshold is a model score of 0.60 with a 0.15 margin. These are conservative application gates, **not a guarantee of correctness or calibrated probabilities**. The upstream checkpoint warns that its 11+ choice calibration needs clamping; the package handles that, but scores from that option-count bucket are uncalibrated. Keep commands concise and check the displayed result.

A stable recognized clause can be sent to Laya before you finish speaking (600 ms stability window); free text waits for a clause/utterance boundary. The worker runs separately from microphone processing. Stop invalidates queued and in-flight decisions, so they cannot execute afterward. Already completed actions cannot be undone by a later correction.

## Setup

The original checkout has its environment and both model downloads prepared. On another machine:

- Install `quickshell`, `qt6-multimedia`, `pipewire`, `uv`, `curl`, and `unzip`.
- Run `./scripts/setup.sh`. This installs CPU PyTorch, Vosk and Laya, downloads the ~40 MB Vosk model and ~805 MB Laya checkpoint, and prepares them for offline use.
- Run `./hyprash.sh`.
- Optional: `python3 scripts/install.py` installs the launcher and **Super+Shift+J**, checking conflicts, backing up `bindings.lua`, and validating Hyprland after reload. It adds no autostart service.

The installer requires Omarchy's Lua config layout. App launch targets match this machine: default browser, Foot, Nautilus and VS Code. Keep this checkout in place while the launcher refers to it.

Runtime Laya loading is pinned to `55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851`, with Hugging Face and Transformers offline mode enforced. CPU inference uses four threads. The first load takes several seconds; the engine is then kept resident. `scripts/download_laya.py` is the explicit online setup step. There is no API key.

Uninstall integration: `python3 scripts/install.py --uninstall`. Quit: `./hyprash.sh quit`. Status: `./hyprash.sh status` (includes engine, activity, orb state and last inference duration).

## Data and limits

- Notes are editable and stored in `data/notes/*.json`; `HYPRASH_DATA` can override that directory before launch. Opening Notes restores the latest note; older note files remain on disk.
- Photos use a camera preview and preparation delay; Qt saves them to the system Pictures location and shows the exact path.
- Microphone audio is processed in memory, never recorded. Transcripts are not persisted. Speech and decision inference remain on this machine.
- Opening websites and searches uses your normal browser and the internet.
- This is a bounded desktop command assistant, not a general chatbot or arbitrary computer-use agent. It cannot read webpages or control arbitrary application interfaces. Vosk's small English model may mishear names and accents; typed input is available.
- The reveal originates at the top center of the screen, aligned to a centered laptop webcam; it cannot originate physically inside the bezel. No macOS notch is added.

## Verification and development

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/check_laya.py     # real model, offline; no desktop effects
node --test tests/test_orbs.mjs            # all 9 original animation states
.venv/bin/python scripts/check_live.py     # brief real microphone capture
python3 scripts/check_motion.py           # captures small top-center screenshots
./hyprash.sh foreground
./hyprash.sh text 'create a note titled hello'
```

The real-model command suite includes the demo sequence, natural app phrasing, unsupported requests and negation. The tests are focused checks, not a general accuracy benchmark.

- `hyprash/decision.py`: pinned offline Laya inference, candidate selection and score gate.
- `hyprash/backend.py`: microphone lifecycle, asynchronous decisions, cancellation and desktop dispatch.
- `ui/LiquidSurface.qml`: changing camera-to-island contour and reversible reveal.
- `ui/ThinkingOrb.qml`: Qt Canvas binding and visibility-aware animation clock.
- `vendor/thinking-orbs/`: unmodified upstream animation sources plus a small native binding, with the original MIT license and pinned source revision.

Rebuild the bundled orb engine with `npm ci --prefix scripts/orb-build && node scripts/orb-build/build.mjs`. The application does not need Node at runtime.

Sources: [Laya](https://github.com/NandhaKishorM/laya), [checkpoint](https://huggingface.co/convaiinnovations/laya), [Thinking orbs](https://libraries.dev/orbs), [Vosk](https://github.com/alphacep/vosk-api), [Quickshell](https://quickshell.org/docs/v0.2.1/types/Quickshell/PanelWindow/). Laya and its checkpoint are Apache-2.0; thinking-orbs is MIT © 2026 Jakub Antalik; the Vosk English model is Apache-2.0.
