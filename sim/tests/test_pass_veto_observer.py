"""Loss observer retains result identity and only records the selected seat."""
from types import SimpleNamespace
import pytest
from test_horn_evaluation import board
from test_concession_eligibility import scenario
from audit_pass_veto import observe_pass_veto
from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController


def test_observer_does_not_change_search_result_or_own_state(board,monkeypatch):
    state,context,reference=scenario(board)
    before=state.clone()
    original=lambda controller,position,context:reference
    monkeypatch.setattr(ResponseAIPlayerController,'search',original)
    audit=[]
    with observe_pass_veto(0,audit):
        assert ResponseAIPlayerController.search(SimpleNamespace(playerID=1),state,context) is reference
        assert audit==[]
        assert ResponseAIPlayerController.search(SimpleNamespace(playerID=0),state,context) is reference
    assert ResponseAIPlayerController.search is original
    assert state==before
    assert len(audit)==1 and audit[0]['inertMushroom']
    assert audit[0]['eligibilityVetoes']==['unsupported_hand']
    assert len(audit[0]['ownHand'])==len(state.hand)
    assert 'opponentHand' not in audit[0] and 'opponentDeck' not in audit[0]


def test_observer_restores_search_after_error():
    original=ResponseAIPlayerController.search
    with pytest.raises(RuntimeError):
        with observe_pass_veto(0,[]):raise RuntimeError('test observer interruption')
    assert ResponseAIPlayerController.search is original
