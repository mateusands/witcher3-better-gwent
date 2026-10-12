# Research behind Better Gwent

What I studied, what the AI and its tests are built on, what I tried and what I dropped.
Papers are cited as references; the software tools are listed with their licenses.

## How the AI decides

Gwent hides information: the opponent's hand and both decks are unknown. The AI never
reads them (see "Fair play" in the README). It samples plausible hidden hands from public
information and searches its own moves and the opponent's replies against those samples.

- **Information Set Monte Carlo Tree Search**
  - Reference: P. I. Cowling, E. J. Powley, D. Whitehouse, *Information Set Monte Carlo Tree Search*, IEEE Transactions on Computational Intelligence and AI in Games, 2012
  - Where it is used: Experimental ISMCTS kernel and hybrid policy; its lessons shaped V8's hidden-hand handling
- **Sampling hidden information (determinization)**
  - Reference: J. Long, N. R. Sturtevant, M. Buro, T. Furtak, [*Understanding the Success of Perfect Information Monte Carlo Sampling in Game Tree Search*](https://ojs.aaai.org/index.php/AAAI/article/view/7562), AAAI 2010
  - Where it is used: V8 opponent-hand hypotheses; when sampling works well and where it fails
- **Self-play and learned evaluation**
  - Reference: D. Silver et al., *A general reinforcement learning algorithm that masters chess, shogi, and Go through self-play* (AlphaZero), Science, 2018
  - Where it is used: Plan for parameter tuning by self-play and a small value network

## How the AI is tested

- **Same luck for every compared option (duplicate games, common random numbers)**
  - Reference: Duplicate format of the Annual Computer Poker Competition, described in [*OpenHoldem: A Benchmark for Large-Scale Imperfect-Information Game Research*](https://arxiv.org/abs/2012.06168), 2020
  - Where it is used: Benchmarks (same deck pair and seed for native and Better AI) and the blunder hunter (same later luck for every alternative)
- **What counts as a mistake**
  - Reference: S. Ganzfried, [*Mistakes in Games*](https://arxiv.org/abs/1910.00225), 2019
  - Where it is used: Definition behind the blunder hunter: a decision is a mistake only if another move is better on average
- **Sequential Halving**
  - Reference: Z. Karnin, T. Koren, O. Somekh, *Almost Optimal Exploration in Multi-Armed Bandits*, ICML 2013
  - Where it is used: Deep blunder hunt: every legal move gets a small budget, the worse half is dropped, the budget doubles
- **Gumbel planning**
  - Reference: I. Danihelka, A. Guez, J. Schrittwieser, D. Silver, *Policy improvement by planning with Gumbel*, ICLR 2022
  - Where it is used: Where Sequential Halving became the root selection of modern AlphaZero-style search
- **Testing card-game AIs**
  - Reference: A. Dockhorn, S. Mostaghim, [*Introducing the Hearthstone-AI Competition*](https://arxiv.org/abs/1906.04238), 2019
  - Where it is used: How card-game agents are evaluated across decks and opponents
- **Diverse deck generation**
  - Reference: Y. Zhang, M. C. Fontaine, A. K. Hoover, S. Nikolaidis, [*Deep Surrogate Assisted MAP-Elites for Automated Hearthstone Deckbuilding*](https://arxiv.org/abs/2112.03534), GECCO 2022
  - Where it is used: Inspiration for player-style decks (power, synergy, random, early-game)

## Studied, not used (yet)

- **Variance reduction for evaluating agents**
  - Reference: N. Burch, M. Schmid, M. Moravčík, D. Morrill, M. Bowling, [*AIVAT: A New Variance Reduction Technique for Agent Evaluation in Imperfect Information Games*](https://ojs.aaai.org/index.php/AAAI/article/view/11481), AAAI 2018
  - Why not yet: Needs a calibrated value estimate; a candidate once the value network exists
- **Counterfactual regret minimization**
  - Reference: M. Zinkevich, M. Johanson, M. Bowling, C. Piccione, *Regret Minimization in Games with Incomplete Information*, NeurIPS 2007
  - Why not yet: Solves the whole game offline; far too heavy for the game's Flash runtime
- **Deep counterfactual value search**
  - Reference: M. Moravčík et al., *DeepStack: Expert-level artificial intelligence in heads-up no-limit poker*, Science, 2017
  - Why not yet: Same: too heavy for real-time decisions inside the game

## Planned

- **Tuning many parameters at once with noisy measurements**
  - Reference: J. C. Spall, *Multivariate stochastic approximation using a simultaneous perturbation gradient approximation* (SPSA), IEEE Transactions on Automatic Control, 1992
  - Plan: Phase 3: tune V8's weights by self-play, accepted only if stronger on NPC and player-style decks at every level
- **Small value network**
  - Reference: AlphaZero (above)
  - Plan: Phase 4: estimate win probability from the board, only if it runs fast enough in Flash and wins in benchmarks

## What I tried

- **V1–V2**
  - What changed: Corrected Horn estimates (whole row, siege baselines), round-two spending against round-three resources, pass planning
  - Outcome: Kept
- **V3**
  - What changed: Exact gains for supported units, combination-aware pass safeguards
  - Outcome: Kept
- **V4**
  - What changed: Immediate gain separated from next-round reserve value; Muster as a group resource
  - Outcome: Kept
- **V5**
  - What changed: Immutable public-position model; search over own move sequences, passing compared with match resources
  - Outcome: Kept; base of everything after
- **V6**
  - What changed: Opponent replies from public-catalog hypotheses; Medic recovery chains
  - Outcome: Kept
- **V7**
  - What changed: Leaders as searchable "use now or keep" actions
  - Outcome: Kept; clear gain over V6
- **ISMCTS hybrid**
  - What changed: Full information-set tree search with exhaustive passed-round solver
  - Outcome: Measured, not faster or stronger than V7 alone; useful parts reused
- **Learned evaluator**
  - What changed: Small logistic model over board features (experimental)
  - Outcome: Not shipped; superseded by the planned value network
- **Guards**
  - What changed: No overplay or pointless pass against a passed opponent, concede unwinnable chases, Decoy and Medic priorities, Spy reserve value, Mushroom transformations, hero preservation
  - Outcome: Kept where measured neutral or better
- **V8**
  - What changed: All of the above ported to ActionScript and running inside the game, with time limits and native fallback
  - Outcome: Current version
- **NPC opening exchange**
  - What changed: The NPC exchanges up to two opening cards, chosen from its own hand and remaining deck composition
  - Outcome: Kept from Medium up: +5.4 points of NPC win share on Expert with Adaptive decks, with the player exchanging too (z 3.9)
- **Weather that changes nothing, three Decoys against spy factions**
  - What changed: Count a weather card that changes no score as wasted; NPC decks carry three Decoys against Nilfgaard and Northern Kingdoms player decks (spies)
  - Outcome: Dropped: no measurable effect (z below 1)
- **Tests, 11 and 12 October 2026**
  - What changed: The leader's weather card goes back first in the opening exchange; Skellige cards (Mardroeme, Berserkers, Clan Dimun Pirate, Kambi) in the search; up to four spies in the NPC decks; three levels (512 / 768 / 2,048 nodes: 52.9 / 57.6 / 59.5%, more nodes added nothing)
  - Outcome: Kept, each proven in the Lab. Dropped: passing a safe lead after a lost round and never playing a weather card that changes nothing (both proven worse), remembering cards back in the player's hand (no effect)
- **Tests, 12 October 2026: NPC deck shape and heroes**
  - What changed: Lean NPC decks (Strong: 22 units and at most 4 special cards, no Triss; Adaptive: at most 2 special cards); Adaptive heroes that fit the faction, varied per match; the NPC picturing Scorch in the player's hand
  - Outcome: Lean decks kept (Strong +15.0 Hard, +15.9 Normal; Adaptive +4.4 Hard, +8.2 Normal; confirmed with new luck). Adaptive heroes kept (no measurable change); the same rule for Strong dropped (about -5). Picturing Scorch dropped (no measurable effect)
- **In-game fixes**
  - What changed: Stalls, wasted Frost/Horn, round-1 overcommit, Medic choosing a Spy when out of cards, NPC extra-card requirements
  - Outcome: Kept
- **No self-harm (in-game match g151)**
  - What changed: A Scorch that would destroy only the NPC's own units is never played; a wasted Frost/Horn with nothing better becomes a pass even after a lost round, when the hand would be empty afterwards or the search values passing higher
  - Outcome: Kept as a fix. In a 60-game V8 sample (Hard, Adaptive decks) the Scorch rule changed 12 of 1,582 decisions and the pass rule 6; not yet measured in the Lab

Every change is measured on the same decks and luck as the version before it, and kept
only when it does not make the AI weaker. Details and numbers: [TESTING.md](TESTING.md).

## Software

- **[PyPy](https://pypy.org)**
  - License: MIT
  - Use: Runs the simulations about 2x faster with identical results
- **[psutil](https://github.com/giampaolo/psutil)**
  - License: BSD-3-Clause
  - Use: CPU, memory and disk readings in the Lab panel
- **[uv](https://github.com/astral-sh/uv)**
  - License: MIT / Apache-2.0
  - Use: Installs PyPy
- **[JPEXS Free Flash Decompiler](https://github.com/jindrapetrik/jpexs-decompiler)**
  - License: GPL-3.0
  - Use: Local build tool for the Gwent interface; not distributed with the mod
- **[Node.js](https://nodejs.org)**
  - License: MIT
  - Use: Runs the ActionScript AI in the tests to compare it with the Python reference
