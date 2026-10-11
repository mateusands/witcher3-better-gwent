"""Original narrow safeguard against spending a plain hero on a secured round.

A passed opponent cannot reply. A plain hero cannot help faction carry, which
excludes heroes, and has no secondary effect. Spending it cannot improve the round
winner; retaining it preserves a future action. No future win probability is used.
"""
from dataclasses import replace
from gwentsim import constants as C
from gwentsim.response_search import secured


def refine_hero_pass(position,context,result):
    if not context.opponent_passed or result.action is None or not secured(position,context):return result
    source=result.action.source
    if source not in position.hand:return result
    card=position.cards[source]
    plain=(card.is_type(C.CardType_Creature) and card.is_type(C.CardType_Hero)
        and not card.is_type(C.CardType_Spy) and set(card.effects)<={C.CardEffect_None})
    if not plain:return result
    return replace(result,action=None,value=result.pass_value,reason='pass_for_match_resources',revision='hero-pass-v1')
