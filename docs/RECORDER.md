# Recorder edition (for testers)

The recorder edition is not a release. It is the same mod plus a **match recorder**, shared only with
people who want to help with development: recorded matches show where the AI still makes
mistakes. It is not part of the public downloads; ask for it if you want to help. Everyone else
should use the normal download.

## What the recorder does

- It records every Gwent match you play (with the mod On or Off): the deal, every card played
  by both sides, the opening exchanges and the AI's diagnostic notes.
- The records are text entries in the section `[GwaiRec]` of your game settings file,
  `Documents/The Witcher 3/dx12user.settings` (or `user.settings` with DirectX 11). They are not
  in your saves. A note on screen confirms each saved match.
- Each match adds about 20-25 KB to that settings file.
- Nothing is sent anywhere. You choose what to share.

## Install

The same steps as the normal download (see the main installation notes): extract into the game
folder, register `modGwentAI.xml;` in the filelists if they exist, start the game. It uses the
same `Mods/modBetterGwent` folder as the normal edition. Delete that folder before switching
from one edition to the other, so no file of the other edition stays behind.

## Sharing records

Close the game and send your `dx12user.settings` (or `user.settings`) file, or only its
`[GwaiRec]` section, through the GitHub issues of the project. Mention the mod options you used.
Developers read it with `tools/rec_read.py <settings file>`, which checks each record and writes
one JSON per match.

## Removing the records

Close the game and delete the `[GwaiRec]` section from the settings file (or keep it; the game
ignores it). Uninstall the mod as described in the main installation notes.

Source: https://github.com/mateusands/witcher3-better-gwent
