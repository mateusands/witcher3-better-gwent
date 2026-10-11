"""Source-derived timing diagnostic must preserve callback logic and restore hooks."""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fx_timeline_diagnostic import native_timelines, timeline_hook
from gwentsim.gwint.headless import CardFX, Scheduler


def test_completion_frames_come_from_native_timeline():
    values = native_timelines()
    assert values['CardFXDeploy']['finishFrame'] == 19
    assert values['CardFXScorch']['finishFrame'] == 43
    assert values['CardFXDeploy']['playFrame'] == values['CardFXScorch']['playFrame'] == 1
    assert values['CardFXDeploy']['fps'] == values['CardFXScorch']['fps'] == 24
    assert values['CardFXScorch']['durationMs'] > values['CardFXDeploy']['durationMs']


def test_later_deploy_finishes_before_earlier_scorch():
    events = []; scheduler = Scheduler()
    scorch = CardFX('CardFXScorch'); deploy = CardFX('CardFXDeploy')
    scorch.cardFXManagerFinishCallback = lambda fx: events.append(('scorch', scheduler.now))
    deploy.cardFXManagerFinishCallback = lambda fx: events.append(('deploy', scheduler.now))
    with timeline_hook():
        scorch.play()
        scheduler.at(500, deploy.play)
        scheduler.run(lambda: len(events) == 2)
    assert events == [('deploy', 1250), ('scorch', 1750)]


def test_diagnostic_restores_play_even_on_failure():
    original = CardFX.play
    with pytest.raises(RuntimeError):
        with timeline_hook():
            assert CardFX.play is not original
            raise RuntimeError('intentional diagnostic failure')
    assert CardFX.play is original
