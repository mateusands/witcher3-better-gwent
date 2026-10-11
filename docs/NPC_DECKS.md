# NPC deck option (in development)

A planned menu option, **NPC decks: Original / Adaptive / Strong**, Original by default.
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
- **Size:** at least 22 units; special cards limited to a playable kit (at most 8). Native
  NPC decks carry about 10 special cards on average, and up to 13 weather cards.
- **Weather:** at most two types, never one that hits the deck's own strong rows (a deck
  built on siege units carries no Torrential Rain); Skellige's weather-resistant leader is
  the exception.
- **Leader-aware:**
  - a leader that clears weather replaces the Clear Weather card;
  - a leader that doubles a row leaves one Horn for the other rows, and that row's units
    are preferred;
  - a leader that pulls a weather card from the deck gets exactly that card.
- **Synergy whole or not at all:** muster groups complete, tight bond with two or more copies,
  medics capped at two, spies capped at three. Avallac'h, the neutral hero spy, fits most decks.

**Adaptive** (internal mode name `balanced`) starts from the NPC's own deck, makes it legal under these rules, and swaps its
weakest units for better eligible ones until its strength reaches the strength of the
player's deck (the same measure the game uses for its extra NPC cards). The target follows the mod's
difficulty: 85% of the player's deck strength on Easy, 95% on Medium, 100% on Hard and 110% on
Expert. It is never weakened below the NPC's base deck. **Strong** builds the best deck the rules allow for the faction.
Only the strength of the player's deck is used, never the player's hand.

## Which NPCs

Every Gwent opponent, including quest and tournament players, except the tutorial.

## Testing

- An automatic rule check runs on every generated deck (all 51 NPC decks in Strong, all 490
  player-deck matchups in Adaptive pass with no violation).
- Simulator benchmarks compare Original, Adaptive and Strong against player-style decks
  (early-game, random, power, synergy and my own real decks) with the same luck.
  Target: Adaptive close to an even match, Strong above it.
- In game: switch the option on and off in the same save and confirm the native deck returns.

Code: `sim/gwentsim/npc_balance.py` (the in-game version will use decks precomputed from it).
