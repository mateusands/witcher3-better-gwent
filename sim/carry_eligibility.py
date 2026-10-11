"""Do not predict Skellige revival of a board creature banished by round clear.

Known grave creatures retain native eligibility. Monster retention is deliberately
unchanged: the native keep-card selection precedes the banishment branch.
Expected printed power, Spy sign and ignored secondary effects remain V7 heuristics.
"""
from gwentsim import constants as C
from gwentsim.position import ROWS
from gwentsim.sequence_search import faction_carry as reference_carry


def eligible_carry(position, side, faction, next_round):
    if faction != C.FactionId_Skellige or next_round != 2:
        return reference_carry(position, side, faction, next_round)
    pool = [position.cards[k] for k in position.grave[side]] + [
        position.cards[k] for row in ROWS for k in position.board[side, row]
        if not position.cards[k].banished_on_clear]
    units = [c for c in pool if c.is_type(C.CardType_Creature)
             and not c.is_type(C.CardType_Hero)]
    return min(2, len(units)) * sum(-c.power if c.is_type(C.CardType_Spy) else c.power
                                  for c in units) / len(units) if units else 0
