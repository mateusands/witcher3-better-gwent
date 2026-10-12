# Known limitations

What Better Gwent does not do well yet, or cannot do, and why. Items move to the
[Roadmap](ROADMAP.md) or out of this list as they are fixed.

## NPC decks

- **Adaptive has a ceiling against very strong player decks.** Adaptive builds the NPC deck up to
  a target strength (85% of yours on Easy, 100% on Normal, 110% on Hard), from its own faction
  and neutral cards. Some NPC decks cannot reach a high target even with every hero allowed.
  Test, 12 October 2026, against a 237-strength player deck: on Hard only 24% of the NPC decks
  reach the target. In match g154 a 266-strength player deck met a Scoia'tael NPC deck of 234,
  the strongest that NPC's faction allows under the deck rules.
- **The deck builder rates cards by their printed power.** Cards whose value is in their ability
  are underrated: Dandelion (a Commander's Horn on a unit) and Gaunter O'Dimm (summons three
  Gaunter O'Dimm: Darkness, 14 power in one play) almost never enter Strong decks. Under test.

## AI decisions

Seen in recorded matches and being tested as Lab switches (not yet changed in the game):

- Spending too many cards to win round 1, or to chase a round it cannot win.
- Winning a round by far more than needed.
- A leader weather ability used too early (for example a first-move Biting Frost on an empty
  board), and units then played into its own weathered row; an agile unit placed in a
  weathered row while its other row is free.
- A Medic played with nothing in the graveyard to revive.

## Card art

- The per-copy art shows in matches and in the deck builder. A few views keep the stock picture:
  the leader carousel (leaders have no alternate art), and the card notification of other mods.
- In the deck builder, a split tile moves the top copy of that card, not always the tile clicked;
  the counts are always right.

## Simulator

- One recorded native match (g100) does not replay exactly, because of a Scorch ordering case.
  It is kept as a known open issue and never hidden by the tests.
