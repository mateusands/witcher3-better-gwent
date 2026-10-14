# Contributing to Better Gwent

Thanks for helping. Better Gwent is a fan modification for The Witcher 3: Wild Hunt; this guide
explains what a change needs before it can be kept. Local setup, builds and the Lab are in
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Ground rules

- **Nothing from the game in the repository.** No game files, extracted XML or scripts, no
  textures, no built bundles or SWFs. Only work written for this project is committed; see
  [docs/PUBLICATION_SCOPE.md](docs/PUBLICATION_SCOPE.md). The only exception is the game's own
  unused card art shown in the docs: `docs/img/bond-card-art.png` and `docs/img/lost-cards/`.
- **English** for code, comments, commits and documentation.
- **Install and uninstall at any time.** The mod never writes to saves, game folders or the
  card definitions. Everything ships in `Mods/modBetterGwent` and the menu file.
- **Off means vanilla.** With the main switch Off the game behaves and looks as shipped,
  wagers included.
- **The core changes no card, ability or rule.** Card changes (new cards, balance) belong in
  separate, optional modules; see the [Roadmap](docs/ROADMAP.md).
- **Fair play.** The AI only uses what a player could see; it never reads your hand or deck order.

## AI-assisted contributions

You may use AI tools, as long as you say so. As in other open emulation and modding projects
(shadPS4, RPCS3), every contribution says whether AI helped:

- **Commits:** add the trailer `AI-assisted: yes` (or `AI-assisted: no`) at the end of the message.
- **Pull requests and issues:** start the description with **AI-assisted: yes** or **AI-assisted: no**,
  and, when yes, say in one line what the AI did (for example "wrote the first draft of the
  parser; I reviewed and tested it").
- **You are responsible** for every line you submit, AI-written or not: you understand it, it
  follows the rules above and below, and its tests and Lab measurements are yours to answer for.
- Undisclosed AI use, or AI-generated changes submitted without being reviewed and tested by the
  contributor, are closed without review.

## Changing the AI or the NPC decks

1. **Python first.** The simulator in `sim/gwentsim` is the reference. Make the change there,
   behind an experiment switch, so it can be compared with the current behaviour.
2. **Measure it in the Lab.** Paired games: the same decks and the same luck with and without
   the switch, against player-style decks, at Normal and Hard, with Adaptive and Strong NPC
   decks. A change is kept only when it is proven (|z| of at least 2 in its favour) or proven
   harmless where its purpose is not strength (for example variety). Heavy batteries run on
   rented servers, not on a player's PC.
3. **Port to AS3.** The game runs the same logic in `mod/v8/as3`. Python and AS3 must agree
   decision for decision; the parity tests in `sim/tests/test_v8_as_*.py` check it.
4. **Check recorded matches.** `sim/record_review.py` rebuilds in-game matches from the
   recorder edition and compares every NPC decision with the reference.
5. **Write the result down.** Charts come from `lab/dashboard.py`; results go in
   [docs/TESTING.md](docs/TESTING.md) or [docs/RESEARCH.md](docs/RESEARCH.md), dated in plain
   words, for example "Test, 12 October 2026: ...".

## Before you open a pull request

- `python -m pytest -q sim/tests` passes (known failures are listed in docs/TESTING.md).
- Built packages (`tools/build_v8_package.py release` and `recorder`) pass their tests.
- The game was started with the change at least once: scripts compile, a match runs, and the
  mod Off still gives the original game.
- Docs updated where the behaviour changed (README features, INSTALL, NPC_DECKS).
- Commits are small and say what changed and why, in the present tense
  ("Adaptive: every hero allowed when faction heroes cannot reach the target").
- The commits and the pull request description carry the AI-assisted line (see above).

## Reporting a problem

Say which edition (release or recorder), the mod settings (difficulty, NPC decks, wagers), what
happened and what you expected. A screenshot helps. With the recorder edition, the match itself
can be rebuilt and checked decision by decision; see [docs/RECORDER.md](docs/RECORDER.md).
