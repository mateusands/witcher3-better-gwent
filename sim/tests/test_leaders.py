"""Leader abilities in the public-position model: legality, transitions and reserve."""
import pytest
from dataclasses import replace
from test_horn_evaluation import board,card,unit
from test_position import capture
from gwentsim import constants as C
from gwentsim.position import Action,Card

MELEE=C.CardType_Creature|C.CardType_Melee


LEADERS={}


def leader(board,effect,player=0):
    king=card(board,0,10,0,(effect,),player)
    LEADERS[id(board)]=king
    return king


def ready(state,own=True,other=False):
    # The test board holds plain instances; register the leader as from_manager would.
    king=LEADERS.get(id(CURRENT[0]))
    cards=dict(state.cards)
    if king is not None:
        t=king.templateRef
        cards[king.instanceId]=Card(king.instanceId,king.templateId,0,0,tuple(t.effectFlags),(),0,0,10)
    return replace(state,cards=cards,leaders={0:king.instanceId if king else None,1:None},
                   leader_ready={0:own,1:other})


CURRENT=[None]


@pytest.fixture(autouse=True)
def _current(board):
    CURRENT[0]=board


def test_leader_horn_doubles_its_row_and_needs_a_free_modifier_slot(board):
    king=leader(board,C.CardEffect_Melee_Horn);unit(board,4,5);unit(board,10,5,hero=True)
    state=ready(capture(board))
    assert state.actions()==(Action(king.instanceId,8),)
    after=state.apply(Action(king.instanceId,8))
    assert after.scores()==(18,0) and not after.leader_ready[0] and not after.leader_actions()
    assert state.leader_ready[0] and state.scores()==(14,0)


def test_leader_row_scorch_needs_ten_power_and_spares_heroes(board):
    king=leader(board,C.CardEffect_Siege_Scorch)
    siege=C.CardType_Creature|C.CardType_Siege
    card(board,5,3,siege,player=1);card(board,4,3,siege,player=1)
    state=ready(capture(board))
    assert not state.leader_actions()
    card(board,6,3,siege|C.CardType_Hero,player=1)
    state=ready(capture(board))
    assert state.apply(Action(king.instanceId)).scores()==(0,10)


def test_resurrection_moves_a_graveyard_unit_to_hand_and_enemy_variant_steals(board):
    own=leader(board,C.CardEffect_Resurect)
    mine=card(board,7,2,MELEE);card(board,9,2,MELEE|C.CardType_Hero)
    theirs=card(board,8,2,MELEE,player=1)
    state=ready(capture(board))
    assert {a.target for a in state.leader_actions()}=={mine.instanceId}
    after=state.apply(Action(own.instanceId,target=mine.instanceId))
    assert mine.instanceId in after.hand and mine.instanceId not in after.grave[0]
    assert after.apply(Action(mine.instanceId,5)).scores()==(7,0)
    state.cards[own.instanceId]=replace(state.cards[own.instanceId],effects=(C.CardEffect_Resurect_Enemy,))
    stolen=state.apply(Action(own.instanceId,target=theirs.instanceId))
    assert theirs.instanceId in stolen.hand and theirs.instanceId not in stolen.grave[1]


def test_weather_pick_uses_own_deck_counts_and_plays_the_card(board):
    king=leader(board,C.CardEffect_Pick_Frost)
    frost=card(board,0,1,C.CardType_Weather,(C.CardEffect_Melee,),player=1)  # template only
    unit(board,6,5);card(board,8,5,MELEE,player=1)
    state=capture(board);state.counts={frost.templateId:1};state=ready(state)
    after=state.apply(Action(king.instanceId,9,target=frost.templateId))
    assert after.scores()==(1,1) and after.counts[frost.templateId]==0


def test_choose_weather_offers_each_template_but_not_clear_sky(board):
    king=leader(board,C.CardEffect_Pick_Weather)
    fog=card(board,0,1,C.CardType_Weather,(C.CardEffect_Ranged,),player=1)
    clear=card(board,0,1,C.CardType_Weather,(C.CardEffect_ClearSky,),player=1)
    state=capture(board);state.counts={fog.templateId:1,clear.templateId:2};state=ready(state)
    assert state.leader_actions()==(Action(king.instanceId,9,target=fog.templateId),)


def test_graveyard_shuffle_returns_own_units_to_deck_counts(board):
    king=leader(board,C.CardEffect_GraveyardShuffle)
    a=card(board,3,2,MELEE);card(board,5,2,MELEE|C.CardType_Hero);b=card(board,4,2,MELEE,player=1)
    after=ready(capture(board)).apply(Action(king.instanceId))
    assert after.counts.get(a.templateId)==1 and b.templateId not in after.counts
    assert a.instanceId not in after.grave[0] and b.instanceId not in after.grave[1] and len(after.grave[0])==1


def test_passive_and_used_leaders_have_no_action_and_do_not_block(board):
    leader(board,C.CardEffect_DoubleSpy);unit(board,4,5)
    state=ready(capture(board))
    assert not state.leader_actions() and not state.leader_unmodeled(0)
    used=ready(capture(board),own=False)
    assert not used.leader_actions()


def test_kept_horn_leader_adds_reserve_value(board):
    leader(board,C.CardEffect_Melee_Horn)
    card(board,6,1,MELEE)
    state=capture(board)
    assert ready(state).reserve()==12 and ready(state,own=False).reserve()==6


def test_reserve_cache_key_tracks_graveyard_for_recovery(board):
    card(board,5,1,MELEE,(C.CardEffect_Nurse,));card(board,7,2,MELEE)
    state=capture(board);emptied=state.clone();emptied.grave={0:(),1:()}
    assert state.reserve_key()!=emptied.reserve_key() and state.reserve()!=emptied.reserve()
