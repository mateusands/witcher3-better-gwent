"""Original resource safeguard for a won round against a passed opponent.

Do not spend a card that only raises this round's score. Preserve resource-producing
effects and faction carry candidates. The projection uses own information and public
effects, never the opponent's hidden hand or the actual shuffled draw order.
"""
from dataclasses import replace
from gwentsim import constants as C
from gwentsim.position import UnsupportedPosition
from gwentsim.response_search import secured


def safe_spy_draw(position,context,action):
    """A single spy is beneficial only if it draws and preserves the secured result.

    This diagnostic is not a veto on multi-action spy/Decoy plans. Printed power
    alone is insufficient because weather, Horn and DoubleSpy change its cost.
    """
    card=position.cards.get(action.source)
    if card is None or not card.is_type(C.CardType_Spy):return False
    try:after=position.apply(action)
    except (UnsupportedPosition,ValueError):return False
    return after.unknown_draws>position.unknown_draws and secured(after,context)


def refine_secured_round(position,context,result):
    if not context.opponent_passed or result.action is None or not secured(position,context):return result
    source=result.action.source
    if source not in position.hand:return result
    card=position.cards[source]
    # Spies, Medic, Decoy, Muster, transformation and death summons can conserve
    # or produce future resources. Do not replace those plans with a blanket pass.
    plain=card.is_type(C.CardType_Creature) and not card.is_type(C.CardType_Spy) and set(card.effects)<={C.CardEffect_None}
    carry_faction=context.own_faction in (C.FactionId_No_Mans_Land,C.FactionId_Skellige)
    useless_body=plain and (card.is_type(C.CardType_Hero) or not carry_faction)
    horn=card.is_type(C.CardType_Row_Modifier) and set(card.effects)=={C.CardEffect_Horn}
    weather=card.is_type(C.CardType_Weather) and set(card.effects)<={
        C.CardEffect_Melee,C.CardEffect_Ranged,C.CardEffect_Siege,C.CardEffect_ClearSky}
    if not (useless_body or horn or weather):return result
    try:position.apply(result.action)
    except (UnsupportedPosition,ValueError):return result
    return replace(result,action=None,value=result.pass_value,
        reason='pass_for_match_resources',revision='secured-round-v1')
