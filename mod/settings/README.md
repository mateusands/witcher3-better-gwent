# Better Gwent AI settings sources

Draft sources for **Options > Mods > Better Gwent AI**:

- `menu/modGwentAI.xml`: main switch, difficulty selector, optional player AI,
  common wager maximum and optional stakes-dependent native NPC strength.
- `menu/labels.en.json`: original English menu text.
- `modGwentAISettings/content/scripts/local/gwai_settings.ws`: defaults, persistence,
  sub-option locking and initial per-match settings capture.
- `modGwentAISettings/content/scripts/local/gwai_betting.ws`: original standard
  pure-gold Gwent wager wrappers and captured native-deck strength adjustment.

Difficulty values: 0 = Easy, 1 = Medium, **2 = Hard (default)**, 3 = Expert.
Missing or invalid main/autoplay switches fall back to Off. Turning the main switch
Off disables both sub-options while preserving their saved selections. Player AI is
effective only when the main switch and the player-AI switch are both On.
The native difficulty preference is preserved.

With Better AI On, draft `GenerateDifficultyData` rebuilds every effective deck
threshold from the mod selection, ignoring the saved native difficulty. The
one-based `GetDifficulty` bounds are corrected for all 15 levels. Easy/Medium/Hard
map to the existing native deck variants 1/2/3; Expert also uses variant 3, with a
separate V8 search budget required at controller dispatch. The independent
stronger-stakes option can explicitly raise deck strength. With Better AI Off,
native behavior is preserved. These arithmetic/settings contracts have local
tests; controller replacement and engine validation remain pending.

The scripts wrap existing menu hooks. They are original mod additions; no original
menu resources are distributed. Compiled labels and generated game artifacts are
excluded from this source repository.

**Not a playable release.** WitcherScript compilation, menu registration, UI behavior,
production AI dispatch, interactive dialogs and internal rematch handling still require
integration and in-game testing. Installing the draft menu alone does not improve AI.
Back up affected game files and settings before a future integration test.


Betting options remain enabled independently of the AI switch. Defaults: maximum
Vanilla (10), stronger opponents Off. Special 50/100 wagers remain vanilla. See
[design](../../docs/DESIGN.md) for eligibility, curve, native behavior and test steps.
Eleven wrapper declarations pass static signature checks against vanilla 5.01;
actual engine compilation has not been confirmed.
