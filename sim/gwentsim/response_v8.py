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
    result = _choose_response_v8(position, context, profile)
    if VARIANT & NPC_SWITCHES:
        result = npc_switches(position, context, result)
    return result


def _choose_response_v8(position, context, profile):
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
        candidates = securing_plays(position, context)
        if candidates:
            is_match_win = (context.opponent_losses >= 1 or context.round_index >= 2)
            is_elimination = (context.own_losses >= 1 or context.round_index >= 2)
            is_round_1_win = (context.round_index == 0 and len(position.hand) >= 2)
            if is_match_win or is_elimination or is_round_1_win:
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
            if context.own_losses == 0 or (not flag('allow-self-harm', position.player)
                                           and (empty_after or result.pass_value > result.value)):
                return replace(result, action=None, value=result.pass_value,
                               reason='pass_for_match_resources', revision='response-v8')

    return replace(result, revision='response-v8')


def securing_plays(position, context):
    """Single non-spy plays after which the round is ours, as (reserve cost, -score gain, action),
    cheapest first (Blunder Fix #2, and overkill-trim against a passed opponent)."""
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
    candidates.sort(key=lambda c: (c[0], c[1], c[2].source))
    return candidates


def alternative_action(data):
    return Action(data['source'], data.get('slot', -1), data.get('target', -1),
                  tuple(tuple(step) for step in data.get('chain', ()) or ()))


def weather_or_horn(position, action):
    """(weather, horn): the action plays a weather card or a leader "pick weather", or a Horn
    card or a leader Horn."""
    card = position.cards.get(action.source)
    if card is None:
        return False, False
    leader = action.source == (position.leaders or {}).get(position.player)
    effect = position.leader_effect(position.player) if leader else None
    weather = (not leader and card.is_type(C.CardType_Weather) and not card.has(C.CardEffect_ClearSky)) or \
        effect in (C.CardEffect_Pick_Fog, C.CardEffect_Pick_Frost, C.CardEffect_Pick_Rain, C.CardEffect_Pick_Weather)
    horn = (not leader and card.is_type(C.CardType_Row_Modifier) and card.has(C.CardEffect_Horn)) or \
        effect in (C.CardEffect_Melee_Horn, C.CardEffect_Range_Horn, C.CardEffect_Siege_Horn)
    return weather, horn


def wasted_move(position, action):
    """Two narrow blunders only (a broad "no gain now" rule measured worse):
    weather that costs us more points than the opponent right now, and a Horn
    (card or leader) that adds nothing because its row has no unit to double."""
    weather, horn = weather_or_horn(position, action)
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



# ---- NPC experiment switches from in-game matches g152-g157 (Lab only, all off by default) ------
# Each is read with flag(name, seat); with none in VARIANT, choose_response_v8 is unchanged.
NPC_SWITCHES = frozenset({'agile-dry', 'weather-guard', 'medic-hold', 'r1-chase', 'overkill-trim'})
# Moves of earlier fixes that the switches leave alone (only agile-dry may still move their row).
PROTECTED = frozenset({'proactive_decoy_spy', 'decoy_spy_retarget', 'medic_spy_retarget', 'proactive_medic_spy'})


def score_gain(position, action):
    """Change of our score lead made by the action now, or None when it cannot be projected."""
    try:
        after = position.apply(action)
    except (UnsupportedPosition, ValueError):
        return None
    own, other = position.player, 1 - position.player
    before, now = position.scores(), after.scores()
    return (now[own] - now[other]) - (before[own] - before[other])


def weathered(position, side, row):
    return any(position.cards[k].is_type(C.CardType_Weather) for k in position.effects.get((side, row), ()))


def in_hand_card(position, action):
    """The hand card an action plays (None for the leader)."""
    if action.source == (position.leaders or {}).get(position.player) or action.source not in position.hand:
        return None
    return position.cards.get(action.source)


def wet_unit(position, action):
    """A non-hero unit placed into our own row under weather, where it loses power."""
    card = in_hand_card(position, action)
    if card is None or not card.is_type(C.CardType_Creature) or card.is_type(C.CardType_Hero) \
            or card.is_type(C.CardType_Spy) or action.slot not in ROWS:
        return False
    return weathered(position, position.player, action.slot) and \
        card.power > (0 if position.half_weather[position.player] else 1)


def useless_weather(position, context, action):
    """weather-guard: a weather play (card or leader pick) whose swing now is not positive."""
    if context.opponent_passed or not weather_or_horn(position, action)[0]:
        return False
    gain = score_gain(position, action)
    return gain is not None and gain <= 0


def empty_medic(position, context, action):
    """medic-hold: a Medic (unit or hero) with no unit to revive, outside the final round."""
    card = in_hand_card(position, action)
    if card is None or not card.has(C.CardEffect_Nurse) or position.recovery_targets(position.player):
        return False
    final = context.round_index >= 2 or (context.own_losses and context.opponent_losses)
    return not final


def vetoed(position, context, action):
    """Moves a replacement must not be: what the active switches remove, and a wasted move."""
    seat = position.player
    if flag('weather-guard', seat) and (useless_weather(position, context, action) or wet_unit(position, action)):
        return True
    if flag('medic-hold', seat) and empty_medic(position, context, action):
        return True
    return wasted_move(position, action)


def one_turn_values(result):
    return [(alternative_action(a['action']), a['oneTurnValue']) for a in result.alternatives]


def replacement(position, context, result, accept=lambda action, value: True):
    """Best searched alternative (the search's own one-turn order) that no switch vetoes."""
    for action, value in one_turn_values(result):
        if action != result.action and accept(action, value) and not vetoed(position, context, action):
            return action, value
    return None


def own_value(result):
    return next((v for a, v in one_turn_values(result) if a == result.action), result.value)


def dry_rows(position, action):
    """agile-dry: the same play with every agile unit it places (the card and its Medic chain)
    moved from a row under weather to its other row when that one is dry. None if nothing moves."""
    own = position.player

    def flip(key, row):
        if row in (4, 5) and position.agile_unit(key) and weathered(position, own, row) \
                and not weathered(position, own, 9 - row):
            return 9 - row
        return row
    card = in_hand_card(position, action)
    if card is None or not card.is_type(C.CardType_Creature) or card.is_type(C.CardType_Spy):
        return None
    slot = flip(action.source, action.slot)
    chain = tuple((key, flip(key, row)) for key, row in action.chain)
    if (slot, chain) == (action.slot, action.chain):
        return None
    return replace(action, slot=slot, chain=chain)


def race(position, context, hypothesis, limit=30):
    """r1-chase: a greedy public race for the rest of this round in one hypothesized opponent hand.

    Whoever is behind plays its supported move with the largest immediate score gain; a side that
    is ahead waits. The race ends when the side behind has no move that gains. Returns
    (we win the round, our cards spent, opponent cards spent)."""
    from .opponent_belief import opponent_view
    own, other = position.player, 1 - position.player
    view = opponent_view(position, hypothesis)
    hands = {own: position.hand, other: view.hand}
    counts = {own: dict(position.counts), other: dict(view.counts)}
    flipped = replace(context, own_losses=context.opponent_losses, opponent_losses=context.own_losses,
                      own_faction=context.opponent_faction, opponent_faction=context.own_faction)
    ties = {own: context.wins_ties or tie_match(context), other: flipped.wins_ties or tie_match(flipped)}
    state = view
    spent = {own: 0, other: 0}

    def ahead(side):
        sc = state.scores()
        gap = sc[side] - sc[1 - side]
        return gap > 0 or (gap == 0 and ties[side])
    last = other
    for _ in range(limit):
        behind = [side for side in (own, other) if not ahead(side)]
        if not behind:
            break
        mover = behind[0] if len(behind) == 1 else 1 - last
        turn = state.clone()
        turn.player, turn.hand, turn.counts, turn.unknown_draws = mover, hands[mover], counts[mover], 0
        best = None
        for action in turn.actions():
            try:
                after = turn.apply(action)
            except (UnsupportedPosition, ValueError):
                continue
            before, now = turn.scores(), after.scores()
            gain = (now[mover] - now[1 - mover]) - (before[mover] - before[1 - mover])
            if gain > 0 and (best is None or gain > best[0]):
                best = (gain, after)
        if best is None:
            break
        state = best[1]
        hands[mover], counts[mover] = state.hand, state.counts
        spent[mover] += 1
        last = mover
    return ahead(own), spent[own], spent[other]


def hopeless_chase(position, context, samples=4):
    """r1-chase: in round 1, against an opponent still playing, the round is not realistically
    ours when, in more than half of the public hypotheses of the opponent's hand (the search's
    own sample count on Hard), the greedy race is lost or is won only by ending with two or more
    cards fewer than the opponent (a won first round is worth one card, as Blunder Fix #2
    assumes). A current lead does not exempt us: the race already contains the opponent's
    answers, and a lead we pass on makes the opponent spend to overtake it. Only with fewer cards
    in hand than the opponent: with as many or more, the chase is left to the search (the
    hypotheses come from the whole public catalog and can overrate the opponent's hand; a pass
    on the first move at 0-0 is never wanted)."""
    from .opponent_belief import hypotheses
    if context.round_index or context.own_losses or context.opponent_passed or context.own_leader_available:
        return False
    if len(position.hand) >= context.opponent_hand_count:
        return False
    if not position.hand or any(not position.supported(position.cards[k]) for k in position.hand):
        return False
    beliefs = hypotheses(position, context, samples)
    if not beliefs:
        return False
    hopeless = 0
    for h in beliefs:
        won, ours, theirs = race(position, context, h)
        if not won or (len(position.hand) - ours) < (context.opponent_hand_count - theirs) - 1:
            hopeless += 1
    return 2 * hopeless > len(beliefs)


def npc_switches(position, context, result, again=False):
    """Apply the active NPC switches to a V8 decision (see NPC_SWITCHES). `again`: a switch has
    already replaced the move, so the pass check of r1-chase is not repeated."""
    seat = position.player
    action = result.action
    if action is not None and result.reason not in PROTECTED:
        # r1-chase: stop spending on a first round that is not realistically ours.
        if flag('r1-chase', seat) and not again and hopeless_chase(position, context):
            return replace(result, action=None, value=result.pass_value, reason='pass_for_match_resources',
                           revision='response-v8+r1-chase')
        # weather-guard: no weather that gains nothing now, no unit into our own weather.
        if flag('weather-guard', seat) and useless_weather(position, context, action):
            found = replacement(position, context, result)
            if found:
                return npc_switches(position, context, again=True, result=replace(result, action=found[0], value=found[1],
                                                                 reason='weather_guard'))
        if flag('weather-guard', seat) and wet_unit(position, action):
            floor = own_value(result)

            def dry_unit(other, value):
                card = in_hand_card(position, other)
                return (value >= floor and card is not None and card.is_type(C.CardType_Creature)
                        and not card.is_type(C.CardType_Hero) and not wet_unit(position, other))
            found = replacement(position, context, result, dry_unit)
            if found:
                return npc_switches(position, context, again=True, result=replace(result, action=found[0], value=found[1],
                                                                 reason='weather_guard_dry_unit'))
        # medic-hold: keep a Medic until the graveyard holds a unit to revive.
        if flag('medic-hold', seat) and empty_medic(position, context, action):
            found = replacement(position, context, result)
            if found:
                return npc_switches(position, context, again=True, result=replace(result, action=found[0], value=found[1],
                                                                 reason='medic_hold'))
        # overkill-trim: win the round with the smallest commitment.
        if flag('overkill-trim', seat) and result.reason not in ('overkill_trim',):
            trimmed = overkill_trim(position, context, result)
            if trimmed is not None:
                return npc_switches(position, context, trimmed, again=True)
    if action is not None and flag('agile-dry', seat):
        moved = dry_rows(position, action)
        if moved is not None:
            wet, dry = score_gain(position, action), score_gain(position, moved)
            # The weathered row is kept only when it is strictly better now (a Horn or Tight Bond
            # there can outweigh the weather).
            if wet is not None and dry is not None and dry >= wet:
                return replace(result, action=moved, reason='agile_dry')
    return result


def overkill_trim(position, context, result):
    """overkill-trim: when the round is won or being won, prefer the cheapest play that keeps it.

    - Opponent passed: the cheapest single non-spy play that secures the round (securing_plays,
      the candidates of Blunder Fix #2) replaces a dearer play or a longer sequence.
    - Opponent still playing, we lead and a later round exists: among the searched alternatives
      that play a non-spy unit from the hand, that the search values above passing, that keep the
      lead and that no switch vetoes, the one costing the least reserve (what our hand is worth
      for later rounds) replaces a dearer play (a hero, a Horn, Scorch, a leader ability).
      Special cards and the leader are not offered as the cheaper play: their worth is in timing."""
    action = result.action
    card = position.cards.get(action.source)
    if card is not None and card.is_type(C.CardType_Spy):
        return None
    before = position.reserve()

    def cost(move):
        try:
            return before - position.apply(move).reserve()
        except (UnsupportedPosition, ValueError):
            return None
    chosen = cost(action)
    if chosen is None:
        return None
    if context.opponent_passed:
        plays = securing_plays(position, context)
        if plays and plays[0][0] < chosen - 1e-9:
            return replace(result, action=plays[0][2], reason='overkill_trim')
        return None
    final = context.round_index >= 2 or (context.own_losses and context.opponent_losses)
    if final or not secured(position, context):
        return None
    best = None
    for move, value in one_turn_values(result):
        unit = in_hand_card(position, move)
        if move == action or unit is None or not unit.is_type(C.CardType_Creature) or unit.is_type(C.CardType_Spy) \
                or value <= result.pass_value or vetoed(position, context, move):
            continue
        c = cost(move)
        if c is None or c >= chosen - 1e-9:
            continue
        try:
            keeps = secured(position.apply(move), context)
        except (UnsupportedPosition, ValueError):
            continue
        if keeps and (best is None or (c, -value) < (best[0], -best[1])):
            best = (c, value, move)
    if best is None:
        return None
    return replace(result, action=best[2], value=best[1], reason='overkill_trim')
