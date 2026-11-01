# Commands

Each `.toml` or `.py` file here is a voice command. Your own go in
`~/.config/blok/commands/` and override these on a name clash. Changes are
picked up on the next thing you say; `blok commands` lists what's loaded.

**TOML** runs a shell command:

```toml
description = "Take a screenshot"                  # what Laya sees; keep it short
phrases = ["take a screenshot", "grab [the] screen"]  # [optional words], {slots}
run = "omarchy-capture-screenshot"                 # {slot} values are shell-quoted
reply = "Screenshot taken"                         # optional, may use {slots}
confirm = false                                    # true asks before running
```

**Python** can do anything; see `timer.py`:

```python
from blok.plugins import command

@command("Roll a dice", phrases=["roll a dice", "roll a {sides} sided dice"])
def roll(sides="6"):
    import random
    return f"You rolled {random.randint(1, int(sides))}."
```

The returned text is shown and spoken. Raise an exception to report a problem.
Exact phrase matches run instantly; other wording reaches your command when Laya
picks its description, so make descriptions clear and distinct.
