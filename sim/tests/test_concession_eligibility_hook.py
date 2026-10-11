"""Concession prototype seat isolation and restoration on match errors."""
from types import SimpleNamespace
import pytest
from test_horn_evaluation import board
from test_concession_eligibility import scenario
from evaluate_concession_eligibility import concession_hook
from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController


def test_hook_only_changes_the_candidate_seat(board,monkeypatch):
    state,context,reference=scenario(board)
    original=lambda controller,position,context:reference
    monkeypatch.setattr(ResponseAIPlayerController,'search',original)
    audit=[]
    with concession_hook(0,audit):
        assert ResponseAIPlayerController.search(SimpleNamespace(playerID=1),state,context) is reference
        assert audit==[]
        corrected=ResponseAIPlayerController.search(SimpleNamespace(playerID=0),state,context)
        assert corrected.action is None and len(audit)==1 and audit[0]['changed']
    assert ResponseAIPlayerController.search is original


def test_match_error_restores_the_original_search():
    original=ResponseAIPlayerController.search
    with pytest.raises(RuntimeError):
        with concession_hook(0,[]):raise RuntimeError('test interrupted match')
    assert ResponseAIPlayerController.search is original
