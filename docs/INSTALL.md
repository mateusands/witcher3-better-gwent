# Better Gwent AI 0.9.0 beta — installation

A stronger Gwent opponent for The Witcher 3, game patch 5.01 (tested on Steam; GOG untested).
The mod changes how the NPCs play Gwent; it adds no cards and changes no card. With the mod switched Off the game
plays Gwent exactly as before.

## Install

1. Close the game.
2. Extract the archive into the game folder (the one with `bin` and `content`). It adds:
   - `Mods/modBetterGwentAI`
   - `bin/config/r4game/user_config_matrix/pc/modGwentAI.xml`
3. If `bin/config/r4game/user_config_matrix/pc/dx11filelist.txt` and `dx12filelist.txt` exist,
   add the line `modGwentAI.xml;` to both (once). A mod manager may do this for you.
4. Start the game; the scripts compile on the first launch.
5. Open **Options > Mods > Better Gwent AI** and switch it On.

## Options

- **Better Gwent AI**: On/Off. Off = the original game, wagers included.
- **Difficulty**: Easy, Normal or Hard (default), independent of the game difficulty.
- **NPC decks**: Original (default), Adaptive or Strong. Which existing cards an NPC brings,
  rebuilt in memory for each match; nothing is written to your save.
- **AI plays for you**: the AI also plays your side (you still pick your deck and your opening
  exchange).
- **Gwent max bet**: Vanilla (10), 25, 50, 100 or 150, for ordinary money wagers only.
- **Higher stakes, stronger opponent**: with a big wager, the NPC uses a stronger existing deck.

On Normal and Hard, the NPC exchanges up to two opening cards, as you can. Settings are read when
a Gwent match opens; to change them, finish the match and start a new one.

## Fair play

The AI does not see your hand, your deck or the order of anyone's deck. It plays from what a
human player could see: the board, both graveyards, the number of cards in your hand, the cards
already played, and its own hand and deck.

## Compatibility

- Only one mod can replace the Gwent board (`gwint_game.redswf`). Other mods that replace it
  conflict with this one.
- Script mods that change the Gwent manager, the Gwent menu or the wager dialog may need a
  script merge.
- Map mods such as Gwent Players Map and Witcher Upgrade Gear Map are fine.

## Uninstall

Close the game and delete `Mods/modBetterGwentAI`, `modGwentAI.xml` and its lines in the
filelists. Saves stay valid: the mod adds no items, quests or cards. Money won in wagers stays
yours.
The per-copy card art (Tight Bond cards, Blue Stripes Commando, Siege Tower) is drawn by the mod at display time; saves store only card
numbers, so removing the mod brings back the stock pictures.

## Known issues

- Beta: please report errors with the game version, the mod options and what happened.
- Olaf in your own deck can, rarely, make the original game's Gwent board throw an error
  when his effect lands after he left the board. This is in the original game; NPC decks
  built by the mod never use Olaf.

Source and development: https://github.com/mateusands/witcher3-better-gwent-ai
