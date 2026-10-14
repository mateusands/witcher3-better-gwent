# Repository scope

This is a **private** repository with the mod sources, the Gwent AI Lab, the tools,
the simulator policy code, the tests and a short documentation set. Mod packages are built
locally into `dist/` and are never committed: they contain the modified Gwent interface.

## What belongs here

- Original work only: mod scripts and the V8 AI, build and test tools, the Lab and
  concise docs (`README.md`, `INSTALL.md`, `FEATURES.md`, `CARD_ART.md`, `RECORDER.md`,
  `NPC_DECKS.md`, `TESTING.md`, `RESEARCH.md`, `DEVELOPMENT.md`, `ROADMAP.md`, this file, and
  `CONTRIBUTING.md` at the root).
- Research notes and the working log stay local.
- One exception, chosen by the owner: previews of the game's own **unused** card art, to show
  what the mod uses or plans to use (`docs/img/bond-card-art.png`, `docs/img/lost-cards/`, including
  `unused-icons.png`, the inventory icons the game never shows).
- `docs/game-study/` describes what I found in the game in my own words: no game code, data,
  file excerpts or game texts are reproduced there.
- Nothing else from the game: no card art the game uses, no other textures, files or data.
- The `.gitignore` is an allowlist: anything not explicitly allowed stays out.

## Before every push

1. Review `git status` and `git diff --cached --stat`.
2. Ignore rules do not remove files that are already tracked, nor history: if something
   that does not belong here was committed, rewrite history before pushing.
3. Write as the project ("I tested in game", "I fix"); no assistant or tool names in docs
   or commit messages.

Making the repository public or publishing a release needs a separate review and an
explicit decision.
