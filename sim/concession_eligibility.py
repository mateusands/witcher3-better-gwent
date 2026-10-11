"""Original V7 experiment: an inert Mushroom must not veto a concession.

No transformation is simulated. Only restore the existing pass comparison when
all unmodeled hand cards are Mushroom row modifiers with no reachable current
target. Future draws/Medic/Muster/Decoy and available leaders retain the veto.
The V7 utility itself remains heuristic; this is not an optimal-pass proof.
"""
from dataclasses import replace
from math import isfinite
from gwentsim import constants as C


def inert_mushroom_veto(position):
    unsupported=[position.cards[k] for k in position.hand
                 if not position.supported(position.cards[k])]
    if not unsupported or position.unknown_draws:return False
    if (position.leader_ready or {}).get(position.player,False):return False
    if any(not c.is_type(C.CardType_Row_Modifier) or
           set(c.effects)!={C.CardEffect_Mushroom} for c in unsupported):return False
    hand=[position.cards[k] for k in position.hand]
    # Without any acquisition/recovery action, unseen own deck Berserkers cannot
    # enter this round. Their future-round value is not erased or reclassified.
    acquiring=(C.CardEffect_Draw,C.CardEffect_Draw2,C.CardEffect_Nurse,
               C.CardEffect_SummonClones,C.CardEffect_UnsummonDummy)
    if any(any(c.has(e) for e in acquiring) for c in hand):return False
    current=hand+[position.cards[k] for (side,row),keys in position.board.items()
                  if side==position.player for k in keys]
    if any(c.has(C.CardEffect_Morph) for c in current):return False
    # Do not infer the outcome of an unmodeled death/transform on the own board.
    if any(c.is_type(C.CardType_Creature) and not position.supported(c)
           for c in current):return False
    return True


def refine_concession_eligibility(position,context,result):
    if context.round_index!=1 or (context.own_losses,context.opponent_losses)!=(0,1):return result
    if context.opponent_passed or context.own_leader_available:return result
    if result.action is None or result.reason!='supported_response' or result.budget_exhausted:return result
    if not all(isfinite(v) and 0<=v<=1 for v in (result.value,result.pass_value)):return result
    if result.pass_value<=result.value+1e-12 or not inert_mushroom_veto(position):return result
    return replace(result,action=None,value=result.pass_value,
        reason='pass_for_match_resources',revision='concession-eligibility-v1')
