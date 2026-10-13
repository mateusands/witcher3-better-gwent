"""NPC deck switch "ability-value" (Lab only): units valued by their abilities, not printed power.

Horn units (Dandelion, Draig Bon-Dhu), muster packages (with every copy: three Darkness for
Gaunter O'Dimm), row-scorch units, Morph units with a Mardroeme source. Default decks unchanged.
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'sim'))

from evaluate_pool import XML, setup  # noqa: E402
from blunder_hunter import card_names  # noqa: E402
from gwentsim.native_decks import NativeDecks  # noqa: E402
from gwentsim import npc_balance as nb  # noqa: E402

C = nb.C
DANDELION, GAUNTER, DARKNESS, DRAKKAR = 12, 18, 19, 520


def data():
    match = setup()['match']
    return match.templates, card_names(), NativeDecks(XML, match.templates)


def muster(packages, index):
    return next(cards for kind, cards in packages if kind == 'muster' and any(c.index == index for c in cards))


def test_default_packages_unchanged_and_switch_holds_every_copy():
    templates, names, _ = data()
    before = muster(nb.packages(templates, C.FactionId_Skellige, names), GAUNTER)
    assert Counter(c.index for c in before) == {GAUNTER: 1, DARKNESS: 1}
    saved = nb._ABILITY_VALUE
    nb._ABILITY_VALUE = True
    try:
        groups = nb.packages(templates, C.FactionId_Skellige, names)
    finally:
        nb._ABILITY_VALUE = saved
    assert Counter(c.index for c in muster(groups, GAUNTER)) == {GAUNTER: 1, DARKNESS: 3}
    assert Counter(c.index for c in muster(groups, DRAKKAR)) == {DRAKKAR: 3}


def test_package_worth_counts_what_one_draw_brings():
    templates, names, _ = data()
    value = lambda t: float(t.power)
    group = [templates[GAUNTER]] + [templates[DARKNESS]] * 3
    assert nb.package_worth('muster', group, value) == (2 + 3 * 4) / 4          # default: the mean
    saved = nb._ABILITY_VALUE
    nb._ABILITY_VALUE = True
    try:
        # Each Darkness is brought by four cards (Gaunter and the three copies): 4 * 1.875.
        assert nb.package_worth('muster', group, value) == (2 + 3 * 4 * 1.875) / 4
        assert nb.package_worth('single', [templates[DANDELION]], value) == 2
    finally:
        nb._ABILITY_VALUE = saved


def test_horn_unit_bonus_does_not_stack_with_a_horn_leader():
    templates, names, native = data()
    by_leader = {}
    for name in native.npc_names():
        deck = native.build(name, 3, repaired=True)
        kit, _ = nb.special_kit(templates, templates[deck.selected_king_index].faction,
                                deck.selected_king_index, [], names)
        bonus = nb.ability_bonus(templates, deck, names, kit)
        horn_row = nb.LEADER_HORN_ROW.get(nb.leader_effect(templates, deck.selected_king_index))
        by_leader[name] = (horn_row, bonus[DANDELION])
        assert bonus[15] == nb.SCORCH_HIT * nb.SCORCH_TOP                          # Villentretenmerth
        assert 20 not in bonus and 525 not in bonus                                 # suicide summons: none
    assert any(row == 'melee' and gain == 0 for row, gain in by_leader.values())   # Dandelion is melee
    assert any(row != 'melee' and gain > 0 for row, gain in by_leader.values())


def test_switch_decks_follow_the_rules_and_use_the_cards():
    templates, names, native = data()
    default, switched = Counter(), Counter()
    for name in native.npc_names():
        deck = native.build(name, 3, repaired=True)
        for mode, counts in (('strong', default), ('strong:ability-value', switched)):
            cards = nb.apply_mode(templates, deck, names, mode).card_indices
            assert not nb.audit(templates, cards, deck.selected_king_index), (name, mode)
            counts.update(set(cards))
            if GAUNTER in cards:
                assert cards.count(DARKNESS) == 3
    assert switched[DANDELION] > default[DANDELION] and switched[GAUNTER] > default[GAUNTER]
    assert switched[450] and switched[475]       # the monster musters (Arachas, Crones) stay picked
    assert nb._ABILITY_BONUS == {} and nb._ABILITY_VALUE is False                  # restored afterwards
