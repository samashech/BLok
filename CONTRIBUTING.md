# Contributing to BLoK

Thanks for helping. The easiest contributions need no knowledge of the internals:

- **Commands**: add a `.toml` or `.py` file to [`commands/`](commands) (see its README). Useful, safe commands that work on a stock Omarchy/Hyprland setup are most welcome.
- **Theme packs**: add a folder to [`themes/`](themes) with a `theme.json` and a screenshot in your pull request.
- **Phrasings that fail**: open an issue with what you said, what BLoK heard (shown in the overlay) and what it did.

## Code changes

1. `./install.sh` sets up the environment and models.
2. Run the tests before and after your change:
   ```sh
   .venv/bin/python -m unittest discover -s tests
   npm ci && node tests/browser_controls.mjs && node tests/browser_workflows.mjs && node --test tests/execution.mjs
   ```
3. Keep the safety rules: nothing destructive without an approval card, file actions stay inside `$HOME`, model output never becomes a shell command, and spoken slots are always quoted.
4. Add a test for any new phrasing or behavior.

Layout: `blok/` is the Python backend (speech, rules, Laya routing, tools), `ui/` the Quickshell overlay, `browser-extension/` the Brave extension, `scripts/` setup and live checks, and `docs/dev/` the development history.
