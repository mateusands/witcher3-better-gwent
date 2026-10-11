"""Algorithm tests with small imperfect-information games, not Gwent win claims."""
from dataclasses import dataclass
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gwentsim.ismcts import search


@dataclass(frozen=True)
class HiddenChoice:
    hidden:bool
    to_move:int=0
    reward:float|None=None

    def legal_actions(self):
        return dict(common='common',**({'rare':'rare'} if self.hidden else {}))

    def next_state(self,action,rng):
        assert action in self.legal_actions()
        return HiddenChoice(self.hidden,reward=1 if action=='rare' else 0.25)

    def terminal_reward(self,observer):return self.reward


def rollout(state,rng,observer):
    while state.terminal_reward(observer) is None:
        state=state.next_state(rng.choice(list(state.legal_actions().values())),rng)
    return state.terminal_reward(observer)


def test_availability_counts_and_shared_tree_across_hidden_hands():
    result=search(lambda rng:HiddenChoice(rng.random()<0.35),rollout,0,iterations=200,seed=19)
    arms={a.move:a for a in result.arms}
    assert result.iterations==200
    assert arms['common'].availability==200
    assert 0<arms['rare'].availability<200
    assert all(0<a.visits<=a.availability for a in result.arms)
    assert sum(a.visits for a in result.arms)==200


@dataclass(frozen=True)
class Adversarial:
    stage:int=0
    to_move:int=0
    reward:float|None=None

    def legal_actions(self):
        return {'safe':'safe','trap':'trap'} if self.stage==0 else {'punish':'punish','blunder':'blunder'}

    def next_state(self,action,rng):
        if self.stage==0:
            return Adversarial(1,1,0.6 if action=='safe' else None)
        return Adversarial(2,0,0 if action=='punish' else 1)

    def terminal_reward(self,observer):return self.reward


def test_opponent_minimizes_observer_reward_instead_of_cooperating():
    result=search(lambda rng:Adversarial(),rollout,0,iterations=600,seed=5)
    assert result.move=='safe'
    trap=next(a for a in result.arms if a.move=='trap')
    assert trap.mean<0.3


def test_fixed_iteration_search_repeats_without_global_randomness():
    kwargs=dict(iterations=80,seed=26)
    a=search(lambda rng:HiddenChoice(rng.random()<0.5),rollout,0,**kwargs)
    b=search(lambda rng:HiddenChoice(rng.random()<0.5),rollout,0,**kwargs)
    assert (a.move,a.iterations,a.arms)==(b.move,b.iterations,b.arms)


def test_time_budget_and_zero_iterations_have_no_speculative_move():
    times=iter([0,0,2,2])
    result=search(lambda rng:HiddenChoice(True),rollout,0,iterations=100,time_limit=1,
        clock=lambda:next(times))
    assert result.iterations==1 and result.stopped=='time'
    empty=search(lambda rng:HiddenChoice(True),rollout,0,iterations=0)
    assert empty.move is None and not empty.arms


def test_invalid_rewards_are_not_backpropagated_as_valid_wins():
    with pytest.raises(ValueError,match='reward'):
        search(lambda rng:Adversarial(),lambda *args:2,0,iterations=4,seed=0)


def test_root_terminal_result_needs_no_legal_moves():
    result=search(lambda rng:HiddenChoice(False,reward=0.5),rollout,0,iterations=4)
    assert result.iterations==4 and result.move is None and not result.arms


def test_observed_chance_results_split_information_sets():
    # The same root action reveals either cue. A later decision may use that cue,
    # so merging the two nodes would cap value near 0.5 instead of learning both.
    from dataclasses import dataclass
    @dataclass
    class Cue:
        stage:int=0
        cue:int=0
        reward:float|None=None
        to_move:int=0
        def legal_actions(self):
            return {'draw':'draw'} if self.stage==0 else {'left':0,'right':1}
        def next_state(self,action,rng):
            if self.stage==0:return Cue(1,rng.randrange(2))
            return Cue(2,self.cue,float(action==self.cue))
        def terminal_reward(self,observer):return self.reward
        def information_key(self,observer):return (self.stage,self.cue)
    result=search(lambda rng:Cue(),lambda state,rng,observer:float(rng.randrange(2)==state.cue),
        0,iterations=500,seed=162)
    assert result.move=='draw' and result.arms[0].mean>0.9


def test_unobserved_chance_cannot_be_used_as_a_visible_cue():
    @dataclass
    class HiddenCue:
        stage:int=0
        hidden:int=0
        reward:float|None=None
        to_move:int=0
        def legal_actions(self):
            return {'draw':'draw'} if self.stage==0 else {'left':0,'right':1}
        def next_state(self,action,rng):
            if self.stage==0:return HiddenCue(1,rng.randrange(2))
            return HiddenCue(2,self.hidden,float(action==self.hidden))
        def terminal_reward(self,observer):return self.reward
        def information_key(self,observer):return self.stage
    result=search(lambda rng:HiddenCue(),lambda state,rng,observer:float(rng.randrange(2)==state.hidden),
        0,iterations=1000,seed=168)
    assert result.move=='draw' and 0.4<result.arms[0].mean<0.6


def test_tree_does_not_turn_an_unresolved_action_set_into_a_forced_win():
    @dataclass(frozen=True)
    class Partial:
        missing:bool=False
        reward:float|None=None
        to_move:int=0
        def legal_actions(self):
            return {'forced':'forced'} if self.missing else {'safe':'safe','unknown':'unknown'}
        def next_state(self,action,rng):
            if action=='safe':return Partial(reward=0.6)
            if action=='unknown':return Partial(missing=True,to_move=1)
            return Partial(reward=1)
        def terminal_reward(self,observer):return self.reward
    def stop(state,observer):return 0.2 if state.missing else None
    def partial_rollout(state,rng,observer):
        return state.reward if state.reward is not None else 0.2
    # Reproduces the old asymmetry: rollout cuts off, but the tree eventually
    # crosses the same boundary and manufactures a terminal result.
    old=search(lambda rng:Partial(),partial_rollout,0,iterations=200,seed=176)
    fixed=search(lambda rng:Partial(),partial_rollout,0,iterations=200,seed=176,cutoff=stop)
    assert old.move=='unknown' and next(a for a in old.arms if a.move=='unknown').mean>0.9
    assert fixed.move=='safe'
    assert next(a for a in fixed.arms if a.move=='unknown').mean==pytest.approx(0.2)


def test_domain_cutoff_at_root_leaves_no_speculative_move_and_validates_reward():
    result=search(lambda rng:HiddenChoice(True),rollout,0,iterations=8,
        cutoff=lambda state,observer:0.4)
    assert result.iterations==8 and result.move is None and not result.arms
    with pytest.raises(ValueError,match='reward'):
        search(lambda rng:HiddenChoice(True),rollout,0,iterations=8,
            cutoff=lambda state,observer:float('nan'))
