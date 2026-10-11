"""Tunable weights of the V8 utility (Phase 3: parameter tuning by self-play).

DEFAULTS are the shipped values, mirrored in mod/v8/as3 (GwaiV8Sequence.as, GwaiV8Position.as);
with them every decision is identical to the untuned policy. SEAT_PARAMS lets an experiment
give one seat different weights (e.g. only the NPC side against a player-style deck); the
V8 controller selects its seat's weights for the duration of each search.
"""
DEFAULTS = dict(
    reserve_weight=0.25,   # remaining resources vs the opponent's, while the round is open
    scale_base=4.0,        # uncertainty scale of the round prospect: base ...
    scale_slope=2.0,       # ... plus slope * sqrt(opponent hand count)
    leader_credit=3.0,     # points credited to an unused opponent leader
    future_edge=1.0,       # opponent average card as the margin for the next round
    pass_risk=1.0,         # weight of the opponent's remaining strength when we pass ahead
    draw_weight=1.0,       # value of cards still to be drawn (spies) in the own reserve
)
ACTIVE = DEFAULTS
SEAT_PARAMS = {}


def use_seat(seat):
    global ACTIVE
    ACTIVE = dict(DEFAULTS, **SEAT_PARAMS[seat]) if seat in SEAT_PARAMS else DEFAULTS


def reset():
    global ACTIVE
    ACTIVE = DEFAULTS
