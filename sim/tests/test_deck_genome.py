"""Deck genome: the knobs the automatic deck tuner turns (sim/gwentsim/npc_balance.py).

Spec (owner, 13 October 2026):
- Fair play: a genome reacts only to what the NPC may know before a match: the player's deck
  faction and the player's deck strength (the game's own NPC decks already follow it). Never
  the player's leader or individual cards.
- decoys {player faction: 0..2}: Decoys added on top of the deck (no unit replaced: Scoia'tael
  is short of good cards already); never more than 2.
- weather {player faction: weather effect}: one weather card added against that faction.
- heroes 'stepped': the Adaptive hero fallback adds one of Geralt and Ciri first (alternating
  per variant), the second only when still short of the target.
- spyval: spies counted by their draw in the Adaptive strength measure.
- scale {NPC faction: x}: Adaptive target multiplier, to balance factions.
- An empty genome changes nothing; special cards stay within 8; Original is never touched.
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'sim'))

from evaluate_pool import player_setup, setup  # noqa: E402
from blunder_hunter import card_names  # noqa: E402
from gwentsim import npc_balance as nb  # noqa: E402

C = nb.C
NR, MONSTERS = C.FactionId_Northern_Kingdom, C.FactionId_No_Mans_Land


def data():
    return setup()['match'].templates, card_names()


def build(npc, player, mode, genome=None):
    templates, names = data()
    with nb.genome(genome or {}):
        return nb.apply_mode(templates, npc.deck, names, mode, player.deck.card_indices, 2).card_indices


def pair_against(faction):
    templates, _ = data()
    return next((n, p) for n, p in player_setup() if nb.deck_faction(templates, p.deck.card_indices) == faction)


def decoys(cards):
    templates, _ = data()
    return sum(templates[i].get_first_effect() == C.CardEffect_UnsummonDummy for i in cards)


def units(cards):
    templates, _ = data()
    return Counter(i for i in cards if templates[i].is_type(C.CardType_Creature))


def specials(cards):
    templates, _ = data()
    return [i for i in cards if not templates[i].is_type(C.CardType_Creature)]


def test_empty_genome_changes_nothing():
    for npc, player in player_setup()[:40]:
        for mode in ('balanced', 'strong'):
            assert build(npc, player, mode, {}) == build(npc, player, mode)


def test_decoys_are_added_on_top_by_player_faction_only():
    npc, player = pair_against(NR)
    for mode in ('balanced', 'strong'):
        plain = build(npc, player, mode)
        tuned = build(npc, player, mode, {'decoys': {NR: 2}})
        # Given 2 Decoys against Northern Realms: 2 Decoys, the same units (none replaced)
        assert decoys(tuned) == 2 and units(tuned) == units(plain)
        # And nothing changes against another faction
        npc2, player2 = pair_against(MONSTERS)
        assert build(npc2, player2, mode, {'decoys': {NR: 2}}) == build(npc2, player2, mode)


def test_never_more_than_two_decoys():
    npc, player = pair_against(NR)
    assert decoys(build(npc, player, 'strong', {'decoys': {NR: 5}})) == 2


def test_weather_against_a_faction():
    npc, player = pair_against(NR)
    templates, _ = data()
    tuned = build(npc, player, 'balanced', {'weather': {NR: C.CardEffect_Siege}})
    assert any(templates[i].get_first_effect() == C.CardEffect_Siege for i in specials(tuned))
    assert len(specials(tuned)) <= 8


def test_scale_raises_the_adaptive_target_for_one_npc_faction():
    templates, _ = data()
    npc, player = next((n, p) for n, p in player_setup()[:200]
                       if len(build(n, p, 'balanced')) and nb.deck_strength(templates, build(n, p, 'balanced'))
                       < nb.deck_strength(templates, p.deck.card_indices) * 1.4)
    faction = templates[npc.deck.selected_king_index].faction
    plain = nb.deck_strength(templates, build(npc, player, 'balanced'))
    stronger = nb.deck_strength(templates, build(npc, player, 'balanced', {'scale': {faction: 1.3}}))
    assert stronger >= plain
    other = MONSTERS if faction != MONSTERS else NR
    assert build(npc, player, 'balanced', {'scale': {other: 1.3}}) == build(npc, player, 'balanced')


def test_stepped_heroes_bring_both_witchers_less_often():
    _, names = data()
    witchers = [set(w) for w in nb.HERO_WITCHERS]
    both = lambda cards: all({names.get(i) for i in cards} & w for w in witchers)
    default = stepped = 0
    for npc, player in player_setup()[:150]:
        default += both(build(npc, player, 'balanced'))
        stepped += both(build(npc, player, 'balanced', {'heroes': 'stepped'}))
    assert default and stepped < default


def test_genome_reads_only_faction_and_strength():
    # Given two player decks of the same faction and strength that differ in one card (a plain
    # unit swapped for another plain unit of equal power)
    templates, _ = data()
    npc, player = pair_against(NR)
    cards = list(player.deck.card_indices)
    plain = lambda t: (t.is_type(C.CardType_Creature) and not t.is_type(C.CardType_Hero) and not nb.is_spy(t)
                       and t.get_first_effect() == C.CardEffect_None)
    swap = next((n, v.index) for n, i in enumerate(cards) if plain(templates[i])
                for v in templates.values() if v.index < 1000 and plain(v) and v.index not in cards
                and v.power == templates[i].power and v.faction in (templates[i].faction, C.FactionId_Neutral))
    other = cards[:]; other[swap[0]] = swap[1]
    assert nb.deck_faction(templates, other) == nb.deck_faction(templates, cards)
    assert nb.deck_strength(templates, other) == nb.deck_strength(templates, cards)
    genome = {'decoys': {NR: 1}, 'weather': {NR: C.CardEffect_Siege}, 'heroes': 'stepped', 'spyval': True}
    _, names = data()
    # When the NPC deck is built against each, then both NPC decks are the same
    for mode in ('balanced', 'strong'):
        with nb.genome(genome):
            a = nb.apply_mode(templates, npc.deck, names, mode, cards, 2).card_indices
            b = nb.apply_mode(templates, npc.deck, names, mode, other, 2).card_indices
        assert a == b, mode
