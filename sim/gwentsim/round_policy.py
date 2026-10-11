"""Experimental pass overlay. No hidden hand, deck order or policy RNG input.

Cached gains are optimistic, non-additive vanilla estimates, not legal rollouts.
This first version only replaces a vanilla action with PASS; tactical play remains
vanilla. Thresholds below are provisional design parameters, not difficulty levels.
"""
from dataclasses import dataclass
from math import inf


@dataclass(frozen=True)
class HandEstimate:
    gain: float
    reserve_value: float


@dataclass(frozen=True)
class RoundObservation:
    round_index: int
    own_losses: int
    opponent_losses: int
    score: int
    opponent_score: int
    wins_ties: bool
    opponent_passed: bool
    opponent_hand_count: int
    hand: tuple[HandEstimate, ...]
    resource_action: bool = False
    leader_available: bool = False


@dataclass(frozen=True)
class PassDecision:
    override: bool
    reason: str
    estimated_chase_cards: float = 0
    estimated_reserve_fraction: float = 1


def decide_pass(state: RoundObservation) -> PassDecision:
    """Keep vanilla unless a public-state conservation condition is met.

    Tied rounds lose a life on both sides. A win already secured against a passed
    opponent needs no further spending. A round that can end the match against us
    is never conceded by this overlay. Spies/Decoy and other resource actions are
    left to vanilla; their immediate score change is not their match value.
    """
    gap = state.opponent_score - state.score + (0 if state.wins_ties else 1)
    if state.opponent_passed and gap <= 0:
        if state.resource_action and not state.opponent_losses:
            return PassDecision(False, 'build_resources_before_next_round')
        return PassDecision(True, 'secured_round')
    if state.own_losses:
        return PassDecision(False, 'critical_round')
    if state.round_index != 1 or state.opponent_losses != 1 or gap <= 0:
        return PassDecision(False, 'retain_tactical_policy')
    if state.resource_action:
        return PassDecision(False, 'resource_action')
    if state.leader_available:
        return PassDecision(False, 'leader_not_evaluated')

    ranked = sorted(state.hand, key=lambda card: card.gain, reverse=True)
    total_reserve = sum(card.reserve_value for card in ranked)
    if not total_reserve:
        return PassDecision(False, 'special_only_hand_not_evaluated')
    remaining_reserve = total_reserve
    gain = 0
    chase_cards = inf
    for count, card in enumerate(ranked, 1):
        if card.gain <= 0:
            break
        gain += card.gain
        remaining_reserve -= card.reserve_value
        if gain >= gap:
            chase_cards = count
            break
    fraction = remaining_reserve / total_reserve if total_reserve else 0
    if chase_cards == inf:
        return PassDecision(True, 'no_estimated_catchup', chase_cards, fraction)
    # Once the opponent passes, an attainable second-round win ends the match.
    if state.opponent_passed or chase_cards <= 1:
        return PassDecision(False, 'affordable_finish', chase_cards, fraction)
    remaining_count = len(state.hand) - chase_cards
    if fraction < 0.5 and remaining_count < state.opponent_hand_count:
        return PassDecision(True, 'preserve_round_three', chase_cards, fraction)
    return PassDecision(False, 'pressure_with_reserve', chase_cards, fraction)
