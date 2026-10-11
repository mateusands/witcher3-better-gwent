# Research behind Better Gwent AI

What I studied, what the AI and its tests are built on, what I tried and what I dropped.
Papers are cited as references; the software tools are listed with their licenses.

## How the AI decides

Gwent hides information: the opponent's hand and both decks are unknown. The AI never
reads them (see "Fair play" in the README). It samples plausible hidden hands from public
information and searches its own moves and the opponent's replies against those samples.

| Idea | Reference | Where it is used |
| --- | --- | --- |
| Information Set Monte Carlo Tree Search | P. I. Cowling, E. J. Powley, D. Whitehouse, *Information Set Monte Carlo Tree Search*, IEEE Transactions on Computational Intelligence and AI in Games, 2012 | Experimental ISMCTS kernel and hybrid policy; its lessons shaped V8's hidden-hand handling |
| Sampling hidden information (determinization) | J. Long, N. R. Sturtevant, M. Buro, T. Furtak, [*Understanding the Success of Perfect Information Monte Carlo Sampling in Game Tree Search*](https://ojs.aaai.org/index.php/AAAI/article/view/7562), AAAI 2010 | V8 opponent-hand hypotheses; when sampling works well and where it fails |
| Self-play and learned evaluation | D. Silver et al., *A general reinforcement learning algorithm that masters chess, shogi, and Go through self-play* (AlphaZero), Science, 2018 | Plan for parameter tuning by self-play and a small value network |

## How the AI is tested

| Idea | Reference | Where it is used |
| --- | --- | --- |
| Same luck for every compared option (duplicate games, common random numbers) | Duplicate format of the Annual Computer Poker Competition, described in [*OpenHoldem: A Benchmark for Large-Scale Imperfect-Information Game Research*](https://arxiv.org/abs/2012.06168), 2020 | Benchmarks (same deck pair and seed for native and Better AI) and the blunder hunter (same later luck for every alternative) |
| What counts as a mistake | S. Ganzfried, [*Mistakes in Games*](https://arxiv.org/abs/1910.00225), 2019 | Definition behind the blunder hunter: a decision is a mistake only if another move is better on average |
| Sequential Halving | Z. Karnin, T. Koren, O. Somekh, *Almost Optimal Exploration in Multi-Armed Bandits*, ICML 2013 | Deep blunder hunt: every legal move gets a small budget, the worse half is dropped, the budget doubles |
| Gumbel planning | I. Danihelka, A. Guez, J. Schrittwieser, D. Silver, *Policy improvement by planning with Gumbel*, ICLR 2022 | Where Sequential Halving became the root selection of modern AlphaZero-style search |
| Testing card-game AIs | A. Dockhorn, S. Mostaghim, [*Introducing the Hearthstone-AI Competition*](https://arxiv.org/abs/1906.04238), 2019 | How card-game agents are evaluated across decks and opponents |
| Diverse deck generation | Y. Zhang, M. C. Fontaine, A. K. Hoover, S. Nikolaidis, [*Deep Surrogate Assisted MAP-Elites for Automated Hearthstone Deckbuilding*](https://arxiv.org/abs/2112.03534), GECCO 2022 | Inspiration for player-style decks (power, synergy, random, early-game) |

## Studied, not used (yet)

| Idea | Reference | Why not yet |
| --- | --- | --- |
| Variance reduction for evaluating agents | N. Burch, M. Schmid, M. Moravčík, D. Morrill, M. Bowling, [*AIVAT: A New Variance Reduction Technique for Agent Evaluation in Imperfect Information Games*](https://ojs.aaai.org/index.php/AAAI/article/view/11481), AAAI 2018 | Needs a calibrated value estimate; a candidate once the value network exists |
| Counterfactual regret minimization | M. Zinkevich, M. Johanson, M. Bowling, C. Piccione, *Regret Minimization in Games with Incomplete Information*, NeurIPS 2007 | Solves the whole game offline; far too heavy for the game's Flash runtime |
| Deep counterfactual value search | M. Moravčík et al., *DeepStack: Expert-level artificial intelligence in heads-up no-limit poker*, Science, 2017 | Same: too heavy for real-time decisions inside the game |

## Planned

| Idea | Reference | Plan |
| --- | --- | --- |
| Tuning many parameters at once with noisy measurements | J. C. Spall, *Multivariate stochastic approximation using a simultaneous perturbation gradient approximation* (SPSA), IEEE Transactions on Automatic Control, 1992 | Phase 3: tune V8's weights by self-play, accepted only if stronger on NPC and player-style decks at every level |
| Small value network | AlphaZero (above) | Phase 4: estimate win probability from the board, only if it runs fast enough in Flash and wins in benchmarks |

## What I tried

| Version | What changed | Outcome |
| --- | --- | --- |
| V1–V2 | Corrected Horn estimates (whole row, siege baselines), round-two spending against round-three resources, pass planning | Kept |
| V3 | Exact gains for supported units, combination-aware pass safeguards | Kept |
| V4 | Immediate gain separated from next-round reserve value; Muster as a group resource | Kept |
| V5 | Immutable public-position model; search over own move sequences, passing compared with match resources | Kept; base of everything after |
| V6 | Opponent replies from public-catalog hypotheses; Medic recovery chains | Kept |
| V7 | Leaders as searchable "use now or keep" actions | Kept; clear gain over V6 |
| ISMCTS hybrid | Full information-set tree search with exhaustive passed-round solver | Measured, not faster or stronger than V7 alone; useful parts reused |
| Learned evaluator | Small logistic model over board features (experimental) | Not shipped; superseded by the planned value network |
| Guards | No overplay or pointless pass against a passed opponent, concede unwinnable chases, Decoy and Medic priorities, Spy reserve value, Mushroom transformations, hero preservation | Kept where measured neutral or better |
| V8 | All of the above ported to ActionScript and running inside the game, with time limits and native fallback | Current version |
| In-game fixes | Stalls, wasted Frost/Horn, round-1 overcommit, Medic choosing a Spy when out of cards, NPC extra-card requirements | Kept |

Every change is measured on the same decks and luck as the version before it, and kept
only when it does not make the AI weaker. Details and numbers: [TESTING.md](TESTING.md).

## Software

| Tool | License | Use |
| --- | --- | --- |
| [PyPy](https://pypy.org) | MIT | Runs the simulations about 2x faster with identical results |
| [psutil](https://github.com/giampaolo/psutil) | BSD-3-Clause | CPU, memory and disk readings in the Lab panel |
| [uv](https://github.com/astral-sh/uv) | MIT / Apache-2.0 | Installs PyPy |
| [JPEXS Free Flash Decompiler](https://github.com/jindrapetrik/jpexs-decompiler) | GPL-3.0 | Local build tool for the Gwent interface; not distributed with the mod |
| [Node.js](https://nodejs.org) | MIT | Runs the ActionScript AI in the tests to compare it with the Python reference |
