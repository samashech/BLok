# BLoK roadmap

The goal: be the voice control layer for Hyprland. It does things, checks they
worked, runs on a laptop CPU and never needs the cloud. Each phase ships on its
own, with tests and a README section, before the next starts.

---

## Phase 1: Hands-free mode

*Who it's for:* people who can't or don't want to use the keyboard and mouse
(RSI, disability, cooking, across the room). Talon is weak on Wayland and EasySpeak
targets GNOME/KDE; nothing targets Hyprland.

### 1a. Numbered hints in the browser (no new dependencies)
- **"show numbers"** (also "numbers", "show links", "show buttons"): the extension
  draws a small numbered label on every visible clickable element: links,
  buttons, fields, video tiles. Labels sit in a shadow-DOM layer so page styles
  can't break them, and are removed on scroll, navigation or "hide numbers".
- **"click 12"**, **"12"** or **"open 12"** clicks it. If 12 is a text field, it's
  focused instead. **"open 12 in a new tab"** works for links.
- The number → element map lives in the page. It's checked against the same
  stale-control fingerprint `click_observed` already uses, so a number never
  clicks something that moved or changed.
- Risky labels (delete, buy, pay, send…) get the usual approval card.

### 1b. Hands-free listening ("hey block")
- **"hands free on"** (or `blok handsfree on`): BLoK keeps the mic open and
  waits for its name. No new model: PipeWire streams 16 kHz audio, an adaptive
  loudness gate cuts it into utterances, and Whisper transcribes only those.
  An utterance runs only when it starts with **"hey block" / "okay block" /
  "block"**, or comes within 8 s of the previous command (so "scroll down"…
  "scroll down" works without repeating the name).
- Mic audio stays in memory and is discarded after each utterance. Listening
  pauses while BLoK is speaking, so it never hears itself.
- The overlay shows a "hands-free" indicator; "hands free off" stops it.
  The setting persists across restarts.

### 1c. Everyday hands-free commands
- **"scroll down / up"**, **"page down"**, **"scroll to the top / bottom"**: in the
  browser by script (exact and smooth), elsewhere with Page Up/Down keys.
- **"type hello world"** types into whatever field has focus (the browser field,
  or any app through `wtype`). **"press enter / tab / escape"**.
- **"go back"**, **"reload"**, **"new tab"**, **"close tab"**, **"next tab"**.

### 1d. Screen grid for other apps (optional `ydotool`)
- **"show grid"**: a full-screen 3×3 numbered overlay (Quickshell layer). **"5"**
  zooms into cell 5 with a new 3×3 grid; three steps reach about 1/27 of the screen.
  **"click"**, **"double click"**, **"right click"**.
- The cursor moves with Hyprland's `hl.dsp.cursor.move`. Clicking needs
  `ydotool` (Hyprland has no click dispatcher), which the installer offers. With AT-SPI apps, "click Save"
  by name keeps working without it.

**Done when:** a full browsing session (open site, search, pick a result, scroll,
fill a field) works without touching keyboard or mouse; idle CPU in hands-free
mode stays under ~3% in a quiet room.

---

## Phase 2: Hinglish and Indian languages

- **Speech:** a multilingual Whisper model (`small`, same size as `small.en`)
  becomes an installer choice. With `language=None` it handles code-mixed speech.
  We then transliterate Devanagari output to Latin script so one rule set works.
- **Understanding:** a Hinglish layer in `tidy_speech` maps common verbs and
  particles before the English rules run: *kholo/khol do → open, chalao/bajao →
  play, band karo → close, dhundo/search karo → search, pe/par → on,
  ke gaane → songs by, awaaz badhao/kam karo → volume up/down, kitne baje hain →
  what time is it*. Word order differs ("YouTube pe Arijit ke gaane chalao" →
  "play Arijit songs on YouTube"), so it's handled by phrase patterns, not
  word swaps. The optional Qwen rephraser gets Hinglish examples too.
- **Voice:** Kokoro's Hindi voices (`hf_alpha`, `hm_omega`, …) as a setting;
  replies stay in the language you spoke.
- **Tests:** a Hinglish test set built like the accent tests (Kokoro Hindi voices →
  Whisper → rules), with a published success rate.

---

## Phase 3: Hyprland window choreography

- **Layouts:** "code on the left, browser on the right" → focus each app's
  window and arrange them with `hl.dsp.window.move`/`swap`/`resize`.
  "make it bigger", "swap them", "put it on the second monitor".
- **Saved setups:** "save this layout as coding" stores every window's app, class,
  workspace, position and size (from `hyprctl clients -j`). "coding mode" launches
  missing apps, waits for their windows, and moves each into place. Stored in
  `~/.config/blok/layouts/<name>.json`, editable by hand.
- **Focus mode:** "focus mode" → Do Not Disturb on, chosen distraction apps
  hidden in a special workspace, optional timer ("focus for 25 minutes"); "I'm done"
  restores everything.
- **Questions:** "what's on workspace 3?", "where's my terminal?", "close everything
  except code" (with approval).

---

## Phase 4: Seeing the screen without a GPU

- **Browser pages:** a new extension op returns the page's readable text (main
  content, not menus). "What's this page about?", "summarize this", "read this to
  me", "what's the price here?".
- **Other apps:** `grim` captures the focused window and `tesseract` OCRs it (with
  word boxes). "Summarize this error in my terminal", "read this dialog".
- **Clicking by appearance:** "click the blue Download button" → OCR word boxes plus
  the color sampled under them; Laya picks among matching candidates; click via
  the browser DOM or `ydotool` (Phase 1d).
- **Answers:** short questions are answered by the local Qwen model when
  installed, else extractive (the most relevant sentences). Spoken by Kokoro.
- Screen text never leaves the machine and isn't stored.

---

## Phase 5: BLoK as an MCP server

- `blok mcp` runs a stdio MCP server (Python `mcp` SDK) exposing BLoK's tools:
  `windows.list/focus/move`, `files.find/read/append` (home folder only),
  `browser.search/open/click/read_page`, `system.volume/brightness`, `say`.
- **Same safety as voice:** destructive tools return "needs approval" and show
  BLoK's approval card on screen; the AI client can't approve on the user's behalf.
- Docs show how to add it to Claude Desktop/Claude Code and local agents.
- Optional reverse direction later: BLoK calling other MCP servers as plugins.

---

## Phase 6: Teach by doing

- **"watch me"**: the extension records your clicks, field entries (never
  password fields) and navigations in the current tab as observed controls
  (name, role, fingerprint), not screen coordinates.
- **"done, call it file an expense"** saves it as a routine (`data/routines/`), with
  typed values turned into slots when you say so ("the amount changes each time").
- **"file an expense, 450 rupees"** replays it with observe → act → verify on each
  step and stops at the first mismatch, the same contract as built-in routines.
- Desktop steps (app launches, window moves) are recorded from BLoK's own actions.

---

## Order and status

| Phase | Status |
|---|---|
| 1a Browser hints | done |
| 1b Hands-free listening | done (idle CPU ≈ 0% in a quiet room) |
| 1c Everyday commands | done |
| 1d Screen grid | planned (needs `ydotool`) |
| 2 Hinglish | done: 11/12 spoken test commands (multilingual small), English unaffected |
| 3 Window choreography | planned |
| 4 Screen understanding | planned |
| 5 MCP server | planned |
| 6 Teach by doing | planned |
