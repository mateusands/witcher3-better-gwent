"""Card templates, deck definitions and recorded matches (game/records/gNNN.json from
tools/rec_read.py). Data only: no game rules here.

Templates come from the recording (what the Flash really received), not from the XML: e.g.
kings get typeArray = 0 from the script, and a card without <effect_flags> has effectFlags = []
while EFFECT_NONE gives [0] (getFirstEffect() is 0 for both, hasEffect(0) is not).
"""
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import constants as C
from .rng import ReplayRandom


@dataclass(frozen=True)
class CardTemplate:
    index: int
    power: int
    faction: int
    type_array: int
    effect_flags: tuple
    summon_flags: Optional[tuple]

    # Same logic as CardTemplate.as.
    def is_type(self, type_id):
        if type_id == C.CardType_None and self.type_array != 0:
            return False
        return (self.type_array & type_id) == type_id

    def get_first_effect(self):
        if not self.effect_flags:
            return C.CardEffect_None
        return self.effect_flags[0]

    def has_effect(self, effect):
        return effect in self.effect_flags

    def get_creature_type(self):
        return self.type_array & C.CardType_SeigeRangedMelee


@dataclass
class DeckDefinition:
    """GwintDeck fields as received from the script (before shuffling)."""
    player: int
    deck_name: str
    selected_king_index: int
    special_card: int
    card_indices: List[int]
    dynamic_card_requirements: List[int]
    dynamic_cards: List[int]


@dataclass
class RecordedMatch:
    game: int
    templates: Dict[int, CardTemplate]
    decks: List[DeckDefinition]
    card_values: Dict[str, float]
    events: List[dict] = field(repr=False)
    instance_base: int = 0

    def randoms(self):
        return [(e['tag'], e['u32']) for e in self.events if e['k'] == 'R']

    def replay_random(self):
        return ReplayRandom(self.randoms())

    def snapshots(self, tag=None):
        return [e for e in self.events if e['k'] == 'S' and (tag is None or e['tag'] == tag)]

    def decisions(self):
        return [e for e in self.events if e['k'] == 'A']

    def first_player(self):
        return next(e['first'] for e in self.events if e['k'] == 'F')


def _tuple(v):
    return None if v is None else tuple(v)


def load_match(path):
    d = json.load(open(path))
    templates = {}
    for t in d['templates'].values():
        templates[t['index']] = CardTemplate(t['index'], t['power'], t['faction'], t['type'],
                                             tuple(t['effects'] or ()), _tuple(t['summon']))
    decks = []
    for p in ('0', '1'):
        x = d['decks'][p]
        decks.append(DeckDefinition(x['player'], x['deckName'], x['king'], x['specialCard'],
                                    list(x['cards']), list(x['dynamicReq'] or []), list(x['dynamicCards'] or [])))
    return RecordedMatch(d['game'], templates, decks, dict(d['cardValues']), d['events'], d.get('instanceBase', 0))
