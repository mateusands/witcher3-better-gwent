"""NPC deck options for Better Gwent On: Original, Adaptive (mode "balanced") and Strong.

Only the choice of cards in an NPC deck changes, in memory, for that match: no card's
power or ability, no deck definition and nothing in a save is edited, and with the option
Off (or the mod Off) the native deck is used. Every card comes from the existing card
templates of the NPC's own faction plus neutral cards. Rules, like a seasoned player builds:

- identity: same faction and leader; the NPC's heroes stay in its deck;
- 22+ units; special cards kept to a playable kit instead of the native pile of weather;
- weather only of types that do not hit the deck's own strong rows (Skellige's weather-
  resistant leader excepted); a leader that pulls a weather gets exactly that card;
- a leader that clears weather replaces the Clear Weather card; a leader that doubles a row
  leaves one Horn for the other rows, and units of that row are preferred;
- synergy whole or not at all: muster groups complete, tight bond with at least 2 copies;
- spies capped (Avallac'h, the neutral hero spy, first), medics capped.

Balanced: start from the NPC's own deck (with the special-card rules applied) and swap its
weakest units for the best eligible ones until its strength reaches the player's (the same
deck-strength measure the game uses for its extra cards). Strong: the best deck those rules
allow for the faction. The player's hand is never read; only the strength of the deck.
"""
from contextlib import contextmanager
from collections import defaultdict

from . import constants as C

MIN_UNITS, MAX_UNITS = 22, 26
# Balanced: target strength as a share of the player's deck strength, by mod difficulty
# (0 Easy, 1 Medium, 2 Hard, 3 Expert).
BALANCED_TARGET = (0.85, 1.0, 1.1, 1.1)   # Easy, Normal, Hard (Expert: simulator only)
KIT_CAP, STRONG_UNITS = 8, 24   # set per deck mode from MODE_SHAPE while a deck is built
# Shipped deck shapes (test, 12 October 2026, 1,020 paired games per cell):
# Strong lean (4 specials, 22 units, no Triss) +15.0 Hard / +15.9 Normal;
# Adaptive at most 2 specials +4.4 Hard / +8.2 Normal.
# Adaptive also draws heroes that fit its faction, one of HERO_VARIANTS per match (test, 12 October 2026:
# no measurable change, -0.9 Normal / +0.9 Hard, |z| 0.6); Strong keeps every hero (-5 there).
# Triss is never in an NPC deck (owner's choice, 12 October 2026), including the Adaptive
# every-hero fallback.
MODE_SHAPE = {'strong': dict(kit=4, units=22, excluded=frozenset({'triss'}), heroes=False),
              'balanced': dict(kit=2, units=24, excluded=frozenset({'triss'}), heroes=True)}
_OVERRIDE = {}   # Lab switches (apply_mode flags) on top of MODE_SHAPE
# Experiment "ability-value" (deck flag, not shipped): units whose builder worth was only their
# printed power although their ability matters. While a deck is built: the extra worth per
# template index (Horn units, row-scorch units, Morph units) and whether muster packages hold
# every copy and are valued by what one draw brings (see ability_bonus and package_worth).
_ABILITY_BONUS = {}
_ABILITY_VALUE = False
MUSTER_SELF_COPIES = 3     # as in native decks: three Darkness, three Light Drakkars
HAND_SHARE = 0.5           # a match puts about 13 of a ~26-card deck in hand
ROUNDS = 3
SCORCH_HIT = 0.5           # row Scorch: chance the player's row holds 10+ when the unit lands
SCORCH_TOP = 6             # typical strongest non-hero unit it then destroys
MAX_SPIES, MAX_MEDICS = 4, 2   # 4 spies since 0.9.0 (test, 12 October 2026: Hard Adaptive +3.19 z 4.0)
AVALLACH = 'mysterious_elf'
# Never put in an NPC deck. Olaf: the game's own CardEffectManager throws when his morale effect
# lands after he has left the board (seen in the Lab with Adaptive Skellige decks, 2026-10-12);
# no native NPC deck uses him.
EXCLUDED = {'olaf'}
ROW_FLAGS = ((C.CardType_Melee, 'melee'), (C.CardType_Ranged, 'ranged'), (C.CardType_Siege, 'siege'))
WEATHER_ROW = {C.CardEffect_Melee: 'melee', C.CardEffect_Ranged: 'ranged', C.CardEffect_Siege: 'siege'}
LEADER_HORN_ROW = {C.CardEffect_Melee_Horn: 'melee', C.CardEffect_Range_Horn: 'ranged',
                   C.CardEffect_Siege_Horn: 'siege'}
LEADER_PICK = {C.CardEffect_Pick_Frost: C.CardEffect_Melee, C.CardEffect_Pick_Fog: C.CardEffect_Ranged,
               C.CardEffect_Pick_Rain: C.CardEffect_Siege}
STRENGTH_BONUS = {C.CardEffect_Melee: 2, C.CardEffect_Ranged: 2, C.CardEffect_Siege: 2, C.CardEffect_ClearSky: 2,
                  C.CardEffect_UnsummonDummy: 4, C.CardEffect_Horn: 5, C.CardEffect_Scorch: 6,
                  C.CardEffect_MeleeScorch: 6, C.CardEffect_SummonClones: 3, C.CardEffect_ImproveNeighbours: 4,
                  C.CardEffect_Nurse: 4, C.CardEffect_Draw2: 6, C.CardEffect_SameTypeMorale: 4}


def deck_strength(templates, cards):
    """The game's own player-deck strength measure (unit power plus fixed ability bonuses)."""
    total = 0
    for i in cards:
        t = templates[i]
        if t.is_type(C.CardType_Creature):
            total += t.power
        total += STRENGTH_BONUS.get(t.get_first_effect(), 0)
    return total


def unit_row(t):
    for flag, name in ROW_FLAGS:
        if t.is_type(flag):
            return name
    return 'melee'


def is_spy(t):
    return t.is_type(C.CardType_Spy) or t.has_effect(C.CardEffect_Draw2)


def unit_value(t, names, horn_row=None):
    """Heuristic worth of a unit for deck building (not the game's strength measure)."""
    if is_spy(t):
        value = 9.0 - 0.3 * t.power          # two draws, minus what it gives away
    else:
        value = float(t.power)
        if t.is_type(C.CardType_Hero):
            value *= 1.25                    # immune to weather, Horn-free and Scorch-proof
        if t.has_effect(C.CardEffect_Nurse):
            value += 4
        if t.has_effect(C.CardEffect_ImproveNeighbours):
            value += 3
        if t.has_effect(C.CardEffect_SameTypeMorale):
            value += 0.5 * t.power           # a pair doubles, so each copy is worth more
        if (t.type_array & C.CardType_RangedMelee) == C.CardType_RangedMelee:
            value += 0.5                     # agile
    if names.get(t.index) == AVALLACH:
        value += 3
    if horn_row and unit_row(t) == horn_row and not t.is_type(C.CardType_Hero):
        value *= 1.15
    return value + _ABILITY_BONUS.get(t.index, 0.0)


def ability_bonus(templates, deck, names, kit):
    """Experiment "ability-value": worth of a unit's ability beyond its printed power, by
    template index, for one NPC deck (unit_value adds it). Simple documented estimates:

    - Horn unit (Dandelion, Draig Bon-Dhu): the Horn doubles his row's expected board in the
      round he is played: the native deck's non-hero, non-spy unit power on that row times
      HAND_SHARE, spread over ROUNDS. No stacking: nothing when the leader horns that row, and
      shared with each Horn card of the kit (divided by 1 + kit Horns), which may take the row.
    - Row-scorch unit (Villentretenmerth, Schirru, Toad): SCORCH_HIT * SCORCH_TOP, the expected
      destroyed power against a typical player row. Clan Dimun Pirate (a Scorch on every row,
      own units included) gets half of it.
    - Morph unit (Berserker -> Bear, Young Berserker -> Young Bear): the power gained by the
      transformation times the chance a Mardroeme source is drawn, only when the deck carries one
      (Ermion; the kit never holds the Mardroeme card). Without one, nothing.
    - Suicide summon (Cow, Kambi's cock): unchanged (no bonus). Their summon needs the unit
      destroyed; a 0-power unit is never the Scorch target and these decks hold no other way to
      destroy their own units, so the printed value stays.
    Muster packages are valued in package_worth."""
    leader = deck.selected_king_index
    horn_row = LEADER_HORN_ROW.get(leader_effect(templates, leader))
    cards = [templates[i] for i in deck.card_indices]
    row_power = defaultdict(int)
    for t in cards:
        if t.is_type(C.CardType_Creature) and not t.is_type(C.CardType_Hero) and not is_spy(t):
            row_power[unit_row(t)] += t.power
    kit_horns = sum(templates[k].has_effect(C.CardEffect_Horn) for k in kit)
    sources = sum(t.is_type(C.CardType_Creature) and t.has_effect(C.CardEffect_Mushroom)
                  and names.get(t.index) not in EXCLUDED for t in cards)
    morph_chance = 1 - (1 - HAND_SHARE) ** sources
    bonus = {}
    for t in templates.values():
        if t.index >= 1000 or not t.is_type(C.CardType_Creature):
            continue
        if t.has_effect(C.CardEffect_Horn):
            row = unit_row(t)
            bonus[t.index] = 0.0 if row == horn_row else row_power[row] * HAND_SHARE / ROUNDS / (1 + kit_horns)
        elif any(t.has_effect(e) for e in (C.CardEffect_MeleeScorch, C.CardEffect_RangedScorch,
                                             C.CardEffect_Siege_Scorch)):
            bonus[t.index] = SCORCH_HIT * SCORCH_TOP
        elif t.has_effect(C.CardEffect_Scorch):
            bonus[t.index] = SCORCH_HIT * SCORCH_TOP / 2
        elif t.has_effect(C.CardEffect_Morph) and t.summon_flags and t.summon_flags[0] in templates:
            bonus[t.index] = max(0, templates[t.summon_flags[0]].power - t.power) * morph_chance
    return bonus


def package_worth(kind, cards, value):
    """Worth per card of a package, by which the builders rank and swap packages.

    Default: the mean unit value, plus 1.5 for a muster group where the Strong builder ranks
    packages (Adaptive ranks by the mean alone), as shipped. Experiment "ability-value": a muster
    member reaches the board when any card that calls it is drawn, so each member counts
    value * (1 - (1 - HAND_SHARE) ** k) / HAND_SHARE, where k is the number of package cards
    that bring it (itself included): 1 for a single card, 1.75 for a group of three, 1.875 for
    four. The same rule in both builders, without the flat 1.5."""
    if kind != 'muster' or not _ABILITY_VALUE:
        return sum(map(value, cards)) / len(cards)
    total = 0.0
    for n, t in enumerate(cards):
        k = sum(1 for m, c in enumerate(cards) if m == n or t.index in (c.summon_flags or ()))
        total += value(t) * (1 - (1 - HAND_SHARE) ** k) / HAND_SHARE
    return total / len(cards)


def hero_identity(t, names):
    """Heroes are unique: one copy, and the GOG bonus version (geraltGOG, ciriGOG) is the same
    character as the base card. None for other cards."""
    if not t.is_type(C.CardType_Hero):
        return None
    return names.get(t.index, str(t.index)).replace('GOG', '')


def packages(templates, faction, names):
    """Units of the faction plus neutrals, grouped so synergies stay whole.

    Muster: cards whose summon targets overlap form one package (Arachas Behemoth calls the
    Arachas, so all four are one package). Tight bond: copies with the same name stem (e.g.
    blue_stripes, blue_stripes2) form one package. Everything else is single."""
    pool = [t for t in templates.values() if t.index < 1000 and t.faction in (faction, C.FactionId_Neutral)
            and t.is_type(C.CardType_Creature) and names.get(t.index) not in EXCLUDED]
    groups = defaultdict(list)
    musters = []                                         # [set of summon targets, cards]
    for t in sorted(pool, key=lambda t: t.index):
        if t.has_effect(C.CardEffect_SummonClones) and t.summon_flags:
            flags, cards = set(t.summon_flags), [t]
            for group in [g for g in musters if g[0] & flags]:
                musters.remove(group)
                flags |= group[0]
                cards += group[1]
            musters.append([flags, cards])
    for flags, cards in musters:                         # plain cards a muster calls (Roach)
        cards += [t for t in pool if t.index in flags and t not in cards]
        if _ABILITY_VALUE:
            # Experiment "ability-value": a member that calls only its own template (Gaunter
            # O'Dimm's Darkness, Light Drakkar) is one card in several copies; the package holds
            # every copy, as other muster groups hold every member, so one draw brings them all.
            for t in list(cards):
                if tuple(t.summon_flags or ()) == (t.index,):
                    cards += [t] * (MUSTER_SELF_COPIES - 1)
    in_muster = {t.index for _, cards in musters for t in cards}
    for t in sorted(pool, key=lambda t: t.index):
        if t.index in in_muster:
            continue
        name = names.get(t.index, str(t.index))
        if t.has_effect(C.CardEffect_SameTypeMorale):
            key = ('bond', name.rstrip('0123456789'))
        else:
            key = ('single', t.index)
        groups[key].append(t)
    result = [(key[0], sorted(cards, key=lambda c: c.index)) for key, cards in groups.items()]
    result += [('muster', sorted(cards, key=lambda c: c.index)) for _, cards in musters]
    return result


def leader_effect(templates, leader):
    return templates[leader].get_first_effect()


def special_kit(templates, faction, leader, units, names):
    """Playable special cards for a deck whose units are known (so weather can spare them)."""
    effect = leader_effect(templates, leader)
    specials = {}
    for t in sorted(templates.values(), key=lambda t: t.index):
        # Lowest index first: the basic card of each effect (Fog before Skellige Storm, which
        # hits two rows and is left out of the kit).
        if t.index < 1000 and t.faction in (faction, C.FactionId_Neutral) and not t.is_type(C.CardType_Creature) \
                and names.get(t.index) != 'skellige_storm':
            specials.setdefault(t.get_first_effect(), t.index)
    row_power = defaultdict(int)
    for t in units:
        if not t.is_type(C.CardType_Hero):
            row_power[unit_row(t)] += t.power
    total = sum(row_power.values()) or 1
    weather_ok = effect == C.CardEffect_WeatherResistant
    kit = []
    picked = LEADER_PICK.get(effect)
    for weather, row in WEATHER_ROW.items():
        if weather not in specials:
            continue
        harmless = weather_ok or row_power[row] / total < 0.25
        if weather == picked or (harmless and len([k for k in kit if templates[k].is_type(C.CardType_Weather)]) < 2):
            if weather == picked or harmless:
                kit.append(specials[weather])
    has_weather = any(templates[k].is_type(C.CardType_Weather) for k in kit)
    if C.CardEffect_ClearSky in specials and effect not in (C.CardEffect_Clear_Weather, C.CardEffect_WeatherResistant):
        kit.append(specials[C.CardEffect_ClearSky])
    horns = 1 if effect in LEADER_HORN_ROW else 2
    kit += [specials[C.CardEffect_Horn]] * horns if C.CardEffect_Horn in specials else []
    spies = sum(is_spy(t) for t in units)
    kit += [specials[C.CardEffect_UnsummonDummy]] * (3 if spies >= 2 else 2) if C.CardEffect_UnsummonDummy in specials else []
    if C.CardEffect_Scorch in specials:
        kit.append(specials[C.CardEffect_Scorch])
    kit = kit[:8]
    if KIT_CAP < 8:
        # Experiment "kitN" (lean decks, as in hand-built archetype decks): keep the weather the
        # leader pulls, then Scorch, a Horn, a Decoy, Clear Weather, the rest in kit order.
        order = [picked, C.CardEffect_Scorch, C.CardEffect_Horn, C.CardEffect_UnsummonDummy, C.CardEffect_ClearSky]
        seen = set()
        ranked = []
        for position, k in enumerate(kit):                # copies of a card share its index
            e = templates[k].get_first_effect()
            first = e not in seen
            seen.add(e)
            ranked.append((order.index(e) if e in order and first else len(order), position, k))
        kit = [k for _, _, k in sorted(sorted(ranked)[:KIT_CAP], key=lambda r: r[1])]
        has_weather = any(templates[k].is_type(C.CardType_Weather) for k in kit)
    return kit, has_weather


def choose_units(templates, faction, leader, names, keep=(), count=24):
    """Best whole packages under the caps, keeping the given units (heroes of the NPC)."""
    horn_row = LEADER_HORN_ROW.get(leader_effect(templates, leader))
    chosen, spies, medics = [], 0, 0
    keep_set = set(keep)
    heroes = set()                           # a hero only once, GOG versions included
    for t in sorted((templates[i] for i in keep_set), key=lambda t: t.index):
        hero = hero_identity(t, names)
        if hero is not None and hero in heroes:
            continue
        heroes.add(hero)
        chosen.append(t); spies += is_spy(t); medics += t.has_effect(C.CardEffect_Nurse)
    ranked = []
    for kind, cards in packages(templates, faction, names):
        cards = [c for c in cards if c.index not in keep_set]
        if not cards or any(hero_identity(c, names) in heroes for c in cards if c.is_type(C.CardType_Hero)):
            continue
        if kind == 'bond' and len(cards) < 2:
            kind = 'single'                  # a lone bond card is just a unit
        value = package_worth(kind, cards, lambda c: unit_value(c, names, horn_row))
        if kind == 'muster' and not _ABILITY_VALUE:
            value += 1.5                     # pulls its group from the deck: card advantage
        ranked.append((value, kind, cards))
    ranked.sort(key=lambda item: (-item[0], item[2][0].index))
    for value, kind, cards in ranked:
        if len(chosen) + len(cards) > count + (2 if kind != 'single' else 0):
            continue
        s = sum(is_spy(c) for c in cards); m = sum(c.has_effect(C.CardEffect_Nurse) for c in cards)
        if spies + s > MAX_SPIES or medics + m > MAX_MEDICS:
            continue
        if any(hero_identity(c, names) in heroes for c in cards if c.is_type(C.CardType_Hero)):
            continue
        chosen += cards; spies += s; medics += m
        heroes.update(hero_identity(c, names) for c in cards if c.is_type(C.CardType_Hero))
        if len(chosen) >= count:
            break
    return chosen


@contextmanager
def shaped(mode, templates=None, deck=None, names=None, variant=0):
    """KIT_CAP, STRONG_UNITS and EXCLUDED for one deck mode while its deck is built."""
    global KIT_CAP, STRONG_UNITS, EXCLUDED, _ABILITY_BONUS, _ABILITY_VALUE
    shape = dict(MODE_SHAPE[mode], **_OVERRIDE)
    saved = KIT_CAP, STRONG_UNITS, EXCLUDED, _ABILITY_BONUS, _ABILITY_VALUE
    heroes = hero_exclusions(templates, deck, names, variant % HERO_VARIANTS) if shape['heroes'] else frozenset()
    KIT_CAP, STRONG_UNITS, EXCLUDED = shape['kit'], shape['units'], EXCLUDED | shape['excluded'] | heroes
    if shape.get('ability_value'):
        leader = deck.selected_king_index
        kit, _ = special_kit(templates, templates[leader].faction, leader, [], names)
        _ABILITY_BONUS, _ABILITY_VALUE = ability_bonus(templates, deck, names, kit), True
    try:
        yield
    finally:
        KIT_CAP, STRONG_UNITS, EXCLUDED, _ABILITY_BONUS, _ABILITY_VALUE = saved


def strong_deck(templates, deck, names, variant=0):
    with shaped('strong', templates, deck, names, variant):
        return _strong_deck(templates, deck, names)


def _strong_deck(templates, deck, names):
    leader = deck.selected_king_index
    faction = templates[leader].faction
    heroes = [i for i in deck.card_indices if templates[i].is_type(C.CardType_Hero)
              and names.get(i) not in EXCLUDED]
    units = choose_units(templates, faction, leader, names, keep=heroes, count=STRONG_UNITS)
    kit, _ = special_kit(templates, faction, leader, units, names)
    return sorted(t.index for t in units) + kit


def balanced_steps(templates, deck, names, variant=0):
    """Every deck balanced_deck can return for this NPC deck, as (strength checked, cards).

    balanced_deck only uses its target to decide when to stop, so for any target the result is
    the cards of the first step whose checked strength reaches it, else the last step. The game
    uses this table instead of running the builder (see tools/build_npc_decks.py)."""
    steps = []
    balanced_deck(templates, deck, names, float('inf'), steps, variant)
    return steps


def balanced_deck(templates, deck, names, target, steps=None, variant=0):
    shape = dict(MODE_SHAPE['balanced'], **_OVERRIDE)
    if not shape['heroes'] or not shape.get('fallback', True):
        with shaped('balanced', templates, deck, names, variant):
            return _balanced_deck(templates, deck, names, target, steps)
    # Faction heroes first; when they cannot reach the target, the steps go on with every hero
    # allowed (the tested lean shape), so a strong player deck still meets a strong NPC deck.
    # The game reads the same list: the first step reaching the target, else the last one.
    combined = hero_fallback_steps(templates, deck, names, variant)
    if steps is not None:
        steps.extend(combined)
    for strength, cards in combined:
        if strength >= target:
            return list(cards)
    return list(combined[-1][1])


def hero_fallback_steps(templates, deck, names, variant):
    """Adaptive steps with faction heroes, then the every-hero steps stronger than its last one."""
    global _OVERRIDE
    own, every = [], []
    with shaped('balanced', templates, deck, names, variant):
        _balanced_deck(templates, deck, names, float('inf'), own)
    saved = _OVERRIDE
    _OVERRIDE = dict(_OVERRIDE, heroes=False)
    try:
        with shaped('balanced', templates, deck, names, variant):
            _balanced_deck(templates, deck, names, float('inf'), every)
    finally:
        _OVERRIDE = saved
    top = own[-1][0]
    return own + [step for step in every if step[0] > top]


def _balanced_deck(templates, deck, names, target, steps=None):
    """The NPC's own units made legal (caps, 22+ units), then the weakest swapped for better
    eligible ones until the deck's strength reaches the player's (never weakened below)."""
    leader = deck.selected_king_index
    faction = templates[leader].faction
    horn_row = LEADER_HORN_ROW.get(leader_effect(templates, leader))
    value = lambda t: unit_value(t, names, horn_row)
    current = sorted((templates[i] for i in deck.card_indices if templates[i].is_type(C.CardType_Creature)),
                     key=lambda t: t.index)
    copies = defaultdict(int)
    kept = []
    heroes = set()
    for t in current:                                   # at most three copies, as in native decks
        if names.get(t.index) in EXCLUDED:
            continue
        hero = hero_identity(t, names)
        if hero is not None:                            # a hero only once (native decks repeat some)
            if hero in heroes:
                continue
            heroes.add(hero)
        copies[t.index] += 1
        if copies[t.index] <= 3:
            kept.append(t)
    current = kept
    for cap, test in ((MAX_SPIES, is_spy), (MAX_MEDICS, lambda t: t.has_effect(C.CardEffect_Nurse)
                                                       and not t.is_type(C.CardType_Hero))):
        extra = sorted((t for t in current if test(t)), key=lambda t: (value(t), t.index))
        for t in extra[:max(0, len(extra) - cap)]:
            current.remove(t)
    groups = packages(templates, faction, names)
    muster_of = {t.index: cards for kind, cards in groups if kind == 'muster' for t in cards}
    present = {t.index for t in current}
    # A muster card without its group (e.g. Arachas Behemoth without Arachas) gets its group.
    for index in sorted(present):
        for t in muster_of.get(index, ()):
            if t.index not in present:
                current.append(t); present.add(t.index)
    if _ABILITY_VALUE:
        # Experiment "ability-value": every copy the package holds (three Darkness).
        for index in sorted(present):
            group = muster_of.get(index, ())
            for t in {u.index: u for u in group}.values():
                while sum(u.index == t.index for u in current) < sum(u.index == t.index for u in group):
                    current.append(t)
    # Candidates are whole packages: a muster group enters complete or not at all, other
    # cards one by one (as before).
    pool = []
    for kind, cards in groups:
        if kind == 'muster':
            if not any(t.index in present for t in cards):
                pool.append(cards)
        else:
            pool += [[t] for t in cards if t.index not in present
                     and (hero_identity(t, names) is None or hero_identity(t, names) not in heroes)]
    worth = lambda cards: package_worth('muster' if cards[0].index in muster_of else 'single', cards, value)
    pool.sort(key=lambda cards: (-worth(cards), cards[0].index))

    def fits(new, without=()):
        group = [u for u in current if not any(u is w for w in without)] + list(new)
        group_heroes = [hero_identity(u, names) for u in group if u.is_type(C.CardType_Hero)]
        if len(set(group_heroes)) != len(group_heroes):
            return False
        return sum(map(is_spy, group)) <= MAX_SPIES and sum(
            u.has_effect(C.CardEffect_Nurse) and not u.is_type(C.CardType_Hero) for u in group) <= MAX_MEDICS

    def removable():
        # Heroes stay; muster members stay too, so no group is broken.
        return sorted((u for u in current if not u.is_type(C.CardType_Hero) and u.index not in muster_of),
                      key=lambda u: (value(u), u.index))

    kit, _ = special_kit(templates, faction, leader, current, names)

    def cards():
        return sorted(t.index for t in current) + kit
    for new in list(pool):
        if len(current) >= MIN_UNITS:
            break
        if fits(new):
            current.extend(new); pool.remove(new)

    def reached():
        strength = deck_strength(templates, cards())
        if steps is not None:
            final, _ = special_kit(templates, faction, leader, current, names)
            snapshot = sorted(t.index for t in current) + final
            if not steps or steps[-1][1] != snapshot:
                steps.append((strength, snapshot))
        return strength >= target
    for new in list(pool):
        if reached():
            break
        out = removable()[:len(new)]
        if len(out) < len(new) or worth(new) <= max(map(value, out)):
            if len(new) == 1:
                break
            continue
        if fits(new, without=out):
            for u in out:
                current.remove(u)
            current.extend(new); pool.remove(new)
    for new in list(pool):                              # still short: add units, up to MAX_UNITS
        if reached() or len(current) >= MAX_UNITS:
            break
        if len(current) + len(new) <= MAX_UNITS + (2 if len(new) > 1 else 0) and fits(new):
            current.extend(new); pool.remove(new)
    kit, _ = special_kit(templates, faction, leader, current, names)
    if steps is not None:
        reached()
    return cards()


SPY_FACTIONS = (C.FactionId_Nilfgaard, C.FactionId_Northern_Kingdom)


def deck_faction(templates, cards):
    """Faction of a deck from its non-neutral cards (public: the leader shows it in game)."""
    counts = defaultdict(int)
    for i in cards:
        if templates[i].faction != C.FactionId_Neutral:
            counts[templates[i].faction] += 1
    return max(counts, key=lambda f: (counts[f], -f)) if counts else C.FactionId_Neutral


def with_decoys(templates, cards, count):
    """Experiment "decoy3": at least `count` Decoys, within the 8 special cards (a second Horn
    makes room first)."""
    cards = list(cards)
    decoy = next((i for i in cards if templates[i].get_first_effect() == C.CardEffect_UnsummonDummy), None)
    if decoy is None:
        return cards
    while sum(templates[i].get_first_effect() == C.CardEffect_UnsummonDummy for i in cards) < count:
        specials = [i for i in cards if not templates[i].is_type(C.CardType_Creature)]
        if len(specials) >= 8:
            horns = [i for i in specials if templates[i].get_first_effect() == C.CardEffect_Horn]
            if len(horns) < 2:
                break
            cards.remove(horns[-1])
        cards.append(decoy)
    return cards


# Experiment "heroes": heroes that fit the NPC's faction, varied per match. Avallac'h (a spy) and
# Yennefer (a medic) stay allowed; 2 or 3 of the faction's heroes are drawn; Geralt or Ciri
# (never both) in about one deck in four; Triss never. The draw depends only on the NPC deck
# and a variant number, so the game can store a few variants per NPC and pick one per match.
HERO_FIXED = frozenset({'yennefer', 'mysterious_elf'})
HERO_WITCHERS = (frozenset({'geralt', 'geraltGOG'}), frozenset({'ciri', 'ciriGOG'}))
HERO_VARIANTS = 3


def hero_exclusions(templates, deck, names, variant):
    """Hero names the builder must leave out for this NPC deck and variant."""
    import hashlib
    from random import Random
    faction = templates[deck.selected_king_index].faction
    key = '%d|%s|%d' % (deck.selected_king_index, ','.join(map(str, sorted(deck.card_indices))), variant)
    rng = Random(int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], 'big'))
    heroes = lambda f: sorted({names[t.index] for t in templates.values() if t.index < 1000 and t.faction == f
                               and t.is_type(C.CardType_Hero) and names.get(t.index)})
    own = heroes(faction)
    keep = set(rng.sample(own, min(len(own), rng.choice((2, 3)))))
    witcher = rng.choice(HERO_WITCHERS) if rng.random() < 0.25 else frozenset()
    neutral = set(heroes(C.FactionId_Neutral)) - HERO_FIXED - witcher
    return frozenset(set(own) - keep) | frozenset(neutral)


def apply_mode(templates, deck, names, mode, player_cards=None, difficulty=2, variant=0):
    """DeckDefinition for the NPC under an option mode ('original', 'balanced', 'strong').

    "<mode>:decoy3" (experiment) gives the NPC 3 Decoys against a Nilfgaard or Northern Kingdoms
    player deck, the factions with the most spies."""
    from dataclasses import replace
    mode, _, flags = (mode or 'original').partition(':')
    if mode == 'original':
        return deck
    global MAX_SPIES, _OVERRIDE
    saved = MAX_SPIES, _OVERRIDE
    switches = set(flags.split('+'))
    override = {}
    if 'spies4' in switches:
        MAX_SPIES = 4                         # experiment: one more spy allowed (shipped since)
    if 'v090' in switches:                    # the 0.9.0 shape: 8 specials, 24 units, Triss allowed
        override.update(kit=8, units=24, excluded=frozenset(), heroes=False)
    for n in (2, 4, 8):
        if 'kit%d' % n in switches:
            override['kit'] = n
    for n in (22, 24):
        if 'units%d' % n in switches:
            override['units'] = n
    if 'notriss' in switches:
        override['excluded'] = frozenset({'triss'})
    if 'triss' in switches:
        override['excluded'] = frozenset()
    if 'heroes' in switches:                  # faction heroes drawn per match (Adaptive default)
        override['heroes'] = True
    if 'strictheroes' in switches:            # faction heroes without the every-hero fallback (g151)
        override.update(heroes=True, fallback=False)
    if 'allheroes' in switches:               # every hero allowed (Strong default; Adaptive before the heroes test)
        override['heroes'] = False
    if 'ability-value' in switches:           # units valued by their abilities, not printed power only
        override['ability_value'] = True
    _OVERRIDE = override
    try:
        if mode == 'strong':
            cards = strong_deck(templates, deck, names, variant)
        elif mode in ('balanced', 'adaptive'):   # "Adaptive" in the menu and docs
            target = deck_strength(templates, player_cards or []) * BALANCED_TARGET[difficulty]
            cards = balanced_deck(templates, deck, names, target, variant=variant)
        else:
            raise ValueError('unknown NPC deck mode %s' % mode)
    finally:
        MAX_SPIES, _OVERRIDE = saved
    if 'decoy3' in flags.split('+') and deck_faction(templates, player_cards or []) in SPY_FACTIONS:
        cards = with_decoys(templates, cards, 3)
    # The chosen deck replaces the native extra-card mechanism for this match.
    return replace(deck, card_indices=list(cards), dynamic_card_requirements=[], dynamic_cards=[])


def audit(templates, cards, leader):
    """Rule check used by the tests: returns a list of violations (empty when the deck is fine)."""
    units = [templates[i] for i in cards if templates[i].is_type(C.CardType_Creature)]
    specials = [templates[i] for i in cards if not templates[i].is_type(C.CardType_Creature)]
    problems = []
    if len(units) < MIN_UNITS:
        problems.append('only %d units' % len(units))
    if len(specials) > 8:
        problems.append('%d special cards' % len(specials))
    if sum(t.is_type(C.CardType_Weather) and not t.has_effect(C.CardEffect_ClearSky) for t in specials) > 3:
        problems.append('too much weather')
    if sum(is_spy(t) for t in units) > MAX_SPIES:
        problems.append('too many spies')
    if sum(t.has_effect(C.CardEffect_Nurse) for t in units) > MAX_MEDICS + sum(
            t.is_type(C.CardType_Hero) and t.has_effect(C.CardEffect_Nurse) for t in units):
        problems.append('too many medics')
    if leader_effect(templates, leader) == C.CardEffect_Clear_Weather and any(t.has_effect(C.CardEffect_ClearSky) for t in specials):
        problems.append('Clear Weather card with a clearing leader')
    if leader_effect(templates, leader) in LEADER_HORN_ROW and sum(t.has_effect(C.CardEffect_Horn) for t in specials) > 1:
        problems.append('more than one Horn with a Horn leader')
    present = set(cards)
    for t in units:
        if t.has_effect(C.CardEffect_SummonClones) and t.summon_flags:
            missing = [i for i in t.summon_flags if i in templates and i not in present
                       and templates[i].faction == templates[t.index].faction]
            if missing:
                problems.append('muster %d without %s' % (t.index, missing))
    from blunder_hunter import card_names
    names = card_names()
    hero_names = [hero_identity(t, names) for t in units if t.is_type(C.CardType_Hero)]
    for hero in sorted(set(hero_names)):
        if hero_names.count(hero) > 1:
            problems.append('hero %s more than once' % hero)
    if len(set(cards)) != len(cards):
        for i in set(cards):
            limit = 3   # native NPC decks already hold up to three copies of a unit
            if cards.count(i) > limit:
                problems.append('too many copies of %d' % i)
    return problems
