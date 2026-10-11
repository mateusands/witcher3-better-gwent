# Better Gwent AI

An unofficial mod in development for The Witcher 3: Wild Hunt (**Steam patch 5.01**)
that replaces the Gwent opponent's decisions with a stronger AI, without changing any
card, ability, rule or native NPC deck.

This is an unofficial fan work and is not approved or endorsed by CD PROJEKT RED.
The repository is private and work in progress: there is no release yet.

## Features

- **Options > Mods > Better Gwent AI**, with an On/Off switch (Off = vanilla game).
- Easy, Medium, **Hard (default)** and Expert, independent of the game difficulty.
- Optional **AI plays for you** (Off by default), using the selected difficulty.
- Common Gwent wager maximum: Vanilla (10), 25, 50, 100 or 150.
- Optional stronger existing NPC deck variants at higher stakes (Off by default).

## Fair play: the AI does not see your cards

The AI plays harder by reasoning better, not by cheating. It only uses what a human
player could see: the board, both graveyards, how many cards you hold, your faction and
leader, the cards you have already played and cards revealed by an effect. It never
reads your hand, your deck list or the order of your draws. It samples plausible hidden
hands from public information instead, and an automated test swaps the hidden hand for
different cards and checks that the decision does not change.

## Status

- The V8 decision engine (ActionScript, `mod/v8/as3`) runs inside the game and plays
  whole matches; on errors or time-outs it falls back to the native AI, so a match
  never stalls.
- Simulator benchmark against the native AI (110 deck matchups covering every faction
  and leader, both seats, 440 games per level; 220 = parity):

  | Level | Better AI | Native |
  | --- | --- | --- |
  | Easy | 242.5 | 220 |
  | Medium | 252.5 | 220 |
  | Hard | 253 – 274.5 | 220 |
  | Expert | 264 – 268 | 220 |

- In progress: blunder hunting (normal and deep), player-style deck matchups (including
  early-game decks), then self-play parameter tuning and a small value network.

## Testing at a glance

| As of 2026-10-11 | |
| --- | --- |
| Simulated matches (Gwent AI Lab + earlier evaluations) | ~70,700 |
| Lab CPU time | ~10 hours |
| Recorded in-game matches analysed | 57 |
| Costly decisions found by the blunder hunter | 43 |

How the AI is measured (fidelity replays, benchmarks, blunder hunting, in-game checks)
and the running totals: [docs/TESTING.md](docs/TESTING.md).

## NPC deck strength: a vanilla bug we fix

Each NPC deck has dynamic extra cards on 15 levels, and each level has a requirement
compared against the strength of the player's deck: the extra card enters only when the
player's deck is strong enough. The NPC deck was meant to grow with the player's.

The vanilla `GetDifficulty` function has its size check inverted: it only returns a real
requirement for **level 15**, and **levels 1–14 always return 0**. So every extra card of
levels 1–14 always enters the NPC deck, even against a weak early-game player deck.

**With Better Gwent AI On, the intended rule applies at every level and every difficulty**:
each extra card uses its real requirement (base 145–230 by level; +80 on Easy, −80 on
Hard and Expert). The highest optional stronger-stakes stage still gives every extra
card. With the mod Off the game is untouched. No card or deck definition is added,
removed or edited.

What changes in practice (extra cards entering, summed over all NPC decks, 225 total):

| Player deck strength | Easy | Medium | Hard / Expert |
| --- | --- | --- | --- |
| 100 (early game) | 0 (vanilla 223) | 0 (vanilla 223) | 101 (vanilla 223) |
| 150 | 0 | 12 | 225 |
| 200 | 0 | 131 | 225 |
| 250 | 62 | 225 | 225 |
| 300 | 185 | 225 | 225 |

Our own recorded player decks measured 214–284, so Hard and Expert NPCs keep every extra
card against a normal deck; the fix mainly makes the early game and Easy/Medium fair.

## Research behind it

The AI samples plausible hidden hands and searches its moves and the opponent's replies
(Information Set Monte Carlo Tree Search; Perfect Information Monte Carlo sampling).
Tests compare options on the same luck, as duplicate poker does, and the deep blunder hunt
narrows every legal move with Sequential Halving (as in Gumbel MuZero). Next: parameter
tuning by self-play (SPSA) and a small value network (AlphaZero). Papers, tools and what I
tried and dropped: [docs/RESEARCH.md](docs/RESEARCH.md).

## Repository layout

| Path | Contents |
| --- | --- |
| `mod/settings/` | Options menu (XML, English labels) and WitcherScript wrappers for settings, wagers and deck difficulty. |
| `mod/v8/as3/` | The V8 AI in ActionScript, compiled into the game's Gwent interface at build time. |
| `mod/recorder/`, `mod/probe/`, `mod/feasibility/` | Script sources of diagnostic builds (match recorder, probes). |
| `tools/` | Build pipeline (`build_v8_core.py`, `build_v8_package.py`), patchers that insert the mod hooks, file-format helpers, recorder readers. |
| `sim/` | Python reference of the V8 policy, evaluation scripts and tests. |
| `sim/gwentsim/` | Policy, search, belief and position models (original code). |
| `lab/` | **Gwent AI Lab**: crash-safe job runner with a local web panel. |
| `docs/` | How the AI is tested, development setup and repository scope. |

## Development (local setup)

Prerequisites: Python 3, `pytest`, `psutil` (Lab), Java + FFDec at `tools/ffdec`, and a
Witcher 3 5.01 installation. Details in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md);
PyPy is installed separately (`uv python install pypy3.11`) and is not part of the repository.

```sh
python3 tools/build_settings.py                     # menu labels -> *.w3strings
python3 tools/build_v8_core.py --with-recorder      # compile V8 into the Gwent interface
python3 tools/build_v8_package.py                   # -> dist/BetterGwentAI-V8-5.01-test.zip
python3 -m pytest sim/tests -q                      # test suite
```

Back up the game files and saves before installing a test build.

### Gwent AI Lab

Runs long benchmarks and blunder hunts in the background, with progress, CPU/GPU/RAM
and disk usage in a browser panel (`http://127.0.0.1:8765`, local only).

```sh
python3 lab/gwent_lab.py            # PC: starts paused, press Resume
python3 lab/gwent_lab.py --no-open  # headless server (reach it through an SSH tunnel)
GWENT_LAB_SERVER=user@host lab/open_server_panel.sh
```

- Data lives in a folder marked with `.gwent_ai_lab_root` (default `/mnt/hdd/GwentAILab`,
  `--data` or `GWENT_LAB_DATA` to change); the Lab refuses to start without the marker.
- Crash-safe: results are committed together with the task state, so a power cut only
  repeats the tasks that were running (`lab/selftest_resume.py` verifies this).
- Workers run at low priority, their number is adjustable live, and they pause while
  `witcher3.exe` runs or when the disk cap is reached.
- Continuous jobs queue the next seed by themselves when they finish.
- Workers can run under PyPy (setting `worker_python`, e.g. from `uv python install pypy3.11`):
  1.7x faster on benchmarks and 2.1x on blunder hunts with identical results, so fewer
  workers (less heat) produce the same output. Changing the setting swaps workers live.

## Documentation

- [Testing](docs/TESTING.md): methods, results and running totals.
- [Research](docs/RESEARCH.md): papers, tools, and what I tried and dropped.
- [Development](docs/DEVELOPMENT.md): local setup, builds, tests and the Lab.
- [Repository scope](docs/PUBLICATION_SCOPE.md): what may and may not be committed.

Detailed research notes and the working log are kept locally, outside the repository.

## AI disclosure

Transparency matters here: this project is built with AI assistants used as tools
throughout development and maintenance.

In practice the AI takes the repetitive, low-level work: writing code for a direction
that is already decided, running and reading simulations, building validation scripts,
tracking down the exact point of a bug, and drafting and updating documentation. Scope,
design and gameplay decisions are mine, every change is measured in the simulator and
tested in game before it is kept, and nothing is merged or released without my review,
including code the AI wrote entirely.

## License and rights

Original contributions are covered by [LICENSE](LICENSE) (MIT). The game, game-derived
material, names and trademarks are excluded. See [NOTICE](NOTICE.md).
