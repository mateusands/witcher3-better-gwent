"""Synthetic designer scenarios for corrected Horn gain and legal row choice."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gwentsim import constants as C
from gwentsim.gwint.card_manager import CardManager
from gwentsim.gwint.card_template import CardTemplate
from gwentsim.horn_evaluation import horn_alternatives, best_horn_alternative


@pytest.fixture
def board(monkeypatch):
    monkeypatch.setattr(CardManager, '_instance', None)
    monkeypatch.setattr(CardManager, 'lastInstanceID', 0)
    manager = CardManager()
    monkeypatch.setattr(manager, 'halfWeatherEnabled', lambda player: False)
    return manager


def card(board, power, row, flags, effects=(), player=0):
    template = CardTemplate()
    template.index = len(board._cardTemplates) + 1
    template.power, template.typeArray = power, flags
    template.effectFlags, template.summonFlags = list(effects), []
    board._cardTemplates[template.index] = template
    instance = board.spawnCardInstance(template.index, player, row)
    instance.inList, instance.listsPlayer = row, player
    board.getCardInstanceList(row, player).append(instance)
    return instance


def horn(board, row=1):
    return card(board, 0, row, C.CardType_Row_Modifier | C.CardType_SeigeRangedMelee, (C.CardEffect_Horn,))


def unit(board, power, row, hero=False):
    row_type = {5: C.CardType_Melee, 4: C.CardType_Ranged, 3: C.CardType_Siege}[row]
    return card(board, power, row, C.CardType_Creature | row_type | (C.CardType_Hero if hero else 0))


def test_sums_entire_row_and_ignores_heroes_and_opponent(board):
    h = horn(board)
    unit(board, 6, 5); unit(board, 5, 5); unit(board, 15, 5, hero=True)
    unit(board, 10, 4)
    card(board, 100, 3, C.CardType_Creature | C.CardType_Siege, player=1)
    options = horn_alternatives(board, h, 0)
    assert [o.gain for o in options] == [11, 10, 0]
    assert best_horn_alternative(options).modifier_slot == 8
    assert all(h not in u.effectedByCardsRefList for row in (3, 4, 5) for u in board.getCardInstanceList(row, 0))


def test_siege_gain_has_no_stale_ranged_baseline(board):
    h = horn(board)
    unit(board, 12, 4)
    unit(board, 6, 3); unit(board, 8, 3)
    best = best_horn_alternative(horn_alternatives(board, h, 0))
    assert (best.modifier_slot, best.gain) == (6, 14)


def test_existing_horn_effect_does_not_stack_and_modifier_slot_is_blocked(board):
    h = horn(board)
    a = unit(board, 8, 5)
    existing = card(board, 2, 5, C.CardType_Creature | C.CardType_Melee, (C.CardEffect_Horn,))
    a.effectedByCardsRefList.append(existing)
    assert horn_alternatives(board, h, 0)[0].gain == 2  # Existing Horn unit itself can gain.
    horn(board, row=8)
    assert all(o.modifier_slot != 8 for o in horn_alternatives(board, h, 0))


def test_weather_morale_and_bonds_use_native_power_order(board):
    h = horn(board)
    a, b = unit(board, 8, 5), unit(board, 8, 5)
    weather = card(board, 0, 9, C.CardType_Weather, (C.CardEffect_Melee,), player=-1)
    morale = card(board, 0, 1, C.CardType_Creature | C.CardType_Melee, (C.CardEffect_ImproveNeighbours,))
    bond = card(board, 0, 1, C.CardType_Creature | C.CardType_Melee, (C.CardEffect_SameTypeMorale,))
    for u in (a, b): u.effectedByCardsRefList.extend((weather, morale, bond))
    # Weather 1, bond +1, morale +1: each unit is 3, Horn adds 3 each.
    assert horn_alternatives(board, h, 0)[0].gain == 6
    assert a.effectedByCardsRefList == [weather, morale, bond]


def test_restores_effects_when_native_power_calculation_fails(board, monkeypatch):
    h, a = horn(board), unit(board, 8, 5)
    calls = 0
    def failing_power():
        nonlocal calls
        calls += 1
        if calls == 2: raise RuntimeError('synthetic rule failure')
        return 8
    monkeypatch.setattr(a, 'getTotalPower', failing_power)
    with pytest.raises(RuntimeError, match='synthetic rule failure'):
        horn_alternatives(board, h, 0)
    assert not a.effectedByCardsRefList


def test_only_native_legal_rows_are_evaluated(board):
    h = card(board, 0, 1, C.CardType_Row_Modifier | C.CardType_Melee, (C.CardEffect_Horn,))
    assert [o.modifier_slot for o in horn_alternatives(board, h, 0)] == [8]
    board.cardListHand[0].remove(h)
    with pytest.raises(ValueError, match='acting player hand'):
        horn_alternatives(board, h, 0)
