"""Rule checks for hero eligibility and order-sensitive automatic graveyard choices.

Uses synthetic templates, not private game assets or recorded outcomes.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gwentsim import constants as C, rng
from gwentsim.gwint.card_manager import CardManager, CARD_LIST_LOC_GRAVEYARD, CARD_LIST_LOC_MELEE, CARD_LIST_LOC_SEIGE
from gwentsim.gwint.card_template import CardTemplate


@pytest.fixture
def manager(monkeypatch):
    monkeypatch.setattr(CardManager, '_instance', None)
    monkeypatch.setattr(CardManager, 'lastInstanceID', 0)
    return CardManager()


def card(manager, template_id, power=10, flags=C.CardType_Creature | C.CardType_Melee):
    template = CardTemplate()
    template.index, template.power, template.typeArray = template_id, power, flags
    template.effectFlags, template.summonFlags = [], []
    manager._cardTemplates[template_id] = template
    return manager.spawnCardInstance(template_id, 0, CARD_LIST_LOC_GRAVEYARD)


def test_heroes_remain_in_grave_but_are_not_resurrection_candidates(manager):
    ordinary = card(manager, 1)
    hero = card(manager, 2, power=15, flags=C.CardType_Creature | C.CardType_Melee | C.CardType_Hero)
    special = card(manager, 3, flags=C.CardType_None)
    manager.cardListGraveyard[0] = [hero, special, ordinary]
    candidates = []
    manager.GetRessurectionTargets(0, candidates, False)
    assert candidates == [ordinary]
    assert manager.cardListGraveyard[0] == [hero, special, ordinary]
    manager.cardListGraveyard[0].reverse()
    reordered = []
    manager.GetRessurectionTargets(0, reordered, False)
    assert reordered == candidates


def test_scorch_excludes_hero_even_if_it_has_the_highest_power(manager):
    ordinary = card(manager, 1)
    hero = card(manager, 2, power=15, flags=C.CardType_Creature | C.CardType_Melee | C.CardType_Hero)
    manager.cardListMelee[0] = [hero, ordinary]
    assert manager.getScorchTargets() == [ordinary]


def test_equal_power_ai_recovery_changes_card_when_grave_order_changes(manager):
    melee = card(manager, 1)
    siege = card(manager, 2, flags=C.CardType_Creature | C.CardType_Siege)
    manager.cardListGraveyard[0] = [melee, siege]
    first = manager.getHigherOrLowerValueCardFromTargetGraveyard(0, True, True, False)
    manager.cardListGraveyard[0].reverse()
    second = manager.getHigherOrLowerValueCardFromTargetGraveyard(0, True, True, False)
    assert first.cardInstance is melee and second.cardInstance is siege
    assert first.comboPoints == second.comboPoints == 10


def test_same_random_value_recovers_different_card_after_grave_reordering(manager, monkeypatch):
    melee = card(manager, 1)
    siege = card(manager, 2, flags=C.CardType_Creature | C.CardType_Siege)
    hero = card(manager, 3, power=15, flags=C.CardType_Creature | C.CardType_Melee | C.CardType_Hero)
    chosen = []
    # Observe the real selector/placement decision without executing the UI/effect layer.
    monkeypatch.setattr(manager, 'addCardInstanceToList', lambda instance, location, player: chosen.append((instance, location, player)))
    for grave in ([hero, melee, siege], [hero, siege, melee]):
        manager.cardListGraveyard[0] = grave
        random = rng.ReplayRandom([('CM3', 0)])
        monkeypatch.setattr(rng.MATH, 'source', random)
        monkeypatch.setattr(rng.MATH, 'listener', None)
        manager.ressurectFromGraveyard(0, 1)
        random.assert_done()
    assert chosen == [(melee, CARD_LIST_LOC_MELEE, 0), (siege, CARD_LIST_LOC_SEIGE, 0)]
