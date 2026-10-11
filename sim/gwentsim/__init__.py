"""gwentsim: simulator port of the Witcher 3 Gwent rules and vanilla AI for the 5.01 project.

Ported from the 5.0 extraction; core Gwent resources are unchanged in the 5.01 audit.
The Scorch callback-order replay gap remains unresolved (docs/SIMULATOR.md).

Modules: as3 (numeric semantics), sort (the only sort allowed), rng (injectable Math.random),
constants (CardTemplate constants), data (templates/decks/recorded matches),
gwint (1:1 port of the rule and AI classes and the headless driver, docs/SIMULATOR.md).
"""
