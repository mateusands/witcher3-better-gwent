"""Designer regressions: real row effects, supported combinations and no mutation."""
from test_horn_evaluation import board, card, horn, unit
from gwentsim import constants as C
from gwentsim.unit_evaluation import unit_alternatives


def test_morale_uses_actual_destination_not_unrelated_siege_row(board):
    unit(board, 8, 5); unit(board, 6, 5); unit(board, 15, 5, hero=True)
    unit(board, 12, 3)
    morale = card(board, 2, 1, C.CardType_Creature | C.CardType_Melee, (C.CardEffect_ImproveNeighbours,))
    before = [list(c.effectedByCardsRefList) for c in board.getCardInstanceList(5, 0)]
    assert unit_alternatives(board, morale, 0)[0].gain == 4
    assert [list(c.effectedByCardsRefList) for c in board.getCardInstanceList(5, 0)] == before
    assert morale.inList == 1 and not morale.effectedByCardsRefList


def test_bond_counts_both_new_and_existing_units(board):
    existing = card(board, 8, 5, C.CardType_Creature | C.CardType_Melee, (C.CardEffect_SameTypeMorale,))
    played = board.spawnCardInstance(existing.templateId, 0, 1)
    played.inList, played.listsPlayer = 1, 0
    board.getCardInstanceList(1, 0).append(played)
    existing.templateRef.summonFlags = [existing.templateId]
    assert unit_alternatives(board, played, 0)[0].gain == 24  # 8 -> 16 + 16.
    assert not existing.effectedByCardsRefList and not played.effectedByCardsRefList


def test_unit_then_horn_can_win_despite_zero_current_horn_gain(board):
    h = horn(board)
    played = card(board, 8, 1, C.CardType_Creature | C.CardType_Melee, (C.CardEffect_None,))
    played.templateRef.typeArray = C.CardType_Creature | C.CardType_Melee
    option = unit_alternatives(board, played, 0, h)[0]
    assert (option.gain, option.horn_sequence_gain) == (8, 16)
    assert not played.effectedByCardsRefList
    assert not board.getCardInstanceList(5, 0)


def test_existing_horn_and_heroes_do_not_double_again(board):
    existing = horn(board, row=8)
    board.cardEffectManager.getEffectList(5, 0).append(existing)
    h = horn(board)
    played = card(board, 8, 1, C.CardType_Creature | C.CardType_Melee, (C.CardEffect_None,))
    played.templateRef.typeArray = C.CardType_Creature | C.CardType_Melee
    option = unit_alternatives(board, played, 0, h)[0]
    assert option.gain == 16 and option.horn_sequence_gain is None
    played.templateRef.typeArray |= C.CardType_Hero
    assert unit_alternatives(board, played, 0)[0].gain == 8


def test_unsupported_spy_medic_muster_are_not_claimed_exact(board):
    for effect in (C.CardEffect_Nurse, C.CardEffect_SummonClones, C.CardEffect_MeleeScorch):
        played = card(board, 5, 1, C.CardType_Creature | C.CardType_Melee, (effect,))
        assert not unit_alternatives(board, played, 0)
    spy = card(board, 5, 1, C.CardType_Creature | C.CardType_Melee | C.CardType_Spy)
    assert not unit_alternatives(board, spy, 0)


def test_morale_gain_includes_existing_horn_and_weather(board):
    existing = unit(board, 8, 5)
    h = horn(board, row=8)
    weather = card(board, 0, 9, C.CardType_Weather, (C.CardEffect_Melee,), player=-1)
    existing.effectedByCardsRefList.extend((h, weather))
    board.cardEffectManager.getEffectList(5, 0).extend((h, weather))
    morale = card(board, 2, 1, C.CardType_Creature | C.CardType_Melee, (C.CardEffect_ImproveNeighbours,))
    # Existing weathered/Horned unit goes 2 -> 4; new unit is 2.
    assert unit_alternatives(board, morale, 0)[0].gain == 4
    assert existing.effectedByCardsRefList == [h, weather]
