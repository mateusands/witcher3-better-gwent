"""Feed recorded human commands into the headless game, never recorded outcomes.

The event cursor synchronizes input with actual simulator output. AI commands are
not fed back: the vanilla AI must independently choose and apply its own moves.
"""
from .headless import Scheduler, SimulationStall, CardTweenManager
from .card_manager import CardManager
from .card_leader_instance import CardLeaderInstance
from .small import CardTransaction

CHOICES = {
    'mulligan': 'handleAcceptMulligan', 'nomulligan': 'handleDeclineMulligan',
    'nurse': 'handleNurseChoice', 'handshow': 'handleHandShowClose',
    'resurrect': 'handleResurrectChoice', 'weather': 'handleCardDrawChoice_Weather',
    'bin': 'handleBinChoice', 'pick': 'handlePickChoice',
}


class ScriptedInput:
    def __init__(self, flow, recorder, events):
        self.flow, self.recorder, self.events = flow, recorder, events
        self.finished = False
        self.pending = None
        self.last_count = -1
        self.last_progress = Scheduler.current().now

    def fail(self, message):
        raise SimulationStall('scripted input at event %d: %s' % (len(self.recorder.events), message))

    def card(self, pair):
        card = CardManager.getInstance().getCardInstance(pair[1])
        if card is None or card.templateId != pair[0]:
            self.fail('card does not exist: %s' % pair)
        return card

    def tick(self):
        count = len(self.recorder.events)
        now = Scheduler.current().now
        if count != self.last_count:
            self.last_count, self.last_progress = count, now
        elif now - self.last_progress > 30000:
            self.fail('no output for 30 virtual seconds (flow=%s, human=%s)' %
                      (self.flow.stateMachine.currentState, self.flow.playerControllers[0]._stateMachine.currentState))
        if count >= len(self.events):
            return
        event = self.events[count]
        human = self.flow.playerControllers[0]
        if self.pending is not None:
            if human._stateMachine.currentState == 'ChoosingCard' and not CardTweenManager.getInstance().isAnyCardMoving():
                human._decidedCardTransaction = self.pending
                self.pending = None
                human._stateMachine.ChangeState('ApplyingCard')
            return
        if event['k'] == 'C':
            dialog = self.flow.mcChoiceDialog
            if not dialog.visible:
                return
            choice = event['choice']
            name = CHOICES.get(choice)
            callbacks = [dialog.acceptCallback, dialog.declineCallback]
            callback = next((cb for cb in callbacks if cb is not None and cb.__name__ == name), None)
            if callback is None:
                self.fail('choice %s does not belong to the open dialog' % choice)
            arg = event['arg']
            if choice == 'nomulligan':
                callback()
            else:
                arg = int(arg)
                ids = [c.index if dialog.templates else c.instanceId for c in dialog.sourceList]
                if choice != 'handshow' and arg not in ids:
                    self.fail('choice %s:%s is not offered: %s' % (choice, arg, ids))
                callback(arg)
        elif event['k'] == 'H' and event['player'] == 0:
            if human._stateMachine.currentState != 'ChoosingCard' or human._stateMachine.awaitingNextState:
                return
            tx_data = event['tx']
            src = self.card(tx_data['source'])
            cm = CardManager.getInstance()
            if src not in cm.getCardInstanceList(1, 0) and src is not cm.getCardLeader(0):
                self.fail('source is outside the human hand/leader')
            if isinstance(src, CardLeaderInstance) and not src.canBeUsed:
                self.fail('leader cannot be used')
            tx = CardTransaction()
            tx.sourceCardInstanceRef = src
            tx.targetSlotID = tx_data['slot']
            tx.targetPlayerID = tx_data['targetPlayer']
            if tx.targetSlotID != -1 and not src.canBePlacedInSlot(tx.targetSlotID, tx.targetPlayerID):
                self.fail('card cannot be placed in the recorded row')
            if tx_data['target'] is not None:
                tx.targetCardInstanceRef = self.card(tx_data['target'])
                if not src.canBeCastOn(tx.targetCardInstanceRef):
                    self.fail('card cannot be cast on the recorded target')
            human.startCardTransaction(src.instanceId)
            self.pending = tx
        elif event['k'] == 'P':
            if event['player'] != 0:
                self.fail('only the human can produce P')
            if human._stateMachine.currentState == 'ChoosingCard' and not human._stateMachine.awaitingNextState:
                human.skipTurn()
        elif event['k'] == 'E' and event['reason'] == 'quit':
            self.recorder.record('E', 'quit')
            self.finished = count + 1 == len(self.events)
