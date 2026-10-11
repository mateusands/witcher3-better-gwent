"""Projection/controller hook is scoped to one seat, including nested calls."""
from types import SimpleNamespace
from dataclasses import replace
import pytest
from test_horn_evaluation import board,unit,card
from test_position import capture
from test_secured_round_refinement import ctx,result
from mushroom_policy import mushroom_hook
from mushroom_position import MushroomPosition
from gwentsim.gwint import sequence_ai_controller as controllers
from gwentsim import constants as C


def test_projection_hook_targets_only_candidate_and_restores_on_nested_peer_call(board,monkeypatch):
    unit(board,7,5);state=capture(board);calls=[]
    reference=replace(result(None),reason='pass_for_match_resources')
    cls=controllers.ResponseAIPlayerController;original_position=controllers.Position
    peer=SimpleNamespace(playerID=1,_decidedCardTransaction=None)
    candidate=SimpleNamespace(playerID=0,_decidedCardTransaction=None)
    def search(controller,position,context):
        calls.append((controller.playerID,type(position)))
        return reference
    def begin(controller):
        if controller.playerID==0:cls.state_begin_ChoseMove(peer)
        return cls.search(controller,controllers.Position(**state.__dict__),ctx())
    monkeypatch.setattr(cls,'search',search)
    monkeypatch.setattr(cls,'state_begin_ChoseMove',begin)
    audit=[]
    with mushroom_hook(0,audit):
        corrected=cls.state_begin_ChoseMove(candidate)
        assert corrected.revision=='mushroom-projection-v1'
        assert calls==[(1,original_position),(0,original_position),(0,MushroomPosition)]
        assert controllers.Position is original_position
        assert len(audit)==1 and not audit[0]['changed']
    assert cls.search is search and cls.state_begin_ChoseMove is begin


def test_projection_and_methods_restore_after_search_error(board,monkeypatch):
    state=capture(board);cls=controllers.ResponseAIPlayerController
    original_position=controllers.Position
    def search(controller,position,context):
        if isinstance(position,MushroomPosition):raise RuntimeError('test projection failure')
        return result(None)
    def begin(controller):return cls.search(controller,controllers.Position(**state.__dict__),ctx())
    monkeypatch.setattr(cls,'search',search);monkeypatch.setattr(cls,'state_begin_ChoseMove',begin)
    with pytest.raises(RuntimeError):
        with mushroom_hook(0,[]):cls.state_begin_ChoseMove(SimpleNamespace(playerID=0,_decidedCardTransaction=None))
    assert cls.search is search and cls.state_begin_ChoseMove is begin
    assert controllers.Position is original_position


def test_failed_search_retains_native_intent_instead_of_reporting_a_false_pass(board,monkeypatch):
    u=card(board,7,1,C.CardType_Creature|C.CardType_Melee)
    state=capture(board);cls=controllers.ResponseAIPlayerController
    reference=replace(result(None),reason='no_supported_plan')
    monkeypatch.setattr(cls,'search',lambda controller,position,context:reference)
    native=SimpleNamespace(sourceCardInstanceRef=u,targetSlotID=5,targetCardInstanceRef=None)
    audit=[]
    with mushroom_hook(0,audit):
        returned=cls.search(SimpleNamespace(playerID=0,_decidedCardTransaction=native),state,ctx())
    assert returned.action is None and returned.reason=='no_supported_plan'
    assert not audit[0]['changed']
    assert audit[0]['reference']['action']==audit[0]['candidate']['action']
    assert audit[0]['candidate']['action']['source']==u.instanceId
