"""Original single-observer information-set MCTS kernel.

Algorithm reference: Cowling, Powley and Whitehouse (2012), Information Set
Monte Carlo Tree Search, DOI 10.1109/TCIAIG.2012.2204883. Written from the paper;
no third-party implementation is used. Domain adapters must supply only sampled
hidden states consistent with their observer, and observable move keys.

This module does not claim Gwent integration: legal transitions, sampled draws,
rollouts and exact passed-opponent finishing are separate adapter requirements.
"""
from dataclasses import dataclass,field
from math import log,sqrt,isfinite
from random import Random
from time import perf_counter
from typing import Hashable,Protocol,Callable


class SearchState(Protocol):
    to_move:int

    def legal_actions(self) -> dict[Hashable,object]:
        """Observable move key -> executable action for this determinization."""
        ...

    def next_state(self,action:object,rng:Random) -> 'SearchState':
        """Return an isolated successor; never mutate the live game."""
        ...

    def terminal_reward(self,observer:int) -> float|None:
        """Return observer reward in [0,1], or None when nonterminal."""
        ...


@dataclass
class Node:
    visits:int=0
    available:int=0
    reward:float=0
    children:dict=field(default_factory=dict)
    outcomes:dict=field(default_factory=dict)

    @property
    def mean(self):
        return self.reward/self.visits if self.visits else 0


@dataclass(frozen=True)
class Arm:
    move:Hashable
    visits:int
    availability:int
    mean:float


@dataclass(frozen=True)
class Result:
    move:Hashable|None
    iterations:int
    elapsed_seconds:float
    arms:tuple
    stopped:str
    revision:str='so-ismcts-kernel-v1'


def search(determinize:Callable[[Random],SearchState],rollout:Callable,
           observer:int,*,iterations:int,seed:int=0,time_limit:float|None=None,
           exploration:float=sqrt(2),max_tree_depth:int=128,clock=perf_counter,
           cutoff:Callable|None=None):
    """Build one shared observer tree with availability-correct UCB selection.

    Each iteration receives a fresh determinization. Opponent nodes minimize the
    observer's reward (two-player zero-sum assumption). Expand at most one edge per
    iteration; use the supplied domain rollout/evaluator thereafter. Return the most
    visited root move, not an optimistic single-determinization best move.

    An iteration budget is reproducible; elapsed-time stopping is not guaranteed to
    be reproducible under worker scheduling. A deadline is checked between iterations;
    domain adapters must bound their own transitions/rollouts.

    Optional cutoff(state, observer) returns an estimated reward at an unresolved
    domain boundary, or None when tree expansion remains valid. It is checked at
    every nonterminal tree state, including newly expanded successors. Missing
    domain actions must not become fictitious forced moves deeper in the tree.
    """
    if iterations<0 or max_tree_depth<1:raise ValueError('invalid iteration/depth budget')
    if time_limit is not None and time_limit<0:raise ValueError('negative time budget')
    if exploration<0 or not isfinite(exploration):raise ValueError('invalid exploration')
    rng=Random(seed);root=Node();started=clock();completed=0;stopped='iterations'
    def evaluate(state):
        reward=state.terminal_reward(observer)
        return cutoff(state,observer) if reward is None and cutoff is not None else reward
    for _ in range(iterations):
        if time_limit is not None and clock()-started>=time_limit:
            stopped='time';break
        state=determinize(rng);node=root;path=[root];reward=None
        for depth in range(max_tree_depth):
            reward=evaluate(state)
            if reward is not None:break
            legal=state.legal_actions()
            if not legal:raise ValueError('nonterminal state has no legal action')
            # Availability belongs to an edge, not its parent visit count. Hidden
            # hands can make the siblings legal on different subsets of iterations.
            for move in legal:
                if move in node.children:node.children[move].available+=1
            unseen=[move for move in legal if move not in node.children]
            if unseen:
                move=rng.choice(unseen)
                child=Node(available=1);node.children[move]=child
                state=state.next_state(legal[move],rng);path.append(child)
                reward=evaluate(state)
                if reward is None:reward=rollout(state,rng,observer)
                break
            maximizing=state.to_move==observer
            def bound(move):
                child=node.children[move]
                exploitation=child.mean if maximizing else 1-child.mean
                return exploitation+exploration*sqrt(log(max(1,child.available))/child.visits)
            scored=[(bound(move),move) for move in legal]
            maximum=max(value for value,move in scored)
            move=rng.choice([move for value,move in scored if abs(value-maximum)<1e-12])
            edge=node.children[move];state=state.next_state(legal[move],rng);path.append(edge)
            # A domain may reveal a draw or stochastic public result between
            # decisions. Keep distinguishable observations in separate information
            # sets, while the action edge aggregates all outcomes for root choice.
            observe=getattr(state,'information_key',None)
            if observe is not None:
                node=edge.outcomes.setdefault(observe(observer),Node());path.append(node)
            else:node=edge
        else:
            reward=rollout(state,rng,observer)
        if reward is None:reward=rollout(state,rng,observer)
        if not isfinite(reward) or not 0<=reward<=1:raise ValueError('reward must be finite and in [0,1]')
        for visited in path:
            visited.visits+=1;visited.reward+=reward
        completed+=1
    arms=tuple(Arm(move,n.visits,n.available,n.mean) for move,n in root.children.items())
    best=max(arms,key=lambda arm:(arm.visits,arm.mean)).move if arms else None
    return Result(best,completed,max(0,clock()-started),arms,stopped)
