# Repository scope

This is a **private** repository with the mod sources, the Gwent AI Lab, the tools,
the simulator policy code, the tests and a short documentation set. There is no release.

## What belongs here

- Original work only: mod scripts and the V8 AI, build and test tools, the Lab and
  concise docs (`README.md`, `TESTING.md`, `RESEARCH.md`, `DEVELOPMENT.md`, this file).
- Research notes and the working log stay local.
- The `.gitignore` is an allowlist: anything not explicitly allowed stays out.

## Before every push

1. Review `git status` and `git diff --cached --stat`.
2. Ignore rules do not remove files that are already tracked, nor history: if something
   that does not belong here was committed, rewrite history before pushing.
3. Write as the project ("I tested in game", "we fix"); no assistant or tool names in docs
   or commit messages.

Making the repository public or publishing a release needs a separate review and an
explicit decision.
