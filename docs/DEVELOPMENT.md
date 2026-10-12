# Development

Commands run from the repository root. They build and test locally; none of them installs
anything into the game.

## Requirements

- Python 3 with `pytest`; `psutil` for the Gwent AI Lab panel.
- PyPy 3.11 for faster Lab workers (optional): `uv python install pypy3.11`. PyPy is an
  external program and is not part of this repository.
- Java and FFDec at `tools/ffdec` (`ffdec.sh`, `ffdec-cli.jar`) to compile the V8 AI into
  the game's Gwent interface.
- The Witcher 3, Steam patch 5.01.

## Build

```sh
python3 tools/build_settings.py                  # menu labels (18 languages) -> *.w3strings
python3 tools/build_npc_decks.py                 # NPC deck table (needs the local vanilla XML)
python3 tools/build_v8_core.py                   # V8 AI into the Gwent interface
python3 tools/build_v8_package.py release        # -> dist/BetterGwent-<version>.zip
python3 tools/build_v8_core.py --with-recorder   # V8 AI + match recorder
python3 tools/build_v8_package.py recorder       # -> dist/BetterGwent-<version>-recorder.zip
```

`tools/extract_vanilla.py` copies the two Gwent interface files the build patches
(`gwint_game.redswf` and `deck_builder.redswf`) into the git-ignored `game/vanilla/swf`. The
deck builder tests read an FFDec script export of `deck_builder.swf` from
`game/vanilla/as_deck_builder` (`ffdec-cli -export script game/vanilla/as_deck_builder
game/vanilla/swf/deck_builder.swf`); without it they are skipped.

The version is `VERSION` in `tools/build_settings.py`; menu translations are in
`mod/settings/menu/labels.translations.json` (a missing text stays in English). Back up the
game files and saves before installing a test build. With the mod Off the game behaves
exactly as vanilla.

## Tests

```sh
python3 -m pytest sim/tests -q
```

The suite checks the settings and wager contracts, the deck-difficulty wrappers, the V8
policy in Python and the same policy compiled from ActionScript (run through Node), fair
play (hidden cards never change a decision), the NPC opening exchange against its Python
reference, the packages and replay fidelity. One replay (a Scorch ordering case) is a known
open failure.

## Measuring strength

The Gwent AI Lab runs benchmarks and blunder hunts in the background:

```sh
python3 lab/gwent_lab.py                          # panel at http://127.0.0.1:8765
python3 lab/report.py <lab databases>             # totals for docs/TESTING.md
python3 lab/dashboard.py <lab databases>          # README charts (docs/img, light and dark)
GWENT_LAB_SERVER=user@host lab/pull_results.sh    # copy a remote Lab's results locally
```

Job kinds: `benchmark` (Better AI vs native AI on the same decks and luck), `hunt`
(replays lost matches with alternative moves) and `deep-hunt` (every match, every move).
Sources: `pool` (NPC decks, every faction and leader) and `player` (NPC decks against
player-style decks, including early-game ones). See [TESTING.md](TESTING.md).

## In-game recordings

The recorder edition records every match into the game's user settings ([RECORDER.md](RECORDER.md)). `tools/rec_harvest.py`
moves finished records into `game/records/` for analysis; `tools/rec_read.py` parses them.
