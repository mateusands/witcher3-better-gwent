# One artwork per card copy

While Better Gwent is On, the copies of one card show different pictures. The artwork is the
game's own: the pictures of the family's other cards, plus alternate card art that ships with
The Witcher 3 but that the vanilla card list never uses.
[See every copy side by side](img/bond-card-art.png).

## How the pictures are chosen

- **Families.** Cards are grouped by family: every non-hero unit that shares a name (Poor
  Fucking Infantry, Kaedweni Siege Expert, Impera Brigade, Blue Stripes Commando, Siege Tower,
  the Scoia'tael, Monster and Skellige groups...). So it works even when the game gives you the
  same card number twice: Poor Fucking Infantry x2 shows two pictures, Kaedweni Siege Expert x3
  three.
- **Order.** Copies are numbered by card number, then copy, and take the family's pictures in
  that order. A picture repeats only when the family runs out (a fourth Blue Stripes Commando
  repeats the first).

## Where it shows

- **Matches:** every copy on the board and in the hand.
- **Deck builder** (pause menu > Gwent decks): the same pictures, with one tile per copy of these
  cards instead of one "x3" tile. Adding or removing any of them moves one copy, as before. The
  right-click zoom shows each copy with the picture of its tile.

## Visual only

- Power, abilities and the card list are unchanged; no card definition file is overridden.
- The pictures are drawn by the mod at display time. Saves store only card numbers, so with the
  mod Off or removed the stock pictures and the stock deck builder (one "x3" tile per card)
  return.

Views that still keep the stock picture, and a deck builder detail, are listed in
[Known limitations](KNOWN_LIMITATIONS.md#card-art). The unused art of the game, including the
pictures this feature uses, is described in [Lost Cards](game-study/lost-cards.md).
