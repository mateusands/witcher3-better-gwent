"""NPC deck options for Better AI On: Original, Adaptive (mode "balanced") and Strong.

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
from collections import defaultdict

from . import constants as C

MIN_UNITS, MAX_UNITS = 22, 26
# Balanced: target strength as a share of the player's deck strength, by mod difficulty
# (0 Easy, 1 Medium, 2 Hard, 3 Expert).
BALANCED_TARGET = (0.85, 0.95, 1.0, 1.1)
MAX_SPIES, MAX_MEDICS = 3, 2
AVALLACH = 'mysterious_elf'
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
    return value


def packages(templates, faction, names):
    """Units of the faction plus neutrals, grouped so synergies stay whole.

    Muster: cards sharing summon targets form one package. Tight bond: copies with the same
    name stem (e.g. blue_stripes, blue_stripes2) form one package. Everything else is single."""
    pool = [t for t in templates.values() if t.index < 1000 and t.faction in (faction, C.FactionId_Neutral)
            and t.is_type(C.CardType_Creature)]
    groups = defaultdict(list)
    for t in pool:
        name = names.get(t.index, str(t.index))
        if t.has_effect(C.CardEffect_SummonClones) and t.summon_flags:
            key = ('muster', tuple(sorted(t.summon_flags)))
        elif t.has_effect(C.CardEffect_SameTypeMorale):
            key = ('bond', name.rstrip('0123456789'))
        else:
            key = ('single', t.index)
        groups[key].append(t)
    return [(key[0], sorted(cards, key=lambda c: c.index)) for key, cards in groups.items()]


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
    return kit[:8], has_weather


def choose_units(templates, faction, leader, names, keep=(), count=24):
    """Best whole packages under the caps, keeping the given units (heroes of the NPC)."""
    horn_row = LEADER_HORN_ROW.get(leader_effect(templates, leader))
    chosen, spies, medics = [], 0, 0
    keep_set = set(keep)
    for t in sorted((templates[i] for i in keep_set), key=lambda t: t.index):
        chosen.append(t); spies += is_spy(t); medics += t.has_effect(C.CardEffect_Nurse)
    ranked = []
    for kind, cards in packages(templates, faction, names):
        cards = [c for c in cards if c.index not in keep_set]
        if not cards:
            continue
        if kind == 'bond' and len(cards) < 2:
            kind = 'single'                  # a lone bond card is just a unit
        value = sum(unit_value(c, names, horn_row) for c in cards) / len(cards)
        if kind == 'muster':
            value += 1.5                     # pulls its group from the deck: card advantage
        ranked.append((value, kind, cards))
    ranked.sort(key=lambda item: (-item[0], item[2][0].index))
    for value, kind, cards in ranked:
        if len(chosen) + len(cards) > count + (2 if kind != 'single' else 0):
            continue
        s = sum(is_spy(c) for c in cards); m = sum(c.has_effect(C.CardEffect_Nurse) for c in cards)
        if spies + s > MAX_SPIES or medics + m > MAX_MEDICS:
            continue
        chosen += cards; spies += s; medics += m
        if len(chosen) >= count:
            break
    return chosen


def strong_deck(templates, deck, names):
    leader = deck.selected_king_index
    faction = templates[leader].faction
    heroes = [i for i in deck.card_indices if templates[i].is_type(C.CardType_Hero)]
    units = choose_units(templates, faction, leader, names, keep=heroes)
    kit, _ = special_kit(templates, faction, leader, units, names)
    return sorted(t.index for t in units) + kit


def balanced_deck(templates, deck, names, target):
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
    for t in current:                                   # at most three copies, as in native decks
        copies[t.index] += 1
        if copies[t.index] <= 3:
            kept.append(t)
    current = kept
    for cap, test in ((MAX_SPIES, is_spy), (MAX_MEDICS, lambda t: t.has_effect(C.CardEffect_Nurse)
                                                       and not t.is_type(C.CardType_Hero))):
        extra = sorted((t for t in current if test(t)), key=lambda t: (value(t), t.index))
        for t in extra[:max(0, len(extra) - cap)]:
            current.remove(t)
    present = {t.index for t in current}
    pool = [t for kind, cards in packages(templates, faction, names) for t in cards if t.index not in present]
    pool.sort(key=lambda t: (-value(t), t.index))

    def fits(t, without=None):
        group = [u for u in current if u is not without] + [t]
        return sum(map(is_spy, group)) <= MAX_SPIES and sum(
            u.has_effect(C.CardEffect_Nurse) and not u.is_type(C.CardType_Hero) for u in group) <= MAX_MEDICS

    kit, _ = special_kit(templates, faction, leader, current, names)

    def cards():
        return sorted(t.index for t in current) + kit
    while len(current) < MIN_UNITS and pool:
        t = pool.pop(0)
        if fits(t):
            current.append(t)
    for t in list(pool):
        if deck_strength(templates, cards()) >= target:
            break
        weakest = min((u for u in current if not u.is_type(C.CardType_Hero)), key=lambda u: (value(u), u.index),
                      default=None)
        if weakest is None or value(t) <= value(weakest):
            break
        if fits(t, without=weakest):
            current.remove(weakest); current.append(t)
    for t in list(pool):                                # still short: add units, up to MAX_UNITS
        if deck_strength(templates, cards()) >= target or len(current) >= MAX_UNITS:
            break
        if t not in current and fits(t):
            current.append(t)
    kit, _ = special_kit(templates, faction, leader, current, names)
    return cards()


def apply_mode(templates, deck, names, mode, player_cards=None, difficulty=2):
    """DeckDefinition for the NPC under an option mode ('original', 'balanced', 'strong')."""
    from dataclasses import replace
    if mode in (None, 'original'):
        return deck
    if mode == 'strong':
        cards = strong_deck(templates, deck, names)
    elif mode in ('balanced', 'adaptive'):   # "Adaptive" in the menu and docs
        target = deck_strength(templates, player_cards or []) * BALANCED_TARGET[difficulty]
        cards = balanced_deck(templates, deck, names, target)
    else:
        raise ValueError('unknown NPC deck mode %s' % mode)
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
    if len(set(cards)) != len(cards):
        for i in set(cards):
            limit = 3   # native NPC decks already hold up to three copies of a unit
            if cards.count(i) > limit:
                problems.append('too many copies of %d' % i)
    return problems
