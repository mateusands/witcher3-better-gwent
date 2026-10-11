"""Learned Afterstate Evaluator for Experimental V8 Decision Search.

Provides calibrated probability predictions for non-terminal afterstates.
STRICTLY preserves exact terminal outcomes (1.0, 0.0, 0.5) to avoid
probabilistic noise on mathematically determined positions.
"""
import json
import math
from pathlib import Path
from typing import Tuple, List

from . import constants as C
from .position import Position
from .afterstate_features import extract_features

ROOT = Path(__file__).resolve().parents[2]
WEIGHTS_PATH = ROOT / 'sim/gwentsim/learned_evaluator_weights.json'

_LOADED = False
_WEIGHTS: List[float] = []
_BIAS: float = 0.0
_CALIB_A: float = 1.0
_CALIB_B: float = 0.0


def _load_weights():
    global _LOADED, _WEIGHTS, _BIAS, _CALIB_A, _CALIB_B
    if _LOADED:
        return
    if not WEIGHTS_PATH.exists():
        raise FileNotFoundError(f"Learned weights file not found: {WEIGHTS_PATH}")
    with open(WEIGHTS_PATH, 'r') as f:
        data = json.load(f)
    _WEIGHTS = data['weights']
    _BIAS = float(data['bias'])
    _CALIB_A = float(data['calib_a'])
    _CALIB_B = float(data['calib_b'])
    _LOADED = True


def predict_win_probability(position: Position, context) -> float:
    """Predict calibrated win probability for non-terminal afterstate."""
    _load_weights()
    features = extract_features(position, context)
    z = sum(w * x for w, x in zip(_WEIGHTS, features)) + _BIAS
    calibrated_z = z * _CALIB_A + _CALIB_B
    clamped = max(-30.0, min(30.0, calibrated_z))
    return 1.0 / (1.0 + math.exp(-clamped))


def evaluate_afterstate_utility(position: Position, context, passing: bool = False) -> float:
    """Evaluates afterstate with strict terminal guards and calibrated utility.

    Terminal Guards:
    - Match already secured on pass: return 1.0
    - Decisive round with opponent passed: return exact 1.0 (win), 0.0 (loss), 0.5 (draw)
    - Non-terminal state: returns calibrated win probability from the learned model.
    """
    own = position.player
    other = 1 - own
    scores = position.scores()
    gap = scores[own] - scores[other]

    tied_match_win = (
        gap == 0 and context.opponent_losses >= 1 and context.own_losses == 0 and
        not (context.opponent_faction == C.FactionId_Nilfgaard and context.own_faction != context.opponent_faction)
    )
    wins = gap >= 0 if context.wins_ties else gap > 0

    # 1. Deterministic Match Win on Opponent Pass
    if context.opponent_passed and tied_match_win:
        return 1.0

    # 2. Final/Decisive Round (Round 3 or both on 1 loss)
    is_final_round = (context.opponent_losses >= 1 and context.own_losses >= 1) or context.round_index == 2
    if is_final_round:
        if context.opponent_passed:
            if gap == 0:
                if context.own_faction == context.opponent_faction or C.FactionId_Nilfgaard not in (context.own_faction, context.opponent_faction):
                    return 0.5
                return 1.0 if context.wins_ties else 0.0
            return 1.0 if wins else 0.0

    # 3. Opponent passed in earlier round
    if context.opponent_passed and wins:
        # We secured the round while opponent passed
        # Evaluate continuation probability with round secured
        pass

    # 4. Non-terminal: Calibrated learned probability
    prob = predict_win_probability(position, context)
    return prob
