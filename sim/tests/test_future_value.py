"""Designer scenarios distinguishing current board gain from future round potential."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gwentsim.future_value import ReserveCard, supported_reserve_power, reserve_marginals


def test_spent_board_partner_is_not_counted_in_next_round_reserve():
    bond=ReserveCard(1,160,4,(0,),bond=True,bond_targets=(160,))
    plain=ReserveCard(2,100,5,(1,))
    assert reserve_marginals((bond,plain))=={1:4,2:5}


def test_two_unplayed_bond_units_preserve_their_future_combination():
    cards=tuple(ReserveCard(i,160,4,(0,),bond=True,bond_targets=(160,)) for i in (1,2))
    assert supported_reserve_power(cards)==16
    assert reserve_marginals(cards)=={1:12,2:12}


def test_future_horn_value_includes_unplayed_units_but_not_heroes():
    cards=(ReserveCard(1,1,0,(0,1,2),horn=True),ReserveCard(2,20,8,(0,)),ReserveCard(3,30,15,(0,),hero=True))
    assert supported_reserve_power(cards)==31
    assert reserve_marginals(cards)[1]==8


def test_agile_assignment_and_morale_choose_best_future_row():
    cards=(ReserveCard(1,10,8,(0,1)),ReserveCard(2,11,2,(1,),morale=True),ReserveCard(3,12,5,(1,)))
    assert supported_reserve_power(cards)==17


def test_second_horn_does_not_double_same_row_and_unsupported_special_retains_value():
    cards=(ReserveCard(1,1,0,(0,),horn=True),ReserveCard(2,1,0,(0,),horn=True),ReserveCard(3,20,8,(0,)),
           ReserveCard(4,30,0,(),unsupported_value=6))
    assert supported_reserve_power(cards)==22
    assert reserve_marginals(cards)[1]==0
    assert reserve_marginals(cards)[4]==6


def test_muster_future_horn_includes_own_deck_copies_once_per_group():
    copies=(ReserveCard(-1,100,4,(0,)),ReserveCard(-2,100,4,(0,)))
    trigger=ReserveCard(1,100,4,(0,),summons=copies)
    h=ReserveCard(2,1,0,(0,),horn=True)
    assert supported_reserve_power((trigger,h))==24
    assert reserve_marginals((trigger,h))[h.key]==12
    assert reserve_marginals((trigger,h))[trigger.key]==24
    second=ReserveCard(3,100,4,(0,),summons=copies)
    assert supported_reserve_power((trigger,second,h))==32
    assert reserve_marginals((trigger,second,h))[trigger.key]==8
