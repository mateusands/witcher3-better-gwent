"""Original fair draw sampler for isolated Gwent determinizations.

Input counts are the observer's own remaining collection, or hypothetical opponent
counts. Never pass the opponent's real private deck or shuffled draw order here.
Only the caller's isolated random generator is used; live game state is untouched.
"""
from dataclasses import replace


def resolve_draws(position,rng):
    """Replace unresolved draw placeholders with a uniform without-replacement sample.

    Position.apply records Spy draws as unknown_draws without decrementing counts.
    Each sample therefore decrements one copy. Future Muster can then consume the
    sampled remainder, without pretending a previously drawn copy stayed in deck.
    """
    count=position.unknown_draws
    if count<0 or any(n<0 for n in position.counts.values()):
        raise ValueError('negative draw/count')
    if count>sum(position.counts.values()):raise ValueError('draws exceed remaining deck')
    if any(n and t not in position.catalog for t,n in position.counts.items()):
        raise ValueError('remaining template missing from catalog')
    state=position.clone()
    for _ in range(count):
        # Sorted template counts ensure repeatability independent of map insertion
        # order. Sampling a copy index gives each remaining physical copy equal odds.
        index=rng.randrange(sum(state.counts.values()))
        for template,n in sorted(state.counts.items()):
            if index<n:break
            index-=n
        state.counts[template]-=1
        state.next_key-=1
        while state.next_key in state.cards:state.next_key-=1
        drawn=replace(state.catalog[template],key=state.next_key,owner=state.player,
            player=state.player,row=1,applied=())
        state.cards[drawn.key]=drawn;state.hand+=(drawn.key,)
    state.unknown_draws=0;state.draw_value=0
    return state
