"""V8 candidate policy: eliminates silly blunders from V7 while preserving public-information fair play."""
from dataclasses import replace
from . import constants as C
from .position import UnsupportedPosition, Action, ROWS, ROW_FLAGS
from .sequence_search import overtaking_bounds
from .response_search import choose_response, secured, tie_match


# Simulator-only experiment switches for A/B tests in the Lab (policy "response-v8:flag+flag").
# Empty in normal use, so response-v8 behaves exactly as shipped.
VARIANT = frozenset()
# Seat of the NPC in a player-deck A/B (set by evaluate_pool.run_player): switches apply to that
# seat only, so the Better AI stand-in for the player keeps playing the shipped AI. None = all seats.
NPC_SEAT = None


def flag(name, seat):
    return name in VARIANT and (NPC_SEAT is None or seat == NPC_SEAT)


def safe_lead_pass(position, context):
    """Experiment "lead-pass": with a round already lost, an open round we lead may be passed
    when, in every public hypothesis of the opponent's hand, even generous bounds cannot
    overtake us (the cards we keep are worth more in the next round)."""
    from .opponent_belief import hypotheses, opponent_view
    from .sequence_search import overtaking_bounds
    if context.opponent_passed or not context.own_losses or not position.hand or not secured(position, context):
        return False
    beliefs = hypotheses(position, context, 6)
    if not beliefs:
        return False
    flipped = replace(context, own_losses=context.opponent_losses, opponent_losses=context.own_losses,
                      own_faction=context.opponent_faction, opponent_faction=context.own_faction)
    tie_for_them = flipped.wins_ties or tie_match(flipped)
    for h in beliefs:
        bounds = overtaking_bounds(opponent_view(position, h))
        if bounds is None or (bounds[0] >= bounds[1] if tie_for_them else bounds[0] > bounds[1]):
            return False
    return True


def choose_response_v8(position, context, profile):
    result = choose_response(position, context, profile)
    if result.action is not None and flag('lead-pass', position.player) and safe_lead_pass(position, context):
        return replace(result, action=None, value=result.pass_value, reason='pass_for_match_resources',
                       revision='response-v8')

    # Blunder Fix #1: Overplay after opponent passed while round is secured.
    # In any round where the opponent has already passed and our score is winning,
    # playing any non-spy card (unit, hero, horn, weather, scorch) is pure waste.
    if context.opponent_passed and result.action is not None and secured(position, context):
        card = position.cards.get(result.action.source)
        is_safe_spy = False
        if card and card.is_type(C.CardType_Spy):
            try:
                after = position.apply(result.action)
                if after.unknown_draws > position.unknown_draws and secured(after, context):
                    is_safe_spy = True
            except (UnsupportedPosition, ValueError):
                pass
        if not is_safe_spy:
            return replace(result, action=None, value=result.pass_value,
                           reason='pass_for_match_resources', revision='response-v8')

    # Blunder Fix #2: Passed when able to win against a passed opponent.
    # If the opponent has passed and we are trailing or tied without tie advantage,
    # passing forfeits the round. If there is a single card that secures the round:
    # 1. Match win: in round 2/3 (opponent has 1 loss or round >= 2), winning this round
    #    wins the entire match immediately. Always take the match win!
    # 2. Elimination round: if we face elimination (own_losses >= 1 or round >= 2),
    #    passing is instant defeat; we must play to survive/win.
    # 3. Round 1: if we have >= 2 cards in hand, spending 1 card to secure Round 1
    #    gives crucial round control (down 1 card on round win is standard in Gwent).
    if context.opponent_passed and (result.action is None or result.reason in ('pass_for_match_resources', 'proven_no_supported_overtake')) and not secured(position, context):
        scores = position.scores()
        own = position.player
        other = 1 - own
        wins_ties = (context.wins_ties or tie_match(context))
        candidates = []
        initial_reserve = position.reserve()
        for act in position.actions():
            card = position.cards.get(act.source)
            if not card or card.is_type(C.CardType_Spy):
                continue
            try:
                after = position.apply(act)
                sc = after.scores()
                if sc[own] > sc[other] or (sc[own] == sc[other] and wins_ties):
                    gain = (sc[own] - sc[other]) - (scores[own] - scores[other])
                    cost = initial_reserve - after.reserve()
                    candidates.append((cost, -gain, act))
            except (UnsupportedPosition, ValueError):
                continue

        if candidates:
            is_match_win = (context.opponent_losses >= 1 or context.round_index >= 2)
            is_elimination = (context.own_losses >= 1 or context.round_index >= 2)
            is_round_1_win = (context.round_index == 0 and len(position.hand) >= 2)
            if is_match_win or is_elimination or is_round_1_win:
                candidates.sort(key=lambda c: (c[0], c[1], c[2].source))
                best_act = candidates[0][2]
                return replace(result, action=best_act, reason='overtake_passed_opponent_win', revision='response-v8')

    # Blunder Fix #3: Concede mathematically unwinnable chase against a passed opponent when safe.
    # When opponent has passed, we are trailing, and we are NOT facing elimination (own_losses == 0
    # and round_index < 2): if overtaking_bounds proves our optimistic ceiling cannot reach the opponent floor,
    # playing any card wastes resources into a guaranteed loss. Pass immediately to save hand for next round.
    if context.opponent_passed and result.action is not None and not secured(position, context):
        if not context.own_losses and context.round_index < 2:
            bounds = overtaking_bounds(position)
            if bounds is not None:
                ceiling, floor = bounds
                wins_ties = (context.wins_ties or tie_match(context))
                unwinnable = (ceiling < floor) if wins_ties else (ceiling <= floor)
                if unwinnable:
                    return replace(result, action=None, value=result.pass_value,
                                   reason='concede_unwinnable_chase', revision='response-v8')

    # Blunder Fix #4: Tactical Decoy & Special Card Thresholds (Forge-style triggers).
    # 1. Proactive Decoy on Enemy Spy:
    # If holding Decoy and an enemy Spy is on our board, opponent has not passed, and own_losses == 0:
    # Taking the enemy spy into hand grants +2 cards and removes opposing points.
    if not context.opponent_passed and context.own_losses == 0:
        decoy_keys = [k for k in position.hand if position.cards[k].has(C.CardEffect_UnsummonDummy)]
        if decoy_keys:
            spy_targets = [
                k for (side, row), keys in position.board.items()
                if side == position.player
                for k in keys
                if (position.cards[k].is_type(C.CardType_Spy) or position.cards[k].has(C.CardEffect_Draw2))
                and not position.cards[k].is_type(C.CardType_Hero)
            ]
            if spy_targets:
                is_already_decoy_on_spy = False
                if result.action is not None and result.action.target in spy_targets:
                    is_already_decoy_on_spy = True
                if not is_already_decoy_on_spy:
                    best_spy = min(spy_targets, key=lambda k: (position.cards[k].power, k))
                    decoy_act = Action(source=decoy_keys[0], target=best_spy)
                    return replace(result, action=decoy_act, reason='proactive_decoy_spy', revision='response-v8')

    # 2. Retarget Decoy to Spy:
    # If Decoy is played, always target an eligible Spy on our board if one exists,
    # rather than bouncing a regular friendly unit.
    if result.action is not None:
        card = position.cards.get(result.action.source)
        if card and card.has(C.CardEffect_UnsummonDummy) and result.action.target != -1:
            target = position.cards.get(result.action.target)
            if target and not (target.is_type(C.CardType_Spy) or target.has(C.CardEffect_Draw2)):
                spy_targets = [
                    k for (side, row), keys in position.board.items()
                    if side == position.player
                    for k in keys
                    if (position.cards[k].is_type(C.CardType_Spy) or position.cards[k].has(C.CardEffect_Draw2))
                    and not position.cards[k].is_type(C.CardType_Hero)
                ]
                if spy_targets:
                    best_spy = min(spy_targets, key=lambda k: (position.cards[k].power, k))
                    new_act = replace(result.action, target=best_spy)
                    return replace(result, action=new_act, reason='decoy_spy_retarget', revision='response-v8')

    # Blunder Fix #5: Tactical Medic (Nurse) Resurrection Priority on Spies and Chains.
    # When a Medic (Hero like Yennefer/Menno, or non-hero like Dun Banner/Siege Tech/etc.) is played,
    # or held in hand when considering a pass in non-elimination rounds:
    # Resurrecting an eligible non-hero Spy from our graveyard yields +2 cards from deck.
    eligible_graves = position.recovery_targets(position.player)
    grave_spies = [
        k for k in eligible_graves
        if (position.cards[k].is_type(C.CardType_Spy) or position.cards[k].has(C.CardEffect_Draw2))
        and not position.cards[k].is_type(C.CardType_Hero)
    ]

    # 1. Retarget Medic chain to Spy:
    # If a Medic is played and its chain resurrected a non-spy unit while an eligible Spy is in our graveyard:
    if result.action is not None and grave_spies:
        source_card = position.cards.get(result.action.source)
        if source_card and source_card.has(C.CardEffect_Nurse):
            current_chain = result.action.chain or ()
            chain_has_spy = any(
                (position.cards[t[0]].is_type(C.CardType_Spy) or position.cards[t[0]].has(C.CardEffect_Draw2))
                for t in current_chain
            )
            if not chain_has_spy:
                is_safe = (context.own_losses == 0)
                # Last card in hand: a recovered spy keeps us in the round with two draws,
                # while a plain unit leaves an empty hand against an opponent still playing
                # (in-game match g129, elimination round).
                deck_left = sum(position.counts.values()) - position.unknown_draws
                if not is_safe and not context.opponent_passed and len(position.hand) == 1 and deck_left >= 2:
                    is_safe = True
                # Experiment: a recovered spy is worth its two draws in any open round.
                if not is_safe and flag('medic-spy-open', position.player) and not context.opponent_passed and deck_left >= 2:
                    is_safe = True
                if not is_safe and context.opponent_passed:
                    best_spy_cand = min(grave_spies, key=lambda k: (position.cards[k].power, k))
                    scores = position.scores()
                    gap = scores[position.player] - scores[1 - position.player]
                    if gap > position.cards[best_spy_cand].power:
                        is_safe = True
                if is_safe:
                    best_spy = min(grave_spies, key=lambda k: (position.cards[k].power, k))
                    spy_card = position.cards[best_spy]
                    valid_spy_rows = tuple(r for r in ROWS if spy_card.is_type(ROW_FLAGS[r]))
                    spy_row = valid_spy_rows[0] if valid_spy_rows else 5

                    grave_medics = [
                        k for k in eligible_graves
                        if position.cards[k].has(C.CardEffect_Nurse)
                        and k != best_spy
                        and not position.cards[k].is_type(C.CardType_Hero)
                    ]
                    if grave_medics:
                        best_med = max(grave_medics, key=lambda k: (position.cards[k].power, k))
                        med_card = position.cards[best_med]
                        valid_med_rows = tuple(r for r in ROWS if med_card.is_type(ROW_FLAGS[r]))
                        med_row = valid_med_rows[0] if valid_med_rows else 5
                        new_chain = ((best_med, med_row), (best_spy, spy_row))
                    else:
                        new_chain = ((best_spy, spy_row),)

                    new_act = replace(result.action, chain=new_chain)
                    return replace(result, action=new_act, reason='medic_spy_retarget', revision='response-v8')

    # 2. Proactive Medic on Graveyard Spy (veto premature pass in non-elimination):
    if result.action is None and not context.opponent_passed and context.own_losses == 0 and grave_spies:
        hand_medics = [
            k for k in position.hand
            if position.cards[k].has(C.CardEffect_Nurse)
            and position.supported(position.cards[k])
        ]
        if hand_medics:
            best_hand_med = min(hand_medics, key=lambda k: (position.cards[k].power, k))
            med_card = position.cards[best_hand_med]
            valid_rows = tuple(r for r in ROWS if med_card.is_type(ROW_FLAGS[r]))
            slot = valid_rows[0] if valid_rows else 5

            best_spy = min(grave_spies, key=lambda k: (position.cards[k].power, k))
            spy_card = position.cards[best_spy]
            valid_spy_rows = tuple(r for r in ROWS if spy_card.is_type(ROW_FLAGS[r]))
            spy_row = valid_spy_rows[0] if valid_spy_rows else 5

            grave_medics = [
                k for k in eligible_graves
                if position.cards[k].has(C.CardEffect_Nurse)
                and k != best_spy
                and not position.cards[k].is_type(C.CardType_Hero)
            ]
            if grave_medics:
                best_med = max(grave_medics, key=lambda k: (position.cards[k].power, k))
                gmed_card = position.cards[best_med]
                valid_gmed_rows = tuple(r for r in ROWS if gmed_card.is_type(ROW_FLAGS[r]))
                gmed_row = valid_gmed_rows[0] if valid_gmed_rows else 5
                new_chain = ((best_med, gmed_row), (best_spy, spy_row))
            else:
                new_chain = ((best_spy, spy_row),)

            medic_act = Action(source=best_hand_med, slot=slot, chain=new_chain)
            return replace(result, action=medic_act, reason='proactive_medic_spy', revision='response-v8')

    # Blunder Fix #6: Wasted resources before the opponent has passed.
    # A move that spends a card or the leader without improving the current score
    # difference (e.g. frost that only weakens our own row, a leader Horn on an empty
    # row) is replaced by the best searched alternative that does, or that costs
    # nothing (spies, Decoy, resurrection to hand). Without one, pass when that cannot
    # lose the match; otherwise keep the original move.
    if not context.opponent_passed and result.action is not None and not flag('no-waste-guard', position.player):
        if wasted_move(position, result.action):
            for alternative in result.alternatives:
                move = alternative_action(alternative['action'])
                if move != result.action and not wasted_move(position, move):
                    return replace(result, action=move, value=alternative['oneTurnValue'],
                                   reason='avoid_wasted_resource', revision='response-v8')
            # Pass also after a lost round when nothing would be left in hand (the
            # leader then gives away only our own points, in-game match g151) or when
            # the search itself values passing above the wasted move.
            empty_after = not [k for k in position.hand if k != result.action.source]
            if context.own_losses == 0 or empty_after or result.pass_value > result.value:
                return replace(result, action=None, value=result.pass_value,
                               reason='pass_for_match_resources', revision='response-v8')

    return replace(result, revision='response-v8')


def alternative_action(data):
    return Action(data['source'], data.get('slot', -1), data.get('target', -1),
                  tuple(tuple(step) for step in data.get('chain', ()) or ()))


def wasted_move(position, action):
    """Two narrow blunders only (a broad "no gain now" rule measured worse):
    weather that costs us more points than the opponent right now, and a Horn
    (card or leader) that adds nothing because its row has no unit to double."""
    card = position.cards.get(action.source)
    if card is None:
        return False
    leader = action.source == (position.leaders or {}).get(position.player)
    effect = position.leader_effect(position.player) if leader else None
    weather = (not leader and card.is_type(C.CardType_Weather) and not card.has(C.CardEffect_ClearSky)) or \
        effect in (C.CardEffect_Pick_Fog, C.CardEffect_Pick_Frost, C.CardEffect_Pick_Rain, C.CardEffect_Pick_Weather)
    horn = (not leader and card.is_type(C.CardType_Row_Modifier) and card.has(C.CardEffect_Horn)) or \
        effect in (C.CardEffect_Melee_Horn, C.CardEffect_Range_Horn, C.CardEffect_Siege_Horn)
    if not weather and not horn:
        return False
    try:
        after = position.apply(action)
    except (UnsupportedPosition, ValueError):
        return False
    own, other = position.player, 1 - position.player
    before_scores, after_scores = position.scores(), after.scores()
    gain = (after_scores[own] - after_scores[other]) - (before_scores[own] - before_scores[other])
    if weather and flag('weather-zero', position.player):
        return gain <= 0   # experiment: weather that changes nothing now is also wasted
    return gain < 0 if weather else gain <= 0

