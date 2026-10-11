"""Returned Muster copies remain summonable while the replacement stays usable."""
from dataclasses import replace
from collections import Counter
from test_horn_evaluation import board,card
from test_position import capture
from gwentsim import constants as C
from gwentsim.position import Action
from mulligan_policy import exchanged
from structural_mulligan import choose_structural_mulligan

MELEE=C.CardType_Creature|C.CardType_Melee


def test_exchange_preserves_completed_muster_group_and_frees_one_hand_card(board):
    a=card(board,4,1,MELEE,(C.CardEffect_SummonClones,))
    a.templateRef.summonFlags=[a.templateId]
    b=board.spawnCardInstance(a.templateId,0,1)
    b.inList,b.listsPlayer=1,0;board.getCardInstanceList(1,0).append(b)
    unit=card(board,6,1,MELEE)
    initial=replace(capture(board),hand=(a.instanceId,b.instanceId),counts={unit.templateId:2})
    decision=choose_structural_mulligan(initial)
    assert decision.source in initial.hand and decision.expected_after is None
    retained=next(k for k in initial.hand if k!=decision.source)
    after=exchanged(initial,decision.source,unit.templateId)
    original_play=initial.apply(Action(retained,5));new_play=after.apply(Action(retained,5))
    roster=lambda p:Counter(p.cards[k].template for k in p.board[p.player,5])
    assert roster(original_play)==roster(new_play)==Counter({a.templateId:2})
    assert original_play.scores()==new_play.scores()==(8,0)
    assert not original_play.hand and tuple(new_play.cards[k].template for k in new_play.hand)==(unit.templateId,)
    assert initial.hand==(a.instanceId,b.instanceId) and initial.counts=={unit.templateId:2}


def test_single_muster_bond_hero_spy_and_empty_deck_are_kept(board):
    a=card(board,4,1,MELEE,(C.CardEffect_SummonClones,));a.templateRef.summonFlags=[a.templateId]
    bond=card(board,4,1,MELEE,(C.CardEffect_SameTypeMorale,));bond.templateRef.summonFlags=[bond.templateId]
    hero=card(board,10,1,MELEE|C.CardType_Hero)
    spy=card(board,0,1,MELEE|C.CardType_Spy,(C.CardEffect_Draw2,))
    unit=card(board,6,1,MELEE)
    initial=replace(capture(board),hand=tuple(c.instanceId for c in (a,bond,hero,spy)),counts={unit.templateId:2})
    assert choose_structural_mulligan(initial).source is None
    assert choose_structural_mulligan(replace(initial,counts={})).source is None
