"""Local deck pool: native decks only, every leader covered, no shared mutable lists."""
from pathlib import Path
from gwentsim.data import load_match
from gwentsim.native_decks import NativeDecks
from gwentsim.deck_pool import build_pool, leader_matchups, leaders, FACTIONS

ROOT=Path(__file__).resolve().parents[2]


def pool():
    match=load_match(ROOT/'game/records/g113.json')
    native=NativeDecks(ROOT/'game/vanilla/xml/content0/gameplay/items',match.templates)
    return match,native,build_pool(native,match.templates)


def test_every_leader_meets_every_faction_with_native_card_lists():
    match,native,decks=pool()
    pairs=leader_matchups(decks)
    assert {a.leader for a,_ in pairs}=={l for ls in leaders(match.templates).values() for l in ls}
    assert len(pairs)==22*len(FACTIONS)
    for own,other in pairs:
        assert other.native_leader and match.templates[own.leader].faction==own.faction
        name,difficulty=own.name.split('/')[:2]
        assert own.deck.card_indices==native.build(name,int(difficulty[1:])).card_indices


def test_seat_copies_do_not_share_lists():
    _,_,decks=pool()
    a=decks[0].for_player(0);a.card_indices.append(-1)
    assert -1 not in decks[0].deck.card_indices and decks[0].for_player(1).player==1
