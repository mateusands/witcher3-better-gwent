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
- **Factions are uneven.** Test, 12 October 2026, NPC win share against player-style decks:
  Northern Realms 77% (Adaptive) and 84% (Strong), Scoia'tael 53% and 43%. Scoia'tael has many
  low-power cards and the deck builder underrates the cards that could help it.
- **Geralt and Ciri come together too often.** Against a strong player deck, Adaptive's
  fallback allows every hero and takes both witchers (all four NPC decks of the Novigrad
  tournament, matches g158-g161). Taking one out costs strength (test, 13 October 2026: -2.8 on
  Hard); a stepped fallback (one witcher first) is being tuned.
- **Spies are counted by their power.** The Adaptive strength measure counts a spy's power for
  its owner, although that power goes to the opponent; a Nilfgaard deck with Stefan Skellen (9),
  Shilard (7) and Vattier (4) looks stronger than it plays. A fix is under test.
- **Decoys are chosen by spies only.** Lean decks rarely hold a Decoy; its worth also comes from
  the NPC's own Medics and row-scorch units. The deck tuner is choosing Decoys per player faction.
- **Fair play.** NPC decks react only to what an NPC may know before a match: the player's deck
  strength (the game's own NPC decks already follow it) and the player's faction. Never the
  player's leader or individual cards.
- **Skellige is validated in the simulator only.** The owner's game has no Blood and Wine
  expansion, so Skellige decks are not checked in real matches.
- Fixed, shipping in the next package: a quest's extra NPC card could duplicate a hero of an
  Adaptive or Strong deck (two Avallac'h in g162). The deck now leaves out such heroes and keeps
  any card within 3 copies counting the extra cards.

## AI decisions

Seen in recorded matches:

- Spending too many cards to win round 1, or to chase a round it cannot win. A first rule for
  round 1 was tested and dropped (it made the NPC weaker on Hard). Seen again in the Novigrad
  tournament: 13 cards for round 1 in g158, 9 cards and the leader for a lost round 1 in g160.
- Units played into their own weather when the whole hand is of that row (four melee units
  under Biting Frost in g161): the weather rule only switches to another unit that stays dry.
- Spies held instead of played early (g159: Stefan Skellen, Shilard and Vattier never played).
  Playing the cheapest spy first and valuing draws more are under test.
- Fixed, shipping in the next package: a leader weather ability or weather card that gains
  nothing (for example a first-move Biting Frost on an empty board), units played into their own
  weathered row, an agile unit placed in a weathered row while its other row is free, a Medic
  played with nothing in the graveyard to revive, and winning a round by far more than needed
  (the NPC now keeps a won round with the cheapest play the search values above passing).

## Card art

- The per-copy art shows in matches and in the deck builder. A few views keep the stock picture:
  the leader carousel (leaders have no alternate art), and the card notification of other mods.
- In the deck builder, a split tile moves the top copy of that card, not always the tile clicked;
  the counts are always right.

## Performance

- **The frame rate drops while the NPC thinks.** The AI runs in the Gwent screen itself, in small
  slices between frames so the game never freezes, but each frame then spends part of its time on
  the search, and the board's animations can stutter until the move is chosen. Recorded matches on
  Hard (13 October 2026, 200 decisions): about 1 s of thinking on average, up to about 2.4 s for nine
  moves in ten, and about 4.6 s at the longest. Easy and Normal search less and think for less time.
  The frame rate returns to normal as soon as the NPC plays.

## Compatibility with other mods

- **Mods that replace the Gwent screens do not work together with Better Gwent.** Better Gwent
  ships its own copy of the two Gwent screens, `gameplay\gui_new\swf\gwint\gwint_game.redswf`
  (the match) and `gameplay\gui_new\swf\gwint\deck_builder.redswf` (the deck builder); the game
  loads only one copy of each, so whichever mod loads first wins and the other one is ignored
  (the AI, the deck options or the card art of Better Gwent, or the other mod's changes).
  Example: Gwent FPS and UI Tweaks (Nexus 14117) replaces `gwint_game.redswf`. Pick one of them.
- Better Gwent's scripts are its own files (wrapping the game's functions, no game script
  replaced), so script mods that do not replace those two screens can run alongside it.

## Simulator

- One recorded native match (g100) does not replay exactly, because of a Scorch ordering case.
  It is kept as a known open issue and never hidden by the tests.
- Three of the four Novigrad tournament matches (g158, g159, g161) do not replay exactly: the
  simulator and the game differ around a Medic reviving a card (the native AI's random choices
  while it evaluates the revived card). Open: in such moments the simulated native AI may
  choose differently from the game's.
