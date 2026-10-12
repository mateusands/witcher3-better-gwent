# NPC deck option

Menu option **NPC decks: Original / Adaptive / Strong** (Options > Mods > Better Gwent),
Original by default.
It only changes *which existing cards* an NPC brings to a match, and only while Better
Gwent AI is On.

## Safe for saves

- The game builds each NPC deck when a match starts, from its own deck definitions
  (`GetCurrentAIDeck` returns a copy). The option rebuilds that copy in memory for that
  match only.
- No card's power or ability changes, no deck definition is edited and nothing is written
  to the save. The cards you win from NPCs are unchanged.
- Turn the option (or the mod) Off and the next match uses the native deck again.

## How a deck is built

Like a seasoned player builds, from the NPC's own faction plus neutral cards:

- **Identity:** same faction and leader; the NPC's heroes stay in its deck.
- **Size:** at least 22 units; special cards limited to a lean playable kit. Native NPC decks
  carry about 10 special cards on average, and up to 13 weather cards.
  - **Strong:** 22 units and at most 4 special cards, no Triss;
  - **Adaptive:** at most 2 special cards;
  - when the kit is cut, it keeps first the weather the leader pulls, then Scorch, a Horn,
    a Decoy and Clear Weather.

  Lab round 4 (2026-10-12, 1,020 paired games per cell, NPC win share against the 0.9.0 shape
  of up to 8 specials, 24 Strong units and Triss): Strong +15.0 points on Hard (z 9.7) and
  +15.9 on Normal (z 10.1); Adaptive +4.4 on Hard (z 2.6) and +8.2 on Normal (z 4.8). Removing
  Triss alone cost about 2 points; in the lean Strong shape it is part of the gain. The Lab
  switch `v090` rebuilds the old shape for comparison.
- **Weather:** at most two types, never one that hits the deck's own strong rows (a deck
  built on siege units carries no Torrential Rain); Skellige's weather-resistant leader is
  the exception.
- **Leader-aware:**
  - a leader that clears weather replaces the Clear Weather card;
  - a leader that doubles a row leaves one Horn for the other rows, and that row's units
    are preferred;
  - a leader that pulls a weather card from the deck gets exactly that card.
- **Synergy whole or not at all:** muster groups complete (a card that calls others, like
  Arachas Behemoth, comes with the cards it calls), tight bond with two or more copies,
  medics capped at two, spies capped at four. Avallac'h, the neutral hero spy, fits most decks.
- **Never Olaf:** the original game's board can throw an error when Olaf's effect lands after
  he left the board, so the builder never adds him (Madman Lugos takes his place in Strong).

**Adaptive** (internal mode name `balanced`) starts from the NPC's own deck, makes it legal under these rules, and swaps its
weakest units for better eligible ones until its strength reaches the strength of the
player's deck (the same measure the game uses for its extra NPC cards). The target follows the mod's
difficulty: 85% of the player's deck strength on Easy, 100% on Normal and 110% on Hard. It is never weakened below the NPC's base deck. **Strong** builds the best deck the rules allow for the faction.
Only the strength of the player's deck is used, never the player's hand.

## Which NPCs

Every Gwent opponent, including quest and tournament players, except the tutorial.

## Testing

- An automatic rule check runs on every generated deck (all 51 NPC decks in Strong, all 490
  player-deck matchups in Adaptive pass with no violation).
- Simulator benchmarks compare Original, Adaptive and Strong against player-style decks
  (early-game, random, power, synergy and my own real decks) with the same luck.
  Target: Adaptive close to an even match, Strong above it.
- In game: Adaptive decks were played and matched the table; switch the option on and off in
  the same save and the native deck returns.

## In the game

- `gwai_npc_decks.ws` wraps `CR4GwintManager.GetCurrentAIDeck`. With Better AI Off, the option
  on Original, or the tutorial match, the native deck is returned untouched.
- The decks are not built in the game: `tools/build_npc_decks.py` writes a table
  (`gwai_npc_decks_data.ws`) for every native NPC deck variant (150 variants of 50 NPC decks; the tutorial deck is listed but never replaced): the Strong deck,
  and every deck Adaptive can produce, each with the strength the builder checked. Adaptive's
  target only decides when the builder stops, so the game takes the first deck that reaches
  the target. The target comes from the player's selected deck (the game's strength measure,
  computed in the script) times the difficulty share.
- The chosen deck gets a deck name with no extra cards, so the native extra-card levels do not
  add to it (as in the simulator).
- `sim/tests/test_npc_deck_table.py` checks that the table gives the simulator's deck for every
  NPC deck variant and target, and that the script's strength bonuses and difficulty shares
  match the simulator.

Code: `sim/gwentsim/npc_balance.py` (builder), `tools/build_npc_decks.py` (table),
`mod/settings/modGwentAISettings/content/scripts/local/gwai_npc_decks.ws` (game).
