"""The blunder hunter replays a player-deck match exactly as the benchmark plays it (same scene)."""
import blunder_hunter
import evaluate_pool
import gwentsim.response_v8 as v8


def test_hunt_matches_benchmark_scene():
    saved = v8.VARIANT, v8.NPC_SEAT
    v8.VARIANT = frozenset({'player-mulligan', 'base-mulligan'})
    try:
        swap = False
        for pair, seed in ((0, 1401), (1, 1402), (2, 1403), (3, 1404)):
            _, npc_seat = evaluate_pool.player_seats(pair, swap)
            bench = evaluate_pool.run_player(pair, seed, swap, 'response-v8', 2, 'balanced')
            spec = dict(source='player', pair=pair, seed=seed, swap=swap, seat=npc_seat, policy='response-v8',
                        profile='hard', npc_decks='balanced')
            hunted, log = blunder_hunter.play(spec)
            assert log
            assert hunted['winner'] == bench['winner'], (pair, seed)
    finally:
        v8.VARIANT, v8.NPC_SEAT = saved
