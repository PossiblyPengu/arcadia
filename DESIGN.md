# Arcadia design language

Arcadia is a full fork of ES-DE for the Steam Deck. Every screen, menu and dialog follows one cozy design language: a warm dark
ground, soft pastel cards, rounded shapes, one accent for focus, and plain sentence-case words. This file is the reference; the
theme (`themes/arcadia`) and the program's own screens both take their values from it.

## Principles

1. **Warm and calm.** Warm browns instead of blue-black, cream instead of white, soft pastels for consoles. Nothing shouts.
2. **Legible first.** Readable from a couch and on a 7" handheld. Text on a surface has at least 4.5:1 contrast.
3. **Focus is unmistakable.** The item the controller is on is the largest thing in view and wears the accent ring.
4. **Content leads, chrome is quiet.** Console cards and covers carry the screen; the clock and button hints stay muted.
5. **Carousels, not grids.** Consoles and games are carousels: the selected one sits large in the middle, the rest get
   smaller and fainter on both sides.
6. **Say it plainly.** Sentence case everywhere ("Show consoles with no games"), short words, no jargon on the main path.
7. **It works with no art.** A library with no scraped covers still looks finished: named tiles, never blank boxes.

## Colour

Four schemes. Ember, moss and dusk share the same ground and differ only in the accent; linen is for bright rooms.

| Token | Ember (default) | Linen | Use |
|---|---|---|---|
| ground | `#1c1613` | `#f4ebdf` | screen ground |
| surface | `#2a211c` | `#fbf5ec` | cards, dialogs, chips |
| raised | `#362a23` | `#efe2d2` | the focused row's fill, buttons at rest, title-only tiles |
| line | `#3a2e27` | `#e6d8c7` | faint hairlines between rows |
| text | `#f7ecde` | `#2a1f19` | titles and labels |
| muted | `#c9b8a6` | `#6e5b4c` | details, values, button hints |
| accent | `#f4a259` amber (moss `#a8c69f`, dusk `#b9a6dc`) | `#c8621e` | the focus ring, switches that are on, the main button, slider fill |
| text on accent | `#2a1708` (moss `#1c2a1b`, dusk `#2b2240`) | `#fff8f0` | |
| pill | `#f7ecde` on `#1c1613` text | `#2a1f19` on `#fbf5ec` | the chosen section in the settings rail, button glyphs |
| ok / warn | sage `#a8c69f` / rose `#e9897a` | `#4f7a45` / `#b5453a` | status only |

Console pastels: amber `#f4a259`, sand `#f2c27a`, sage `#a8c69f`, mint `#9fd0c4`, blue `#9fb8d6`, lavender `#b9a6dc`,
pink `#e6a3c4`, rose `#e9897a`, oat `#c9b8a6`, each with a dark ink of the same hue for text drawn on it. Familiar consoles get
the pastel nearest their own colours (Super Nintendo lavender, NES rose, Game Boy sage); the rest get a stable one from their
name (`themes/arcadia/tools/make_assets.py`).

## Type

Two families, both bundled (SIL Open Font License, `licenses/`):

- **Fraunces SemiBold** for titles: the wordmark, screen and card titles, console names, game names.
- **Nunito** for everything you read and press: Bold for labels, ExtraBold for emphasis and chips, SemiBold for details.

| Role | Size (share of screen height) | Font | Example |
|---|---|---|---|
| Hero | 5.4% | Fraunces | the selected game's name |
| Title | 4.2-5.2% | Fraunces | "Settings", a card's title, the wordmark |
| Label | 3.2% | Nunito Bold | rows, buttons, counts |
| Detail | 2.7% | Nunito SemiBold | descriptions and values |
| Chip and caption | 2.1-2.4% | Nunito ExtraBold | fact chips, the version line (minimum size anywhere) |

Menu text is written in capitals in the code and shown in sentence case in English (`Utils::Localization::readable`, which
keeps names and acronyms such as ROM, BIOS and RetroArch); other languages are shown as translated.

## Shape

- Everything is rounded: cards 30 px at 1280x800, rows and tiles about a third of their height, buttons and chips fully round.
- One level of depth: cards on the ground. Light comes from soft glows in a console's pastel, never from drop shadows.
- Spacing comes from a 1%-of-height unit; cards sit 2% of the width apart.

## Focus

- **Carousels:** the selected card or cover is 1.5-1.7x the size of the others and wears a 4 px accent ring with a gap
  round it; the others are at 55-70% opacity and slightly desaturated. A soft glow in the console's pastel sits behind.
- **Menus and dialogs:** the focused row is a raised, rounded card with a 3 px accent ring; it keeps its size so nothing
  shifts. In the settings rail the chosen section is a cream pill with dark text. The focused button is filled with the accent.
- **Controller-only:** every control is reachable with the D-pad, A/B and the shoulder buttons.

## Screens

| Screen | Made with | Notes |
|---|---|---|
| Consoles | theme | the wordmark and clock on top; a carousel of pastel console cards (the console's picture and name); maker, year and game count below |
| Games | theme | the console's name on top; a carousel of covers (cropped to one shape) or named tiles; the name, fact chips (year, genre, players, last played), the description and a Play button below; a plain-list variant for big libraries |
| Settings | program | "Settings" over a rail of sections on the left (Setup, Look and feel, Sound, Controllers, Covers and info, Collections, Advanced, Tools, Quit); each section opens as a card beside it, and L/R step between sections |
| Setup | program | a progress ring and a checklist (games, emulators, controls, folder access, cloud saves, BIOS files), each step running its tool when chosen, beside a card of tools |
| Dialogs | program | a centred card with room round the message and pill buttons |
| Boot, launch, screensaver | program | the same ground; the boot screen is the amber mark over the Fraunces wordmark with an amber progress bar (`tools/make_splash.py`); the screensaver dims |

## Controls

- **Switch:** a filled accent pill with the knob cut out on the right when on; an outlined muted pill with a solid knob on
  the left when off.
- **Slider:** a 6 px rounded track, filled with the accent up to a cream knob.
- **Choice:** the value in sentence case between thin chevrons.
- **Button hints:** cream round glyphs with the letter cut out, then the action in muted sentence case.

## Motion

| What | Duration | Curve |
|---|---|---|
| Moving between items | 200 ms | ease-out |
| Opening settings, or a section card | 220 ms | ease-out slide in from the left |
| Closing | 150 ms | ease-in |

## Not part of the language

Anything in the games themselves (emulator windows). The design stops at the moment a game starts.
