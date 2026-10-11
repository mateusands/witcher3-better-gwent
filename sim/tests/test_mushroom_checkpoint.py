"""Completed trial groups survive restart; mismatched plans are rejected."""
import pytest
import evaluate_mushroom_policy as runner


def test_completed_group_is_reused_without_resimulating(tmp_path,monkeypatch):
    monkeypatch.setattr(runner,'CHECKPOINT_DIR',tmp_path)
    monkeypatch.setattr(runner,'PLAN_SIGNATURE','same-prospective-plan')
    rows=[{'initialDealSha256':'same-deal'} for _ in range(6)]
    calls=[]
    def run(task):calls.append(task);return rows,None
    monkeypatch.setattr(runner.paired,'group',run)
    task=(2,217,False)
    assert runner.checkpoint_group(task)==(rows,None)
    assert runner.checkpoint_group(task)==(rows,None)
    assert calls==[task]
    assert not list(tmp_path.glob('*.tmp'))
    monkeypatch.setattr(runner,'PLAN_SIGNATURE','changed-source-or-input')
    with pytest.raises(ValueError,match='incompatible checkpoint'):
        runner.checkpoint_group(task)


def test_incomplete_group_is_not_accepted_as_complete(tmp_path,monkeypatch):
    import json
    monkeypatch.setattr(runner,'CHECKPOINT_DIR',tmp_path)
    monkeypatch.setattr(runner,'PLAN_SIGNATURE','plan')
    p=tmp_path/'pair-0-seed-217-swap-0.json'
    p.write_text(json.dumps({'planSignature':'plan','task':[0,217,False],'rows':[],'error':None}))
    with pytest.raises(ValueError,match='incomplete checkpoint'):
        runner.checkpoint_group((0,217,False))
