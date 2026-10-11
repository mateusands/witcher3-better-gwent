"""Original bounded own-action search with explicit pass and match-resource utility.

The move transitions are deterministic where supported. Opponent replies and future
rounds use visible-data heuristics, not solved win probabilities. No hidden hand or
future draw order is sampled. Re-plan after every real turn.
"""
from . import tuning
from dataclasses import dataclass,asdict,replace
from math import exp,sqrt
from . import constants as C
from .position import UnsupportedPosition,ROWS
from .options import Difficulty,PROFILES


@dataclass(frozen=True)
class Context:
    round_index:int
    own_losses:int
    opponent_losses:int
    opponent_passed:bool
    opponent_hand_count:int
    own_faction:int
    opponent_faction:int
    own_leader_available:bool=False
    opponent_leader_available:bool=False

    @property
    def wins_ties(self):
        return self.own_faction==C.FactionId_Nilfgaard and self.opponent_faction!=self.own_faction


@dataclass(frozen=True)
class SearchResult:
    action:object
    sequence:tuple
    utility:float
    pass_utility:float
    nodes:int
    profile:str
    unsupported:int
    reason:str
    revision:str='sequence-v6'

    def audit(self):
        return asdict(self)


def sigmoid(x):
    return 1/(1+exp(-max(-30,min(30,x))))


def public_opponent_average(position):
    other=1-position.player
    known=[c.power for c in position.cards.values() if c.owner==other and
        c.player==other and c.row in (*ROWS,2) and c.is_type(C.CardType_Creature)]
    # A prior avoids extrapolating a whole unseen hand from a single revealed card.
    return (24+sum(known))/(4+len(known))


def faction_carry(position,side,faction,next_round):
    if faction==C.FactionId_No_Mans_Land:
        units=[position.cards[k] for row in ROWS for k in position.board[side,row]
               if position.cards[k].is_type(C.CardType_Creature) and not position.cards[k].is_type(C.CardType_Hero)]
        return sum(c.power for c in units)/len(units) if units else 0
    if faction==C.FactionId_Skellige and next_round==2:
        units=[position.cards[k] for k in position.grave[side]]+[
            position.cards[k] for row in ROWS for k in position.board[side,row]]
        eligible=[c for c in units if c.is_type(C.CardType_Creature) and not c.is_type(C.CardType_Hero)]
        # A recovered spy adds power to the other side. Medic/Muster secondary
        # effects remain outside this expected carry estimate.
        return min(2,len(eligible))*sum((-c.power if c.is_type(C.CardType_Spy) else c.power) for c in eligible)/len(eligible) if eligible else 0
    return 0


def utility(position,context,depth,reserve,opponent_mean,passing=False,opponent_reserve=None):
    T=tuning.ACTIVE
    own=position.player;other=1-own;scores=position.scores()
    replies=0 if context.opponent_passed else max(0,depth-1)
    count=max(0,context.opponent_hand_count-replies)
    gap=scores[own]-scores[other]-replies*opponent_mean
    leader_credit=T['leader_credit'] if context.opponent_leader_available else 0
    opposing=(count*opponent_mean if opponent_reserve is None else opponent_reserve)+leader_credit
    scale=T['scale_base']+sqrt(max(1,count))*T['scale_slope']
    tied_match_win=(gap==0 and context.opponent_losses>=1 and context.own_losses==0 and
        not (context.opponent_faction==C.FactionId_Nilfgaard and context.own_faction!=context.opponent_faction))
    wins=gap>=0 if context.wins_ties else gap>0
    if context.opponent_passed and tied_match_win:return 1
    if not position.hand and not position.unknown_draws and not context.own_leader_available \
            and not position.leader_modeled(own):
        passing=True
    if context.opponent_passed:
        round_prospect=float(wins)
    elif passing:
        # Passing while behind gives the opponent a secured round. While ahead,
        # account for the visible hand count and uncertain remaining strength.
        round_prospect=sigmoid((gap-T['pass_risk']*opposing)/scale) if wins else 0
    else:
        # Initiative plus remaining resources is a heuristic, not a calibrated
        # probability of eventually winning this round.
        round_prospect=sigmoid((gap+(reserve-opposing)*T['reserve_weight'])/scale)
    if context.opponent_losses>=1 and context.own_losses>=1 or context.round_index==2:
        if context.opponent_passed and gap==0 and (
            context.own_faction==context.opponent_faction or
            C.FactionId_Nilfgaard not in (context.own_faction,context.opponent_faction)):
            return 0.5  # Both lose the final life: a drawn match, not a defeat.
        return round_prospect
    next_round=context.round_index+1
    own_future=reserve+faction_carry(position,own,context.own_faction,next_round)
    other_future=opposing+faction_carry(position,other,context.opponent_faction,next_round)
    own_draw=0
    if context.own_faction==C.FactionId_Northern_Kingdom and sum(position.counts.values()):
        own_draw=sum(position.catalog[t].power*n for t,n in position.counts.items())/sum(position.counts.values())
    enemy_draw=opponent_mean if context.opponent_faction==C.FactionId_Northern_Kingdom else 0
    if context.opponent_passed and gap==0 and context.own_losses==context.opponent_losses==0 and (
        context.own_faction==context.opponent_faction or
        C.FactionId_Nilfgaard not in (context.own_faction,context.opponent_faction)):
        # An ordinary first-round draw removes a life from both sides. The next
        # round is decisive; neither side receives a Northern Kingdoms win draw.
        return sigmoid((own_future-other_future)/scale)
    # Winning once permits a later concession; losing requires two wins. The
    # reserve advantage is evaluated separately for those outcomes.
    future_leading=sigmoid((own_future+own_draw-other_future+T['future_edge']*opponent_mean)/scale)
    future_trailing=sigmoid((own_future-other_future-enemy_draw-T['future_edge']*opponent_mean)/scale)
    if context.opponent_losses>=1:
        return round_prospect+(1-round_prospect)*future_leading
    if context.own_losses>=1:
        return round_prospect*future_leading
    return round_prospect*future_leading+(1-round_prospect)*future_trailing


def overtaking_bounds(position):
    """Optimistic own ceiling / pessimistic opponent floor for supported effects.

    Overestimate combinations and destruction deliberately. A failed chase is
    proven only if even those generous bounds cannot win. Unknown draws/recovery
    prevent this proof; the heuristic search remains separate.
    """
    own=position.player;other=1-own
    hand=[position.cards[k] for k in position.hand]
    if any(not position.supported(c) or c.has(C.CardEffect_Draw2) for c in hand):return None
    roster=[position.cards[k] for row in ROWS for k in position.board[own,row]]+hand
    if any(c.has(C.CardEffect_UnsummonDummy) for c in hand) and any(c.has(C.CardEffect_Draw2) for c in roster):return None
    units={c.key:c for c in roster if c.is_type(C.CardType_Creature)}
    templates=set()
    for c in units.values():
        if c.has(C.CardEffect_SummonClones):templates.update(c.targets)
    for template in templates:
        t=position.catalog[template]
        if not position.supported(t) or t.has(C.CardEffect_Draw2):return None
        for index in range(position.counts.get(template,0)):
            key=-(template*10000+index+1)
            units[key]=replace(t,key=key)
    units=tuple(units.values())
    if any(any(c.has(e) for e in (C.CardEffect_SuicideSummon,C.CardEffect_Morph,C.CardEffect_Mushroom)) for c in units):return None
    if any(c.has(C.CardEffect_UnsummonDummy) for c in hand) and any(not position.supported(c) for c in units):return None
    external=[position.cards[k] for row in ROWS for k in position.effects[own,row]
              if k not in {u.key for u in units}]
    horn=any(any(c.has(e) for e in (C.CardEffect_Horn,C.CardEffect_Melee_Horn,
                 C.CardEffect_Range_Horn,C.CardEffect_Siege_Horn)) for c in (*roster,*external))
    ceiling=0
    for unit in units:
        if unit.is_type(C.CardType_Hero):ceiling+=unit.power;continue
        bonds=sum(c.key!=unit.key and c.has(C.CardEffect_SameTypeMorale) and
                  (unit.template in c.targets or c.key in unit.applied) for c in units)
        morale=sum(c.key!=unit.key and c.has(C.CardEffect_ImproveNeighbours) for c in (*units,*external))
        base=unit.power*(2 if unit.is_type(C.CardType_Spy) and position.double_spy else 1)
        ceiling+=(base*(1+bonds)+morale)*(2 if horn else 1)
    destroyed=set()
    weather_rows=set()
    for c in hand:
        if c.has(C.CardEffect_Scorch):destroyed.update(ROWS)
        for effect,row in ((C.CardEffect_MeleeScorch,5),(C.CardEffect_RangedScorch,4),(C.CardEffect_Siege_Scorch,3)):
            if c.has(effect):destroyed.add(row)
        if c.is_type(C.CardType_Weather):
            for effect,row in ((C.CardEffect_Melee,5),(C.CardEffect_Ranged,4),(C.CardEffect_Siege,3)):
                if c.has(effect):weather_rows.add(row)
    floor=0
    for row in ROWS:
        for key in position.board[other,row]:
            c=position.cards[key]
            if c.is_type(C.CardType_Hero):floor+=c.power;continue
            if row in destroyed:continue
            value=position.power(key)
            if row in weather_rows:
                weather=next(c for c in hand if c.is_type(C.CardType_Weather) and c.has({5:C.CardEffect_Melee,4:C.CardEffect_Ranged,3:C.CardEffect_Siege}[row]))
                projected=position.clone();projected.add_effect(key,weather.key)
                value=min(value,projected.power(key))
            floor+=value
    return ceiling,floor

def choose_sequence(position,context,difficulty=Difficulty.HARD):
    profile=PROFILES[Difficulty(difficulty)]
    max_nodes=max(32,profile.search_depth*profile.beam_width*12)
    mean=public_opponent_average(position)
    cache={}
    def reserve(state):
        key=state.reserve_key()
        if key not in cache:cache[key]=state.reserve()
        return cache[key]
    initial_reserve=reserve(position)
    pass_value=utility(position,context,0,initial_reserve,mean,passing=True)
    scores=position.scores();own=position.player
    tie_finishes_match=(context.opponent_losses>=1 and context.own_losses==0 and
        not (context.opponent_faction==C.FactionId_Nilfgaard and context.own_faction!=context.opponent_faction))
    secured=context.opponent_passed and (scores[own]>=scores[1-own] if context.wins_ties or tie_finishes_match else scores[own]>scores[1-own])
    if secured and (context.opponent_losses>=1 or context.round_index>=2):
        return SearchResult(None,(),1,1,0,profile.label,0,'pass_for_match_resources')
    can_pass=not context.own_losses and not context.own_leader_available or secured
    # Do not declare a chase impossible from an unmodeled recovery/leader choice.
    if any(not position.supported(position.cards[k]) for k in position.hand) and not secured:can_pass=False
    bounds=overtaking_bounds(position) if can_pass and context.round_index==1 and context.opponent_losses==1 else None
    if bounds is not None and (bounds[0]<bounds[1] if context.wins_ties or tie_finishes_match else bounds[0]<=bounds[1]):
        return SearchResult(None,(),pass_value,pass_value,0,profile.label,0,'proven_no_supported_overtake')
    best_value=pass_value if can_pass else -1
    best_sequence=();beam=[(position,())];nodes=0;unsupported=0;root_gains={}
    for _ in range(profile.search_depth):
        candidates=[]
        for state,sequence in beam:
            if state.unknown_draws:continue
            for action in state.actions():
                if nodes>=max_nodes:break
                nodes+=1
                try:after=state.apply(action)
                except UnsupportedPosition:unsupported+=1;continue
                path=sequence+(action,)
                if not sequence:
                    sc=after.scores();root_gains[action]=(sc[own]-sc[1-own])-(scores[own]-scores[1-own])
                value=utility(after,context,len(path),reserve(after),mean)
                # Against a passed opponent, any attainable finish is exact. Keep
                # the greatest future reserve when several finishes are possible.
                if context.opponent_passed:
                    sc=after.scores();winning=sc[own]>=sc[1-own] if context.wins_ties or tie_finishes_match else sc[own]>sc[1-own]
                    if winning:value+=0.00001*reserve(after)-0.000001*len(path)
                sc=after.scores()
                net_gain=(sc[own]-sc[1-own])-(scores[own]-scores[1-own])
                beneficial=net_gain>0 or reserve(after)>initial_reserve or after.unknown_draws>0
                if beneficial and (value>best_value+1e-12 or (best_sequence and abs(value-best_value)<1e-12 and
                        root_gains[path[0]]>root_gains[best_sequence[0]])):
                    best_value,best_sequence=value,path
                candidates.append((value,after,path))
            if nodes>=max_nodes:break
        candidates.sort(key=lambda entry:entry[0],reverse=True)
        beam=[(state,path) for value,state,path in candidates[:profile.beam_width]]
        if not beam or nodes>=max_nodes:break
    return SearchResult(best_sequence[0] if best_sequence else None,best_sequence,best_value,
        pass_value,nodes,profile.label,unsupported,
        'pass_for_match_resources' if not best_sequence and can_pass else
        'supported_sequence' if best_sequence else 'no_supported_plan')
