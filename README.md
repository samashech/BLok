# BLok

A native, local voice assistant for Arch Linux + Hyprland/Omarchy. It uses **your existing Voxtype daemon/model for speech recognition** and **Laya for desktop action decisions**. It has never used Jev or a hosted inference API.

The top-center surface emerges from the webcam position as a small connected drop, spreads into an island, and reveals its content after expanding. Dismissal contracts it back to the same point. The 1.15-second reveal uses the sampled springs from [Libraries.dev Gooey](https://libraries.dev/gooey), adapted to native Qt Quick with a two-pass Gaussian blur and alpha-threshold shader. A descending neck and merging lobes resolve into the selected theme; text stays sharp outside the filter. The thinking orb uses the original [Libraries.dev thinking-orbs](https://libraries.dev/orbs) geometry and presets, compiled for native Qt Quick Canvas; it is not a lookalike spinner or a webview.

## Use

Hold **Ctrl+.** to speak; release to transcribe and execute. Normal **F9** Voxtype dictation stays unchanged. You can also launch **Hyprash** from the application launcher or run `./hyprash.sh`. Click the mic control to start/finish recording, **Aa** to type, and **×** to retract. Closing the panel cancels recording and pending actions. A spoken **stop listening** command cancels after transcription. Typing a command stops a simultaneous microphone session so the two inputs cannot duplicate one another.

Try:

1. “Open notes and create a new note and make the title say hello.”
2. “Write this is my first local voice note.”
3. “Open youtube.com and search for bbs.”
4. “Open the first link that showed up.”
5. “Google search games.”
6. “Open Spotify and play God’s Plan.”
7. “Open x dot com.”
8. “Open camera.” Then: “Take a picture of me.”

Multi-step examples supported in one utterance:

- “Create a note saying hello in Obsidian” writes `hello` into a new note, using a unique title if needed.
- “Play a Justin Bieber song” searches Spotify, selects a song credited to that artist, and verifies the selected track is playing. “Play a song by Adele” also works.
- “Open a new tab” creates a tab through the Brave extension.
- “Search for bbs in YouTube and play the second video” waits for results, selects the requested video, and checks playback.
- “Open GitHub and go to my repositories and find ClickyAI and open it” uses the signed-in account's repository list and matches the requested repository name.

These are supported task sequences, not arbitrary autonomous browsing. A failed or cancelled step stops the remaining steps. YouTube playback can be blocked by site restrictions; Spotify can require account permissions. Hyprash reports these failures instead of claiming playback.

The dedicated Obsidian vault is `data/Obsidian`; `data/obsidian-vault.json` selects it without deleting other vault registrations. Back up this folder like any other notes. Create/register it explicitly with `.venv/bin/python scripts/setup_obsidian_vault.py`; ordinary note commands do not create or move vaults.

Named controls: “click the Search button”, “click the search bar”, “type bbs into Search”, or “click Close”. Matching uses visible labels; ambiguous matches ask for a fuller label. Password fields require direct typing.

Browser controls: “Go to the address bar”, “type weather in Delhi”, “press enter”, “new tab”, “go back”, “go forward”, “reload the page”. You can combine them: “Go to the address bar and type weather in Delhi and press enter”. Searches accept “search for”, “look up”, and “look online for”; queries keep words such as “and”.

Also: “Can you bring up my terminal?”, “open files”, “open code”, “open github”, “visit example.com”, and “switch to workspace three”.

**Orb states follow real work:** breathing when idle, connecting while loading, listening with microphone activity, solving during Laya inference, working during action dispatch. No fabricated model reasoning is shown. Set `HYPRASH_REDUCED_MOTION=1` before launch to disable reveal and particle animation.

## Themes

**Omarchy** is selected by default: a flat box with 2 px corners, compact square controls, Adwaita Mono, and your active Omarchy palette. On this setup it matches **Fire and Shadow**. Palette changes are picked up within two seconds by reading Omarchy's current theme; no desktop configuration is modified. The reveal remains liquid, with corners settling into the box shape at the end.

Click **▦** on the overlay to switch between **Omarchy** and the rounded **Liquid** theme, or run:

```sh
./hyprash.sh theme omarchy
./hyprash.sh theme liquid
```

The choice is saved in `data/settings.json` (or `HYPRASH_DATA`). Theme definitions are in `themes/`; notes, camera, controls and the orb use the selected palette too.

## How decisions work

`convaiinnovations/laya` is an independent Apache-2.0 decision model, not Jev's weights or a speech-to-text model. Voxtype turns audio into text using the model already selected for F9. Laya chooses among typed action options; it does not generate conversation or arbitrary code.

For explicit commands, a grammar extracts literal titles, URLs, queries, and workspace numbers, then Laya accepts or rejects the proposed action. For other phrasing, Laya selects among the supported concrete desktop actions. Model rejection/failure never bypasses to the old parser. Unknown arguments and uncertain decisions result in no action. A negative/cancel phrase is a hard veto.

The action threshold is a model score of 0.60 with a 0.15 margin. These are conservative application gates, **not a guarantee of correctness or calibrated probabilities**. The upstream checkpoint warns that its 11+ choice calibration needs clamping; the package handles that, but scores from that option-count bucket are uncalibrated. Keep commands concise and check the displayed result.

Only completed Voxtype transcripts are sent to Laya; partial recognition cannot execute an action. The worker runs separately from microphone processing. Stop invalidates queued and in-flight decisions, so they cannot execute afterward. Already completed actions cannot be undone by a later correction.

## Setup

The original checkout has its environment and local Laya model prepared. On another machine:

- Install `quickshell`, `qt6-multimedia`, `voxtype`, `wtype`, and `uv`. Configure and start Voxtype with a local model.
- Run `./scripts/setup.sh`. This installs CPU PyTorch and Laya and downloads the ~805 MB Laya checkpoint. Speech reuses your existing Voxtype model; it downloads no additional speech model.
- Run `./hyprash.sh`.
- Optional: `python3 scripts/install.py` installs the launcher and **Ctrl+.** hold/release, checking conflicts, backing up `bindings.lua`, and validating Hyprland after reload. It adds no autostart service.

For Brave Origin, open `brave://extensions`, enable Developer mode, choose **Load unpacked**, and select this checkout's `browser-extension` directory. Run the installer first to register the local native-messaging host. After extension code changes, click its reload control. The extension uses your existing tabs and sign-ins; it does not launch a separate browser profile.

Permissions: HTTP/HTTPS page access lets it locate named controls on sites you ask it to use; tabs/scripting operate those tabs, native messaging connects to Hyprash, and storage/alarms preserve cancellation state and reconnect after disconnection. No page content is sent to an inference service. The private local Unix socket accepts only the supported action types. Keep the extension enabled for browser actions.

The installer requires Omarchy's Lua config layout. App launch targets match this machine: default browser, Foot, Nautilus and VS Code. Keep this checkout in place while the launcher refers to it.

Runtime Laya loading is pinned to `55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851`, with Hugging Face and Transformers offline mode enforced. CPU inference uses four threads. The first load takes several seconds; the engine is then kept resident. `scripts/download_laya.py` is the explicit online setup step. There is no API key.

Uninstall integration: `python3 scripts/install.py --uninstall`. Quit: `./hyprash.sh quit`. Status: `./hyprash.sh status` (includes engine, activity, orb state and last inference duration).

## Data and limits

- “Open notes” prefers installed Obsidian with a valid vault (otherwise uses Hyprash Notes); “open camera” prefers GNOME Camera. “Open Hyprash notes” and “open Hyprash camera” select the built-in windows explicitly. Other installed apps can be opened by their desktop-launcher names.
- Built-in notes are editable and stored in `data/notes/*.json`; `HYPRASH_DATA` can override that directory before launch. Opening Notes restores the latest note; older note files remain on disk.
- Built-in photos use a camera preview and preparation delay; Qt saves them to the system Pictures location and shows the exact path.
- Voxtype owns microphone capture and transcription. Hyprash uses its per-recording file-output override in a private runtime directory, reads the completed transcript, and removes the temporary directory. It does not change normal F9 dictation or use the clipboard. This setup reports local Whisper `base.en`; future Voxtype model changes are reused.
- Opening websites and searches uses your normal browser and the internet.
- Browser search workflows cover Google, YouTube and Spotify; first-result selection includes recognized sponsored result cards. Spotify reports success only when its player identifies the requested song as playing. Consent dialogs, account restrictions, changed site layouts and ambiguous labels can block actions.
- Desktop named controls require the app to expose AT-SPI accessibility. Camera exposes its shutter and modes on this machine. Obsidian note creation/append uses its URI interface and requires one selected vault; duplicate new-note titles are rejected. Some apps expose no usable controls and will report that limitation.
- This is a bounded command assistant, not a general chatbot or unrestricted computer-use agent. Recognition accuracy is the same as your Voxtype setup; typed input is available.
- The reveal originates at the top center of the screen, aligned to a centered laptop webcam; it cannot originate physically inside the bezel. No macOS notch is added.

## Verification and development

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/check_laya.py     # real model, offline; no desktop effects
.venv/bin/python scripts/check_pipeline.py # real model → persisted notes; cancellation
node tests/browser_workflows.mjs          # ordering, cancellation, native tabs and playback verification
node tests/browser_controls.mjs           # isolated browser DOM fixtures (Playwright)
.venv/bin/python scripts/check_browser_bridge.py # native messaging bridge
node --test tests/test_orbs.mjs            # all 9 original animation states
.venv/bin/python scripts/check_live.py     # real Voxtype recording/cancellation
.venv/bin/python scripts/check_voxtype.py --browser # real browser address-bar check
python3 scripts/check_motion.py           # captures small top-center screenshots
./hyprash.sh foreground
./hyprash.sh text 'create a note titled hello'
```

Live browser checks are opt-in: `scripts/check_browser_live.py` navigates your actual tabs; passing `spotify` starts playback. `scripts/check_desktop_live.py` opens installed apps and inspects controls.

The real-model command suite includes the demo sequence, natural app phrasing, unsupported requests and negation. The tests are focused checks, not a general accuracy benchmark.

- `hyprash/decision.py`: pinned offline Laya inference, candidate selection and score gate.
- `hyprash/backend.py`: microphone lifecycle, asynchronous decisions, cancellation and desktop dispatch.
- `ui/LiquidSurface.qml`: camera-origin merging shapes, native GPU goo filter, and reversible reveal.
- `ui/ThinkingOrb.qml`: Qt Canvas binding and visibility-aware animation clock.
- `vendor/thinking-orbs/`: unmodified upstream animation sources plus a small native binding, with the original MIT license and pinned source revision.

`vendor/liquid-gooey/` contains the pinned MIT upstream spring sources and native binding; `ui/shaders/` contains the native goo filter. Rebuild shader bundles with `./scripts/build-shaders.sh` (requires Qt 6 shader tools).

Rebuild the bundled orb and spring engines with `npm ci --prefix scripts/orb-build && node scripts/orb-build/build.mjs`. The application does not need Node at runtime.

Sources: [Laya](https://github.com/NandhaKishorM/laya), [checkpoint](https://huggingface.co/convaiinnovations/laya), [Thinking orbs](https://libraries.dev/orbs), [Voxtype](https://voxtype.io/), [Quickshell](https://quickshell.org/docs/v0.2.1/types/Quickshell/PanelWindow/). Laya and its checkpoint are Apache-2.0; thinking-orbs is MIT © 2026 Jakub Antalik.
