# Research behind Better Gwent

What I studied, what the AI and its tests are built on, and what I tried and dropped.
Papers are cited as references; the software tools are listed with their licenses.

## How the AI decides

Gwent hides information: the opponent's hand and both decks are unknown. The AI never
reads them (see [Fair play](FEATURES.md#fair-play-the-ai-does-not-see-your-cards)). It samples plausible hidden hands from public
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

- **Sequential testing of changes (SPRT)**
  - Reference: A. Wald, *Sequential Tests of Statistical Hypotheses*, Annals of Mathematical Statistics, 1945; its use for engine patches in Stockfish's [Fishtest](https://github.com/official-stockfish/fishtest/wiki/Fishtest-faq) and the [Chess Programming Wiki](https://chessprogramming.org/SPRT)
  - Where it is used: Lab A/B tests and every candidate of the deck tuner stop as soon as their answer is clear (since 13 October 2026)
- **Racing configurations**
  - Reference: M. López-Ibáñez et al., [*The irace package*](https://mirror.linux.duke.edu/pub/cran/web/packages/irace/vignettes/irace-package.pdf); L. Li et al., [*Hyperband*](https://arxiv.org/pdf/1603.06560), JMLR 2018
  - Where it is used: The deck tuner races several candidates per round and drops the weak ones early
- **Tuning weights from positions (Texel's method)**
  - Reference: P. Österlund, [*Texel's Tuning Method*](https://www.chessprogramming.org/Texel%27s_Tuning_Method)
  - Where it is used: The V8 utility weights fitted to the results of many recorded positions, without playing matches during the fit; every fitted set is confirmed by a paired A/B test
  - How it runs: `lab/remote/texel_run.sh` on the Lab server collects, fits and queues the A/B tests; it uses the Lab's PyPy at the workers' priority, so it shares the CPU evenly with the Lab (Test, 13 October 2026: the first run used CPython at a higher priority than the workers and slowed the Lab by about a third)

## Studied, not used (yet)

- **Variance reduction for evaluating agents**
  - Reference: N. Burch, M. Schmid, M. Moravčík, D. Morrill, M. Bowling, [*AIVAT: A New Variance Reduction Technique for Agent Evaluation in Imperfect Information Games*](https://ojs.aaai.org/index.php/AAAI/article/view/11481), AAAI 2018
  - Why not yet: Needs a calibrated value estimate; a candidate once the value network exists. My paired matchups (the same deal and luck for both versions) already apply the simpler "Baseline" control variate of the same group (J. Davidson, C. Archibald, M. Bowling, [AAMAS 2013](https://webdocs.cs.ualberta.ca/~bowling/publications/b2hd-13aamas-baseline.html))
- **Optimisers for very noisy measurements**
  - Reference: R. Coulom, [*CLOP: Confident Local Optimization for Noisy Black-Box Parameter Tuning*](https://www.remi-coulom.fr/CLOP/CLOP.pdf); L. Kocsis, C. Szepesvári, [*Universal parameter optimisation in games based on SPSA*](https://www.datalearner.com/academic/journal-papers/0885-6125/volumes-and-issues/63/paper-detail/11141), Machine Learning 2006
  - Why not yet: Texel's method replaces game-playing optimisation for the weights; CLOP stays an option if a parameter can only be measured by playing
- **Self-play learning with search for hidden-information games**
  - Reference: N. Brown et al., [*ReBeL*](https://arxiv.org/pdf/2007.13544), NeurIPS 2020; M. Schmid et al., [*Student of Games*](https://arxiv.org/pdf/2112.03178), Science Advances 2023
  - Why not yet: Far beyond what the game's Flash runtime can run; the planned small value network is the realistic step
- **Counterfactual regret minimization**
  - Reference: M. Zinkevich, M. Johanson, M. Bowling, C. Piccione, *Regret Minimization in Games with Incomplete Information*, NeurIPS 2007
  - Why not yet: Solves the whole game offline; far too heavy for the game's Flash runtime
- **Deep counterfactual value search**
  - Reference: M. Moravčík et al., *DeepStack: Expert-level artificial intelligence in heads-up no-limit poker*, Science, 2017
  - Why not yet: Same: too heavy for real-time decisions inside the game

## Planned

- **Tuning many parameters at once with noisy measurements**
  - Reference: J. C. Spall, *Multivariate stochastic approximation using a simultaneous perturbation gradient approximation* (SPSA), IEEE Transactions on Automatic Control, 1992
  - Plan: Phase 3: tune V8's weights by self-play, accepted only if stronger on NPC and player-style decks at every level. First run (13 October 2026) not kept: it tuned in a scene without opening exchanges and on the original decks; a second run in the game's scene is under way
- **Automatic NPC deck tuning**
  - Reference: Y. Zhang, M. C. Fontaine, A. K. Hoover, S. Nikolaidis, [*Deep Surrogate Assisted MAP-Elites for Automated Hearthstone Deckbuilding*](https://arxiv.org/abs/2112.03534), GECCO 2022
  - Plan: under way since 13 October 2026: a deck genome (Decoys and a weather card per player faction, the hero fallback, spy counting, an Adaptive target per NPC faction) improved by paired A/B hill climbing on a cloud server; only the player's deck faction and strength are read (fair play)
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
  - Outcome: Lean decks kept (Strong +15.0 Hard, +15.9 Normal; Adaptive +4.4 Hard, +8.2 Normal; confirmed with new luck). Adaptive heroes kept with a fallback that allows every hero when the faction's heroes cannot reach the target (without it: -10.4 Normal, -12.3 Hard); the same rule for Strong dropped (about -5). Picturing Scorch dropped (no measurable effect)
- **In-game fixes**
  - What changed: Stalls, wasted Frost/Horn, round-1 overcommit, Medic choosing a Spy when out of cards, NPC extra-card requirements
  - Outcome: Kept
- **No self-harm (in-game match g151)**
  - What changed: A Scorch that would destroy only the NPC's own units is never played; a wasted Frost/Horn with nothing better becomes a pass even after a lost round, when the hand would be empty afterwards or the search values passing higher
  - Outcome: Kept. Test, 12 October 2026: the old rule was worse in every cell (Adaptive -1.1 Normal, z -3.0; Original -1.6 Normal, z -3.8; Adaptive -1.0 Hard; Strong -0.4 Normal, -0.6 Hard)
- **Test, 12 October 2026: candidates from in-game matches g152-g157**
  - What changed: Lab switches, NPC only and off by default. agile-dry: an agile unit goes to its dry row instead of a frozen one (unless the frozen row is strictly better now, e.g. a Horn). weather-guard: no weather card or leader weather that gains nothing now while the opponent still plays (the first-move Frost of g154), and no unit into its own weather when a dry unit is valued as high. medic-hold: a Medic waits while the graveyard holds nothing to revive (Yennefer in g155). r1-chase: in round 1, with fewer cards than the opponent, pass when a greedy race over the public hypotheses of the opponent's hand says the round is lost or won only two cards down (g152, g156). overkill-trim: when the round is ours, the cheapest play the search values above passing (g153). ability-value (NPC decks): Horn units, muster groups (every copy; one draw brings the group), row-Scorch and Morph units valued by their abilities, not printed power
  - Outcome: agile-dry + weather-guard + medic-hold together: no change in strength (Adaptive -0.05 Normal, -0.19 Hard; Strong +0.10 Normal; |z| below 0.4), they ship (default NPC rules in the simulator and the game; the Lab switch careless turns them off for comparisons) because they remove moves that look careless. overkill-trim: positive in all four measured cells (Adaptive +0.43 Normal, +0.67 Hard; Strong +0.86 Normal, +0.19 Hard; combined z about 2.0), it ships as a default NPC rule in the simulator and the game (it wins the round with the smallest commitment the search values above passing; careless turns it off too). r1-chase: dropped (Adaptive Hard -0.52, z -2.0). ability-value: not kept as is (Adaptive -2.48, z -2.0; Strong +1.57, z 1.3); by faction, Strong looked better for Scoia'tael and Monsters and worse for Northern Realms, to be measured with more games
- **Test, 13 October 2026: the Lab checked**
  - What changed: A control job (the shipped weights through the tuning path) read -4.4% instead of zero: tuned-weight jobs had lost the scene's opening exchanges. Three more Lab defects were found the same way and fixed, each with a test that failed first: the blunder hunter's "pass" option replayed the native AI's move instead of passing (findings that said "should have passed" before this date are void), hunts and SPSA ran without the opening exchanges, and SPSA compared its plus and minus sides on different matchups when a task failed
  - Outcome: Control now reads +0.00%. SPSA weights from the first run: not kept (Adaptive -0.31%, Strong -1.02% z -2.3)
- **Test, 13 October 2026: the spy engine (Novigrad tournament, in-game matches g158-g161)**
  - What changed: Lab switches. spyval: the Adaptive strength measure counts a spy by its draw, not by the power it gives away. spymirror / spymirror1: NPC spies limited to the player's (one fewer), with or without matching Decoys. decoy3 fixed (it did nothing on the lean decks). witcherone: one of Geralt and Ciri in the hero fallback. spy-first: the NPC plays its cheapest spy first outside the final round. draw15 / draw20: the NPC values cards still to be drawn more
  - Outcome: Spy mirror dropped in every form (NPC win share -2.8 to -8.4 points, z -3 to -8: spies are worth a lot). witcherone dropped as is (-2.8 Hard, -4.1 Normal); a stepped fallback (one witcher first, the second only when still short) goes to the deck tuner. decoy3 mixed (+1.9 Adaptive Hard, -1.5 to -2.2 elsewhere): Decoys per player faction go to the deck tuner. spyval, spy-first and draw weights positive but not proven yet; they keep running

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
