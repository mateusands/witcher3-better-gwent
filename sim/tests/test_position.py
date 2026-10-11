"""Public model scenarios: deterministic transitions, consumed resources and privacy."""
from dataclasses import replace
from copy import deepcopy
from test_horn_evaluation import board,card,horn,unit
from gwentsim.gwint.small import GwintCardValues
from gwentsim import constants as C
from gwentsim.position import Position,Action


def capture(board):
    board.cardValues=GwintCardValues()
    return Position.from_manager(board,0)


def test_unit_horn_sequence_changes_board_without_touching_live_cards(board):
    h=horn(board);u=card(board,8,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_None,))
    initial=capture(board);after=initial.apply(Action(u.instanceId,5)).apply(Action(h.instanceId,8))
    assert initial.scores()==(0,0) and len(initial.hand)==2
    assert after.scores()==(16,0) and not after.hand
    assert not board.getCardInstanceList(5,0) and u.inList==1 and h.inList==1


def test_muster_consumes_every_hand_copy_and_own_deck_copy_once(board):
    a=card(board,4,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_SummonClones,))
    a.templateRef.summonFlags=[a.templateId]
    b=board.spawnCardInstance(a.templateId,0,1);b.inList,b.listsPlayer=1,0
    board.getCardInstanceList(1,0).append(b)
    board.playerDeckDefinitions[0].cardIndicesInDeck=[a.templateId,a.templateId]
    initial=capture(board);after=initial.apply(Action(a.instanceId,5))
    assert after.scores()==(16,0) and not after.hand
    assert len(after.board[0,5])==4 and after.counts[a.templateId]==0
    assert len(initial.hand)==2 and initial.counts[a.templateId]==2


def test_scorch_removes_equal_maxima_both_sides_but_not_heroes(board):
    a=unit(board,8,5);b=card(board,8,5,C.CardType_Creature|C.CardType_Melee,player=1)
    unit(board,15,5,hero=True)
    scorch=card(board,0,1,C.CardType_Spell|C.CardType_Global_Effect,(C.CardEffect_Scorch,))
    after=capture(board).apply(Action(scorch.instanceId))
    assert after.scores()==(15,0)
    assert a.instanceId in after.grave[0] and b.instanceId in after.grave[1]


def test_decoy_recovery_drops_bond_on_remaining_partner(board):
    a=card(board,4,5,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_SameTypeMorale,))
    b=board.spawnCardInstance(a.templateId,0,5);b.inList,b.listsPlayer=5,0
    board.getCardInstanceList(5,0).append(b)
    a.templateRef.summonFlags=[a.templateId]
    a.effectedByCardsRefList=[b];b.effectedByCardsRefList=[a]
    decoy=card(board,0,1,C.CardType_Spell,(C.CardEffect_UnsummonDummy,))
    initial=capture(board);after=initial.apply(Action(decoy.instanceId,target=a.instanceId))
    assert initial.scores()==(16,0) and after.scores()==(4,0)
    assert a.instanceId in after.hand and not after.cards[a.instanceId].applied
    assert a.effectedByCardsRefList==[b] and b.effectedByCardsRefList==[a]


def test_repeated_weather_is_discarded_and_clear_sky_restores_ordinary_units(board):
    a=unit(board,8,5)
    old=card(board,0,9,C.CardType_Weather,(C.CardEffect_Melee,),player=-1)
    old.owningPlayer=0;a.effectedByCardsRefList=[old]
    board.cardEffectManager.getEffectList(5,0).append(old)
    again=card(board,0,1,C.CardType_Weather,(C.CardEffect_Melee,))
    clear=card(board,0,1,C.CardType_Weather,(C.CardEffect_ClearSky,))
    first=capture(board).apply(Action(again.instanceId,9))
    assert first.scores()==(1,0) and first.board[-1,9]==(old.instanceId,)
    assert again.instanceId in first.grave[0]
    second=first.apply(Action(clear.instanceId,9))
    assert second.scores()==(8,0) and not second.board[-1,9]


def test_capture_never_reads_opponent_hand_or_deck_order(board,monkeypatch):
    unit(board,5,5)
    getter=board.getCardInstanceList
    def guarded(row,player):
        if row==1 and player==1:raise AssertionError('opponent hand read')
        return getter(row,player)
    monkeypatch.setattr(board,'getCardInstanceList',guarded)
    class HiddenDeck:
        def __getattr__(self,name):raise AssertionError('opponent deck read')
    board.playerDeckDefinitions[1]=HiddenDeck()
    initial=capture(board)
    assert initial.scores()==(5,0)
