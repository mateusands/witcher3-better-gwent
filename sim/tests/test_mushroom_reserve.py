"""Held combos respect modifier capacity and preserve all observed inputs."""
from dataclasses import replace
from test_horn_evaluation import board, horn, card
from test_mushroom_position import berserker, mushroom, projected
from gwentsim import constants as C
from mushroom_reserve import MushroomReservePosition, mushroom_reserve_hook
import mushroom_policy


def reserve_position(board):
    return MushroomReservePosition(**projected(board).__dict__)


def test_native_ranged_pair_value_and_identity(board):
    a, target = berserker(board, ranged=True, bond=True)
    b = board.spawnCardInstance(a.templateId, 0, 1)
    b.inList, b.listsPlayer = 1, 0
    board.getCardInstanceList(1, 0).append(b)
    mushroom(board)
    state = reserve_position(board); before = state.clone()
    assert projected(board).reserve() == 4
    assert state.reserve() == 32
    assert state == before and state.cards[a.instanceId].template == a.templateId


def test_modifier_mushroom_and_horn_cannot_share_row(board):
    berserker(board); m = mushroom(board); horn(board)
    state = reserve_position(board)
    assert state.reserve() == 14
    state.cards[m.instanceId] = replace(state.cards[m.instanceId],
        types=C.CardType_Row_Modifier | C.CardType_Ranged)
    assert state.reserve() == 2


def test_hero_mushroom_shares_horn_without_hero_buff(board):
    berserker(board); mushroom(board, creature=True); horn(board)
    assert reserve_position(board).reserve() == 30


def test_transformed_morale_counts_all_other_nonheroes(board):
    berserker(board); mushroom(board)
    card(board, 5, 1, C.CardType_Creature | C.CardType_Melee, (C.CardEffect_None,))
    assert reserve_position(board).reserve() == 20


def test_no_source_or_unsafe_target_keeps_v7(board):
    a, target = berserker(board)
    state = reserve_position(board)
    assert state.reserve() == projected(board).reserve()
    mushroom(board); target.templateRef.effectFlags = [C.CardEffect_SuicideSummon]
    assert reserve_position(board).reserve() == projected(board).reserve()


def test_existing_board_mushroom_is_not_a_future_held_source(board):
    berserker(board); mushroom(board, row=8)
    assert reserve_position(board).reserve() == projected(board).reserve() == 2


def test_available_leader_horn_also_respects_modifier_slot(board, monkeypatch):
    a, target = berserker(board); mushroom(board)
    state = reserve_position(board)
    # Model the same known leader Horn reserve without inventing a native leader.
    from gwentsim.future_value import ReserveCard
    from gwentsim.position import Position
    monkeypatch.setattr(Position, 'leader_reserve',
        lambda self: ((ReserveCard(-999, 1, 0, (0,), horn=True),), 0))
    assert state.reserve() == 14


def test_context_restores_projection_on_error():
    original = mushroom_policy.MushroomPosition
    try:
        with mushroom_reserve_hook(0, []):
            assert mushroom_policy.MushroomPosition is MushroomReservePosition
            raise RuntimeError('test')
    except RuntimeError:
        pass
    assert mushroom_policy.MushroomPosition is original


def test_real_skelhard_deal_reproduces_and_fixes_the_gap():
    from diagnose_mushroom_reserve import (ROOT, DealObserved, load_match,
        NativeDecks, run_match, CardManager, SeededRandom, MushroomPosition)
    from gwentsim.position import Action
    match = load_match(ROOT/'game/records/g113.json')
    native = NativeDecks(ROOT/'game/vanilla/xml/content0/gameplay/items', match.templates)
    captured = []
    def observe(event):
        if event['k'] == 'S' and event['tag'] == 'deal':
            captured.append(MushroomPosition.from_manager(CardManager.getInstance(), 0))
            raise DealObserved()
    try:
        run_match(match.templates.values(),
            [native.build('SkelHard', 3, player=0), native.build('Crach', 3, player=1)],
            match.card_values, SeededRandom(0), on_event=observe, coin_toss_choice=lambda: True)
    except DealObserved:
        pass
    state = captured[0]
    keys = tuple([k for k in state.hand if state.cards[k].template == 515][:2]
                 + [k for k in state.hand if state.cards[k].template == 22][:1])
    assert len(keys) == 3
    subset = replace(state, hand=keys, counts={}, leader_ready={0: False, 1: False})
    corrected = MushroomReservePosition(**subset.__dict__)
    after = subset.apply(Action(keys[0], 4)).apply(Action(keys[1], 4)).apply(Action(keys[2], 7))
    assert subset.reserve() == 4
    assert corrected.reserve() == after.scores()[0] == 32
    assert corrected == MushroomReservePosition(**subset.__dict__)
