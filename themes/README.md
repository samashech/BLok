# Theme packs

A theme is a folder containing `theme.json` plus any images it names. BLoK loads
packs from this folder and from `~/.config/blok/themes/` (yours win on a name
clash). Click ▦ in the overlay or run `blok theme <name>` to switch.

```
~/.config/blok/themes/neon/
├── theme.json
└── star.svg
```

## `theme.json`

| Field | Meaning |
|---|---|
| `name` | Shown in the tooltip (defaults to the folder name) |
| `mode` | `dark` or `light` |
| `font` | Any installed font family |
| `radius`, `controlRadius` | Corner radius of the panel and its buttons, in px |
| `background`, `backgroundTop`, `backgroundBottom` | Panel fill (a vertical gradient) |
| `foreground`, `muted` | Main and secondary text |
| `accent` | Highlight while working |
| `border`, `surface`, `hover` | Panel edge, button fill, button hover |
| `success`, `error` | Listening/ok and error colors |
| `orb`, `orbSecondary` | Colors for the thinking orb or ring |
| `ring` | Replace the orb with a ring: `sparks`, `arc` or `pixels` (omit for the classic orb) |
| `badge` | Corner badge on the ring: an emoji, a pixel sprite (`pumpkin`, `creeper`, `pickaxe`) or an image file in the pack |
| `micIcon` | Same choices, shown on the mic button |
| `dot`, `iconColor`, `micBorder` | Status dot, theme-button and mic-button border colors |
| `chamfer` | Cut-corner size in px (0 = normal corners) |
| `pixelFrame`, `innerEdge` | Doubled pixel border and its inner line color |
| `glow` | Soft outer glow color |
| `followDesktop` | `true` takes colors from the current Omarchy theme (see `omarchy/`) |

Start from a shipped pack, change the colors, and drop it in `~/.config/blok/themes/`.
Pull requests with new packs are welcome; include a screenshot.
