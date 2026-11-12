# Arcadia design language

Arcadia is a full fork of ES-DE for the Steam Deck. Every screen, menu and dialog follows one design language. This file is the
reference; the theme (`themes/arcadia-es-de`) and the program's own screens both take their values from it.

## Principles

1. **Legible first.** Readable from a couch and on a 7" handheld. Body text is never smaller than 3% of the screen height;
   text on a surface has at least 4.5:1 contrast.
2. **One accent, one tint per console.** The interface uses a single accent. Each console also has its own colour, which
   lights the glow behind it and tints that console's screens.
3. **Focus is unmistakable.** Whatever the controller is on is the brightest, largest thing in view. Nothing else competes.
4. **Content leads, chrome is quiet.** Art and logos carry the screen. The clock, status and button hints stay muted.
5. **Calm motion.** 150-250 ms slides and fades with ease-out. No bounce, no loops, nothing that moves unless you did.
6. **It works with no art.** A library with no scraped covers must still look finished (labelled tiles, never blank boxes).

## Colour

| Token | Ink (default) | OLED | Paper | Use |
|---|---|---|---|---|
| ink | `#10121a` | `#000000` | `#eef0f5` | screen ground |
| surface | `#1b1e2b` | `#0a0b0f` | `#e2e5ee` | panels, tiles, dialogs |
| raised | `#20232f` | `#14161d` | `#d6dae6` | selected rows, buttons at rest |
| line | `#2d3140` | `#23262f` | `#c2c7d6` | dividers, tile outlines |
| text | `#f1f3f9` | same | `#14151b` | titles, selected text |
| muted | `#9aa1b4` | same | `#4d5468` | secondary text, button hints |
| faint | `#5d6477` | same | `#7d8498` | disabled, placeholders |
| accent | `#5aa9ff` | same | `#1f6fd1` | counts, links, the focus fill |
| console tint | per console | per console | per console | glow, console-specific highlights |
| ok / warn / error | `#6fcf97` / `#f2a33a` / `#e5645f` | same | same | status only, never decoration |

Console tints are generated, one per system, by `themes/arcadia-es-de/tools/make_assets.py` (a familiar colour for well-known
consoles, a stable hue from the name for the rest).

## Type

One family (Akrobat, bundled): Bold for titles, SemiBold for labels, Regular for body. Sizes are fractions of the screen
height so they scale from the Deck to a TV:

| Role | Size | Weight | Example |
|---|---|---|---|
| Hero title | 5.6% | Bold | the selected game's name |
| Title | 4.6% | Bold | menu and dialog titles |
| Label | 3.4% | SemiBold | list rows, buttons, counts |
| Body | 3.0% | Regular | descriptions, help text |
| Caption | 2.6% | SemiBold | hints, the clock (minimum size anywhere) |

Upper case only for system names and short labels, never for sentences.

## Space and shape

- A 1%-of-height base unit. Spacing is 1, 2, 3, 5 or 8 units.
- Corners: 0.6% of width on tiles and covers, fully round on pills, none on full-width bars.
- One level of depth: surface on ink. Shadows are glows, never drop shadows.

## Focus

- **Screens:** the selected item is 1.5-1.7x the size of the others, which are dimmed to 35-45% opacity and desaturated. The
  console's tint glows behind it.
- **Menus and dialogs:** the focused row or button has a 3-pixel white ring and a lighter fill, and keeps its size so nothing shifts.
- **Controller-only:** every control is reachable with the D-pad and A/B. Anything that needs a mouse is a bug.

## Motion

| What | Duration | Curve |
|---|---|---|
| Moving between items | 200 ms | ease-out |
| Opening a screen or menu | 220 ms | ease-out, slide plus fade |
| Closing | 150 ms | ease-in |
| Glow change on a new console | 250 ms | linear cross-fade |

## Screens

| Screen | Made with | Notes |
|---|---|---|
| Console ring | theme | picture and glow above, ring of logos below, name and count under it |
| Game shelf / list | theme | selected cover large, details underneath; plain-list variant for big libraries |
| Menus and dialogs | program | the colour, type and focus rules above, as the default (and only dark) scheme |
| Setup hub | program | native screens: first run, sort ROMs, emulators, BIOS, saves and sync, backup, updates |
| Launch, screensaver, boot | program | the same ground, glow and type |

## Not part of the language

Anything in the games themselves (emulator windows). The design stops at the moment a game starts.
