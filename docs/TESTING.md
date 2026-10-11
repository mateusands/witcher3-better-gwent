# How Better Gwent AI is tested

The AI is measured in a local simulator that reproduces the game's Gwent rules, then
checked in real matches inside the game.

## 1. Fidelity: does the simulator play like the game?

- In-game matches are recorded with every random draw and decision. The fidelity corpus
  of native AI-vs-AI recordings is replayed move by move and must match exactly:
  **21 of 22** do; the remaining one (a Scorch ordering case) is a known open issue and
  is never hidden by the tests.
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

| Level | Better AI | Native AI | Games |
| --- | --- | --- | --- |
| Easy | 242.5 | 220 | 440 |
| Medium | 252.5 | 220 | 440 |
| Hard | 253 / 274.5 | 220 | 440 per seed, 2 seeds |
| Expert | 264 / 268 | 220 | 440 per seed, 2 seeds |

## 3. Mistakes: blunder hunting

For matches the AI lost or drew, every decision is replayed with alternative moves. Each
option is compared on the **same** later luck (like duplicate poker), so luck is not
mistaken for a mistake; a decision is reported only when another move is clearly better
on average.

A deeper hunt also covers won matches, every legal move (narrowed with Sequential
Halving, as in Gumbel MuZero) and smaller mistakes. Findings become regression cases.

## 4. In-game validation

I test every build in real matches with the mod installed; each match is recorded and
analysed (decision source, timing, errors). Problems I found in game and fixed so far:
stalled matches, wager menu values, wasted Frost/Horn, round-1 overcommit, weaker NPC
decks, Medic choosing a siege unit over a Spy.

## Running totals

Updated as tests run (`python3 lab/report.py <lab databases> --evaluations <reports>`).

| | As of 2026-10-11 |
| --- | --- |
| Simulated matches in the Gwent AI Lab | 9,131 |
| CPU time in the Lab | ~10 hours |
| Simulated matches in earlier evaluations (V1–V8 development) | ~61,600 |
| Recorded in-game matches | 57 |
| Costly decisions found by the blunder hunter | 43 |

## Infrastructure

- **Gwent AI Lab** (`lab/`): crash-safe job runner; a power cut only repeats the tasks
  that were running, and a self-test kills workers repeatedly and requires identical results.
- Workers run under **PyPy** (1.7–2.1x faster than CPython, identical results), on
  my PC, a home server or a rented cloud server (16 ARM cores; ARM results are
  identical to x86).
- Every result is deterministic: the same task always gives the same result.
