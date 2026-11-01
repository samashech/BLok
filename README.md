# BLoK

**An offline Jarvis for Hyprland: it hears you, sees your screen, clicks, and talks back. No cloud, no API keys.**

Hold <kbd>Ctrl</kbd>+<kbd>.</kbd>, talk the way you normally talk, let go. BLoK opens apps and sites, searches, plays music and videos, finds and edits your files, controls windows, volume and brightness, clicks the button you're pointing at, and tells you what it did. Speech recognition, decisions and the voice all run on your own computer.

<p align="center">
  <img src="docs/images/theme-omarchy.png" width="420" alt="BLoK in the Omarchy theme"><br>
  <img src="docs/images/theme-diwali.png" width="420" alt="Diwali theme">
  <img src="docs/images/theme-halloween.png" width="420" alt="Halloween theme"><br>
  <img src="docs/images/theme-minecraft.png" width="420" alt="Minecraft theme">
  <img src="docs/images/theme-liquid.png" width="420" alt="Liquid theme">
</p>

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/samashech/BLoK/main/install.sh | bash
```

The installer checks your system packages, then lets you pick models and shows their sizes before downloading anything:

| Part | Choices | Download |
|---|---|---|
| Decisions (Laya, required) | — | ~820 MB |
| Speech recognition (Whisper) | base.en / **small.en** / medium.en | 145 MB / **465 MB** / 1.5 GB |
| Voice (Kokoro) | **full** / compact / espeak only | **340 MB** / 115 MB / 0 |
| Rephraser (Qwen2.5 3B via Ollama, optional) | yes / **no** | 1.9 GB / 0 |
| Python packages | — | ~1.2 GB |

`--minimal` and `--full` pick for you; `--yes` takes the recommended (bold) choices. From a clone: `./install.sh`. An AUR package (`blok-git`, then `blok setup`) is ready in [`packaging/aur`](packaging/aur).

Then load the browser extension once: `brave://extensions` → Developer mode → **Load unpacked** → the `browser-extension` folder. Requirements: Arch Linux with Hyprland (built and tested on Omarchy), PipeWire, and Brave or another Chromium browser for web control.

## Talk to it

You don't need to phrase things properly. Fillers, stutters, slang and mid-sentence corrections are fine.

| You say | BLoK does |
|---|---|
| “hey man, open spotify or something” | opens Spotify |
| “yo can u look up reddit for me” | opens Reddit (and “look up how to cook pasta” searches Google) |
| “open youtube” … “get me a pewdiepie video” | plays one, in the same tab |
| “open steam” … “search for phantom blade” | searches Steam, because that's the page in front of you |
| *(pointing with the mouse)* “click that button” | clicks what you're pointing at; asks first if it says delete, buy or pay |
| “find my resume pdf” … “open it” | finds it in your home folder, then opens it |
| “add buy milk to my todo file” | appends the line |
| “delete old.txt” | moves it to the trash, after you approve |
| “it's way too loud” · “make the screen dimmer” | volume down · brightness down |
| “put this window on workspace three” | moves it |
| “uh what day is it today?” | tells you, out loud |
| “download supertux” | finds the official page, picks the download link, asks, downloads |
| “make it spooky” | switches to the Halloween theme |

Anything that changes or deletes something, or that BLoK isn't sure about, shows an approval card first. Say “yes” or press Enter to approve; say “no” or press Esc to cancel.

## Make it yours

### Add a command in 30 seconds

Drop a file in `~/.config/blok/commands/`. It works on the next thing you say; no restart needed.

```toml
# ~/.config/blok/commands/transparency.toml
description = "Toggle window transparency"
phrases = ["toggle transparency", "make [the] windows see through", "solid windows"]
run = "omarchy-hyprland-window-transparency-toggle"
reply = "Toggled transparency"
```

`[words]` are optional and `{slot}` captures part of what you said (passed safely quoted). For anything more involved, write Python:

```python
# ~/.config/blok/commands/dice.py
import random
from blok.plugins import command

@command("Roll a dice", phrases=["roll a dice", "roll a {sides} sided dice"])
def roll(sides="6"):
    return f"You rolled {random.randint(1, int(sides))}."
```

Exact phrases run instantly; looser wording is routed to your commands by Laya. `blok commands` lists what's loaded and reports broken files. See [`commands/`](commands) for the bundled examples (screenshot, wallpaper, color picker, QR code, gaps, timers).

### Make a theme pack

A theme is a folder with a `theme.json` and any images it uses. Put it in `~/.config/blok/themes/<name>/` and click ▦ to cycle to it. See [`themes/README.md`](themes/README.md) for every field; the shipped [`themes/`](themes) are good starting points. Packs can use a ring style (`sparks`, `arc`, `pixels`), a corner badge and mic icon (emoji, a built-in pixel sprite, or your own PNG/SVG), cut corners, a pixel border and a glow.

Built-in themes: **Omarchy** (follows your desktop palette), **Liquid**, **Diwali**, **Halloween** and **Minecraft**.

## How it works

```
Ctrl+. ─► Whisper (local) ─► speech cleanup ─► rules ──────────────► plan ─► act ─► verify ─► Kokoro voice
                                               └─► Qwen rephrase* ─► Laya ─┘      (browser / desktop / files)
```

- **Hearing:** PipeWire records while you hold the key; [faster-whisper](https://github.com/SYSTRAN/faster-whisper) transcribes in about a second on a laptop CPU.
- **Understanding:** fast rules handle clear requests. Everything else goes to [Laya](https://github.com/NandhaKishorM/laya), a small local decision model that chooses among concrete actions (area first, then action) and never writes code or shell commands. An optional local Qwen model only *rephrases* rambling speech; Laya still decides.
- **Acting:** a browser extension drives your real, signed-in tabs (observe → act once → verify); desktop actions use Hyprland and Omarchy's own commands; file actions stay inside your home folder.
- **Seeing:** before each command BLoK checks which window and page are in front, so follow-ups like “search for …” and “click that” mean what you'd expect.
- **Talking:** [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) speaks the result; ElevenLabs is optional (`blok elevenlabs-key`) and espeak is the fallback.

## Settings

| Variable | Effect |
|---|---|
| `BLOK_WHISPER_MODEL` | Speech model folder or name (default: the installed size, small.en preferred) |
| `BLOK_KOKORO_VOICE` / `BLOK_KOKORO_SPEED` | Voice (`af_heart`, `am_michael`, `bm_george`, …) and pace |
| `BLOK_TTS=0` | Silence spoken replies (`blok voice off` does the same) |
| `BLOK_REPHRASE=0` / `BLOK_REPHRASE_MODEL` | Turn off or choose the Ollama rephraser |
| `BLOK_STT=voxtype` | Use a running Voxtype daemon instead of built-in Whisper |
| `BLOK_HOME` / `BLOK_DATA` | Where models, the Python environment and your data live |
| `BLOK_REDUCED_MOTION=1` | No reveal or ring animation |

Names Whisper gets wrong (artists, games, friends) go one per line in `~/.config/blok/words.txt`. If recognition is poor, run `blok mic-test`: it shows your input level and exactly what Whisper heard.

## Privacy and safety

- Everything runs locally. Nothing you say leaves your computer unless you turn on ElevenLabs, which only receives the reply text.
- Recordings live in a private runtime folder and are deleted right after transcription.
- The browser extension only acts when you ask, and only remembers where your mouse is on the current page.
- File actions never touch hidden folders or overwrite files, and deleting goes to the trash. BLoK can't install packages, shut down your computer, or send or upload anything.

## Commands

```sh
blok                 # show the overlay       blok commands     # list your commands
blok mic-test        # check your microphone  blok theme diwali # switch theme
blok setup           # choose/download models blok voice off    # mute replies
blok text "open youtube"                      # type instead of talking
scripts/slim.sh      # see what disk space can be reclaimed (changes nothing without --apply)
```

## Contributing

Commands and theme packs are the easiest way in: see [CONTRIBUTING.md](CONTRIBUTING.md). Run the tests with

```sh
.venv/bin/python -m unittest discover -s tests
npm ci && node tests/browser_controls.mjs && node tests/browser_workflows.mjs && node --test tests/execution.mjs
```

## Credits

[Whisper](https://github.com/openai/whisper) via [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (MIT) · [Laya](https://github.com/NandhaKishorM/laya) and its [checkpoint](https://huggingface.co/convaiinnovations/laya) (Apache-2.0) · [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache-2.0) · [Quickshell](https://quickshell.org) · [Libraries.dev thinking-orbs and gooey](https://libraries.dev/orbs) (MIT © 2026 Jakub Antalik) · DOM indexing adapted from [browser-use](https://github.com/browser-use/browser-use) (MIT).

BLoK is licensed under Apache-2.0.
