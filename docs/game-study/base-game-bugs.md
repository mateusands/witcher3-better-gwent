# Bugs of the base game

What we found while reading the base game, and what Better Gwent does about each.

## Fixed by Better Gwent

- **NPCs always got their extra cards.** NPC decks were meant to gain extra cards only when your
  deck is strong enough, with thresholds that depend on the difficulty. A reversed check made
  almost every threshold zero, so nearly every NPC received all its extra cards in every match,
  whatever your deck. Recorded matches confirmed it. With Better Gwent on, the intended rule
  applies at every level, also with the Original NPC decks: an extra card joins the NPC's deck only
  when your deck is strong enough. (Adaptive and Strong build the NPC's deck themselves, see
  [NPC decks](../NPC_DECKS.md).) With Better Gwent off, the game behaves as before. The numbers
  and a chart of the repaired rule are in
  [NPC decks: the extra-card rule, repaired](../NPC_DECKS.md#original-the-extra-card-rule-repaired).
- **The revive window had no title.** When you play a Medic, or a leader that revives a card, the
  game opens a window to pick the card. That window should say to choose a card to revive, but it
  asks for its sentence with a misspelled name, so the sentence is never found and the window
  opens without it, in every language. The sentence itself is in the game, correctly spelled.
  Better Gwent's copy of the Gwent screen asks for the right one, and the window now shows its
  sentence (checked in game on 13 October 2026). Visual only: the choice and the match are
  unchanged.

## Replaced by Better Gwent's AI

The native AI is replaced for the NPC by Better Gwent's AI while the mod is on. Reading it showed:

- **Much of it is chance.** Whether it passes, waits or plays hard, and whether it plays a spy, is
  often decided by a dice roll rather than by a calculation (a spy is played with a one-in-five
  chance in one of its moods).
- **Two of its moods share one number,** so the "lose this round cheaply" mood never runs its own
  plan and runs another mood's plan instead.
- **A path into that mood can never be taken:** its chance is computed so that it is always zero
  or below.
- **Some counts are used before they are filled in,** so one check about a hand made only of
  Decoys and spies goes wrong.
- **One leader was never taught to the AI:** Eredin's "discard two, pick one", as the game's own
  code admits. Better Gwent's AI does not use it either yet: on that leader it still leaves the
  decision to the native AI. Planned.

## Not changed (outside the mod's scope)

- **Merchants' random Gwent card:** a counting mistake means the last card of the list (the
  Wyvern) is never picked while any other card is still available.
- **"Can I play this faction?" check:** a quest check meant to count 22 unit cards of a faction
  stops at the first card it finds, so it counts at most three.
- **The Northern Realms deck of the Toussaint tournament** (Blood and Wine) exists, but no quest
  uses it: the other four factions have their tournament decks in play, the Northern Realms does
  not.
- **Tutorials and glossary:** one glossary entry (on special abilities) is very likely never shown,
  because the game asks for it under a misspelled name; the last step of the deck builder
  tutorial can never be reached. (Read from the files, not yet seen in game.)
- **Skellige's faction ability has no sound:** the game plays a sound for it that does not exist,
  while the other four factions have theirs. (Read from the files, not yet heard in game.)
- **The collection achievement** once counted the three versions of a leader wrongly; the
  developers fixed this themselves.
