# Better Gwent

Smarter opponents and fair decks, from White Orchard to the endgame. An unofficial mod for
The Witcher 3: Wild Hunt (**Steam patch 5.01**) that gives Gwent a stronger opponent AI with
three difficulty levels, NPC decks that can follow the strength of yours, better wagers and the
game's own unused card art, without changing any card, ability or rule. Everything returns to
vanilla when the mod is turned Off, and it can be installed or removed at any time.

> **Not magic, not a miracle.** The AI can still make mistakes. Better Gwent only
> improves how it decides and what it brings, through math, search and a lot of testing.

*Formerly "Better Gwent AI": the AI is now one feature among several.*

This is an unofficial fan work and is not approved or endorsed by CD PROJEKT RED.
**Status: 0.9.0 beta.**

## Features

- **A stronger opponent AI**: Easy, Normal and Hard (default), independent of the game
  difficulty; on errors it falls back to the native AI, so a match never stalls.
  [Details](docs/FEATURES.md#the-opponent-ai)
- **Fair play**: the AI never sees your hand, your deck or the order of your draws; it reasons
  from what a human player could see. [Details](docs/FEATURES.md#fair-play-the-ai-does-not-see-your-cards)
- **NPC decks: Adaptive (default), Original or Strong**: which existing cards an NPC brings,
  rebuilt in memory for each match, safe for saves. [Details](docs/NPC_DECKS.md)
- **NPC deck strength, a vanilla bug I fix**: the base game gives NPCs their extra cards
  whatever your deck; with the mod On they follow your deck's strength again.
  [Details](docs/NPC_DECKS.md#original-the-extra-card-rule-repaired)
- **The NPC exchanges opening cards** (Normal and Hard), as you can.
  [Details](docs/FEATURES.md#the-opponent-ai)
- **One artwork per card copy** (while the mod is On): the copies of one card show different
  pictures, from the game's own art. Visual only. [Details](docs/CARD_ART.md)
- **Better wagers**: a higher maximum bet for common matches, and optional stronger NPC decks at
  higher stakes. [Details](docs/FEATURES.md#wagers)
- **Optional "AI plays for you"**, and a menu in 18 languages.

## Install

Extract the archive into the game folder, register `modGwentAI.xml;` in the filelists if they
exist, start the game and switch the mod On in **Options > Mods > Better Gwent**. Full steps,
updating from "Better Gwent AI" and uninstall: [docs/INSTALL.md](docs/INSTALL.md).

## Options

- **Better Gwent On/Off**: Off = the original game, wagers included.
- **Difficulty** (how well the NPC thinks) and **NPC decks** (which cards it plays): two
  independent dials. [Choosing your challenge](docs/FEATURES.md#choosing-your-challenge)
- **AI plays for you**, **Gwent max bet** and **Higher stakes, stronger opponent**.
  [All options](docs/FEATURES.md)

## Compatibility

Mods that replace the Gwent board or deck builder screens cannot run together with Better Gwent;
other script mods usually can. [Compatibility with other mods](docs/KNOWN_LIMITATIONS.md#compatibility-with-other-mods)

## How it is tested

Every change is measured in a simulator that reproduces the game's Gwent rules, on the same decks
and luck, and then played in real matches in the game. Methods and all results:
[docs/TESTING.md](docs/TESTING.md).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/kpis-dark.svg">
  <img src="docs/img/kpis-light.svg" alt="1,253,132 simulated matches, 1,286 hours of Lab CPU time, 123 recorded matches, 357 mistakes found, 25% more NPC wins than the native AI over all 9 deck mode and level settings" width="880">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/levels-dark.svg">
  <img src="docs/img/levels-light.svg" alt="Better AI score share against the native AI: Easy 52.9%, Normal 57.6%, Hard 59.5% (native AI = 50%)" width="880">
</picture>

## Documentation

- [Installation](docs/INSTALL.md): install, options, compatibility and uninstall.
- [Features and options](docs/FEATURES.md): every option in detail, fair play and how to choose your challenge.
- [NPC decks](docs/NPC_DECKS.md): the Original / Adaptive / Strong option and the repaired extra-card rule.
- [Card art](docs/CARD_ART.md): one artwork per card copy.
- [Recorder edition](docs/RECORDER.md): for testers only, not a release; records matches to help development.
- [Testing](docs/TESTING.md): methods, results and running totals.
- [Research](docs/RESEARCH.md): papers, tools, and what I tried and dropped.
- [Development](docs/DEVELOPMENT.md): repository layout, local setup, builds, tests and the Gwent AI Lab.
- [Known limitations](docs/KNOWN_LIMITATIONS.md): what does not work well yet, and why.
- [Studying the game](docs/game-study/README.md): cut cards, unused art, abandoned features and bugs of the base game.
- [Roadmap](docs/ROADMAP.md): planned work, including optional modules for new cards and card balance.
- [Repository scope](docs/PUBLICATION_SCOPE.md): what may and may not be committed.
- [Contributing](CONTRIBUTING.md): what a change needs before it is kept.

Detailed research notes and the working log are kept locally, outside the repository.

## AI disclosure

This project is built with AI assistants, used as tools throughout development and
maintenance.

In practice the AI takes the repetitive, low-level work: writing code for a direction
that is already decided, running and reading simulations, building validation scripts,
tracking down the exact point of a bug, and drafting and updating documentation. Scope,
design and gameplay decisions are mine. Every change is measured in the simulator and
tested in game before it is kept, and nothing is merged or released without my review,
including code the AI wrote entirely.

## Credits

- [JPEXS Free Flash Decompiler](https://github.com/jindrapetrik/jpexs-decompiler): the open-source
  Flash decompiler and editor used to build the V8 AI into the game's Gwent interface.
- The [WolvenKit](https://github.com/WolvenKit) and W3Edit teams: for pioneering Witcher 3
  reverse engineering and documenting the file formats (CR2W, bundles) that the community
  tools, including this project's own, build on.
- The Witcher 3, Gwent and all their assets belong to CD PROJEKT RED.

## License and rights

Original contributions are covered by [LICENSE](LICENSE) (MIT). The game, game-derived
material, names and trademarks are excluded. See [NOTICE](NOTICE.md).
