"""Original full-match public transition scenarios for the ISMCTS adapter."""
from dataclasses import replace
from random import Random
import pytest
from test_horn_evaluation import board,card,unit
from test_position import capture
from test_sequence_search import context
from gwentsim import constants as C
from gwentsim.position import Action,UnsupportedPosition
from gwentsim.ismcts_gwent import GwentState,Determinization,move_key,clear_round,recover_skellige

MELEE=C.CardType_Creature|C.CardType_Melee


def state_from_board(board,ctx=None):
    own=capture(board);other=own.clone();other.player=1
    other.hand=tuple(u.instanceId for u in board.getCardInstanceList(1,1))
    # Fixture-only construction is deliberately separate from the fair production
    # determinizer; these cards are synthetic test inputs, never live hidden data.
    for u in board.getCardInstanceList(1,1):
        t=own.catalog[u.templateId]
        own.cards[u.instanceId]=replace(t,key=u.instanceId,owner=1,player=1,row=1)
    other.cards=dict(own.cards);other.counts={}
    return GwentState.from_sample(Determinization(0,(own,other),'fixture',0),ctx or context(round_index=0,opponent_losses=0,opponent_passed=False))


def test_alternating_play_preserves_both_private_hands_and_shared_effects(board):
    a=card(board,4,1,MELEE);b=card(board,6,1,MELEE,player=1)
    spare=card(board,1,1,MELEE);remote=card(board,1,1,MELEE,player=1)
    state=state_from_board(board)
    after=state.next_state(Action(a.instanceId,5),Random(162))
    assert after.to_move==1 and after.positions[0].hand==(spare.instanceId,)
    assert after.positions[1].hand==(b.instanceId,remote.instanceId)
    final=after.next_state(Action(b.instanceId,5),Random(162))
    assert final.positions[0].scores()==final.positions[1].scores()==(4,6)
    assert final.positions[1].hand==(remote.instanceId,) and state.positions[0].hand==(a.instanceId,spare.instanceId)


def test_missing_actions_are_a_boundary_even_with_other_supported_choices(board):
    card(board,4,1,MELEE)
    card(board,0,1,MELEE,(C.CardEffect_SuicideSummon,))
    state=state_from_board(board)
    assert len(state.legal_actions())>1
    assert state.unresolved_choices()==('unsupported_hand',)
    assert state.positions[0].hand==state_from_board(board).positions[0].hand


def test_historical_warning_is_not_a_current_missing_action(board):
    card(board,4,1,MELEE)
    state=replace(state_from_board(board),limitations=('unsupported_hand',))
    assert not state.unresolved_choices()
    assert 'unsupported_hand' in state.limitations


def test_actual_terminal_result_does_not_require_modeling_unused_cards(board):
    card(board,0,1,MELEE,(C.CardEffect_SuicideSummon,))
    state=replace(state_from_board(board),winner=0)
    assert not state.unresolved_choices() and state.terminal_reward(0)==1


def test_two_zero_finishes_but_one_each_reaches_third_round(board):
    unit(board,5,5)
    card(board,1,1,MELEE);card(board,1,1,MELEE,player=1)
    state=state_from_board(board);r=Random(162)
    next_round=state.next_state(None,r).next_state(None,r)
    assert next_round.round_index==1 and next_round.losses==(0,1) and next_round.to_move==0
    assert not next_round.positions[0].board[0,5]
    own=next_round.positions[0].clone()
    original=state.positions[0].cards[next(iter(state.positions[0].board[0,5]))]
    own.cards[original.key]=replace(original,row=5,player=0,applied=())
    own.board[0,5]=(original.key,)
    from gwentsim.ismcts_gwent import synchronize
    next_round.positions=synchronize(next_round.positions,0,own)
    result=next_round.next_state(None,r).next_state(None,r)
    assert result.winner==0 and result.terminal_reward(0)==1
    card(board,8,5,MELEE,player=1)
    split=state_from_board(board,context(round_index=1,own_losses=0,opponent_losses=1,opponent_passed=False))
    third=split.next_state(None,r).next_state(None,r)
    assert third.round_index==2 and third.losses==(1,1) and third.winner is None


def test_ordinary_draw_removes_both_lives_and_nilfgaard_wins_ties(board):
    unit(board,5,5);card(board,5,5,MELEE,player=1)
    card(board,1,1,MELEE);card(board,1,1,MELEE,player=1)
    state=state_from_board(board,context(round_index=0,opponent_losses=0,opponent_passed=False,
        opponent_faction=C.FactionId_Northern_Kingdom));r=Random(162)
    after=state.next_state(None,r).next_state(None,r)
    assert after.losses==(1,1) and after.round_index==1
    final=after.next_state(None,r).next_state(None,r)
    assert final.winner==-1 and final.terminal_reward(0)==0.5
    nilf=replace(state,factions=(C.FactionId_Nilfgaard,C.FactionId_Northern_Kingdom))
    after=nilf.next_state(None,r).next_state(None,r)
    assert after.losses==(0,1) and after.to_move==0


def test_northern_draw_and_monster_keep_use_only_local_random_samples(board):
    a=unit(board,5,5);hero=unit(board,20,5,hero=True)
    card(board,8,5,MELEE,player=1)
    spare=card(board,4,1,MELEE)
    state=state_from_board(board)
    own=state.positions[0].clone();own.counts={spare.templateId:1}
    state=replace(state,positions=(own,state.positions[1]),factions=(C.FactionId_Northern_Kingdom,C.FactionId_No_Mans_Land))
    after=state.next_state(None,Random(162)).next_state(None,Random(162))
    assert len(after.positions[0].hand)==2 and after.positions[0].counts[spare.templateId]==0
    assert len(after.positions[1].board[1,5])==1
    monsters=clear_round(state.positions,(C.FactionId_No_Mans_Land,C.FactionId_Northern_Kingdom),Random(162))
    assert monsters[0].board[0,5]==(a.instanceId,) and hero.instanceId in monsters[0].grave[0]


def test_clear_banishes_summoned_card_and_rejects_death_effect(board):
    a=unit(board,5,5);a.BanishInsteadOfGraveyard=True
    state=state_from_board(board)
    cleared=clear_round(state.positions,(0,0),Random(162))
    assert not cleared[0].board[0,5] and a.instanceId not in cleared[0].grave[0]
    card(board,0,5,MELEE,(C.CardEffect_SuicideSummon,))
    with pytest.raises(UnsupportedPosition,match='death'):
        clear_round(state_from_board(board).positions,(0,0),Random(162))


def test_skellige_recovers_two_nonheroes_from_public_grave(board):
    a=card(board,4,2,MELEE);b=card(board,7,2,MELEE);h=card(board,10,2,MELEE|C.CardType_Hero)
    state=state_from_board(board)
    after=recover_skellige(state.positions,0,Random(162))
    assert after[0].scores()==(11,0) and after[0].grave[0]==(h.instanceId,)
    assert set(after[0].board[0,5])=={a.instanceId,b.instanceId}
    assert after[0].board==after[1].board and not state.positions[0].board[0,5]


def test_move_keys_and_information_keys_ignore_sample_instance_ids(board):
    a=card(board,4,1,MELEE,player=1)
    state=state_from_board(board);other=state.positions[1]
    key=move_key(other,Action(a.instanceId,5))
    clone=other.clone();new=-999
    clone.cards[new]=replace(clone.cards.pop(a.instanceId),key=new);clone.hand=(new,)
    assert move_key(clone,Action(new,5))==key
    hidden=replace(state,positions=(state.positions[0],clone))
    assert hidden.information_key(0)==state.information_key(0)
    own=state.positions[0].clone();own.counts={a.templateId:1}
    assert replace(state,positions=(own,clone)).information_key(0)!=state.information_key(0)


def test_leader_generated_horn_goes_to_grave_like_native_apply_horn(board):
    king=card(board,0,10,0,(C.CardEffect_Melee_Horn,))
    state=state_from_board(board);own=state.positions[0].clone()
    own.cards[king.instanceId]=replace(own.catalog[king.templateId],key=king.instanceId,row=10)
    own.leaders[0]=king.instanceId;own.leader_ready[0]=True
    after=own.apply(Action(king.instanceId,8));generated=after.board[0,8][0]
    assert not after.cards[generated].banished_on_clear
    cleared=clear_round((after,state.positions[1]),(0,0),Random(162))
    assert generated in cleared[0].grave[0]


def test_next_round_does_not_reactivate_empty_hand_only_for_unused_leader(board):
    king=card(board,0,10,0,(C.CardEffect_Melee_Horn,));unit(board,10,5)
    card(board,4,1,MELEE,player=1)
    state=state_from_board(board);own=state.positions[0].clone()
    own.cards[king.instanceId]=replace(own.catalog[king.templateId],key=king.instanceId,row=10)
    own.leaders[0]=king.instanceId;own.leader_ready[0]=True
    state.positions=(own,state.positions[1])
    after=state.next_state(None,Random(162)).next_state(None,Random(162))
    assert after.round_index==1 and after.passed==(True,False) and after.to_move==1
    assert after.positions[0].leader_ready[0] and not after.positions[0].hand


def test_empty_hands_force_next_round_and_last_card_finishes_immediately(board):
    unit(board,10,5)
    state=state_from_board(board)
    after=state.next_state(None,Random(162)).next_state(None,Random(162))
    assert after.round_index==1 and after.winner==0
    a=card(board,4,1,MELEE)
    final=state_from_board(board,context(round_index=2,own_losses=1))
    played=final.next_state(Action(a.instanceId,5),Random(162))
    assert played.winner==0 and played.terminal_reward(0)==1


def test_open_search_excludes_self_only_scorch_but_keeps_medic_setup(board):
    from gwentsim.ismcts_gwent import self_scorch_without_recovery
    victim=unit(board,4,5)
    scorch=card(board,0,1,C.CardType_Spell|C.CardType_Global_Effect,(C.CardEffect_Scorch,))
    card(board,6,1,MELEE)
    state=state_from_board(board);own=state.positions[0]
    action=Action(scorch.instanceId);after=own.apply(action)
    assert self_scorch_without_recovery(own,after,action,state.context(0))
    assert action not in state.legal_actions().values()
    card(board,5,1,MELEE,(C.CardEffect_Nurse,))
    recovery=state_from_board(board);own=recovery.positions[0]
    assert not self_scorch_without_recovery(own,own.apply(action),action,recovery.context(0))
    assert action in recovery.legal_actions().values()


def test_scorch_destroying_enemy_and_future_skellige_recovery_stay_searchable(board):
    from gwentsim.ismcts_gwent import self_scorch_without_recovery
    unit(board,8,5);card(board,8,5,MELEE,player=1)
    scorch=card(board,0,1,C.CardType_Spell|C.CardType_Global_Effect,(C.CardEffect_Scorch,))
    state=state_from_board(board);action=Action(scorch.instanceId);own=state.positions[0]
    assert not self_scorch_without_recovery(own,own.apply(action),action,state.context(0))
    assert action in state.legal_actions().values()
    own=own.clone();own.board[1,5]=()
    skellige=replace(state.context(0),own_faction=C.FactionId_Skellige)
    assert not self_scorch_without_recovery(own,own.apply(action),action,skellige)


def test_decoy_can_reuse_board_medic_after_self_scorch_setup(board):
    from gwentsim.ismcts_gwent import self_scorch_without_recovery
    villain=card(board,10,5,MELEE,(C.CardEffect_MeleeScorch,))
    medic=card(board,5,5,MELEE,(C.CardEffect_Nurse,))
    card(board,6,5,MELEE,player=1);card(board,6,5,MELEE,player=1)
    scorch=card(board,0,1,C.CardType_Spell|C.CardType_Global_Effect,(C.CardEffect_Scorch,))
    decoy=card(board,0,1,C.CardType_Spell,(C.CardEffect_UnsummonDummy,))
    state=state_from_board(board);own=state.positions[0];action=Action(scorch.instanceId)
    after=own.apply(action)
    assert not self_scorch_without_recovery(own,after,action,state.context(0))
    after=after.apply(Action(decoy.instanceId,target=medic.instanceId))
    after=after.apply(Action(medic.instanceId,5,chain=((villain.instanceId,5),)))
    assert after.scores()==(15,0)


def test_observation_key_ignores_hypothetical_hidden_templates_and_counts(board):
    a=card(board,4,1,MELEE,player=1);b=card(board,9,1,MELEE,player=1)
    state=state_from_board(board);other=state.positions[1].clone()
    other.cards[a.instanceId]=replace(other.cards[a.instanceId],template=b.templateId,power=9)
    other.counts={b.templateId:17}
    changed=replace(state,positions=(state.positions[0],other))
    assert changed.information_key(0)==state.information_key(0)
    assert changed.information_key(1)!=state.information_key(1)
