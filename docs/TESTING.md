# How Better Gwent is tested

The AI is measured in a local simulator that reproduces the game's Gwent rules, then
checked in real matches inside the game.

## 1. Fidelity: does the simulator play like the game?

- In-game matches are recorded with every random draw and decision. The fidelity corpus
  (matches against the native AI) is replayed move by move and must match exactly:
  **22 of 23** do; the remaining one (a Scorch ordering case) is a known open issue and
  is never hidden by the tests. Matches played by Better AI are analysed separately
  (decision notes, timing, errors); the native replay cannot reproduce its decisions.
- NPC decks built by the simulator match the game's decks in every available recording.

## 2. Strength: benchmark against the native AI

Each matchup is played three times with the same deck pair and the same luck (seed):
native AI vs native AI, then Better AI in each seat. The score compares the Better AI
seat against the native AI in the same seat (win = 1, draw = 0.5).

- **Deck pool:** 110 matchups covering every faction and every leader, built from the
  game's own NPC decks; both seats, 440 games per level per seed.
- **Player-style decks:** 490 matchups of NPC decks against decks a player builds
  (power, synergy, random and early-game styles for every faction and leader, plus
  my 10 real decks). The player side is played by Better AI itself as a strong
  stand-in for a human; the NPC side is played by the native AI or by Better AI.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="img/levels-dark.svg">
  <img src="img/levels-light.svg" alt="Better AI score share against the native AI: Easy 52.9%, Normal 57.6%, Hard 59.5% (native AI = 50%)" width="880">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="img/player-decks-dark.svg">
  <img src="img/player-decks-light.svg" alt="NPC win share against player-style decks, Better AI vs native AI, by deck style" width="880">
</picture>

### NPC deck modes

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="img/deck-modes-dark.svg">
  <img src="img/deck-modes-light.svg" alt="NPC win share by deck mode against player-style decks" width="880">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="img/deck-modes-mine-dark.svg">
  <img src="img/deck-modes-mine-light.svg" alt="NPC win share by deck mode against my own real decks" width="880">
</picture>

## 3. Mistakes: blunder hunting

For matches the AI lost or drew, every decision is replayed with alternative moves. Each
option is compared on the **same** later luck (like duplicate poker), so luck is not
mistaken for a mistake; a decision is reported only when another move is clearly better
on average.

A deeper hunt also covers won matches, every legal move (narrowed with Sequential
Halving, as in Gumbel MuZero) and smaller mistakes. Findings become regression cases.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="img/mistakes-dark.svg">
  <img src="img/mistakes-light.svg" alt="Costly decisions found by round" width="880">
</picture>

### A/B tests

Every change to the AI is compared with the current AI on the same matchups and luck, and kept
only when the gain is proven (z of 2 or more) and nothing gets worse.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="img/ab-dark.svg">
  <img src="img/ab-light.svg" alt="A/B tests from the NPC deck battery: the evaluated NPC mulligan is proven on Adaptive and Strong decks, also when the player exchanges too; weather that changes nothing and 3 Decoys are not proven" width="880">
</picture>

### Tests, 13 October 2026

The four careful-play rules (agile units out of the frost, no weather that gains nothing, the
Medic waits for a target, the cheapest winning play) do not weaken the NPC; the SPSA weights
were not kept; the spy engine experiments came from the Novigrad tournament (in-game matches
g158-g161) and the owner's own Northern Realms spy deck. Spies are worth a lot: limiting the
NPC's spies to the player's makes the NPC clearly weaker everywhere, so that mirror was dropped.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="img/ab-spy-dark.svg">
  <img src="img/ab-spy-light.svg" alt="A/B tests of 13 October 2026: the careful-play rules are neutral; tuned weights not kept; spy mirror variants and one witcher in the fallback make the NPC weaker; spy counting, spy-first and draw weights not proven yet" width="880">
</picture>

### Sequential tests (since 13 October 2026)

A/B tests stop as soon as their answer is clear, as chess engines test their patches (SPRT, the
method of Stockfish's Fishtest), instead of always playing a fixed number of matches. Each paired
matchup gives the difference between the candidate and the current AI on the same deal and luck;
a sequential probability ratio test decides "better" or "not better" with 5% error each way, and
gives up as "undecided" at a match budget. With the Lab's real spread of results, a clearly worse
change is decided in about 120 matchups, a clear gain in about 180 and a neutral change in about
1,000, against 2,100 for a fixed test (`lab/sprt.py`, job kind `ab`).

Test, 13 October 2026: on the first 21 decided tests the Lab played 32,183 matchups where fixed
tests would have played 44,100 (1.4x fewer). Most ideas were only slightly worse (1 to 3 points),
close to the smallest gain the test looks for, so they needed 1,000 to 2,200 matchups; clearly
worse ones stopped near 600. Two tests needed more than 2,100 (3,399 and 4,997) and would have
been "unclear" with a fixed size. Since then batches are 100 matchups (was 200), the next batch
is queued while the last one still runs, and the test is checked at every step of the Lab.

Test, 13 October 2026, rented servers (rounds 11 to 17, about 70 sequential tests): two ideas
passed three times on new matchups, both on the Original mode only: playing a spy before other
cards while later rounds remain ("spy-first"), and keeping 20% of what the search's second ply
adds to a move ("fusion20"). Everything else was worse or neutral: changes of the utility weights
(draw value, reserve), giving up round 1 early, more or fewer imagined hands, a wider or narrower
second ply, a margin for passing, caution towards the worst hand, other fusion shares, and a
ceiling on round-1 spending on Adaptive. Two early passes (fusion25 on Strong, fusion15 on
Original) failed their confirmations: about 1 in 20 passes is luck, which is why every pass is
confirmed.

### Autopilot (since 13 October 2026)

The cloud server improves the NPC on its own (`lab/autopilot.py`, a service on the server): it
keeps a few idea jobs running from a list of idea families, gives every passed test two
confirmation tests on new matchups (about 1 in 20 passes is luck, and many tests run), and writes
a report of promoted, rejected and waiting ideas. Only promoted ideas are turned into changes of
the mod, and nothing needs testing move by move in the game.

### Automatic deck tuner

A small self-improving search for NPC decks, running around the clock on a cloud server (`lab/core.py`,
job kind `deck-tune`). The deck builder has knobs (a genome): Decoys (0 to 2) and a weather card
per player faction, how the Adaptive hero fallback adds Geralt and Ciri, how spies count, and
an Adaptive target per NPC faction. Each round races several changes at once (racing, as in
irace and Hyperband): every candidate plays against the current genome on the same matchups,
luck and opening exchanges, in small batches, with its own sequential test. A candidate that is
not better is dropped early; the best one proven better is kept. Then the next race starts.

Fair play: the genome reacts only to what an NPC may know before a match, the player's deck
faction and deck strength (the game's own NPC decks already follow the strength). It never uses
the player's leader or cards.

## 4. In-game validation

I test every build in real matches with the mod installed; each match is recorded and
analysed (decision source, timing, errors). Problems I found in game and fixed so far:
stalled matches, wager menu values, wasted Frost/Horn, round-1 overcommit, weaker NPC
decks, Medic choosing a siege unit over a Spy, muster groups split by the Adaptive decks, and
the NPC never exchanging opening cards (now it does, on Normal and Hard), repeated heroes in
the NPC decks, and a 3 s thinking limit that cut Hard's opening searches.

## Running totals

Updated as tests run (`python3 lab/report.py <lab databases> --evaluations <reports>`); the README
charts come from `python3 lab/dashboard.py <lab databases>`.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="img/kpis-dark.svg">
  <img src="img/kpis-light.svg" alt="1,253,132 simulated matches, 1,286 hours of Lab CPU time, 123 recorded matches, 357 mistakes found, 25% more NPC wins than the native AI over all 9 deck mode and level settings" width="880">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="img/totals-dark.svg">
  <img src="img/totals-light.svg" alt="Lab matches, earlier evaluation matches, Lab CPU time, in-game matches and mistakes found" width="880">
</picture>

## Infrastructure

- **Gwent AI Lab** (`lab/`): crash-safe job runner; a power cut only repeats the tasks
  that were running, and a self-test kills workers repeatedly and requires identical results.
- Workers run under **PyPy** (1.7–2.1x faster than CPython, identical results), on
  my PC, a home server or rented cloud servers (16 ARM cores, and 32 x86 cores for the NPC
  deck battery; ARM results are identical to x86).
- Every result is deterministic: the same task always gives the same result.
- Since 13 October 2026 a cloud server runs the Lab around the clock (12 cores): continuous
  A/B tests, the deep blunder hunt on my own recorded decks, SPSA tuning and the deck tuner.
  Short batteries go to rented 32-core servers, split across several when a run is long.
- Lab audit, 13 October 2026: picking the next task scanned every task of every job (150 ms
  inside a write lock on a 73,000-task database, so 32 workers queued for the lock); an index
  on the tasks' job and status makes it 0.2 ms.
- The Lab's own code is tested like the AI: the weights path, the hunter's pass option, the
  scene of hunts and tuning, the task split across servers, the queue release and the
  database pull each have a test that failed before its fix.
