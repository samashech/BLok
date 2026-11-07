# Learning from Aside's browser agent

What BLoK is borrowing from [Aside](https://aside.com), and how far along each piece is.
Everything known about Aside comes from its public website, engineering post and benchmark
repo. The app itself was not taken apart.

## Status

| # | Idea | Status |
|---|------|--------|
| 1 | Compact page snapshots with reference IDs | Built. Needs an extension reload to go live |
| 2 | Tell BLoK what a click caused (new tab, download, navigation) | Built. Needs the same reload |
| 3 | Hide passwords from the model, autofill them, log each use | Not started, needs a decision (below) |
| 4 | Fall back to the screen when page controls fail | Not started (below) |

**To turn it on:** open `brave://extensions`, click Reload on BLoK, then reload your open pages.
Until then BLoK keeps using the old literal-label click, so nothing breaks.

## Why BLoK does it differently

Aside has a strong cloud model write Playwright code. BLoK runs offline, so the model can't be
counted on for that. BLoK uses the same page representation, but Python decides which control
you meant, and Laya only helps when the words alone don't settle it.

## Log

### 1. Compact page snapshots: built

Problem: "click X" matched labels literally. One misheard word gave "No visible control", two
matches gave "say its full label", and the control list was cut off in page order at 120 with
no idea of what was on screen.

What now happens when you say "click X":
1. The extension's `snapshot` action lists up to 150 visible controls, on-screen ones first, each
   with a reference ID, role, name, section and state. Field contents are never read, only
   whether a field is filled.
2. `blok/snapshot.py` scores your words against the names, allowing for misheard words. It
   understands "second add to cart", "save in the footer" and "the code tab". If several fit, it
   prefers the one on screen, and otherwise asks rather than guesses.
3. If the words don't match, Laya suggests a control ("sign up" → "Create account"), and you
   confirm before anything is clicked. If Laya isn't sure, BLoK offers the closest names.
4. Risky controls are confirmed by their real name, so "click repository" can't quietly press
   "Delete repository".
5. It clicks that exact control by reference ID, and refuses if the page changed since the
   snapshot.

AI clients over MCP get the same list through a new `page_snapshot` tool, and `page_click` takes
a reference ID. Both need your approval, and the card shows the control's real name.

Size on real pages, in a throwaway browser:

| Page | Page HTML (chars) | Snapshot (chars) | Share | Time |
|------|-------------------|------------------|-------|------|
| GitHub repo | 271,966 | 4,790 | 1.8% | 33 ms |
| Wikipedia article | 611,114 | 5,179 | 0.8% | 43 ms |
| Hacker News | 34,641 | 3,900 | 11.3% | 23 ms |
| Steam store | 974,168 | 6,573 | 0.7% | 29 ms |

Testing against those real pages found three bugs, now fixed and covered by tests: "download pdf"
picked a link named "downloaded", "the code tab" was needlessly ambiguous on GitHub, and "second
comments" failed on Hacker News.

Laya, tried on one made-up page: got "sign up", "log in", "how much does it cost" and "my basket"
right, and correctly refused "launch the rocket". It declined "the docs" and "talk to someone".
Declining is safe, but those two still need the real label.

### 2. What a click caused: built

The extension watches for up to 0.6 s after a click. BLoK then says "opened a new tab", "the page
changed" or "downloading game.zip", and follows you to the new tab or page, so the next command
acts on the right one. This covers "click X", numbered hints and "click that". It only reports
after a click: unlike Aside, it doesn't push events to the agent while a task runs, because the
extension link is request and reply.

### 3. Hiding passwords: needs a decision

BLoK has no password manager. Snapshots never read field contents, and BLoK refuses to type into
password fields, so neither path handles a password. Aside's feature is storing passwords and
filling them for you, which means building encrypted storage. Brave's own password manager
may be enough. Decide whether this is wanted before building it.

### 4. Falling back to the screen: not started

BLoK can already read words off the screen, but clicking there needs `ydotool` (not installed) or
a reliable way to map screen positions onto the page, including display scaling. For now, a
control the snapshot can't see can still be reached with "show numbers".

## Known limits

- Only the top frame of a page is read, so controls inside embedded frames aren't listed.
- Pages with more than 150 controls list the first 150, on-screen ones first. Below that, BLoK
  falls back to the exact-label click.
- "Click the blue X" still uses the old path, because the snapshot has no colors.
- "Type X into the Y field" still matches the field's label literally. Snapshots cover clicks only.

## Not yet verified

The whole chain hasn't run in your real browser, because the extension needs a reload first. So
far, the snapshot was tested in real Brave on real pages, while the extension's message handling
and the Python click flow were tested with stand-ins.
