"""Original immutable public-position model for bounded decision search.

Captures own hand/deck counts and public cards/effects only. No opponent private
cards, deck composition or shuffled draw order. Unsupported death/choice effects
are explicit; never silently modeled as ordinary units.
"""
from collections import Counter
from dataclasses import dataclass, replace

from . import constants as C
from .future_value import ReserveCard, ROW_TYPES, supported_reserve_power

ROWS=(5,4,3)
MODS={5:8,4:7,3:6}
ROW_FLAGS={5:C.CardType_Melee,4:C.CardType_Ranged,3:C.CardType_Siege}
SIMPLE={C.CardEffect_None,C.CardEffect_ImproveNeighbours,C.CardEffect_SameTypeMorale,
        C.CardEffect_Horn,C.CardEffect_SummonClones,C.CardEffect_Draw2,
        C.CardEffect_MeleeScorch,C.CardEffect_RangedScorch,C.CardEffect_Siege_Scorch,
        C.CardEffect_Nurse}
# Units whose recovered value the reserve estimate can place without further choices.
RESERVE_SIMPLE={C.CardEffect_None,C.CardEffect_ImproveNeighbours,C.CardEffect_SameTypeMorale,
                C.CardEffect_SummonClones,C.CardEffect_Nurse}


LEADER_HORN={C.CardEffect_Melee_Horn:5,C.CardEffect_Range_Horn:4,C.CardEffect_Siege_Horn:3}
LEADER_SCORCH={C.CardEffect_MeleeScorch:5,C.CardEffect_RangedScorch:4,C.CardEffect_Siege_Scorch:3}
# Native deck lookups for the weather leaders: (required effect, excluded effect).
LEADER_PICK={C.CardEffect_Pick_Fog:(C.CardEffect_Ranged,C.CardEffect_Siege),
             C.CardEffect_Pick_Frost:(C.CardEffect_Melee,None),
             C.CardEffect_Pick_Rain:(C.CardEffect_Siege,None)}
# Leader abilities modeled as explicit actions. Passive leaders have no action;
# discard-2-draw-1 is a hidden-card choice and stays unsupported.
LEADER_ACTIONS={*LEADER_HORN,*LEADER_SCORCH,*LEADER_PICK,C.CardEffect_Pick_Weather,
    C.CardEffect_Clear_Weather,C.CardEffect_Resurect,C.CardEffect_Resurect_Enemy,
    C.CardEffect_View_3_Enemy,C.CardEffect_GraveyardShuffle,C.CardEffect_AgileReposition}


class UnsupportedPosition(ValueError):
    pass


@dataclass(frozen=True)
class Card:
    key:int
    template:int
    power:int
    types:int
    effects:tuple
    targets:tuple
    owner:int
    player:int
    row:int
    applied:tuple=()
    faction:int=C.FactionId_Neutral
    banished_on_clear:bool=False

    def is_type(self,flag):
        return (self.types & flag)==flag

    def has(self,flag):
        return flag in self.effects


@dataclass(frozen=True)
class Action:
    source:int
    slot:int=-1
    target:int=-1
    # Medic recovery chain: ((grave key, row), ...), one entry per recovery in order.
    chain:tuple=()


@dataclass
class Position:
    player:int
    cards:dict
    hand:tuple
    board:dict
    grave:dict
    effects:dict
    counts:dict
    catalog:dict
    half_weather:tuple
    double_spy:bool
    weights:dict
    unknown_draws:int=0
    draw_value:float=0
    next_key:int=-10000000
    random_recovery:bool=False
    # Leader instance key per side (public) and whether it can still be used.
    leaders:dict=None
    leader_ready:dict=None

    @classmethod
    def from_manager(cls,cm,player):
        cards={}
        def observe(unit):
            if unit.instanceId in cards:return
            t=unit.templateRef
            cards[unit.instanceId]=Card(unit.instanceId,unit.templateId,t.power,t.typeArray,
                tuple(t.effectFlags),tuple(t.summonFlags or ()),unit.owningPlayer,
                unit.listsPlayer,unit.inList,tuple(x.instanceId for x in unit.effectedByCardsRefList),t.factionIdx,
                bool(unit.BanishInsteadOfGraveyard))
            for effect in unit.effectedByCardsRefList:observe(effect)
        hand=cm.getCardInstanceList(1,player)
        for unit in hand:observe(unit)
        board={};grave={};effects={}
        for side in (0,1):
            grave[side]=tuple(u.instanceId for u in cm.getCardInstanceList(2,side))
            for unit in cm.getCardInstanceList(2,side):observe(unit)
            for row in (*ROWS,6,7,8):
                board[side,row]=tuple(u.instanceId for u in cm.getCardInstanceList(row,side))
                for unit in cm.getCardInstanceList(row,side):observe(unit)
            for row in ROWS:
                active=cm.cardEffectManager.getEffectsForList(row,side)
                effects[side,row]=tuple(u.instanceId for u in active)
                for unit in active:observe(unit)
        board[-1,9]=tuple(u.instanceId for u in cm.getCardInstanceList(9,-1))
        for unit in cm.getCardInstanceList(9,-1):observe(unit)
        leaders={};leader_ready={}
        for side in (0,1):
            leader=cm.getCardLeader(side)
            leaders[side]=leader.instanceId if leader else None
            if leader:observe(leader)
            # Own: full native usability. Opponent: only the public used/countered
            # state; whether its deck still holds a weather card is not observed.
            leader_ready[side]=bool(leader and (leader.canBeUsed if side==player else leader._canBeUsed))
        catalog={t.index:Card(0,t.index,t.power,t.typeArray,tuple(t.effectFlags),
                    tuple(t.summonFlags or ()),player,player,1,faction=t.factionIdx) for t in cm._cardTemplates.values()}
        return cls(player,cards,tuple(u.instanceId for u in hand),board,grave,effects,
            dict(Counter(cm.playerDeckDefinitions[player].cardIndicesInDeck)),catalog,
            tuple(cm.halfWeatherEnabled(side) for side in (0,1)),
            cm.cardEffectManager.doubleSpyEnabled,
            dict(cm.cardValues.getEffectValueDictionary(),weather=cm.cardValues.weatherCardValue),
            random_recovery=bool(cm.cardEffectManager.randomResEnabled),
            leaders=leaders,leader_ready=leader_ready)

    def clone(self):
        return replace(self,cards=dict(self.cards),board=dict(self.board),grave=dict(self.grave),
                       effects=dict(self.effects),counts=dict(self.counts),
                       leaders=dict(self.leaders or {0:None,1:None}),
                       leader_ready=dict(self.leader_ready or {0:False,1:False}))

    def power(self,key):
        card=self.cards[key]
        if card.is_type(C.CardType_Hero):return card.power
        active=[self.cards[x] for x in card.applied]
        weather=any(c.is_type(C.CardType_Weather) for c in active)
        base=card.power
        if weather:base=max(0,base//2) if self.half_weather[card.player] else min(1,base)
        if card.is_type(C.CardType_Spy) and self.double_spy:base*=2
        bond=sum(c.has(C.CardEffect_SameTypeMorale) for c in active)
        morale=sum(c.has(C.CardEffect_ImproveNeighbours) for c in active)
        value=base*(1+bond)+morale
        if any(any(c.has(e) for e in (C.CardEffect_Horn,C.CardEffect_Melee_Horn,
                C.CardEffect_Range_Horn,C.CardEffect_Siege_Horn)) for c in active):value*=2
        return value

    def scores(self):
        return tuple(sum(self.power(key) for row in ROWS for key in self.board[side,row]) for side in (0,1))

    def supported(self,card):
        # A random non-hero recovery is not a choice the search could commit to.
        if card.has(C.CardEffect_Nurse) and self.random_recovery and not card.is_type(C.CardType_Hero):return False
        if card.is_type(C.CardType_Creature):return set(card.effects)<=SIMPLE
        if card.is_type(C.CardType_Row_Modifier):return card.has(C.CardEffect_Horn)
        return card.is_type(C.CardType_Weather) or card.has(C.CardEffect_Scorch) or card.has(C.CardEffect_UnsummonDummy)

    def actions(self):
        actions=[]
        for key in self.hand:
            card=self.cards[key]
            if not self.supported(card):continue
            if card.has(C.CardEffect_UnsummonDummy):
                for row in ROWS:
                    for target in self.board[self.player,row]:
                        t=self.cards[target]
                        if t.is_type(C.CardType_Creature) and not t.is_type(C.CardType_Hero):
                            actions.append(Action(key,target=target))
            elif card.is_type(C.CardType_Creature):
                chains=self.recovery_chains(self.player) if card.has(C.CardEffect_Nurse) else ((),)
                for row in ROWS:
                    if card.is_type(ROW_FLAGS[row]):
                        actions.extend(Action(key,row,chain=chain) for chain in chains)
            elif card.is_type(C.CardType_Row_Modifier):
                for row in ROWS:
                    if card.is_type(ROW_FLAGS[row]) and not self.board[self.player,MODS[row]]:
                        actions.append(Action(key,MODS[row]))
            elif card.is_type(C.CardType_Weather):actions.append(Action(key,9))
            elif card.has(C.CardEffect_Scorch):actions.append(Action(key))
        return tuple(actions)+self.leader_actions()

    def recovery_targets(self,side,taken=()):
        # Native eligibility: every non-hero creature in that side's graveyard.
        return tuple(k for k in self.grave[side] if k not in taken
            and self.cards[k].is_type(C.CardType_Creature) and not self.cards[k].is_type(C.CardType_Hero))

    def recovery_chains(self,side,taken=()):
        """Explicit Medic choices. Empty tuple only when nothing is eligible.

        Same-template graveyard copies are equivalent choices. A chain through an
        unsupported recovered effect is omitted rather than modeled as a plain unit.
        """
        eligible=self.recovery_targets(side,taken)
        if not eligible:return ((),)
        chains=[];seen=set()
        for key in reversed(eligible):
            card=self.cards[key]
            if card.template in seen:continue
            seen.add(card.template)
            if not self.supported(card):continue
            rest=self.recovery_chains(side,taken+(key,)) if card.has(C.CardEffect_Nurse) else ((),)
            for row in ROWS:
                if card.is_type(ROW_FLAGS[row]):
                    chains.extend(((key,row),)+tail for tail in rest)
        return tuple(chains)

    def add_effect(self,target,source):
        card=self.cards[target]
        self.cards[target]=replace(card,applied=card.applied+(source,))

    def remove_effect(self,key):
        for target,card in tuple(self.cards.items()):
            if key in card.applied:self.cards[target]=replace(card,applied=tuple(x for x in card.applied if x!=key))
        for slot,active in tuple(self.effects.items()):self.effects[slot]=tuple(x for x in active if x!=key)

    def remove_from_board(self,key,grave=True):
        card=self.cards[key]
        self.board[card.player,card.row]=tuple(x for x in self.board[card.player,card.row] if x!=key)
        self.remove_effect(key)
        if grave:
            destination=card.owner if card.is_type(C.CardType_Weather) else card.player
            self.grave[destination]+= (key,)
            self.cards[key]=replace(card,player=destination,row=2,applied=())

    def place_unit(self,key,row,side,chain=()):
        card=self.cards[key]
        if not self.supported(card):raise UnsupportedPosition('unsupported summoned/recovered unit effect')
        self.cards[key]=replace(card,player=side,row=row,applied=self.effects[side,row])
        existing=self.board[side,row]
        self.board[side,row]=existing+(key,)
        if card.has(C.CardEffect_ImproveNeighbours) or card.has(C.CardEffect_Horn):
            for target in existing:
                unit=self.cards[target]
                if not unit.is_type(C.CardType_Hero) and not unit.has(C.CardEffect_UnsummonDummy):self.add_effect(target,key)
            self.effects[side,row]+= (key,)
        if card.has(C.CardEffect_SameTypeMorale):
            for target in existing:
                unit=self.cards[target]
                if unit.template in card.targets and not unit.is_type(C.CardType_Hero):
                    self.add_effect(target,key);self.add_effect(key,target)
        for effect,enemy_row in ((C.CardEffect_MeleeScorch,5),(C.CardEffect_RangedScorch,4),(C.CardEffect_Siege_Scorch,3)):
            if card.has(effect):
                enemy=1-side
                if sum(self.power(k) for k in self.board[enemy,enemy_row])>=10:self.scorch((enemy,), (enemy_row,))
        if card.has(C.CardEffect_SummonClones):
            if self.unknown_draws:raise UnsupportedPosition('Muster counts uncertain after unresolved draws')
            # Every own hand copy is spent together; no hidden draw order is read.
            for template in card.targets:
                for target in tuple(self.hand):
                    if target in self.hand and self.cards[target].template==template:
                        self.hand=tuple(k for k in self.hand if k!=target)
                        self.place_unit(target,self.default_row(self.cards[target]),side)
                count=self.counts.get(template,0)
                self.counts[template]=0
                for _ in range(count):
                    self.next_key-=1
                    summoned=replace(self.catalog[template],key=self.next_key,
                        owner=self.player,player=self.player)
                    self.cards[summoned.key]=summoned
                    self.place_unit(summoned.key,self.default_row(summoned),side)
        if card.has(C.CardEffect_Draw2):
            if 1-side!=self.player:raise UnsupportedPosition('unobserved opponent draw identities')
            draw=min(2,max(0,sum(self.counts.values())-self.unknown_draws))
            self.unknown_draws+=draw
            total=sum(self.counts.values())
            mean=sum(self.catalog[t].power*n for t,n in self.counts.items())/total if total else 0
            self.draw_value+=draw*mean
        if card.has(C.CardEffect_Nurse):self.recover(card,side,chain)
        elif chain:raise ValueError('recovery chain for a card without Medic')

    def recover(self,card,side,chain):
        # The native Medic resolves after the card's own placement effects; the
        # recovered unit then applies its own effects, including a further Medic.
        eligible=self.recovery_targets(side)
        if not eligible:
            if chain:raise ValueError('recovery chain without eligible targets')
            return
        if not chain:raise UnsupportedPosition('Medic recovery choice not specified')
        (target,row),rest=chain[0],chain[1:]
        if target not in eligible:raise ValueError('ineligible recovery target')
        recovered=self.cards[target]
        if not recovered.is_type(ROW_FLAGS.get(row,-1)):raise ValueError('illegal recovery row')
        self.grave[side]=tuple(k for k in self.grave[side] if k!=target)
        self.place_unit(target,row,1-side if recovered.is_type(C.CardType_Spy) else side,rest)

    @staticmethod
    def default_row(card):
        return next((row for row in ROWS if card.is_type(ROW_FLAGS[row])),-1)

    def scorch(self,sides=(0,1),rows=ROWS):
        eligible=[k for side in sides for row in rows for k in self.board[side,row]
            if not self.cards[k].is_type(C.CardType_Hero) and self.cards[k].is_type(C.CardType_Creature)]
        maximum=max((self.power(k) for k in eligible),default=-1)
        targets=[k for k in eligible if self.power(k)==maximum]
        if any(any(self.cards[k].has(e) for e in (C.CardEffect_SuicideSummon,C.CardEffect_Morph,C.CardEffect_Mushroom)) for k in targets):
            raise UnsupportedPosition('death summons need an explicit transition')
        for key in targets:self.remove_from_board(key)

    def apply(self,action):
        if action.source==(self.leaders or {}).get(self.player):
            # Any eligible same-template graveyard copy is legal for a resurrection,
            # although leader_actions() offers one per template.
            effect=self.leader_effect(self.player)
            if effect in (C.CardEffect_Resurect,C.CardEffect_Resurect_Enemy) and self.leader_modeled(self.player):
                source=self.player if effect==C.CardEffect_Resurect else 1-self.player
                if action.target not in self.recovery_targets(source):raise ValueError('illegal projected action')
            elif action not in self.leader_actions():raise ValueError('illegal projected action')
            return self.apply_leader(action)
        # Chains are checked step by step by recover(): any eligible same-template
        # graveyard copy is legal, although actions() offers one per template.
        if not any((a.source,a.slot,a.target)==(action.source,action.slot,action.target)
                   for a in self.actions()):raise ValueError('illegal projected action')
        state=self.clone();card=state.cards[action.source]
        state.hand=tuple(k for k in state.hand if k!=card.key)
        if card.has(C.CardEffect_UnsummonDummy):
            target=state.cards[action.target]
            state.remove_from_board(target.key,grave=False)
            state.cards[target.key]=replace(target,player=state.player,row=1,applied=())
            state.hand+=(target.key,)
            state.cards[card.key]=replace(card,player=state.player,row=target.row,applied=())
            state.board[state.player,target.row]+=(card.key,)
        elif card.is_type(C.CardType_Creature):
            side=1-state.player if card.is_type(C.CardType_Spy) else state.player
            state.place_unit(card.key,action.slot,side,action.chain)
        elif card.is_type(C.CardType_Row_Modifier):
            state.place_modifier(card,action.slot,state.player)
        elif card.is_type(C.CardType_Weather):
            state.play_weather(card)
        elif card.has(C.CardEffect_Scorch):
            state.scorch();state.cards[card.key]=replace(card,row=2,applied=())
            state.grave[card.owner]+=(card.key,)
        return state

    def recoverable_after_clear(self):
        """Own non-hero units a later Medic could recover after a normal clear.

        Uses the public own graveyard plus own-side board units, which a normal round
        end sends there. Spies and unsupported effects are left out (no value).
        """
        side=self.player
        keys=self.grave[side]+tuple(k for row in ROWS for k in self.board[side,row])
        return tuple(self.cards[k] for k in keys if self.cards[k].is_type(C.CardType_Creature)
            and not self.cards[k].is_type(C.CardType_Hero) and not self.cards[k].is_type(C.CardType_Spy)
            and set(self.cards[k].effects)<=RESERVE_SIMPLE)

    def recovery_reserve(self,medics):
        # Each Medic recovers one unit. A recovered Medic recovers again, so taking
        # every recoverable Medic first never lowers the total; then the strongest units.
        if not medics or self.random_recovery:return ()
        pool=self.recoverable_after_clear()
        nurses=[c for c in pool if c.has(C.CardEffect_Nurse)]
        units=sorted((c for c in pool if not c.has(C.CardEffect_Nurse)),key=lambda c:(-c.power,c.key))
        out=[]
        def reserve_card(c):
            rows=tuple(i for i,flag in enumerate(ROW_TYPES) if c.is_type(flag))
            return ReserveCard(c.key,c.template,c.power,rows,
                morale=c.has(C.CardEffect_ImproveNeighbours),bond=c.has(C.CardEffect_SameTypeMorale),
                bond_targets=c.targets)
        out.extend(reserve_card(c) for c in nurses)
        out.extend(reserve_card(c) for c in units[:medics])
        return tuple(out)

    def place_modifier(self,card,slot,side):
        row=next(r for r,s in MODS.items() if s==slot)
        self.cards[card.key]=replace(card,row=slot,player=side,applied=())
        self.board[side,slot]+=(card.key,)
        self.effects[side,row]+=(card.key,)
        for target in self.board[side,row]:
            if not self.cards[target].is_type(C.CardType_Hero):self.add_effect(target,card.key)

    def play_weather(self,card):
        if card.has(C.CardEffect_ClearSky):
            for key in tuple(self.board[-1,9]):self.remove_from_board(key)
            self.cards[card.key]=replace(card,row=2,applied=())
            self.grave[card.owner]+=(card.key,)
            return
        current=tuple(self.board[-1,9])
        if len(card.effects)>1:
            for key in current:
                previous=self.cards[key]
                if previous.template==card.template or (previous.effects and previous.effects[0] in card.effects):
                    self.remove_from_board(key)
        elif any(card.effects and card.effects[0] in self.cards[key].effects for key in current):
            self.cards[card.key]=replace(card,row=2,applied=())
            self.grave[card.owner]+=(card.key,)
            return
        self.cards[card.key]=replace(card,row=9,player=-1,applied=())
        self.board[-1,9]+=(card.key,)
        for effect,row in ((C.CardEffect_Melee,5),(C.CardEffect_Ranged,4),(C.CardEffect_Siege,3)):
            if card.has(effect):
                for side in (0,1):
                    self.effects[side,row]+=(card.key,)
                    for target in self.board[side,row]:
                        if not self.cards[target].is_type(C.CardType_Hero):self.add_effect(target,card.key)

    # ---- Leaders -------------------------------------------------------------

    def leader_effect(self,side):
        key=(self.leaders or {}).get(side)
        card=self.cards.get(key) if key is not None else None
        return card.effects[0] if card is not None and card.effects else None

    def leader_modeled(self,side):
        """Ready leader whose ability this model can search (passives return False)."""
        effect=self.leader_effect(side)
        if not (self.leader_ready or {}).get(side) or effect not in LEADER_ACTIONS:return False
        return not (effect in (C.CardEffect_Resurect,C.CardEffect_Resurect_Enemy) and self.random_recovery)

    def leader_unmodeled(self,side):
        effect=self.leader_effect(side)
        passive=effect in (C.CardEffect_11th_card,C.CardEffect_Counter_King,C.CardEffect_RandomRessurect,
                           C.CardEffect_DoubleSpy,C.CardEffect_WeatherResistant)
        return bool((self.leader_ready or {}).get(side)) and not passive and not self.leader_modeled(side)

    def weather_templates(self,required=None,excluded=None):
        return sorted(t for t,n in self.counts.items() if n>0 and self.catalog[t].is_type(C.CardType_Weather)
            and not self.catalog[t].has(C.CardEffect_ClearSky)
            and (required is None or self.catalog[t].has(required))
            and (excluded is None or not self.catalog[t].has(excluded)))

    def reposition_gain(self,key):
        card=self.cards[key]
        other=4 if card.row==5 else 5
        # Native estimate: the other row's registered effects only (no bonds).
        moved=self.clone();moved.cards[key]=replace(card,applied=self.effects[card.player,other])
        return max(0,moved.power(key)-self.power(key))

    def leader_actions(self):
        side=self.player
        if not self.leader_modeled(side):return ()
        key=self.leaders[side];effect=self.leader_effect(side);enemy=1-side
        if effect in LEADER_HORN:
            slot=MODS[LEADER_HORN[effect]]
            return (Action(key,slot),) if not self.board[side,slot] else ()
        if effect in LEADER_SCORCH:
            row=LEADER_SCORCH[effect]
            targets=[k for k in self.board[enemy,row] if self.cards[k].is_type(C.CardType_Creature)
                     and not self.cards[k].is_type(C.CardType_Hero)]
            return (Action(key),) if targets and sum(self.power(k) for k in self.board[enemy,row])>=10 else ()
        if effect==C.CardEffect_Clear_Weather:
            return (Action(key),) if self.board[-1,9] else ()
        if effect in LEADER_PICK:
            options=self.weather_templates(*LEADER_PICK[effect])
            # Several matching templates: the native pick follows hidden deck order.
            return (Action(key,9,target=options[0]),) if len(options)==1 else ()
        if effect==C.CardEffect_Pick_Weather:
            return tuple(Action(key,9,target=t) for t in self.weather_templates())
        if effect in (C.CardEffect_Resurect,C.CardEffect_Resurect_Enemy):
            source=side if effect==C.CardEffect_Resurect else enemy
            seen=set();out=[]
            for target in reversed(self.recovery_targets(source)):
                if self.cards[target].template not in seen:
                    seen.add(self.cards[target].template);out.append(Action(key,target=target))
            return tuple(out)
        if effect==C.CardEffect_View_3_Enemy:
            return (Action(key),)
        if effect==C.CardEffect_GraveyardShuffle:
            return (Action(key),) if self.recovery_targets(0) or self.recovery_targets(1) else ()
        if effect==C.CardEffect_AgileReposition:
            units=[k for row in (4,5) for k in self.board[side,row] if self.agile_unit(k)]
            return (Action(key),) if any(self.reposition_gain(k)>0 for k in units) else ()
        return ()

    def agile_unit(self,key):
        card=self.cards[key]
        return (card.is_type(C.CardType_Creature) and not card.is_type(C.CardType_Hero)
                and card.is_type(C.CardType_RangedMelee))

    def apply_leader(self,action):
        state=self.clone();side=state.player;enemy=1-side
        effect=state.leader_effect(side);state.leader_ready[side]=False
        if effect in LEADER_HORN:
            state.next_key-=1
            horn=Card(state.next_key,1,0,C.CardType_Row_Modifier|C.CardType_SeigeRangedMelee,
                      (C.CardEffect_Horn,),(),side,side,action.slot)
            state.cards[horn.key]=horn;state.place_modifier(horn,action.slot,side)
        elif effect in LEADER_SCORCH:
            state.scorch((enemy,),(LEADER_SCORCH[effect],))
        elif effect==C.CardEffect_Clear_Weather:
            for key in tuple(state.board[-1,9]):state.remove_from_board(key)
        elif effect in LEADER_PICK or effect==C.CardEffect_Pick_Weather:
            state.counts[action.target]-=1;state.next_key-=1
            card=replace(state.catalog[action.target],key=state.next_key,owner=side,player=side,row=1)
            state.cards[card.key]=card;state.play_weather(card)
        elif effect in (C.CardEffect_Resurect,C.CardEffect_Resurect_Enemy):
            source=side if effect==C.CardEffect_Resurect else enemy
            card=state.cards[action.target]
            state.grave[source]=tuple(k for k in state.grave[source] if k!=card.key)
            state.cards[card.key]=replace(card,player=side,row=1,applied=())
            state.hand+=(card.key,)
        elif effect==C.CardEffect_GraveyardShuffle:
            # Non-hero units return to the deck of the graveyard they were in.
            for s in (0,1):
                moved=state.recovery_targets(s)
                state.grave[s]=tuple(k for k in state.grave[s] if k not in moved)
                if s==side:
                    for key in moved:
                        t=state.cards[key].template;state.counts[t]=state.counts.get(t,0)+1
        elif effect==C.CardEffect_AgileReposition:
            for key in [k for row in (4,5) for k in state.board[side,row] if state.agile_unit(k)]:
                if state.reposition_gain(key)<=0:continue
                card=state.cards[key]
                if set(card.effects)-{C.CardEffect_None,C.CardEffect_ImproveNeighbours,C.CardEffect_SameTypeMorale}:
                    raise UnsupportedPosition('repositioned unit would re-trigger an effect')
                target=4 if card.row==5 else 5
                state.remove_from_board(key,grave=False);state.place_unit(key,target,side)
        return state

    def reserve_key(self):
        """Everything reserve() reads; a cache keyed on less would return stale values."""
        side=self.player
        recovery=()
        if self.recovery_relevant():
            recovery=(self.grave[0],self.grave[1],tuple(self.board[s,row] for s in (0,1) for row in ROWS))
        return (side,tuple(sorted((k,self.cards[k].template) for k in self.hand)),
                tuple(sorted(self.counts.items())),self.unknown_draws,self.draw_value,
                self.leader_modeled(side),recovery)

    def recovery_relevant(self):
        effect=self.leader_effect(self.player) if self.leader_modeled(self.player) else None
        return (effect in (C.CardEffect_Resurect,C.CardEffect_Resurect_Enemy)
                or any(self.cards[k].has(C.CardEffect_Nurse) for k in self.hand))

    def leader_reserve(self):
        """Value of keeping a modeled leader for a later round (ReserveCards, extra recoveries)."""
        side=self.player
        if not self.leader_modeled(side):return (),0
        effect=self.leader_effect(side);key=self.leaders[side]
        if effect in LEADER_HORN:
            index={5:0,4:1,3:2}[LEADER_HORN[effect]]
            return (ReserveCard(key,1,0,(index,),horn=True),),0
        if effect==C.CardEffect_Resurect:
            return (),1
        if effect==C.CardEffect_Resurect_Enemy:
            enemy=1-side
            pool=[self.cards[k] for k in self.grave[enemy]+tuple(k for row in ROWS for k in self.board[enemy,row])]
            pool=[c for c in pool if c.is_type(C.CardType_Creature) and not c.is_type(C.CardType_Hero)
                  and not c.is_type(C.CardType_Spy) and set(c.effects)<=RESERVE_SIMPLE]
            if not pool:return (),0
            best=max(pool,key=lambda c:(c.power,-c.key))
            rows=tuple(i for i,flag in enumerate(ROW_TYPES) if best.is_type(flag))
            return (ReserveCard(best.key,best.template,best.power,rows),),0
        # Provisional weights for leaders whose later value depends on unseen cards.
        if effect in LEADER_SCORCH:
            weight=self.weights.get(C.CardEffect_Scorch,0)
        elif effect in LEADER_PICK or effect in (C.CardEffect_Pick_Weather,C.CardEffect_Clear_Weather):
            weight=self.weights.get('weather',0)
        else:
            weight=0
        return (ReserveCard(key,0,0,(),unsupported_value=weight),),0

    def reserve(self):
        cards=[];medics=0
        for key in self.hand:
            card=self.cards[key]
            rows=tuple(i for i,flag in enumerate(ROW_TYPES) if card.is_type(flag))
            nurse=card.has(C.CardEffect_Nurse) and not (self.random_recovery and not card.is_type(C.CardType_Hero))
            medics+=nurse
            simple=card.is_type(C.CardType_Creature) and not card.is_type(C.CardType_Spy) and set(card.effects)<={
                C.CardEffect_None,C.CardEffect_ImproveNeighbours,C.CardEffect_SameTypeMorale,C.CardEffect_SummonClones,
                *((C.CardEffect_Nurse,) if nurse else ())}
            horn=card.is_type(C.CardType_Row_Modifier) and card.has(C.CardEffect_Horn)
            summons=[]
            if simple and card.has(C.CardEffect_SummonClones) and not self.unknown_draws:
                for template in sorted(set(card.targets)):
                    t=self.catalog[template]
                    safe=t.is_type(C.CardType_Creature) and not t.is_type(C.CardType_Spy) and set(t.effects)<={C.CardEffect_None,C.CardEffect_SummonClones}
                    for index in range(self.counts.get(template,0)):
                        summons.append(ReserveCard(-(template*10000+index+1),template,t.power,
                            tuple(i for i,flag in enumerate(ROW_TYPES) if t.is_type(flag)) if safe else (),
                            hero=t.is_type(C.CardType_Hero),unsupported_value=0 if safe else t.power))
            weight=max(card.power,*(self.weights.get(e,0) for e in card.effects),0)
            if card.is_type(C.CardType_Weather):weight=max(weight,self.weights['weather'])
            cards.append(ReserveCard(key,card.template,card.power,rows if simple or horn else (),
                hero=card.is_type(C.CardType_Hero),morale=simple and card.has(C.CardEffect_ImproveNeighbours),
                bond=simple and card.has(C.CardEffect_SameTypeMorale),bond_targets=card.targets,
                horn=horn,unsupported_value=0 if simple or horn else weight,summons=tuple(summons)))
        leader_cards,extra=self.leader_reserve()
        if extra:
            if self.random_recovery:extra=0
            medics+=extra
        return supported_reserve_power(tuple(cards)+leader_cards+self.recovery_reserve(medics))+self.draw_value
