"""Candidate isolation and auditing for the paired resource-search experiment."""
from types import SimpleNamespace
import pytest
from test_horn_evaluation import board,unit
from test_position import capture
from test_secured_round_refinement import ctx,result
from evaluate_secured_resources import refinement_hook,summarize
from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController


def test_hook_targets_only_candidate_seat_and_counts_calls_separately(board,monkeypatch):
    unit(board,7,5);state=capture(board);reference=result(None)
    original=lambda controller,position,context:reference
    monkeypatch.setattr(ResponseAIPlayerController,'search',original)
    audit=[]
    with refinement_hook(0,audit):
        assert ResponseAIPlayerController.search(SimpleNamespace(playerID=1),state,ctx()) is reference
        assert audit==[]
        corrected=ResponseAIPlayerController.search(SimpleNamespace(playerID=0),state,ctx())
        assert corrected.action is None and len(audit)==1 and not audit[0]['changed']
        assert audit[0]['candidate']['revision']=='secured-resources-v1.1'
    assert ResponseAIPlayerController.search is original


def test_hook_restores_reference_when_match_raises(monkeypatch):
    original=ResponseAIPlayerController.search
    with pytest.raises(RuntimeError):
        with refinement_hook(0,[]):raise RuntimeError('test match failure')
    assert ResponseAIPlayerController.search is original


def test_summary_counts_actual_wins_draws_and_paired_regressions():
    def row(seed,variant,score,kind='native'):
        return dict(pair=0,seed=seed,swapped=False,seat=0,variant=variant,kind=kind,
            faction=3,score=score,calls=2 if variant=='candidate' else 0,
            actionChanges=1 if variant=='candidate' else 0)
    rows=[row(1,'v7',0),row(1,'candidate',1),row(2,'v7',1),row(2,'candidate',.5),
        row(3,'candidate',.5,'direct')]
    report=summarize(rows)
    assert report['paired']==dict(gains=1,regressions=1,equal=0,netScore=.5)
    assert report['versusNative']['candidate']==dict(games=2,score=1.5,wins=1,draws=1,losses=0,calls=4,actionChanges=2)
    assert report['direct']['score']==.5 and report['direct']['draws']==1
