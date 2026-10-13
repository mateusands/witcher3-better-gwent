# NPC deck option

Menu option **NPC decks: Original / Adaptive / Strong** (Options > Mods > Better Gwent),
Adaptive by default (a saved choice is kept).
It only changes *which existing cards* an NPC brings to a match, and only while Better
Gwent is On.

## The three modes

Native NPC decks are uneven: many carry piles of weather and special cards (about 10 special
cards on average, up to 13 weather cards), and the vanilla game gives them extra cards regardless
of your deck because of an inverted check (see below). This option chooses what the NPC brings:

- **Original:** the NPC's own deck with the game's own adaptive rule, repaired. Each NPC has a
  few extra cards on 15 levels that enter only when your deck is strong enough; with the inverted
  check fixed, they finally follow your deck. But it is a small lever: 4.4 extra cards per NPC on
  average (14 of 51 NPCs have none), worth about +31 strength (173 to 205), while a good player
  deck sits at 250-300, and the pile of weather cards stays in.
- **Adaptive:** the same idea done fully. The NPC keeps its faction, leader and heroes; its whole
  deck is made legal and playable, and its weakest units are swapped for better cards of its
  faction until it matches the strength of *your* deck at that match: 85% on Easy, 100% on
  Normal, 110% on Hard. A fair fight at every stage of the game.
- **Strong:** the best deck the NPC's faction allows under the same rules.

How the two dials (AI difficulty and NPC decks) combine: [Choosing your
challenge](FEATURES.md#choosing-your-challenge).

## Original: the extra-card rule, repaired

Each NPC deck has dynamic extra cards on 15 levels, and each level has a requirement compared
against the strength of the player's deck: the extra card enters only when the player's deck is
strong enough. The NPC deck was meant to grow with the player's.

The vanilla `GetDifficulty` function has its size check inverted: it only returns a real
requirement for **level 15**, and **levels 1-14 always return 0**. So every extra card of levels
1-14 always enters the NPC deck, even against a weak early-game player deck.

**With Better Gwent On, the intended rule applies at every level and every difficulty**: each
extra card uses its real requirement (base 145-230 by level; +80 on Easy, -80 on Hard). The
highest optional stronger-stakes stage still gives every extra card. With the mod Off the game is
untouched. No card or deck definition is added, removed or edited.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="img/requirements-dark.svg">
  <img src="img/requirements-light.svg" alt="Extra NPC cards by the strength of the player's deck: vanilla gives about 223 of 225 at any strength; with Better Gwent On, Hard reaches all extras at 160, Normal at 240, Easy at 320" width="880">
</picture>

Our own recorded player decks measured 214-284, so Hard NPCs keep every extra card against a
normal deck; the fix mainly makes the early game and Easy/Normal fair. The bug is also listed
with the other [bugs of the base game](game-study/base-game-bugs.md).

## Original: how the AI plays these decks

With the Original decks, the NPC also plays two small changes that the Lab proved on these decks
only (Test, 13 October 2026: each passed three times on new matchups; on Adaptive and Strong they
were worse, so there the AI is unchanged):

- **Spy first:** while later rounds remain and the player still plays, the NPC plays its cheapest
  Spy before other cards, so it draws its cards early.
- **A more careful look ahead:** in its second step of look-ahead the search picks its next move
  for each imagined player hand as if it knew that hand; with these decks it trusts only 20% of
  what that step adds to a move.

The NPC decks option reaches the AI with the match settings; your own side in autoplay is not
affected.

## Safe for saves

- The game builds each NPC deck when a match starts, from its own deck definitions
  (`GetCurrentAIDeck` returns a copy). The option rebuilds that copy in memory for that
  match only.
- No card's power or ability changes, no deck definition is edited and nothing is written
  to the save. The cards you win from NPCs are unchanged.
- Turn the option (or the mod) Off and the next match uses the native deck again.

## Fair play

An NPC deck reacts only to what an NPC may know before a match: the strength of the player's
selected deck (the game's own NPC decks already add cards by it) and the player's faction.
Never the player's leader or individual cards. During a match the AI sees what both players
see: the board, the graveyards, both leaders and the number of cards in hand.

## Copies of a card

NPC decks may hold up to three copies of a card that is not a hero, as the game's own NPC decks
do: several of them carry two Vattier de Rideaux, Villentretenmerth or Botchlings, although a
player can own only one of each. Better Gwent keeps that standard of the game. Heroes are unique
in every NPC deck, also when a quest adds its own extra cards to the NPC.

## How a deck is built

Like a seasoned player builds, from the NPC's own faction plus neutral cards:

- **Identity:** same faction and leader; the NPC's heroes stay in its deck.
- **Size:** at least 22 units; special cards limited to a lean playable kit. Native NPC decks
  carry about 10 special cards on average, and up to 13 weather cards.
  - **Strong:** 22 units and at most 4 special cards, no Triss;
  - **Adaptive:** at most 2 special cards;
  - when the kit is cut, it keeps first the weather the leader pulls, then Scorch, a Horn,
    a Decoy and Clear Weather.

  Test, 12 October 2026 (1,020 paired games per cell; NPC win share against the 0.9.0 shape
  of up to 8 specials, 24 Strong units and Triss): Strong +15.0 points on Hard (z 9.7) and
  +15.9 on Normal (z 10.1); Adaptive +4.4 on Hard (z 2.6) and +8.2 on Normal (z 4.8). Removing
  Triss alone cost about 2 points; in the lean Strong shape it is part of the gain. The Lab
  switch `v090` rebuilds the old shape for comparison. A second test the same day, with new
  luck, confirmed it: the old shape was 5.3 to 9.5 points weaker in every cell.
- **Heroes (Adaptive):** Avallac'h and Yennefer stay allowed, 2 or 3 of the faction's heroes are
  drawn, Geralt or Ciri in about one deck in four, never Triss (in no NPC deck, fallback included); the game stores three variants
  per NPC and picks one per match. When those heroes cannot reach the target strength, every
  hero is allowed again, so a strong player deck still meets the strongest deck the rules allow.
  Tests, 12 October 2026: with the AI as shipped, faction heroes alone cost Adaptive 10.4
  points on Normal and 12.3 on Hard (z -7.6 and -8.9) against this version, which allows every
  hero when needed, so the fallback is essential. Strong keeps every hero (the faction-hero
  rule cost it about 5 points).
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

  Measured in the simulator (same decks and luck; the player side is played by Better AI):

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="img/deck-modes-dark.svg">
  <img src="img/deck-modes-light.svg" alt="NPC win share by deck mode against all player-style decks, Easy to Hard, Better AI vs native AI: Original 35-40%, Adaptive 64-74%, Strong 68-71% with Better AI" width="880">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="img/deck-modes-mine-dark.svg">
  <img src="img/deck-modes-mine-light.svg" alt="NPC win share by deck mode against my own real decks, Easy to Hard, Better AI vs native AI: Original 29-35%, Adaptive 61-71%, Strong 60-66% with Better AI" width="880">
</picture>

  Against my own real decks (140 games per cell), Adaptive goes from 37% on Easy to 53% on
  Hard, an even fight, and Strong stays hard but winnable at 52-55% on every level.
- In game: Adaptive decks were played and matched the table; switch the option on and off in
  the same save and the native deck returns.

## In the game

- `gwai_npc_decks.ws` wraps `CR4GwintManager.GetCurrentAIDeck`. With Better Gwent Off, the option
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
