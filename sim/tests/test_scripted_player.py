"""Reject invalid input and independently detect corrupted recorded outcomes."""
import copy
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import replay

ROOT = os.path.join(os.path.dirname(__file__), '..', '..')


def changed_recording(change):
    match = copy.deepcopy(replay.load_match(os.path.join(ROOT, 'game', 'records', 'g107.json')))
    change(match.events)
    with patch.object(replay, 'load_match', return_value=match):
        return replay.replay('modified-in-memory.json')[2]


def first(events, kind, predicate=lambda e: True):
    return next(e for e in events if e['k'] == kind and predicate(e))


def test_rejects_unoffered_mulligan_card():
    def change(events):
        first(events, 'C', lambda e: e['choice'] == 'mulligan')['arg'] = '99999'
    div = changed_recording(change)
    assert div is not None and 'not offered' in div.detail


def test_rejects_invalid_human_destination():
    def change(events):
        first(events, 'H', lambda e: e['player'] == 0)['tx']['slot'] = 2
    div = changed_recording(change)
    assert div is not None and 'cannot be placed' in div.detail


def test_detects_corrupted_snapshot_instead_of_copying_it():
    def change(events):
        first(events, 'S', lambda e: e['tag'].startswith('t'))['players'][0]['score'] += 1
    div = changed_recording(change)
    assert div is not None and 'P0.score' in div.detail


def test_rejects_unoffered_medic_choice():
    def change(events):
        player = None
        for event in events:
            if event['k'] == 'H':
                player = event['player']
            if event['k'] == 'C' and event['choice'] == 'nurse' and player == 0:
                event['arg'] = '99999'
                return
        raise AssertionError('no human medic choice in fixture')
    div = changed_recording(change)
    assert div is not None and 'not offered' in div.detail
