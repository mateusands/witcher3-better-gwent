"""NPC changes for the Original deck mode (proven in the Lab, 13 October 2026).

Spec (owner, 13 October 2026): two ideas passed three times on new matchups with the game's own
NPC decks (Original mode) and were worse or neutral on Adaptive and Strong, so the game uses them
only when the NPC decks option is Original:
- spy-first: outside the final round, while the opponent still plays, a spy in hand goes before
  a non-spy card (the cheapest spy);
- fusion20: the search's second ply keeps 20% of what it adds to a move's one-ply value (in that
  ply the search picks its next move per imagined hand, as if it knew the hand).
- The NPC decks option reaches the AI with the match settings ("npcdecks", 0 Original,
  1 Adaptive, 2 Strong); the context carries original_decks for the NPC side only (autoplay on
  the player's side is unchanged). Missing or another mode: unchanged.
- The AS3 port decides exactly as the Python reference, with and without the mode.

- The Lab plays the shipped AI too: a player-deck match with the Original NPC decks (or no deck
  mode) sets the switch for the NPC seat, so Original-mode tests start from the AI in the game.

Given a position, when the NPC decks are Original, then the NPC plays a spy first and the search
uses fusion20, in Python and AS3 alike; with Adaptive or Strong nothing changes.
"""
from dataclasses import replace
from pathlib import Path

from test_horn_evaluation import board, card  # noqa: F401  (board is a fixture)
from test_position import capture
from test_v8_npc_rules import ctx, decide, same, MELEE
from test_v8_as_response import compare as compare_response
from gwentsim import constants as C
from gwentsim.position import Action
from gwentsim.sequence_search import Context
from gwentsim import response_search
from gwentsim.options import Difficulty

ROOT = Path(__file__).resolve().parents[2]
SPY = C.CardType_Creature | C.CardType_Melee | C.CardType_Spy


def original(context):
    return replace(context, original_decks=True)


def spy_hand(board):
    unit = card(board, 8, 1, MELEE)
    spy = card(board, 2, 1, SPY, (C.CardEffect_Draw2,))
    card(board, 6, 5, MELEE, player=1)
    return unit, spy, capture(board)


def test_spy_first_only_with_original_decks(board, monkeypatch):
    unit, spy, position = spy_hand(board)
    move = Action(source=unit.instanceId, slot=5)
    shipped = decide(monkeypatch, position, ctx(), move)
    assert same(shipped, move)                                        # Adaptive / Strong: unchanged
    first = decide(monkeypatch, position, original(ctx()), move)
    assert first['reason'] == 'spy_first' and first['action']['source'] == spy.instanceId


def test_no_spy_first_in_the_final_round_or_after_a_pass(board, monkeypatch):
    unit, spy, position = spy_hand(board)
    move = Action(source=unit.instanceId, slot=5)
    assert same(decide(monkeypatch, position, original(ctx(round_index=2, own_losses=1, opponent_losses=1)), move), move)
    assert same(decide(monkeypatch, position, original(ctx(passed=True)), move), move)


def test_fusion20_only_with_original_decks():
    plain = Context(0, 0, 0, False, 3, 3, 1)
    assert response_search.search_settings(Difficulty.HARD, 1, plain).fusion == 1.0
    assert response_search.search_settings(Difficulty.HARD, 1, original(plain)).fusion == 0.2


def test_search_parity_with_original_decks(board):
    card(board, 5, 1, 9); card(board, 10, 1, 137)
    card(board, 8, 5, 9, player=1); card(board, 4, 4, 10)
    card(board, 0, 1, 16, (23,))
    state = capture(board)
    changed = False
    for level in (2, 3):
        fused = compare_response(state, Context(0, 0, 0, False, 3, 3, 1, original_decks=True), level)
        plain = compare_response(state, Context(0, 0, 0, False, 3, 3, 1), level)
        fused_value = response_search.choose_response(state, Context(0, 0, 0, False, 3, 3, 1, original_decks=True), level).value
        plain_value = response_search.choose_response(state, Context(0, 0, 0, False, 3, 3, 1), level).value
        changed = changed or fused != plain or abs(fused_value - plain_value) > 1e-9
    assert changed                                   # the scenario reaches the second ply


def test_the_npc_decks_option_reaches_the_ai():
    ws = (ROOT / 'mod/settings/modGwentAISettings/content/scripts/local/gwai_settings.ws').read_text()
    assert 'packet.SetMemberFlashInt("npcdecks", GwaiSettingsNpcDecks());' in ws
    runtime = (ROOT / 'tools/v8_runtime_patch.py').read_text()
    assert 'npcDecks' in runtime and 'gwaiNpcDeckMode' in runtime
    context = (ROOT / 'mod/v8/as3/GwaiV8Context.as').read_text()
    assert 'original_decks:flow.gwaiNpcDeckMode() == 0 && own == 1' in context


def test_the_lab_plays_original_mode_like_the_game():
    import evaluate_pool
    from gwentsim import response_v8 as v8
    for mode, expected in ((None, True), ('original', True), ('balanced', False), ('strong', False)):
        with evaluate_pool.scene(1, 7, 'response-v8', mode):
            assert v8.ORIGINAL_DECKS is expected
            assert v8.original_decks_for(1) is expected and v8.original_decks_for(0) is False
    controller = (ROOT / 'sim/gwentsim/gwint/sequence_ai_controller.py').read_text()
    assert 'original_decks=response_v8.original_decks_for(own)' in controller


def test_lab_switch_turns_the_original_mode_ai_off(monkeypatch):
    # Spec (owner, 14 October 2026): spy-first and fusion20 were proven on Hard only, but the mod
    # uses them on every level with the Original decks. To measure them on Easy and Normal, an A/B
    # base plays the Original decks without them: Lab switch "no-original-ai" (Lab only).
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import gwentsim.response_v8 as v8
    from evaluate_pool import scene
    for variant, expected in ((frozenset(), True), (frozenset({'no-original-ai'}), False)):
        monkeypatch.setattr(v8, 'VARIANT', variant)
        with scene(1, 7, 'response-v8', 'original'):
            assert v8.ORIGINAL_DECKS is expected
            assert v8.original_decks_for(1) is expected
