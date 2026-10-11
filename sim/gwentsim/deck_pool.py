"""Local simulator-only deck pool built from native NPC deck definitions.

Every deck is an existing native NPC deck (vanilla XML through NativeDecks) using the
runtime card templates captured in recordings. Leader variants replace only the
leader with another leader of the same faction, so every leader can be exercised.
Nothing here touches the game, a save or a player's card collection.
"""
from dataclasses import dataclass, replace

from . import constants as C

FACTIONS = (C.FactionId_No_Mans_Land, C.FactionId_Nilfgaard, C.FactionId_Northern_Kingdom,
            C.FactionId_Scoiatael, C.FactionId_Skellige)


@dataclass(frozen=True)
class PoolDeck:
    name: str
    faction: int
    leader: int
    native_leader: bool
    deck: object

    def for_player(self, player):
        return replace(self.deck, player=player, card_indices=list(self.deck.card_indices),
                       dynamic_card_requirements=list(self.deck.dynamic_card_requirements),
                       dynamic_cards=list(self.deck.dynamic_cards))


def leaders(templates):
    out = {}
    for t in templates.values():
        if t.index >= 1000 and t.faction in FACTIONS:
            out.setdefault(t.faction, []).append(t.index)
    return {f: sorted(v) for f, v in out.items()}


def build_pool(native, templates, difficulty=3, repaired=False):
    """Native NPC decks at one native deck difficulty, plus same-faction leader variants.

    repaired=True uses Better AI's repaired dynamic-card requirements (mod On)."""
    pool = []
    by_faction = leaders(templates)
    for name in native.npc_names():
        deck = native.build(name, difficulty, repaired=repaired)
        faction = templates[deck.selected_king_index].faction
        pool.append(PoolDeck('%s/d%d' % (name, difficulty), faction, deck.selected_king_index, True, deck))
        for leader in by_faction.get(faction, ()):
            if leader != deck.selected_king_index:
                pool.append(PoolDeck('%s/d%d/leader%d' % (name, difficulty, leader), faction, leader, False,
                                     replace(deck, selected_king_index=leader)))
    return pool


def leader_matchups(pool):
    """Each leader against each faction: deterministic rotation over the base decks.

    The opposing deck always keeps its native leader. Returns (deck, opponent) pairs.
    """
    natives = {f: [d for d in pool if d.native_leader and d.faction == f] for f in FACTIONS}
    by_leader = {}
    for d in pool:
        by_leader.setdefault(d.leader, []).append(d)
    pairs = []
    for i, leader in enumerate(sorted(by_leader)):
        own = by_leader[leader]
        for j, faction in enumerate(FACTIONS):
            opponents = natives[faction]
            if not opponents:
                continue
            pairs.append((own[(i + j) % len(own)], opponents[(i * 7 + j) % len(opponents)]))
    return pairs
