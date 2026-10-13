"""Spy engine experiments for the NPC decks (Lab deck flags, Adaptive and Strong; Original untouched).

Spec (agreed with the owner, 13 October 2026, after the Novigrad tournament g158-g161):
- spyval: in the strength measure a spy counts by the cards it draws, not by its printed power
  (that power goes to the opponent). Applies to both decks, so the Adaptive target stays fair.
- spymirror / spymirror1: the NPC may carry as many spies as the player's deck (spymirror1: one
  fewer), at least 1 (Avallac'h). A limit, not a quota: the builder decides within it.
- decoymirror / decoyhalf: as many Decoys as the player's spies (decoyhalf: half, rounded up).
- decoy3: three Decoys against a Nilfgaard or Northern Realms player deck, also when the lean
  kit holds no Decoy (before, the switch only copied a Decoy already in the deck).
- witcherone: the Adaptive every-hero fallback still holds at most one of Geralt and Ciri.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'sim'))

from evaluate_pool import player_setup, setup  # noqa: E402
from blunder_hunter import card_names  # noqa: E402
from gwentsim import npc_balance as nb  # noqa: E402

C = nb.C


def data():
    return setup()['match'].templates, card_names()


def index_of(name):
    return next(i for i, n in card_names().items() if n == name)


def spies(templates, cards):
    return sum(templates[i].is_type(C.CardType_Creature) and nb.is_spy(templates[i]) for i in cards)


def decoys(templates, cards):
    return sum(templates[i].get_first_effect() == C.CardEffect_UnsummonDummy for i in cards)


def pairs_by_player_spies():
    """{player spy count: (npc deck, player deck)} over the Lab's player-deck matchups, with a
    spy-faction NPC (Nilfgaard, Northern Realms), whose default decks carry several spies."""
    templates, _ = data()
    out = {}
    for npc, player in player_setup():
        if templates[npc.deck.selected_king_index].faction in nb.SPY_FACTIONS:
            out.setdefault(spies(templates, player.deck.card_indices), (npc, player))
    return out


def build(npc, player, mode):
    templates, names = data()
    return nb.apply_mode(templates, npc.deck, names, mode, player.deck.card_indices, 2).card_indices


# ---- spyval ---------------------------------------------------------------------------------

def test_spy_counts_by_its_draw_not_its_power():
    # Given Stefan Skellen (a 9-power spy)
    templates, _ = data()
    stefan = index_of('stefan')
    default = nb.deck_strength(templates, [stefan])
    # When the strength measure counts spies by their draw
    with nb.spy_valued():
        valued = nb.deck_strength(templates, [stefan])
    # Then his 9 power no longer counts, only the draw bonus
    assert default == templates[stefan].power + nb.STRENGTH_BONUS[C.CardEffect_Draw2]
    assert valued == nb.STRENGTH_BONUS[C.CardEffect_Draw2]


# ---- spymirror ------------------------------------------------------------------------------

def test_spy_mirror_caps_npc_spies_by_the_players():
    templates, _ = data()
    by = pairs_by_player_spies()
    assert 0 in by and max(by) >= 3
    for count, (npc, player) in by.items():
        for mode in ('balanced', 'strong'):
            assert spies(templates, build(npc, player, mode)) > 1      # by default: several spies
            # Given a player deck with `count` spies, when the NPC deck is built with the mirror
            got = spies(templates, build(npc, player, mode + ':spymirror'))
            # Then the NPC holds at most that many (at least one allowed: Avallac'h)
            assert got <= max(1, count), (mode, count, got)
            got1 = spies(templates, build(npc, player, mode + ':spymirror1'))
            assert got1 <= max(1, count - 1), (mode, count, got1)


def test_original_decks_ignore_the_flags():
    npc, player = next(iter(pairs_by_player_spies().values()))
    assert build(npc, player, 'original:spymirror+decoymirror') == npc.deck.card_indices


# ---- decoys ---------------------------------------------------------------------------------

def test_decoys_follow_the_players_spies():
    templates, _ = data()
    for count, (npc, player) in pairs_by_player_spies().items():
        for mode in ('balanced', 'strong'):
            assert decoys(templates, build(npc, player, mode + ':decoymirror')) == count
            assert decoys(templates, build(npc, player, mode + ':decoyhalf')) == math.ceil(count / 2)


def test_decoy3_adds_decoys_even_without_one_in_the_kit():
    templates, _ = data()
    for npc, player in player_setup():
        if nb.deck_faction(templates, player.deck.card_indices) in nb.SPY_FACTIONS:
            plain = build(npc, player, 'balanced')
            assert decoys(templates, plain) == 0                     # the lean kit: Horn and Scorch
            assert decoys(templates, build(npc, player, 'balanced:decoy3')) == 3
            return
    raise AssertionError('no spy-faction player deck in the pool')


def test_special_cards_stay_within_eight():
    templates, _ = data()
    for count, (npc, player) in pairs_by_player_spies().items():
        cards = build(npc, player, 'strong:decoymirror')
        assert sum(not templates[i].is_type(C.CardType_Creature) for i in cards) <= 8


# ---- witcherone -----------------------------------------------------------------------------

def test_fallback_holds_at_most_one_witcher():
    templates, names = data()
    witchers = [set(w) for w in nb.HERO_WITCHERS]
    both = 0
    for npc, player in player_setup()[:120]:
        cards = {names.get(i) for i in build(npc, player, 'balanced:witcherone')}
        assert not all(cards & w for w in witchers)
        both += all({names.get(i) for i in build(npc, player, 'balanced')} & w for w in witchers)
    assert both, 'the default fallback should show the problem somewhere in these matchups'
