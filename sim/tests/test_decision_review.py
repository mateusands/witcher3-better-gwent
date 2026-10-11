"""Review alerts respect match survival and expose needless spending without omniscience."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from review_decisions import flag_decision


def state(**changes):
    result = dict(transaction={'source': [4, 19]}, duplicateWeather=False, estimatedGain=10,
                  opponentPassed=False, score=20, opponentScore=30, roundIndex=1,
                  roundWins=1, opponentRoundWins=0, spendsHandCard=True, handCount=2)
    result.update(changes)
    return result


def test_reserve_alert_requires_a_round_the_ai_can_afford_to_lose():
    assert 'round_two_reserve_at_risk' in flag_decision(state())
    assert 'round_two_reserve_at_risk' not in flag_decision(state(roundWins=0, opponentRoundWins=1))
    assert 'round_two_reserve_at_risk' not in flag_decision(state(roundIndex=2))


def test_duplicate_weather_and_last_card_are_separate_concerns():
    flags = flag_decision(state(duplicateWeather=True, estimatedGain=0, handCount=1))
    assert 'duplicate_weather_without_estimated_gain' in flags
    assert 'last_hand_card_without_estimated_gap_reduction' in flags
    assert 'duplicate_weather_without_estimated_gain' not in flag_decision(state(duplicateWeather=True, estimatedGain=12))


def test_passing_and_leader_use_do_not_count_as_hand_card_spending():
    assert flag_decision(state(transaction=None)) == []
    assert 'round_two_reserve_at_risk' not in flag_decision(state(spendsHandCard=False))


def test_win_already_secured_against_passed_opponent_is_flagged():
    assert 'spending_after_opponent_passed_while_ahead' in flag_decision(state(opponentPassed=True, score=40))
    assert 'spending_after_opponent_passed_while_ahead' not in flag_decision(state(opponentPassed=True, score=30))
