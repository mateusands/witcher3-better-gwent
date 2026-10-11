"""Own-deck information boundary, native exchange semantics and synergy retention."""
from dataclasses import replace
from test_horn_evaluation import board,card,horn,unit
from test_position import capture
from gwentsim import constants as C
from mulligan_policy import choose_mulligan,exchanged

MELEE=C.CardType_Creature|C.CardType_Melee


def remaining(board,hand,counts):
    state=capture(board)
    return replace(state,hand=tuple(c.instanceId for c in hand),counts=counts)


def test_weak_unit_exchanged_without_peeking_next_card_or_mutating_inputs(board):
    weak=card(board,1,1,MELEE);strong=card(board,10,1,MELEE)
    state=remaining(board,(weak,),{strong.templateId:2})
    decision=choose_mulligan(state)
    assert decision.source==weak.instanceId and (decision.before,decision.expected_after)==(1,10)
    assert state.hand==(weak.instanceId,) and state.counts=={strong.templateId:2}
    after=exchanged(state,weak.instanceId,strong.templateId)
    assert after.counts=={strong.templateId:1,weak.templateId:1}


def test_keep_horn_combination_and_keep_a_strong_hand(board):
    h=horn(board);u=card(board,8,1,MELEE);poor=card(board,5,1,MELEE)
    state=remaining(board,(h,u),{poor.templateId:3})
    decision=choose_mulligan(state)
    assert decision.source is None and decision.before==16


def test_bond_partners_are_not_treated_as_independent_base_power(board):
    a=card(board,4,1,MELEE,(C.CardEffect_SameTypeMorale,))
    a.templateRef.summonFlags=[a.templateId]
    b=board.spawnCardInstance(a.templateId,0,1);b.inList,b.listsPlayer=1,0
    board.getCardInstanceList(1,0).append(b)
    weaker=card(board,5,1,MELEE)
    state=remaining(board,(a,b),{weaker.templateId:2})
    assert choose_mulligan(state).source is None and choose_mulligan(state).before==16


def test_muster_duplicate_returns_to_deck_and_still_remains_summonable(board):
    a=card(board,4,1,MELEE,(C.CardEffect_SummonClones,))
    a.templateRef.summonFlags=[a.templateId]
    b=board.spawnCardInstance(a.templateId,0,1);b.inList,b.listsPlayer=1,0
    board.getCardInstanceList(1,0).append(b)
    good=card(board,10,1,MELEE)
    state=remaining(board,(a,b),{good.templateId:1})
    decision=choose_mulligan(state)
    assert decision.source in (a.instanceId,b.instanceId)
    assert decision.before==8 and decision.expected_after==18
    after=exchanged(state,decision.source,good.templateId)
    assert after.counts[a.templateId]==1 and after.reserve()==18


def test_no_remaining_cards_means_no_exchange_and_weighted_copies_are_counted(board):
    weak=card(board,1,1,MELEE);good=card(board,9,1,MELEE)
    other=card(board,3,1,MELEE)
    state=remaining(board,(weak,),{})
    assert choose_mulligan(state).source is None
    state=replace(state,counts={good.templateId:1,other.templateId:3})
    assert choose_mulligan(state).expected_after==4.5


def test_mushroom_preserves_two_transformers_and_their_transformed_bond(board):
    from mulligan_policy import initial_hand_potential
    target=card(board,8,1,C.CardType_Creature|C.CardType_Ranged,(C.CardEffect_SameTypeMorale,))
    target.templateRef.summonFlags=[target.templateId]
    a=card(board,2,1,C.CardType_Creature|C.CardType_Ranged,(C.CardEffect_Morph,))
    a.templateRef.summonFlags=[target.templateId]
    b=board.spawnCardInstance(a.templateId,0,1);b.inList,b.listsPlayer=1,0
    board.getCardInstanceList(1,0).append(b)
    mushroom=card(board,0,1,C.CardType_Row_Modifier|C.CardType_Ranged,(C.CardEffect_Mushroom,))
    poor=card(board,4,1,MELEE)
    state=remaining(board,(a,b,mushroom),{poor.templateId:2})
    assert state.reserve()==4 and initial_hand_potential(state)==32
    assert choose_mulligan(state).source is None


def test_mushroom_cannot_transform_other_row_or_share_horn_modifier_slot(board):
    from mulligan_policy import initial_hand_potential
    target=card(board,8,1,C.CardType_Creature|C.CardType_Ranged)
    a=card(board,2,1,C.CardType_Creature|C.CardType_Ranged,(C.CardEffect_Morph,))
    a.templateRef.summonFlags=[target.templateId]
    wrong=card(board,0,1,C.CardType_Row_Modifier|C.CardType_Melee,(C.CardEffect_Mushroom,))
    assert initial_hand_potential(remaining(board,(a,wrong),{}))==2
    correct=card(board,0,1,C.CardType_Row_Modifier|C.CardType_Ranged,(C.CardEffect_Mushroom,))
    h=card(board,0,1,C.CardType_Row_Modifier|C.CardType_Ranged,(C.CardEffect_Horn,))
    assert initial_hand_potential(remaining(board,(a,correct,h),{}))==8


def test_death_summon_has_later_round_value_instead_of_zero(board):
    from mulligan_policy import initial_hand_potential
    target=card(board,8,1,MELEE)
    cow=card(board,0,1,C.CardType_Creature|C.CardType_Ranged,(C.CardEffect_SuicideSummon,))
    cow.templateRef.summonFlags=[target.templateId]
    poor=card(board,4,1,MELEE)
    state=remaining(board,(cow,),{poor.templateId:2})
    assert state.reserve()==0 and initial_hand_potential(state)==8
    assert choose_mulligan(state).source is None
