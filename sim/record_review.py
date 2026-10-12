#!/usr/bin/env python3
"""Review the NPC decisions of an in-game match played by Better AI (diagnostic only).

The recorded match is rebuilt in the simulator with BOTH sides scripted: the player's
commands as in replay.py, and the NPC's recorded decisions ("A" events), opening exchanges
and diagnostic notes ("X"). At every NPC decision the simulator's V8 (Python reference) is
asked what it would play from the same public position, so in-game decisions can be compared
with the reference and judged with luck continuations (see judge()).

Usage: python3 sim/record_review.py game/records/g138.json [--judge INDEX ...]
"""
import argparse
import json
import random as _random
import sys
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from gwentsim import constants as C  # noqa: E402
from gwentsim.data import load_match  # noqa: E402
from gwentsim.gwint import gwint_game_flow_controller as gfc  # noqa: E402
from gwentsim.gwint.ai_player_controller import AIPlayerController, TACTIC_PASS  # noqa: E402
from gwentsim.gwint.base_player_controller import ROUND_PLAYER_STATUS_DONE  # noqa: E402
from gwentsim.gwint.card_manager import CardManager  # noqa: E402
from gwentsim.gwint.match import run_match  # noqa: E402
from gwentsim.gwint.sequence_ai_controller import ResponseV8AIPlayerController  # noqa: E402
from gwentsim.gwint.small import CardTransaction  # noqa: E402
from gwentsim.position import Position  # noqa: E402
from gwentsim.rng import ReplayRandom  # noqa: E402
from gwentsim.sequence_search import Context  # noqa: E402

NPC = 1
PROFILE_NAMES = ['easy', 'medium', 'hard', 'expert']


class Stop(Exception):
    pass


def capture(controller):
    """Position and context exactly as SequenceAIPlayerController builds them."""
    cm = CardManager.getInstance(); own, other = controller.playerID, controller.opponentID
    position = Position.from_manager(cm, own)
    context = Context(controller.gameFlowControllerRef.currentRound,
        sum(r.played and r.winningPlayer != own for r in cm.roundResults),
        sum(r.played and r.winningPlayer != other for r in cm.roundResults),
        controller.gameFlowControllerRef.playerControllers[other].currentRoundStatus == ROUND_PLAYER_STATUS_DONE,
        len(cm.getCardInstanceList(1, other)), cm.playerDeckDefinitions[own].getDeckFaction(),
        cm.playerDeckDefinitions[other].getDeckFaction(),
        position.leader_unmodeled(own), position.leader_unmodeled(other))
    from gwentsim import response_v8
    if response_v8.flag('known-hand', own):
        from gwentsim.known_hand import known_templates
        known = known_templates(cm, other)
        if known:
            context = replace(context, opponent_known=known)
    return position, context


def level_of(events):
    for e in events:
        if e['k'] == 'X' and ':lvl=' in e['where']:
            return int(e['where'].rsplit(':lvl=', 1)[1])
    return 2


def go_free(npc, rec, branch):
    """From this NPC decision on, both sides are played by V8 with fresh luck: the remaining
    decks of both players are reshuffled (hands and board stay as recorded)."""
    from gwentsim import rng
    from gwentsim.rng import SeededRandom
    flow = npc.gameFlowControllerRef; cm = CardManager.getInstance()
    rng.set_random_source(SeededRandom(branch['seed']), rec.random)
    shuffle = _random.Random('deck/%s' % branch['seed'])
    for p in (0, 1):
        shuffle.shuffle(cm.playerDeckDefinitions[p].cardIndicesInDeck)
    old = flow.playerControllers[0]
    player = ResponseV8AIPlayerController('AI P1', branch['player_profile'])
    player.gameFlowControllerRef = flow; player.playerID = 0; player.opponentID = 1
    for name in ('_boardRenderer', '_playerRenderer', '_cardZoomEnabled', '_currentRoundStatus', '_turnOver'):
        if name in old.__dict__:
            setattr(player, name, getattr(old, name))
    player.on_choose_move = rec.decision
    player._stateMachine.ChangeState('Idle')
    flow.playerControllers[0] = player
    branch['state']['free'] = True


def rebuild(path, on_decision=None, stop_at=None, branch=None):
    """Run the recorded match with both sides scripted.

    on_decision(index, controller, position, context, recorded_A) is called at every NPC decision.
    stop_at: event index of an NPC "A" event; the run stops (raises Stop) right before it is
    executed, leaving the simulator in that position. Returns the recorder and the flow."""
    m = load_match(path)
    events = m.events
    level = level_of(events)
    state = {}
    if branch is not None:
        branch['state'] = state
        branch.setdefault('player_profile', level)

    def emit_notes(rec):
        while len(rec.events) < len(events) and events[len(rec.events)]['k'] == 'X':
            rec._emit(dict(events[len(rec.events)]))

    class ScriptedNPC(ResponseV8AIPlayerController):
        def __init__(self, fsm_name='AI P2'):
            super().__init__(fsm_name, level)

        def state_begin_ChoseMove(self):
            if state.get('free'):
                return ResponseV8AIPlayerController.state_begin_ChoseMove(self)
            rec = state['rec']; emit_notes(rec)
            index = len(rec.events); recorded = events[index]
            if recorded['k'] != 'A' or int(recorded['player']) != self.playerID:
                cm = CardManager.getInstance(); leader = cm.getCardLeader(self.playerID)
                if not cm.getCardInstanceList(1, self.playerID) and not (leader and leader.canBeUsed):
                    # Nothing left to play: the game passes without recording a decision.
                    self._decidedCardTransaction = None; self.attitude = TACTIC_PASS
                    self.on_choose_move = lambda *args: None
                    return
                raise RuntimeError('event %d: expected an NPC decision, recorded %s' % (index, recorded))
            position, context = capture(self)
            if on_decision is not None:
                on_decision(index, self, position, context, recorded)
            if stop_at == index:
                state['flow'] = self.gameFlowControllerRef
                raise Stop()
            if branch is not None and branch['index'] == index:
                go_free(self, rec, branch)
                original = self.search

                def forced(position, context):
                    self.search = original
                    if branch['action'] is None:
                        return replace(original(position, context), action=None, reason='pass_for_match_resources')
                    return replace(original(position, context), action=branch['action'], reason='forced_alternative')
                self.search = forced
                return ResponseV8AIPlayerController.state_begin_ChoseMove(self)
            cm = CardManager.getInstance(); tx = recorded['tx']
            self.attitude = int(recorded['attitude'])
            if tx is None:
                self._decidedCardTransaction = None; self.attitude = TACTIC_PASS
            else:
                t = CardTransaction(); t.sourceCardInstanceRef = cm.getCardInstance(tx['source'][1])
                t.targetSlotID = tx['slot']; t.targetPlayerID = tx['targetPlayer']
                if tx['target'] is not None:
                    t.targetCardInstanceRef = cm.getCardInstance(tx['target'][1])
                t.powerChangeResult = tx['powerChange']; t.strategicValue = tx['strategic']
                self._decidedCardTransaction = t
                # The recorded Medic choices of this play (C nurse events before the next decision).
                chain = []
                for later in events[index + 1:]:
                    if later['k'] == 'A' or (later['k'] == 'H' and int(later['player']) != self.playerID):
                        break
                    if later['k'] == 'C' and later['choice'] == 'nurse':
                        target = cm.getCardInstance(int(later['arg']))
                        row = next((r for r, flag in ((5, 1), (4, 2), (3, 4)) if target.templateRef.typeArray & flag), 5)
                        chain.append((target.instanceId, row))
                if chain:
                    t.sourceCardInstanceRef.candidateRecoveryPlan = tuple(chain)
            self.on_choose_move = lambda *args: rec._emit(dict(recorded))

    original_mulligan = gfc.GwintGameFlowController.state_begin_Mulligan

    def mulligan(flow):
        original_mulligan(flow)
        rec = state['rec']; cm = flow.cardManager
        while len(rec.events) < len(events) and events[len(rec.events)]['k'] == 'X':
            note = events[len(rec.events)]['where']
            if note.startswith('gwai:npc_mulligan:'):
                old, new = (int(x) for x in note.rsplit(':', 1)[1].split('>'))
                card = next(c for c in cm.getCardInstanceList(1, NPC) if c.templateId == old)
                fresh = cm.mulliganCard(card)
                if fresh is None or fresh.templateId != new:
                    raise RuntimeError('NPC exchange %s drew %s, recorded %s' % (old, fresh and fresh.templateId, new))
            rec._emit(dict(events[len(rec.events)]))

    saved = gfc.AIPlayerController
    gfc.AIPlayerController = ScriptedNPC
    gfc.GwintGameFlowController.state_begin_Mulligan = mulligan
    import gwentsim.gwint.match as match_module
    recorder_cls = match_module.Recorder

    class Rec(recorder_cls):
        def __init__(self, *a, **k):
            super().__init__(*a, **k); state['rec'] = self
    match_module.Recorder = Rec
    from gwentsim.gwint import scripted_player
    tick = scripted_player.ScriptedInput.tick
    scripted_player.ScriptedInput.tick = lambda driver: None if state.get('free') else tick(driver)
    try:
        try:
            rec, flow = run_match(m.templates.values(), m.decks, m.card_values, ReplayRandom(m.randoms()),
                                  double_ai=False, scripted_events=events, instance_base=m.instance_base)
        except Stop:
            return m, state['rec'], state['flow']
    finally:
        gfc.AIPlayerController = saved
        gfc.GwintGameFlowController.state_begin_Mulligan = original_mulligan
        match_module.Recorder = recorder_cls
        scripted_player.ScriptedInput.tick = tick
    return m, rec, flow


def judge(path, index, continuations=16, extra=(), jobs=10):
    """Mean NPC result (win 1, draw 0.5) of the recorded move, V8's alternatives and a pass at
    the NPC decision `index`, each continued to the end by V8 on both sides over reshuffled decks.
    Full information is used ONLY to judge after the fact."""
    from gwentsim.response_v8 import alternative_action
    found = {}

    def on_decision(i, controller, position, context, recorded):
        if i == index:
            result = controller.search(position, context)
            found.update(position=position, result=result)
    rebuild(path, on_decision, stop_at=index)
    position, result = found['position'], found['result']
    options = [('chosen', result.action)]
    for alt in result.alternatives or ():
        action = alternative_action(alt['action'])
        if action != result.action and all(action != o[1] for o in options):
            options.append(('alternative', action))
    options += [('extra', a) for a in extra]
    if result.action is not None:
        options.append(('pass', None))
    import multiprocessing
    tasks = [(str(path), index, action, k) for _, action in options for k in range(continuations)]
    with multiprocessing.get_context('fork').Pool(jobs) as pool:
        results = pool.map(_continuation, tasks, chunksize=1)
    out = []
    for n, (kind, action) in enumerate(options):
        chunk = results[n * continuations:(n + 1) * continuations]
        out.append(dict(kind=kind, action=action, mean=sum(r[0] for r in chunk) / continuations,
                        rounds=sum(r[1] for r in chunk) / continuations))
    return position, result, out


def _continuation(task):
    path, index, action, k = task
    _, _, flow = rebuild(path, branch=dict(index=index, action=action, seed=k))
    won = 1.0 if flow.gameWinner == NPC else 0.5 if flow.gameWinner not in (0, 1) else 0.0
    return won, sum(r.played and r.winningPlayer == NPC for r in flow.cardManager.roundResults)


def describe(position, action, names):
    if action is None:
        return 'pass'
    card = position.cards.get(action.source)
    name = names.get(card.template, str(card.template)) if card else str(action.source)
    extra = ''
    if action.target not in (-1, None) and action.target in position.cards:
        t = position.cards[action.target]; extra = ' -> ' + names.get(t.template, str(t.template))
    return '%s (row %s)%s' % (name, action.slot, extra)


def review(path):
    from blunder_hunter import card_names
    names = card_names(); rows = []

    def on_decision(index, controller, position, context, recorded):
        result = controller.search(position, context)
        tx = recorded['tx']
        game = 'pass' if tx is None else names.get(tx['source'][0], str(tx['source'][0])) + ' (row %s)' % tx['slot'] + (
            ' -> ' + names.get(tx['target'][0], '?') if tx['target'] else '')
        reference = describe(position, result.action, names) if result.action is not None or result.reason else 'pass'
        rows.append(dict(index=index, round=context.round if hasattr(context, 'round') else None,
                         game=game, reference=reference, reason=result.reason))
    rebuild(path, on_decision)
    return rows


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('record')
    parser.add_argument('--judge', type=int, nargs='*', default=[], help='NPC decision event indices to judge')
    parser.add_argument('--continuations', type=int, default=16)
    args = parser.parse_args(argv)
    if args.judge:
        from blunder_hunter import card_names
        names = card_names()
        for index in args.judge:
            position, result, rows = judge(args.record, index, args.continuations)
            print('decision %d (%s)' % (index, result.reason))
            for row in rows:
                print('   %-11s %-40s NPC result %.2f  rounds won %.2f' % (row['kind'], describe(position, row['action'], names),
                                                                         row['mean'], row['rounds']))
        return
    for row in review(args.record):
        same = '' if row['game'].split(' (')[0] == row['reference'].split(' (')[0] else '   <- differs'
        print('%4d  game: %-40s python: %-40s %s%s' % (row['index'], row['game'], row['reference'], row['reason'], same))


if __name__ == '__main__':
    main(sys.argv[1:])
