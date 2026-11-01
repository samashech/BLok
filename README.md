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
- “Open Spotify—no wait, open YouTube” repairs mid-utterance disfluencies and executes the corrected target.
- “Fire up a new tab and look up some games for me” handles casual slang, conversational fillers, and output-to-input tab-ID binding.
- “Start recording routine morning” / “Stop recording routine” / “Save that as my morning routine” automatically records verified actions and compiles them into persistent routines.

These are supported task sequences, not arbitrary autonomous browsing. A failed or cancelled step stops the remaining steps. YouTube playback can be blocked by site restrictions; Spotify can require account permissions. Hyprash reports these failures instead of claiming playback.

The **Action Timeline** displays a real-time execution trace directly inside the overlay (`pending`, `running`, `awaiting_approval`, `verified`, `failed`, `skipped`) with domain badges and millisecond timings.

The **Human-in-the-Loop (HITL) Approval Gate** protects against state-mutating or destructive actions (`delete`, `remove`, `pay`, `checkout`, note overwrite) or borderline model confidence. Execution pauses at an Approval Card with a 30s countdown; confirm with Enter, click **Approve**, or say “approve” / “yes”. Cancel with Esc, click **Reject**, or say “reject” / “no”.

The dedicated Obsidian vault is `data/Obsidian`; `data/obsidian-vault.json` selects it without deleting other vault registrations. Back up this folder like any other notes. Create/register it explicitly with `.venv/bin/python scripts/setup_obsidian_vault.py`; ordinary note commands do not create or move vaults.

Named controls: “click the Search button”, “click the search bar”, “type bbs into Search”, or “click Close”. Matching uses visible labels; ambiguous matches ask for a fuller label. Password fields require direct typing.

Browser controls: “Go to the address bar”, “type weather in Delhi”, “press enter”, “new tab”, “go back”, “go forward”, “reload the page”. You can combine them: “Go to the address bar and type weather in Delhi and press enter”. Searches accept “search for”, “look up”, and “look online for”; queries keep words such as “and”.

Desktop tools (rules first, Laya for looser phrasing):

- **Files** (only inside your home folder; hidden folders are never changed): “open my downloads folder”, “find my resume pdf” → “open it”, “open the latest screenshot”, “read my readme file”, “add buy milk to my todo file”, “create a file called ideas with buy a GPU”, “rename report.pdf to old.pdf”, “move notes.md to my documents folder”, “copy …”, “delete old.txt” (moves it to the trash after you approve).
- **System:** “turn the volume up”, “set the volume to forty”, “mute”, “make the screen dimmer”, “pause the music”, “next/previous track”, “lock the screen”.
- **Windows:** “close this window”, “make it fullscreen”, “float this window”, “move this window to workspace 3”, “switch to Firefox”.
- **Questions** (answered aloud through `espeak-ng`; set `HYPRASH_TTS=0` to mute, or `HYPRASH_TTS_CMD` for another voice): “what time is it”, “what's the date”, “how much battery do I have”.
- **Downloads:** “download https://…”, “download SuperTux” (searches Google, Laya picks the download page and then the download link, you approve, and Brave verifies the download started), “download Portal on Steam” (opens Steam store results).

Also: “Can you bring up my terminal?”, “open files”, “open code”, “open github”, “visit example.com”, and “switch to workspace three”. Casual slang like “spin up”, “hop to”, “pop open”, “blast”, or “throw on” is recognized natively.

**Orb states follow real work:** breathing when idle, connecting while loading, listening with microphone activity, solving during Laya inference, working during action dispatch. No fabricated model reasoning is shown. Set `HYPRASH_REDUCED_MOTION=1` before launch to disable reveal and particle animation.

## Themes

**Omarchy** is selected by default: a flat box with 2 px corners, compact square controls, Adwaita Mono, and your active Omarchy palette. On this setup it matches **Fire and Shadow**. Palette changes are picked up within two seconds by reading Omarchy's current theme; no desktop configuration is modified. The reveal remains liquid, with corners settling into the box shape at the end.

Click **▦** on the overlay to cycle through **Omarchy**, the rounded **Liquid**, **Halloween** (pumpkin orange on purple-black) and **Diwali** (marigold and diya gold on deep plum). You can also say “switch to the Halloween theme”, “make it spooky” or “Diwali mode”, or run:

```sh
./hyprash.sh theme halloween   # omarchy | liquid | halloween | diwali | next
```

The choice is saved in `data/settings.json` (or `HYPRASH_DATA`). Theme definitions are in `themes/`; notes, camera, controls and the orb use the selected palette too.

## Talk to it normally

You don't have to phrase commands properly. “hey man, open spotify or something”, “yo can u look up reddit for me”, “uh google uh best laptops under 50k”, “open the open the browser”, “bro it's way too loud”, “so like, can you find that resume thing i had”: Hyprash removes fillers (“uh”, “like”, “what's it called”, “or something”), stutters and friendly openers, expands chat slang (“u”, “wanna”, “yt”), and understands “look up reddit” as opening Reddit while “look up how to cook pasta” searches Google. When something is too vague (“open this app”), it asks instead of guessing.

If **Ollama** is running with a small model **already installed**, Hyprash also uses it to restate rambling speech as plain commands (“is it late already” → “what time is it”). It prefers `qwen2.5:3b`, then `gemma2:2b`; set `HYPRASH_REPHRASE_MODEL` to choose, or `HYPRASH_REPHRASE=0` to turn it off. Hyprash never downloads a model. The rewrite only *suggests* wording: it still goes through the rules and Laya, it is called only when the rules don't understand you (~200–400 ms), and a rewrite that names an app, file or site you didn't say is thrown away. If Ollama isn't running, everything else works the same.

## Voice replies

Hyprash says what it did (“Opened your Downloads folder”, “Sorry, no file matches …”). Multi-step requests are summarised once at the end, and speaking stops as soon as you start talking.

- **Kokoro (default, free, offline):** the open-source Kokoro-82M voice (Apache-2.0) runs locally on the CPU, about 5× faster than real time. Set it up once with `uv pip install --python .venv/bin/python kokoro-onnx soundfile && .venv/bin/python scripts/download_kokoro.py` (~350 MB into `models/kokoro`). Choose a voice with `HYPRASH_KOKORO_VOICE` (default `af_heart`; others include `af_bella`, `af_nicole`, `am_michael`, `am_fenrir`, `bf_emma`, `bm_george`) and the pace with `HYPRASH_KOKORO_SPEED` (default `1.05`). Nothing leaves your computer.
- **ElevenLabs (optional, paid):** run `./hyprash.sh elevenlabs-key` (hidden prompt; saved to `~/.config/hyprash/elevenlabs.key`, mode 600, outside this repo) or set `ELEVENLABS_API_KEY`, then restart Hyprash. Audio streams through `mpv`. Optional: `HYPRASH_ELEVENLABS_VOICE` (voice ID) and `HYPRASH_ELEVENLABS_MODEL` (default `eleven_flash_v2_5`). Only the reply text is sent to ElevenLabs, which includes file text when you ask Hyprash to read a file aloud.
- Priority: ElevenLabs if a key exists, otherwise Kokoro, otherwise `espeak-ng`. If a voice fails, Hyprash says so once and falls back.
- `./hyprash.sh voice kokoro|elevenlabs|local|off` switches voices; `HYPRASH_TTS=0` silences it.

## How decisions work

Hyprash uses local rules plus local Laya, optionally helped by an installed Ollama model that only rephrases speech (see above). There is no cloud model for decisions.

1. **Rules (<2 ms):** `hyprash/nlu.py` and `hyprash/router.py` normalize slang, fillers and self-corrections, then match clear commands directly to a typed action.
2. **Laya router (~250–400 ms):** any clause the rules don't understand goes to Laya 0.4.1 on CPU. Laya only answers bounded `choice` questions, so routing is two-stage: first the **area** (files, browser, media, windows, system, notes, camera, questions), then the **action** within the top two areas, with a "None of these" option. Python then extracts the literal arguments (file name, text, workspace number…). If an argument is missing, Hyprash asks for it instead of guessing.
3. **Laya picker:** when several files match, or a page has several download links, Laya chooses among the concrete candidates (≤8). If it isn't confident, Hyprash lists them ("Say *open file 2*").
4. **Laya check:** rule-matched steps below 0.90 confidence still need Laya to accept the proposed action over "Do nothing" (score ≥ 0.60, margin ≥ 0.15).

Laya-routed actions that change state (delete, rename, move, copy, append, create, close window, lock, download) show an approval card unless Laya is ≥90% sure. Deleting, renaming, moving, copying and downloading **always** ask first, and the card names the exact file or link. Scores are conservative gates, **not calibrated probabilities**.

Only completed Voxtype transcripts are sent to the compiler; partial recognition cannot execute an action. The worker runs separately from microphone processing. Stop invalidates queued and in-flight decisions, so they cannot execute afterward. Already completed actions cannot be undone by a later correction.

## Setup

The original checkout has its environment and local Laya model prepared. On another machine:

- Install `quickshell`, `qt6-multimedia`, `voxtype`, `wtype`, `uv`, `fd`, `wl-clipboard` and optionally `espeak-ng` and `poppler` (PDF reading). Configure Voxtype with a local model and keep its daemon running: `systemctl --user enable --now voxtype` (a daemon started in a terminal stops when that terminal closes). If it is stopped, Hyprash says so instead of recording. Hyprash records with Voxtype's `--file` output mode, so nothing is typed into your windows and the clipboard is untouched.
- `HYPRASH_VOXTYPE_MODEL=small.en` (or any model shown by `voxtype info models`) uses a larger model for Hyprash commands only; F9 dictation keeps its own model.
- Run `./scripts/setup.sh`. This installs CPU PyTorch and Laya and downloads the ~805 MB Laya checkpoint. Speech reuses your existing Voxtype model; it downloads no additional speech model.
- Run `./hyprash.sh`.
- Optional: `python3 scripts/install.py` installs the launcher and **Ctrl+.** hold/release, checking conflicts, backing up `bindings.lua`, and validating Hyprland after reload. It adds no autostart service.

For Brave Origin, open `brave://extensions`, enable Developer mode, choose **Load unpacked**, and select this checkout's `browser-extension` directory. Run the installer first to register the local native-messaging host. After extension code changes, click its reload control. Downloads need the `downloads` permission added in `phase7-v1`; reload the extension once and accept it (`./hyprash.sh` reports the running version if it is older). The extension uses your existing tabs and sign-ins; it does not launch a separate browser profile.

Permissions: HTTP/HTTPS page access lets it locate named controls on sites you ask it to use; tabs/scripting operate those tabs, native messaging connects to Hyprash, and storage/alarms preserve cancellation state and reconnect after disconnection. No page content is sent to an inference service. The private local Unix socket accepts only the supported action types. Keep the extension enabled for browser actions.

The installer requires Omarchy's Lua config layout. App launch targets match this machine: default browser, Foot, Nautilus and VS Code. Keep this checkout in place while the launcher refers to it.

Runtime Laya loading is pinned to `55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851`, with Hugging Face and Transformers offline mode enforced. CPU inference uses four threads. The first load takes several seconds; the engine is then kept resident. `scripts/download_laya.py` is the explicit online setup step. There is no API key.

Uninstall integration: `python3 scripts/install.py --uninstall`. Quit: `./hyprash.sh quit`. Status: `./hyprash.sh status` (includes engine, activity, orb state and last inference duration).

## Data and limits

- “Open notes” prefers installed Obsidian with a valid vault (otherwise uses Hyprash Notes); “open camera” prefers GNOME Camera. “Open Hyprash notes” and “open Hyprash camera” select the built-in windows explicitly. Other installed apps can be opened by their desktop-launcher names.
- Built-in notes are editable and stored in `data/notes/*.json`; `HYPRASH_DATA` can override that directory before launch. Opening Notes restores the latest note; older note files remain on disk.
- Built-in photos use a camera preview and preparation delay; Qt saves them to the system Pictures location and shows the exact path.
- Voxtype owns microphone capture and transcription. Hyprash uses its per-recording file-output override in a private runtime directory, reads the completed transcript, and removes the temporary directory. It does not change normal F9 dictation, type into windows or use the clipboard. This setup reports local Whisper `base.en`; future Voxtype model changes are reused.
- Opening websites and searches uses your normal browser and the internet.
- Browser search workflows cover Google, YouTube and Spotify; first-result selection includes recognized sponsored result cards. Spotify reports success only when its player identifies the requested song as playing. Consent dialogs, account restrictions, changed site layouts and ambiguous labels can block actions.
- Desktop named controls require the app to expose AT-SPI accessibility. Camera exposes its shutter and modes on this machine. Obsidian note creation/append uses its URI interface and requires one selected vault; duplicate new-note titles are rejected. Some apps expose no usable controls and will report that limitation.
- This is a bounded command assistant, not a general chatbot or unrestricted computer-use agent. It cannot install system packages, shut down, or send/upload anything. Downloads stop at the browser's download; running an installer is up to you. Recognition accuracy is the same as your Voxtype setup; typed input is available.
- The reveal originates at the top center of the screen, aligned to a centered laptop webcam; it cannot originate physically inside the bezel. No macOS notch is added.

## Verification and development

Phased reliability work and its measured limits are tracked in [simular-similar.md](simular-similar.md).
Browser execution separates readiness observations, one-time actions, and outcome checks. Generic button clicks report an unverified result and cannot automatically advance a dependent browser sequence. Current progress is shown in the overlay; `./hyprash.sh status` includes the latest execution evidence and stage timings.

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/check_latency.py  # monotonic latency profiler across all pipeline stages
.venv/bin/python scripts/check_laya.py     # real model, offline; no desktop effects
.venv/bin/python scripts/check_pipeline.py # real model → persisted notes; cancellation
npm ci                                  # project-local browser test dependency
node --test tests/execution.mjs          # polling, one-time actions, cancellation and timeouts
node tests/browser_workflows.mjs          # ordering, cancellation, native tabs and playback verification
node tests/browser_controls.mjs           # isolated browser DOM fixtures (Playwright)
.venv/bin/python scripts/check_browser_bridge.py # native messaging bridge
node --test tests/test_orbs.mjs            # all 9 original animation states
.venv/bin/python scripts/check_live.py     # real Voxtype recording/cancellation
.venv/bin/python scripts/check_voxtype.py --browser # real browser address-bar check
python3 scripts/check_motion.py           # captures small top-center screenshots
./hyprash.sh foreground
./hyprash.sh text 'can you please open a new tab and search for games'
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
