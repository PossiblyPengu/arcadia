# Arcadia design language

Arcadia is a full fork of ES-DE for the Steam Deck. Every screen, menu and dialog follows one cozy design language: a pale
pastel ground, white cards, soft pastel colour everywhere, rounded shapes, one accent for focus, and plain sentence-case words. This file is the reference; the
theme (`themes/arcadia`) and the program's own screens both take their values from it. Its sister app
[Deckhand](https://github.com/PossiblyPengu/deckhand) uses the same colours, fonts and shapes (its `deckhand/theme.py`), so a change here
should be mirrored there.

## Principles

1. **Soft and calm.** Pastels carry the colour: console cards, section chips, the accent. Neutrals are pale lavender and
   plum, never brown or blue-black. Nothing shouts.
2. **Legible first.** Readable from a couch and on a 7" handheld. Text on a surface has at least 4.5:1 contrast.
3. **Focus is unmistakable.** The item the controller is on is the largest thing in view and wears the accent ring.
4. **Content leads, chrome is quiet.** Console cards and covers carry the screen; the clock and button hints stay muted.
5. **Carousels, not grids.** Consoles and games are carousels: the selected one sits large in the middle, the rest get
   smaller and fainter on both sides.
6. **Say it plainly.** Sentence case everywhere ("Show consoles with no games"), short words, no jargon on the main path.
7. **It works with no art.** A library with no scraped covers still looks finished: named tiles, never blank boxes.

## Colour

Two schemes: **cloud**, light pastels and the default, and **dusk**, the same pastels on a deep violet for playing in the dark.

| Token | Cloud (default) | Dusk | Use |
|---|---|---|---|
| ground | `#f4eff8` | `#1f1d2e` | screen ground |
| surface | `#ffffff` | `#2b2940` | cards, dialogs, chips |
| raised | `#f6f0fc` (menus), `#ece4f6` (tiles) | `#37344f` | the focused row's fill, buttons at rest, title-only tiles |
| line | `#eee7f4` | `#3a3752` | faint hairlines between rows |
| text | `#3a3150` plum | `#f6f1fa` | titles and labels |
| muted | `#7d7394` | `#bdb6d0` | details, values, button hints |
| accent | `#f08fae` pink | `#f7b2c4` | the focus ring, switches that are on, the main button, slider fill |
| text on accent | `#3a1f2e` | `#3a1f2e` | |
| pill | `#3a3150` with white text | `#f6f1fa` with `#1f1d2e` text | the chosen section in the settings rail |
| ok / warn | `#86bf7f` / `#d9707f` | `#a8d5a2` / `#f2a39a` | status only |

Pastels: peach `#f7c19a`, butter `#f5dd9b`, sage `#bcd9b0`, mint `#addfcf`, sky `#b3cdef`, lavender `#cdbdf0`,
pink `#f2b6cf`, rose `#f4b0a6`, cloud grey `#d4cee0`, each with a dark ink of the same hue for text drawn on it. They are used
for the console cards (familiar consoles get the pastel nearest their own colours: Super Nintendo lavender, NES rose, Game Boy
sage; the rest a stable one from their name, `themes/arcadia/tools/make_assets.py`) and for the chips behind the settings
section icons (Setup peach, Look and feel lavender, Sound sky, Controllers mint, Covers and info butter, Collections pink,
Advanced sage, Tools rose).

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
  shifts. In the settings rail the chosen section is a plum pill with white text (cream with dark text in dusk). The focused
  button is filled with the accent.
- **Controller-only:** every control is reachable with the D-pad, A/B and the shoulder buttons.

## Screens

| Screen | Made with | Notes |
|---|---|---|
| Consoles | theme | the wordmark and clock on top; a carousel of pastel console cards (the console's picture and name); maker, year and game count below |
| Games | theme | the console's name on top; a carousel of covers (cropped to one shape) or named tiles; the name, fact chips (year, genre, players, last played), the description and a Play button below; a plain-list variant for big libraries |
| Settings | program | "Settings" over a rail of sections on the left (Setup, Look and feel, Sound, Controllers, Covers and info, Collections, Advanced, Tools, Quit); each section opens as a card beside it, and L/R step between sections |
| Setup | program | a progress ring and a checklist (games, emulators, controls, folder access, cloud saves, BIOS files), each step running its tool when chosen, beside a card of tools |
| Dialogs | program | a centred card: a pastel badge that says what it is about (question lavender, done mint, problem peach, removing something coral, information sky; picked from the words and the main button), the first sentence as a Fraunces title, the rest quieter below, pill buttons |
| Notifications | program | a card at the top with the same badge beside the message, in sentence case; it slides down as it fades in. A problem says where to fix it (a missing emulator points to Setup → Emulators) |
| Setup tools | program | their output appears line by line as they work; when done, a badge beside the title says whether it worked |
| Boot, launch, screensaver | program | the scheme's ground; the boot screen is the lavender mark over the Fraunces wordmark with a pink progress bar (`tools/make_splash.py`, one for each scheme); the screensaver dims |

## Controls

- **Switch:** a filled accent pill with the knob cut out on the right when on; an outlined muted pill with a solid knob on
  the left when off.
- **Slider:** a 6 px rounded track, filled with the accent up to a plum knob (cream in dusk).
- **Choice:** the value in sentence case between thin chevrons.
- **Button hints:** round glyphs in the text colour with the letter cut out, then the action in muted sentence case.

## Motion

| What | Duration | Curve |
|---|---|---|
| Moving between items | 200 ms | ease-out |
| Opening settings, or a section card | 220 ms | ease-out slide in from the left |
| Closing | 150 ms | ease-in |

## Not part of the language

Anything in the games themselves (emulator windows). The design stops at the moment a game starts.
