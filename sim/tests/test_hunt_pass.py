"""The blunder hunter's "pass" option really passes (sim/blunder_hunter.py).

Spec: an option the hunter labels "pass" must make the NPC pass the round. A decision the
policy leaves to the native AI is a different option ("native move"), never mixed up with a pass.

Given a recorded player-deck match and the NPC's first decision of round 1,
when the hunter replays it with the pass option forced,
then the NPC makes no further decision in round 1.
"""
import blunder_hunter
import evaluate_pool
import gwentsim.response_v8 as v8


def spec_for(pair, seed):
    _, npc_seat = evaluate_pool.player_seats(pair, False)
    return dict(source='player', pair=pair, seed=seed, swap=False, seat=npc_seat, policy='response-v8',
                profile='hard', npc_decks='balanced')


def test_forced_pass_ends_the_round_for_the_npc():
    saved = v8.VARIANT, v8.NPC_SEAT
    v8.VARIANT = frozenset({'player-mulligan', 'base-mulligan'})
    try:
        spec = spec_for(0, 1401)
        _, log = blunder_hunter.play(spec)
        assert log[0]['context'].round_index == 0 and log[1]['context'].round_index == 0
        _, forced = blunder_hunter.play(spec, (0, blunder_hunter.PASS))
        assert all(entry['context'].round_index > 0 for entry in forced[1:])
    finally:
        v8.VARIANT, v8.NPC_SEAT = saved


def test_pass_and_native_move_are_different_options():
    assert blunder_hunter.describe(None, blunder_hunter.PASS) == 'pass'
    assert blunder_hunter.describe(None, None) == 'native move'
