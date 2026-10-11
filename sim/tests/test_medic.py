"""Medic recovery in the public-position model: eligibility, chains, spies and reserve."""
from dataclasses import replace
from test_horn_evaluation import board,card,unit
from test_position import capture
from gwentsim import constants as C
from gwentsim.position import Action

MELEE=C.CardType_Creature|C.CardType_Melee
NURSE=(C.CardEffect_Nurse,)


def grave(board,power,flags=MELEE,effects=(),player=0):
    return card(board,power,2,flags,effects,player)


def test_medic_choices_exclude_heroes_and_non_units_and_follow_chains(board):
    medic=card(board,5,1,C.CardType_Creature|C.CardType_Siege,NURSE)
    weak=grave(board,3);strong=grave(board,7)
    grave(board,10,MELEE|C.CardType_Hero)
    grave(board,0,C.CardType_Weather|C.CardType_Melee,(C.CardEffect_Melee,))
    again=grave(board,2,C.CardType_Creature|C.CardType_Ranged,NURSE)
    state=capture(board)
    chains={a.chain for a in state.actions() if a.source==medic.instanceId}
    assert ((strong.instanceId,5),) in chains and ((weak.instanceId,5),) in chains
    assert ((again.instanceId,4),(strong.instanceId,5)) in chains
    assert all(len(chain)>=1 for chain in chains)
    after=state.apply(Action(medic.instanceId,3,chain=((again.instanceId,4),(strong.instanceId,5))))
    assert after.scores()==(14,0) and not after.hand
    assert after.grave[0]==tuple(k for k in state.grave[0] if k not in (again.instanceId,strong.instanceId))
    assert board.getCardInstanceList(3,0)==[] and strong.inList==2


def test_medic_without_eligible_target_is_a_plain_unit(board):
    medic=card(board,5,1,MELEE,NURSE)
    grave(board,10,MELEE|C.CardType_Hero)
    state=capture(board)
    assert [a.chain for a in state.actions()]==[()]
    assert state.apply(Action(medic.instanceId,5)).scores()==(5,0)


def test_recovered_spy_goes_to_the_opponent_and_draws_for_the_medic_owner(board):
    medic=card(board,5,1,MELEE,NURSE)
    spy=grave(board,4,MELEE|C.CardType_Spy,(C.CardEffect_Draw2,))
    board.playerDeckDefinitions[0].cardIndicesInDeck=[medic.templateId]*3
    after=capture(board).apply(Action(medic.instanceId,5,chain=((spy.instanceId,5),)))
    assert after.scores()==(5,4) and after.unknown_draws==2 and spy.instanceId in after.board[1,5]


def test_unsupported_recovered_effects_are_not_offered(board):
    medic=card(board,5,1,MELEE,NURSE)
    grave(board,6,MELEE,(C.CardEffect_Morph,))
    plain=grave(board,1)
    chains={a.chain for a in capture(board).actions()}
    assert chains=={((plain.instanceId,5),)}


def test_random_recovery_is_not_a_searchable_choice_except_for_heroes(board):
    medic=card(board,5,1,MELEE,NURSE);grave(board,3)
    hero=card(board,0,1,MELEE|C.CardType_Hero,NURSE)
    state=replace(capture(board),random_recovery=True)
    assert {a.source for a in state.actions()}=={hero.instanceId}


def test_reserve_values_post_clear_recovery_instead_of_a_flat_weight(board):
    card(board,5,1,MELEE,NURSE)
    grave(board,7);unit(board,9,5);unit(board,12,5,hero=True)
    grave(board,4,MELEE|C.CardType_Spy,(C.CardEffect_Draw2,))
    state=capture(board)
    # Medic 5 plus the strongest non-hero, non-spy unit cleared from the own board.
    assert state.reserve()==14
    assert replace(state,random_recovery=True).reserve()==max(5,state.weights.get(C.CardEffect_Nurse,0))


def test_reserve_takes_recoverable_medics_before_units(board):
    card(board,5,1,MELEE,NURSE)
    grave(board,2,MELEE,NURSE);grave(board,6);grave(board,3)
    assert capture(board).reserve()==5+2+6
