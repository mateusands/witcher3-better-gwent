"""Original fair Gwent determinization boundary for the ISMCTS adapter.

Only own/public Position data and explicit catalog hypotheses enter this module.
No live manager, private opponent deck, or shuffled order is accepted. Modeled
match transitions are isolated; unsupported effects are explicit boundaries.
"""
from dataclasses import dataclass
from .opponent_belief import hypotheses,opponent_view
from .sampled_draws import resolve_draws
from .position import UnsupportedPosition


@dataclass(frozen=True)
class Determinization:
    observer:int
    positions:tuple
    prior:str
    unsupported:int


def determinize(position,context,rng):
    """Fresh sampled opponent hand/counts plus sampled unresolved own draws.

    The three existing sensitivity priors are equally sampled, not calibrated to
    actual opponent collections. Two isolated views share the same sampled public
    cards but retain separate private hands/counts. Future transitions must sync
    public state between them without replacing either private collection.
    """
    beliefs=hypotheses(position,context,3,rng=rng)
    if not beliefs:raise UnsupportedPosition('insufficient public catalog')
    belief=rng.choice(beliefs)
    own=resolve_draws(position,rng)
    other=opponent_view(own,belief)
    own.cards.update(other.cards)
    seats=[None,None];seats[own.player]=own;seats[other.player]=other
    return Determinization(own.player,tuple(seats),belief.prior,belief.unsupported)

from dataclasses import replace,field
from . import constants as C
from .position import ROWS,MODS,LEADER_PICK
from .sequence_search import Context,utility,public_opponent_average
from .response_search import inert_discard


def card_key(position,key):
    """Observable descriptor, never a sampled instance ID or hidden hand index."""
    if key==-1:return None
    card=position.cards[key]
    effects=tuple(sorted((position.cards[k].template,position.cards[k].player,
        position.cards[k].row) for k in card.applied))
    return (card.template,card.owner,card.player,card.row,card.types,card.power,effects,card.banished_on_clear)


def move_key(position,action):
    if action is None:return ('pass',)
    leader=action.source==(position.leaders or {}).get(position.player)
    effect=position.leader_effect(position.player) if leader else None
    weather=leader and (effect in LEADER_PICK or effect==C.CardEffect_Pick_Weather)
    target=('weather',action.target) if weather else card_key(position,action.target)
    return ('leader' if leader else 'card',card_key(position,action.source),
        action.slot,target,tuple((card_key(position,k),row) for k,row in action.chain))



def self_scorch_without_recovery(before,after,action,context):
    """Guard a global Scorch sacrificing only own units without recovery resources.

    This is a targeted search guard, not a proof of dominance under every hidden
    tempo scenario. Keep Medic/resurrection/shuffle/future-draw recovery lines and
    Skellige recovery searchable; exact passed-round enumeration is unaffected.
    """
    if action is None or not before.cards[action.source].has(C.CardEffect_Scorch):return False
    own=before.player;other=1-own
    units=lambda state,side:{k for row in ROWS for k in state.board[side,row]
        if state.cards[k].is_type(C.CardType_Creature)}
    if not units(before,own)-units(after,own) or units(before,other)-units(after,other):return False
    if any(before.cards[k].has(C.CardEffect_Nurse) for k in before.hand):return False
    if any(before.cards[k].has(C.CardEffect_UnsummonDummy) for k in before.hand) and any(
            before.cards[k].has(C.CardEffect_Nurse) for row in ROWS for k in before.board[own,row]):return False
    effect=before.leader_effect(own)
    if before.leader_modeled(own) and effect in (C.CardEffect_Resurect,C.CardEffect_GraveyardShuffle):return False
    if context.own_faction==C.FactionId_Skellige and context.round_index<2:return False
    future_medics=any(n and before.catalog[t].has(C.CardEffect_Nurse) for t,n in before.counts.items())
    drawing=before.unknown_draws or any(before.cards[k].has(C.CardEffect_Draw2) or
        before.cards[k].has(C.CardEffect_UnsummonDummy) for k in before.hand)
    return not (future_medics and drawing)


def synchronize(positions,actor,after):
    """Transfer public effects/locations but retain the other private hand/counts."""
    other=1-actor;old=positions[other]
    remote=old.clone()
    remote.cards=dict(after.cards);remote.board=dict(after.board)
    remote.grave=dict(after.grave);remote.effects=dict(after.effects)
    remote.leaders=dict(after.leaders);remote.leader_ready=dict(after.leader_ready)
    remote.next_key=after.next_key
    result=[None,None];result[actor]=after;result[other]=remote
    return tuple(result)


@dataclass
class GwentState:
    positions:tuple
    to_move:int
    round_index:int
    losses:tuple
    factions:tuple
    passed:tuple=(False,False)
    winner:int|None=None
    limitations:tuple=()
    _legal:dict|None=field(default=None,repr=False)
    _after:dict=field(default_factory=dict,repr=False)
    _unresolved:tuple=field(default=(),repr=False)

    @classmethod
    def from_sample(cls,sample,context):
        own=sample.observer;other=1-own
        losses=[0,0];losses[own]=context.own_losses;losses[other]=context.opponent_losses
        factions=[0,0];factions[own]=context.own_faction;factions[other]=context.opponent_faction
        passed=[False,False];passed[other]=context.opponent_passed
        return cls(sample.positions,own,context.round_index,tuple(losses),tuple(factions),tuple(passed))

    def context(self,side):
        other=1-side
        return Context(self.round_index,self.losses[side],self.losses[other],
            self.passed[other],len(self.positions[other].hand),self.factions[side],
            self.factions[other],self.positions[side].leader_unmodeled(side),
            self.positions[other].leader_unmodeled(other))

    def terminal_reward(self,observer):
        if self.winner is None:return None
        return 0.5 if self.winner==-1 else float(self.winner==observer)

    def information_key(self,observer):
        """Public board/history and observer-owned information only.

        Distinct observed draws/carry outcomes fork the tree. Actual opponent
        sampled identities/counts do not enter this observation key.
        """
        own=self.positions[observer]
        return (self.to_move,self.round_index,self.losses,self.factions,self.passed,
            tuple(sorted((slot,tuple(card_key(own,k) for k in keys)) for slot,keys in own.board.items())),
            tuple((side,tuple(card_key(own,k) for k in own.grave[side])) for side in (0,1)),
            tuple(sorted(card_key(own,k) for k in own.hand)),tuple(sorted(own.counts.items())),
            len(self.positions[1-observer].hand),tuple(sorted(own.leader_ready.items())))

    def legal_actions(self):
        if self.winner is not None:return {}
        if self._legal is not None:return self._legal
        own=self.positions[self.to_move];legal={('pass',):None};skipped=set(self.limitations)
        unresolved=set()
        for action in own.actions():
            try:after=own.apply(action)
            except UnsupportedPosition:
                unresolved.add('unsupported_transition');continue
            if inert_discard(own,after,action) or self_scorch_without_recovery(own,after,action,self.context(self.to_move)):continue
            key=move_key(own,action)
            legal.setdefault(key,action);self._after[key]=after
        if any(not own.supported(own.cards[k]) for k in own.hand):unresolved.add('unsupported_hand')
        if own.leader_unmodeled(own.player):unresolved.add('unsupported_leader')
        effect=own.leader_effect(own.player)
        if own.leader_modeled(own.player) and effect in LEADER_PICK and len(own.weather_templates(*LEADER_PICK[effect]))>1:
            unresolved.add('ambiguous_weather_leader')
        if any(own.cards[k].has(C.CardEffect_Nurse) for k in own.hand) and any(
                not own.supported(own.cards[k]) for k in own.recovery_targets(own.player)):
            unresolved.add('unsupported_recovery')
        self._unresolved=tuple(sorted(unresolved))
        self.limitations=tuple(sorted(skipped|unresolved));self._legal=legal
        return legal

    def unresolved_choices(self):
        """Current actor's missing actions, separately from historical warnings.

        A partial legal-action list is useful for diagnostics, but is not a complete
        decision node. The search must stop before choosing from it. Only sampled
        private state and observer-owned/public data are inspected here.
        """
        if self.winner is not None:return ()
        self.legal_actions()
        return self._unresolved

    def next_state(self,action,rng):
        actor=self.to_move;own=self.positions[actor]
        key=move_key(own,action);legal=self.legal_actions()
        if key not in legal:raise ValueError('illegal Gwent search move')
        passed=list(self.passed);positions=self.positions
        if action is None:passed[actor]=True
        else:
            after=self._after[key]
            positions=synchronize(positions,actor,resolve_draws(after,rng))
            # Position's single-seat projection updates only its own shuffled
            # grave counts. The adapter also knows the hypothetical other counts.
            if action.source==own.leaders.get(actor) and own.leader_effect(actor)==C.CardEffect_GraveyardShuffle:
                remote=positions[1-actor].clone()
                for k in own.recovery_targets(1-actor):
                    template=own.cards[k].template
                    remote.counts[template]=remote.counts.get(template,0)+1
                positions=list(positions);positions[1-actor]=remote;positions=tuple(positions)
        if action is not None:
            active=positions[actor]
            # Native status is automatically DONE when no hand/usable leader is
            # left. Do not insert fictitious extra turns into that round.
            effect=active.leader_effect(actor)
            ambiguous=(active.leader_modeled(actor) and effect in LEADER_PICK and
                len(active.weather_templates(*LEADER_PICK[effect]))>1)
            if not active.hand and not active.leader_actions() and not active.leader_unmodeled(actor) and not ambiguous:
                passed[actor]=True
        result=replace(self,positions=positions,passed=tuple(passed),_legal=None,_after={},_unresolved=())
        if all(passed):return result.finish_round(rng)
        result.to_move=actor if passed[1-actor] else 1-actor
        return result

    def heuristic(self,observer):
        terminal=self.terminal_reward(observer)
        if terminal is not None:return terminal
        own=self.positions[observer];other=self.positions[1-observer]
        return utility(own,self.context(observer),0,own.reserve(),
            public_opponent_average(own),passing=self.passed[observer],opponent_reserve=other.reserve())

    def finish_round(self,rng):
        scores=self.positions[0].scores()
        if scores[0]!=scores[1]:winner=0 if scores[0]>scores[1] else 1
        elif self.factions[0]!=self.factions[1] and C.FactionId_Nilfgaard in self.factions:
            winner=self.factions.index(C.FactionId_Nilfgaard)
        else:winner=-1
        losses=tuple(n+int(winner!=side) for side,n in enumerate(self.losses))
        if max(losses)>=2 or self.round_index==2:
            final=-1 if losses[0]==losses[1] else (0 if losses[0]<losses[1] else 1)
            return replace(self,losses=losses,winner=final,_legal=None,_after={},_unresolved=())
        positions=clear_round(self.positions,self.factions,rng)
        result=replace(self,positions=positions,round_index=self.round_index+1,
            losses=losses,passed=(False,False),to_move=self.to_move if winner==-1 else winner,
            _legal=None,_after={},_unresolved=())
        if winner!=-1 and self.factions[winner]==C.FactionId_Northern_Kingdom:
            own=result.positions[winner].clone()
            own.unknown_draws=min(1,sum(own.counts.values()))
            result.positions=synchronize(result.positions,winner,resolve_draws(own,rng))
        if result.round_index==2:
            for side in (0,1):
                if self.factions[side]==C.FactionId_Skellige:
                    result.positions=recover_skellige(result.positions,side,rng)
        # Native BasePlayerController.resetCurrentRoundStatus() reactivates only
        # a nonempty hand. A leader alone does not reset an explicit prior pass.
        result.passed=tuple(not p.hand for p in result.positions)
        if all(result.passed):return result.finish_round(rng)
        if result.passed[result.to_move]:result.to_move=1-result.to_move
        return result


def clear_round(positions,factions,rng):
    state=positions[0].clone();kept={}
    for side in (0,1):
        units=[k for row in ROWS for k in state.board[side,row]
            if state.cards[k].is_type(C.CardType_Creature) and not state.cards[k].is_type(C.CardType_Hero)]
        kept[side]=rng.choice(units) if units and factions[side]==C.FactionId_No_Mans_Land else None
    for key in tuple(state.board[-1,9]):state.remove_from_board(key)
    for side in (0,1):
        for row in (*ROWS,8,7,6):
            for key in tuple(state.board[side,row]):
                if key==kept[side]:continue
                card=state.cards[key]
                if card.has(C.CardEffect_SuicideSummon):
                    raise UnsupportedPosition('round-clear death summons')
                state.remove_from_board(key,grave=not card.banished_on_clear)
    return synchronize(positions,0,state)


def recover_skellige(positions,side,rng):
    own=positions[side].clone();eligible=list(own.recovery_targets(side))
    for _ in range(min(2,len(eligible))):
        key=rng.choice(eligible);eligible.remove(key)
        if key not in own.grave[side]:raise UnsupportedPosition('Skellige recovery changed candidate pool')
        card=own.cards[key]
        if not own.supported(card):raise UnsupportedPosition('unsupported Skellige recovered effect')
        chains=own.recovery_chains(side,taken=(key,)) if card.has(C.CardEffect_Nurse) else ((),)
        if not chains:raise UnsupportedPosition('unsupported Skellige recovery chain')
        # Choices within the sampled continuation are rollout choices, not changes
        # to the native recovery rule; non-Medic random recovery remains uniform.
        chain=max(chains,key=lambda c:sum(own.cards[k].power for k,row in c))
        own.grave[side]=tuple(k for k in own.grave[side] if k!=key)
        own.place_unit(key,own.default_row(card),1-side if card.is_type(C.CardType_Spy) else side,chain)
        own=resolve_draws(own,rng)
    return synchronize(positions,side,own)
