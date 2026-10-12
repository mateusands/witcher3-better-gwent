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
ability or text in the game.

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

### Card balance (planned)

Adjust cards that are rarely worth a slot, so more decks and strategies are viable.

- Small, documented changes (power or ability), each tested in the Lab against the AI and the
  NPC decks.
- Off by default and fully reversible: removing the module restores the original values.

## Core (ongoing)

- **AI:** fixes found in recorded matches. Next: the NPC no longer hurts its own score for
  nothing (a Scorch that burns only its own cards, a leader ability wasted with an empty hand).
- **NPC decks:** more variety without losing strength; Adaptive already draws faction heroes
  per match.
- **Card art:** the game's own unused alternate art on every copy (done in matches and in the
  deck builder).
- **Translations** for the menu (18 languages today).
- **Release:** an in-game check of the normal edition, then a public release.
