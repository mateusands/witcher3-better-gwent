"""Simulator-only player-style decks, so the NPC AI is tested against decks a player builds.

Native NPC decks are the opponents the Better AI controls in the game; the player's side
is what it plays against. Three deterministic styles per faction and leader, built only
from existing card templates and following the deck rules (at least 22 units, at most 10
special cards, one leader; units once, special cards up to 3 copies):

  power    heroes and the strongest units, the usual "best cards" deck;
  synergy  muster, tight bond, morale, medic and spy units first, then the strongest;
  random   a rule-respecting random deck (seeded), for decks nobody planned for;
  early    an early-game collection: the 22 weakest non-hero units, a Decoy and one
           weather card (deck strength around 100), so the repaired NPC requirements
           give the NPC fewer extra cards, as in the start of the game.

My own recorded decks are added as they are. Nothing here edits a card, a deck
definition, the game or a save.
"""
import random
from dataclasses import dataclass, replace
from pathlib import Path

from . import constants as C
from .data import DeckDefinition
from .deck_pool import FACTIONS, PoolDeck, leaders

STYLES = ('power', 'synergy', 'random', 'early')
SYNERGY = (C.CardEffect_SummonClones, C.CardEffect_SameTypeMorale, C.CardEffect_ImproveNeighbours,
           C.CardEffect_Morale_Boost, C.CardEffect_Nurse, C.CardEffect_Draw2)
MIN_UNITS, MAX_SPECIALS, MAX_COPIES = 22, 10, 3


def _units(templates, faction):
    return [t for t in templates.values() if t.index < 1000 and t.faction in (faction, C.FactionId_Neutral)
            and t.is_type(C.CardType_Creature)]


def _specials(templates, faction):
    return [t for t in templates.values() if t.index < 1000 and t.faction in (faction, C.FactionId_Neutral)
            and not t.is_type(C.CardType_Creature)]


def _strength(t):
    return (t.is_type(C.CardType_Hero), t.power)


def _special_kit(specials):
    """A typical player kit: Decoys, Horns, a Scorch, one of each weather and a Clear Weather."""
    by_effect = {}
    for t in specials:
        by_effect.setdefault(t.get_first_effect(), []).append(t.index)
    kit = []
    for effect, copies in ((C.CardEffect_UnsummonDummy, 2), (C.CardEffect_Horn, 2), (C.CardEffect_Scorch, 1),
                           (C.CardEffect_ClearSky, 1), (C.CardEffect_Melee, 1), (C.CardEffect_Ranged, 1),
                           (C.CardEffect_Siege, 1)):
        for index in sorted(by_effect.get(effect, []))[:1]:
            kit += [index] * copies
    return kit[:MAX_SPECIALS]


def build_deck(templates, faction, leader, style, seed=0):
    units, specials = _units(templates, faction), _specials(templates, faction)
    if style == 'power':
        chosen = sorted(units, key=lambda t: (_strength(t), -t.index), reverse=True)[:26]
        kit = _special_kit(specials)
    elif style == 'synergy':
        engine = [t for t in units if t.get_first_effect() in SYNERGY or t.is_type(C.CardType_Spy)]
        rest = sorted((t for t in units if t not in engine), key=lambda t: (_strength(t), -t.index), reverse=True)
        chosen = (sorted(engine, key=lambda t: t.index) + rest)[:max(MIN_UNITS, min(30, len(engine) + 8))]
        kit = _special_kit(specials)
    elif style == 'random':
        rng = random.Random('%d/%d/%d' % (faction, leader, seed))
        chosen = rng.sample(sorted(units, key=lambda t: t.index), min(len(units), rng.randint(MIN_UNITS, 30)))
        pool = sorted(t.index for t in specials) * MAX_COPIES
        kit = sorted(rng.sample(pool, min(len(pool), rng.randint(0, MAX_SPECIALS))))
    elif style == 'early':
        plain = [t for t in units if not t.is_type(C.CardType_Hero)]
        chosen = sorted(plain, key=lambda t: (t.power, t.index))[:MIN_UNITS]
        kit = [i for i in _special_kit(specials)
               if templates[i].get_first_effect() in (C.CardEffect_UnsummonDummy, C.CardEffect_Melee)]
        kit = sorted(set(kit))
    else:
        raise ValueError('unknown style %s' % style)
    cards = sorted(t.index for t in chosen) + kit
    validate(templates, cards)
    return DeckDefinition(0, 'player/%s/%d' % (style, leader), leader, -1, cards, [], [])


def validate(templates, cards):
    units = sum(1 for i in cards if templates[i].is_type(C.CardType_Creature))
    specials = len(cards) - units
    if units < MIN_UNITS or specials > MAX_SPECIALS:
        raise ValueError('deck breaks the rules: %d units, %d specials' % (units, specials))
    for i in set(cards):
        limit = 1 if templates[i].is_type(C.CardType_Creature) else MAX_COPIES
        if cards.count(i) > limit:
            raise ValueError('too many copies of card %d' % i)


def recorded_player_decks(templates, records_dir):
    """My own decks (player 0 of the recorded matches), each distinct deck once."""
    from .data import load_match
    seen, out = set(), []
    for path in sorted(Path(records_dir).glob('g[0-9][0-9][0-9].json')):
        try:
            deck = load_match(path).decks[0]
        except Exception:
            continue
        key = (deck.selected_king_index, tuple(sorted(deck.card_indices)))
        if key in seen or deck.selected_king_index not in templates:
            continue
        if any(i not in templates for i in deck.card_indices):
            continue
        seen.add(key)
        out.append(PoolDeck('recorded/%s/%d' % (path.stem, deck.selected_king_index),
                            templates[deck.selected_king_index].faction, deck.selected_king_index, True,
                            replace(deck, player=0, dynamic_card_requirements=[], dynamic_cards=[])))
    return out


def build_player_pool(templates, records_dir=None):
    pool = []
    for faction, faction_leaders in sorted(leaders(templates).items()):
        for leader in faction_leaders:
            for style in STYLES:
                deck = build_deck(templates, faction, leader, style)
                pool.append(PoolDeck(deck.deck_name, faction, leader, True, deck))
    if records_dir is not None:
        pool += recorded_player_decks(templates, records_dir)
    return pool


def player_matchups(npc_pool, player_pool):
    """Each player deck against one native NPC deck of every faction (deterministic rotation).

    Returns (npc deck, player deck) pairs; the NPC side is the one the Better AI controls."""
    natives = {f: [d for d in npc_pool if d.native_leader and d.faction == f] for f in FACTIONS}
    pairs = []
    for i, player in enumerate(player_pool):
        for j, faction in enumerate(FACTIONS):
            if natives[faction]:
                pairs.append((natives[faction][(i * 7 + j) % len(natives[faction])], player))
    return pairs
