# Roadmap

Planned work for Better Gwent. Nothing here is promised for a date; each item ships only after
it is measured in the Lab and played in game.

## Principles

- **The core stays as it is:** no card, ability or rule changes, and it can be installed or
  removed at any time. Off means the original game.
- **Card changes are optional modules.** Each one is a separate download in its own folder,
  does nothing unless installed, and can be combined with the core or left out.
- **Every module is measured.** The AI must know how to play the new or changed cards, and the
  NPC decks must use them sensibly, before a module is released.

## Optional modules

### Lost Cards (planned)

The game files keep artwork for cards that never made it into Gwent, for example a Northern
Realms [*Ballista Officer*](img/lost-cards/ballista-officer.png) and
[*Witch Hunters*](img/lost-cards/witch-hunters.png) (click to see the art). They have no power,
ability or text in the game. What we found while studying the game is gathered in
[Studying the game](game-study/README.md).

- Give them abilities that fit their faction (our own design, documented as such), starting
  with abilities the game already has (Tight Bond, Medic, Spy, Muster, Morale).
- **Additive, never stored in the save.** The intended design keeps the game's files and saves
  untouched, like the per-copy card art:
  - the card definitions are appended by our scripts to the list the game sends to the Gwent
    screens, so the game's card list is not replaced;
  - the art already ships with the game, and names and texts go in our own string files;
  - which new cards you own and put in a deck lives in the mod's own data, not in the save,
    and the cards join your deck only when a match starts;
  - removing the module leaves the save and your decks exactly as before.
- First step: an in-game feasibility test with one test card (shown, played and scored
  correctly; save and decks unchanged after uninstalling) before any real card is designed.
- **Icons already in the game, kept for these cards.** The game ships inventory icons it never
  uses ([see them](img/lost-cards/unused-icons.png)): faction versions of Decoy, Horn, Scorch and
  Weather (every special card in the game is neutral), soldier icons for Monsters, Northern Realms
  and Skellige, and a Scoia'tael siege icon (Scoia'tael has no siege unit). They fit new cards
  naturally: a Scoia'tael siege unit (Scoia'tael is short of good cards), faction special cards.
  The mod would point to the game's own icons, never copy them, through its scripts (no item
  file of the game overridden).
- **Abilities the game defines but never uses**, as a starting point for new cards (our own
  design, documented as such): Ambush, Backstab, ToughSkin, a second Morale boost, discard two
  or three cards, and draw one card. They exist only as names in the game's code.
- **A card type that plays on the opponent's row.** The game already has the placement rule for
  it, but no card uses it. It suits a new card that weakens the enemy's row, for example an
  "anti-Horn".

### Card balance (planned)

Adjust cards that are rarely worth a slot, so more decks and strategies are viable.

- Small, documented changes (power or ability), each tested in the Lab against the AI and the
  NPC decks.
- Off by default and fully reversible: removing the module restores the original values.

## Core (ongoing)

Everything in the core can be installed in the middle of a playthrough and removed at any time:
it lives in Better Gwent's own copy of the Gwent screens and its own scripts, never in the game's
files or the save.

- **AI**
  - Fixes found in recorded matches and by the blunder hunter: spending too many cards on
    round 1, Horn and weather timing, units into their own weather, Spy value and spies held
    instead of played early.
  - Then self-play parameter tuning and a small value network (see [Research](RESEARCH.md)).
  - **Eredin's "discard two, pick one" leader:** neither the native AI nor Better Gwent's AI uses
    it today; Better Gwent's AI will search it like the other leaders.
  - **Opponent personality** (an On/Off option): the game's quests mark each opponent with a
    difficulty and a play style (Hard, Aggressive, Defensive, "all I have"), but the game never
    uses those marks. With the option on, each opponent plays the way the developers marked it:
    a Hard opponent always at the strongest level, an aggressive one pressing early, a defensive
    one keeping its cards. Each style is measured in the Lab so it stays strong, only different.
- **NPC decks:** the automatic deck tuner (Decoys and weather per player faction, hero variety,
  an even fight on Adaptive), with fair play (only your deck's faction and strength are read).
- **Content the game left unfinished** (no card or rule changes):
  - the Medic and leader revive window shows its sentence again (done);
  - the agile card sound the game never plays;
  - a sound for Skellige's faction ability, which today calls a sound that does not exist (done
    with care, so nothing breaks if the sound is missing);
  - the glossary page on leader cards, ready in the game but never unlocked, and the entry on
    special abilities, very likely hidden by a misspelled name.
- **Card art:** the game's own unused alternate art on every copy (done in matches and in the
  deck builder).
- **Translations** for the menu (18 languages today).
- **Release:** an in-game check of the normal edition, then a public release.

What we found while studying the game is in [Studying the game](game-study/README.md).
