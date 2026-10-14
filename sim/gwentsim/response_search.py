"""Experimental public-belief search with explicit alternating opponent moves.

Hypotheses are provisional sensitivity scenarios, not clairvoyance or calibrated
probabilities. Only supported transitions are searched; unsupported hand effects
and available leaders are recorded as unresolved. Native execution is unchanged.
"""
from dataclasses import dataclass,replace,asdict
from . import constants as C
from .options import Difficulty,PROFILES
from .position import UnsupportedPosition,ROWS
from .opponent_belief import hypotheses,opponent_view
from .sequence_search import choose_sequence,utility,public_opponent_average


@dataclass(frozen=True)
class ResponseResult:
    action:object
    value:float
    pass_value:float
    samples:int
    nodes:int
    unsupported:int
    unresolved_leader:bool
    reason:str
    alternatives:tuple=()
    budget_exhausted:bool=False
    revision:str='response-v7'

    def audit(self):return asdict(self)


class SearchBudgetReached(Exception):
    pass


def tie_match(context):
    return context.opponent_losses>=1 and context.own_losses==0 and not (
        context.opponent_faction==C.FactionId_Nilfgaard and
        context.own_faction!=context.opponent_faction)


def secured(position,context):
    scores=position.scores();gap=scores[position.player]-scores[1-position.player]
    return gap>=0 if context.wins_ties or tie_match(context) else gap>0


def inert_discard(before,after,action):
    card=before.cards[action.source]
    if action.source==(before.leaders or {}).get(before.player):
        # A leader use that changes nothing public or own (e.g. the AI's view-hand
        # ability) only spends the leader.
        return (before.board,before.grave,before.hand,before.counts)==(after.board,after.grave,after.hand,after.counts)
    return (card.has(C.CardEffect_Scorch) or card.is_type(C.CardType_Weather)) and before.board==after.board


def self_harm(before,after,action):
    """V8 skips what inert_discard skips, plus a spell Scorch that leaves every opponent
    row untouched: it destroys nothing or only our own units and only lowers our own
    score (in-game match g151). A unit with Scorch (Clan Dimun Pirate) still adds its
    own power and stays searchable. The ISMCTS kernel keeps its own guard, which allows
    a Medic follow-up."""
    if inert_discard(before,after,action):return True
    from . import response_v8
    if response_v8.flag('allow-self-harm',before.player):return False  # Lab switch: the rule before g151
    card=before.cards[action.source]
    if action.source==(before.leaders or {}).get(before.player) or not card.has(C.CardEffect_Scorch) \
            or card.is_type(C.CardType_Creature):
        return False
    other=1-before.player
    return all(before.board[other,row]==after.board[other,row] for row in ROWS)


@dataclass(frozen=True)
class SearchSettings:
    samples:int
    budget:int
    beam:int
    pass_margin:float
    caution:float
    fusion:float=1.0


def search_settings(difficulty,seat,context=None):
    """Search size for this seat: the shipped values, changed only by Lab switches on the NPC seat
    (beliefsN, nodesN, budget-half, beamN, passN, cautionN, fusionN). With the Original NPC decks the
    second ply keeps 20% of its gain (fusion20, proven there)."""
    from . import response_v8
    difficulty=Difficulty(difficulty)
    samples=2 if difficulty==Difficulty.EASY else 4 if difficulty!=Difficulty.EXPERT else 6
    budget=(512,768,2048,8192)[int(difficulty)]
    beam=PROFILES[difficulty].beam_width;pass_margin=0.0;caution=0.0
    fusion=0.2 if context is not None and getattr(context,'original_decks',False) else 1.0
    if response_v8.flag('budget-half',seat):budget//=2  # experiment: thinking time vs strength
    for f in response_v8.VARIANT:
        if not response_v8.flag(f,seat):continue
        for prefix in ('nodes','beliefs','beam','pass','caution','fusion'):
            if f.startswith(prefix) and f[len(prefix):].isdigit():
                n=int(f[len(prefix):])
                if prefix=='nodes':budget=n  # e.g. nodes1024 (difficulty ladder study)
                elif prefix=='beliefs':samples=n
                elif prefix=='beam':beam=n
                elif prefix=='pass':pass_margin=n/1000
                elif prefix=='caution':caution=n/100
                else:fusion=n/100
    return SearchSettings(samples,budget,beam,pass_margin,caution,fusion)


def combine(values,caution):
    """Value over the imagined hands: the mean, moved towards the worst hand by `caution`."""
    mean=sum(values)/len(values)
    return mean-caution*(mean-min(values))


def second_ply(one,two,fusion):
    """A move's value in one imagined hand after the second ply: the one-ply value plus the share
    `fusion` of what the second ply adds (that gain assumes the search knows the hand)."""
    return one+fusion*(two-one)


def choose_response(position,context,difficulty=Difficulty.HARD):
    profile=PROFILES[Difficulty(difficulty)]
    settings=search_settings(difficulty,position.player,context)
    if context.opponent_passed:
        exact=choose_sequence(position,context,difficulty)
        return ResponseResult(exact.action,exact.utility,exact.pass_utility,0,exact.nodes,
            exact.unsupported,False,exact.reason)
    beliefs=hypotheses(position,context,settings.samples)
    if not beliefs:
        return ResponseResult(None,0,0,0,0,0,context.opponent_leader_available,'insufficient_public_catalog')
    mean=public_opponent_average(position);reserve_cache={}
    def reserve(state):
        key=state.reserve_key()
        if key not in reserve_cache:reserve_cache[key]=state.reserve()
        return reserve_cache[key]
    nodes=0;unsupported=sum(h.unsupported for h in beliefs);exhausted=False
    budget=settings.budget
    def charge():
        nonlocal nodes
        if nodes>=budget:raise SearchBudgetReached()
        nodes+=1
    # Worst supported one-turn response in each hypothesized hand. This includes
    # public destruction/weather effects, rather than subtracting a mean power.
    def response(state,hypothesis,passing=False):
        nonlocal nodes,unsupported
        view=opponent_view(state,hypothesis)
        def value(after,enemy_passed=False):
            own=after.clone();own.player=position.player
            own.hand=state.hand;own.counts=dict(state.counts)
            own.unknown_draws=state.unknown_draws;own.draw_value=state.draw_value
            # A modeled opponent leader is searched as a reply and valued in its
            # reserve; only an unmodeled one keeps the generic leader credit.
            ctx=replace(context,opponent_hand_count=len(after.hand)+after.unknown_draws,
                opponent_passed=enemy_passed,opponent_leader_available=after.leader_unmodeled(after.player))
            return utility(own,ctx,1,reserve(own),mean,passing=passing,
                opponent_reserve=reserve(after)),own,HypothesisState(after),enemy_passed
        # Opponent passing is available when safe to concede, or when it secures
        # the round/match after our pass. Critical losing passes are excluded.
        flipped=replace(context,own_losses=context.opponent_losses,
            opponent_losses=context.own_losses,own_faction=context.opponent_faction,
            opponent_faction=context.own_faction)
        choices=[]
        if not flipped.own_losses or (passing and secured(view,flipped)):
            choices.append(value(view,True))
        for action in view.actions():
            charge()
            try:after=view.apply(action)
            except UnsupportedPosition:unsupported+=1;continue
            choices.append(value(after))
        if not choices:choices.append(value(view,True))
        return min(choices,key=lambda entry:entry[0])
    def HypothesisState(view):
        # Retain only this hypothetical remaining hand/counts. Never introduce
        # these cards into the real runtime or into the acting player's hand.
        from .opponent_belief import Hypothesis
        return Hypothesis(tuple(view.cards[k] for k in view.hand),tuple(sorted(view.counts.items())),
            sum(not view.supported(view.cards[k]) for k in view.hand),'continuation')
    try:pass_values=[response(position,h,True)[0] for h in beliefs]
    except SearchBudgetReached:
        return ResponseResult(None,0,0,len(beliefs),nodes,unsupported,
            context.opponent_leader_available,'no_supported_plan',budget_exhausted=True)
    pass_value=combine(pass_values,settings.caution)
    can_pass=not context.own_losses and not context.own_leader_available
    if any(not position.supported(position.cards[k]) for k in position.hand):can_pass=False
    best_value=pass_value+settings.pass_margin if can_pass else -1;best=None
    roots=[]
    for action in position.actions():
        try:charge()
        except SearchBudgetReached:exhausted=True;break
        try:state=position.apply(action)
        except UnsupportedPosition:unsupported+=1;continue
        # A Scorch that destroys nothing and discarded duplicate/empty-clear
        # weather cannot prepare a future combination. Do not burn them merely
        # because the abstract utility rewards forcing another opponent turn.
        if self_harm(position,state,action):continue
        try:outcomes=[response(state,h) for h in beliefs]
        except SearchBudgetReached:exhausted=True;break
        value=combine([x[0] for x in outcomes],settings.caution)
        roots.append((value,action,state,outcomes))
        if value>best_value+1e-12:best_value,best=value,action
    # Beam limits root continuations. Every explored own continuation receives a
    # further concrete reply; no imaginary uncontested own-turn sequence.
    roots.sort(key=lambda item:item[0],reverse=True)
    if profile.search_depth>=2 and not exhausted:
        for _,root,state,outcomes in roots[:settings.beam]:
            values=[]
            for value,public,h,enemy_passed in outcomes:
                if public.unknown_draws or not public.hand:
                    values.append(value);continue
                if enemy_passed:
                    exact=choose_sequence(public,replace(context,opponent_passed=True,
                        opponent_hand_count=len(h.hand)),difficulty)
                    values.append(exact.utility);continue
                future=value
                for action in public.actions():
                    try:charge()
                    except SearchBudgetReached:exhausted=True;break
                    try:after=public.apply(action)
                    except UnsupportedPosition:unsupported+=1;continue
                    if self_harm(public,after,action):continue
                    try:future=max(future,response(after,h)[0])
                    except SearchBudgetReached:exhausted=True;break
                if exhausted:break
                values.append(second_ply(value,future,settings.fusion))
            if exhausted:break
            value=combine(values,settings.caution)
            if value>best_value+1e-12:best_value,best=value,root
    alternatives=tuple(dict(action=asdict(action),oneTurnValue=value)
        for value,action,state,outcomes in roots)
    return ResponseResult(best,best_value,pass_value,len(beliefs),nodes,unsupported,
        context.opponent_leader_available,'supported_response' if best else
        'pass_for_match_resources' if can_pass else 'no_supported_plan',alternatives,exhausted)
