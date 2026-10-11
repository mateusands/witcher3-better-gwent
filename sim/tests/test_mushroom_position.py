"""Mushroom transforms instances without moving cards, inventing draws or effects."""
from dataclasses import replace
import pytest
from test_horn_evaluation import board,card,horn,unit
from test_position import capture
from gwentsim import constants as C
from gwentsim.position import Action,UnsupportedPosition
from mushroom_position import MushroomPosition


def projected(board):return MushroomPosition(**capture(board).__dict__)


def berserker(board,row=1,ranged=False,bond=False):
    flags=C.CardType_Creature|(C.CardType_Ranged if ranged else C.CardType_Melee)
    target=card(board,8 if bond else 14,2,flags,
        (C.CardEffect_SameTypeMorale if bond else C.CardEffect_ImproveNeighbours,))
    if bond:target.templateRef.summonFlags=[target.templateId]
    source=card(board,2,row,flags,(C.CardEffect_Morph,))
    source.templateRef.summonFlags=[target.templateId]
    return source,target


def mushroom(board,row=1,creature=False):
    flags=(C.CardType_Creature|C.CardType_Hero|C.CardType_Melee) if creature else C.CardType_Row_Modifier|C.CardType_SeigeRangedMelee
    return card(board,2 if creature else 0,row,flags,(C.CardEffect_Mushroom,))


@pytest.mark.parametrize('modifier_first',[False,True])
def test_transformation_preserves_instance_and_applies_transformed_morale(board,modifier_first):
    source,target=berserker(board);m=mushroom(board);other=unit(board,5,5)
    state=projected(board);before=state.clone()
    actions=[Action(m.instanceId,8),Action(source.instanceId,5)]
    if not modifier_first:actions.reverse()
    after=state.apply(actions[0]).apply(actions[1])
    changed=after.cards[source.instanceId]
    assert changed.template==target.templateId and changed.owner==0 and changed.row==5
    assert after.scores()==(20,0) and after.power(other.instanceId)==6
    assert source.instanceId not in after.grave[0]
    assert after.counts==state.counts and state==before
    assert source.templateId!=target.templateId  # Live native instance untouched.


def test_two_transformed_ranged_berserkers_form_a_real_bond(board):
    a,target=berserker(board,ranged=True,bond=True)
    b=board.spawnCardInstance(a.templateId,0,1);b.inList,b.listsPlayer=1,0
    board.getCardInstanceList(1,0).append(b)
    m=mushroom(board)
    after=projected(board).apply(Action(a.instanceId,4)).apply(Action(b.instanceId,4)).apply(Action(m.instanceId,7))
    assert after.scores()==(32,0)
    assert after.cards[a.instanceId].applied==(b.instanceId,)
    assert after.cards[b.instanceId].applied==(a.instanceId,)
    assert m.instanceId not in after.effects[0,4]


def test_mushroom_creature_can_share_horn_row_without_buffing_itself(board):
    source,target=berserker(board);m=mushroom(board,creature=True);h=horn(board)
    after=projected(board).apply(Action(h.instanceId,8)).apply(Action(source.instanceId,5)).apply(Action(m.instanceId,5))
    assert after.scores()==(30,0) and after.power(m.instanceId)==2


def test_modifier_slot_and_opposite_rows_are_respected(board):
    source,target=berserker(board);enemy,_=berserker(board,row=5)
    # Move the second source to the other side in the captured fixture.
    board.getCardInstanceList(5,0).remove(enemy);enemy.listsPlayer=enemy.owningPlayer=1
    board.getCardInstanceList(5,1).append(enemy)
    m=mushroom(board);h=horn(board)
    after=projected(board).apply(Action(source.instanceId,5)).apply(Action(m.instanceId,7))
    assert after.cards[source.instanceId].template==source.templateId
    assert after.cards[enemy.instanceId].template==enemy.templateId
    assert Action(h.instanceId,7) not in after.actions()


def test_weather_survives_transformation_and_duplicate_triggers_do_not_double_morale(board):
    source,target=berserker(board);m=mushroom(board);second=mushroom(board,creature=True)
    frost=card(board,0,1,C.CardType_Weather,(C.CardEffect_Melee,))
    other=unit(board,5,5)
    after=projected(board).apply(Action(frost.instanceId,9)).apply(Action(source.instanceId,5)).apply(Action(m.instanceId,8))
    assert after.power(source.instanceId)==1 and after.power(other.instanceId)==2
    following=after.apply(Action(second.instanceId,5))
    assert following.power(source.instanceId)==1 and following.power(other.instanceId)==2


def test_unmodeled_transformation_target_remains_explicitly_unsupported(board):
    source,target=berserker(board,row=5);target.templateRef.effectFlags=[C.CardEffect_SuicideSummon]
    m=mushroom(board)
    state=projected(board)
    assert not state.supported(state.cards[source.instanceId])
    with pytest.raises(UnsupportedPosition):state.apply(Action(m.instanceId,8))


def test_projection_capture_never_reads_enemy_hand_or_deck(board,monkeypatch):
    source,target=berserker(board);mushroom(board)
    getter=board.getCardInstanceList
    def guarded(row,side):
        if row==1 and side==1:raise AssertionError('enemy private hand read')
        return getter(row,side)
    monkeypatch.setattr(board,'getCardInstanceList',guarded)
    class HiddenDeck:
        def __getattr__(self,name):raise AssertionError('enemy private deck read')
    board.playerDeckDefinitions[1]=HiddenDeck()
    capture(board)  # Initializes native value defaults without exposing enemies.
    state=MushroomPosition.from_manager(board,0)
    assert state.supported(state.cards[source.instanceId])
