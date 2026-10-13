"""The game's AS3 model includes the Skellige cards (sim/skellige_position.py), so the AS3
parity tests compare it with SkelligePosition. The opening-exchange tests keep the plain
Position: the Lab measured that exchange with it, and the AS3 exchange uses the plain reserve."""
import pytest

AS3 = ('test_v8_as_', 'test_v8_runner', 'test_v8_execution', 'test_v8_native_dispatch', 'test_v8_runtime_context')


@pytest.fixture(autouse=True)
def skellige_reference(request, monkeypatch):
    name = request.module.__name__.rpartition('.')[2]
    if name.startswith(AS3) and name != 'test_v8_as_mulligan' and hasattr(request.module, 'capture'):
        from skellige_position import SkelligePosition
        original = request.module.capture
        monkeypatch.setattr(request.module, 'capture', lambda *a, **k: SkelligePosition(**original(*a, **k).__dict__))
    yield


@pytest.fixture(autouse=True)
def lab_globals():
    """Lab tasks set module-wide switches (response_v8.VARIANT and NPC_SEAT, the deck genome, the
    tuning weights) for the task they run; a test never leaves them to the next test."""
    import gwentsim.response_v8 as v8
    from gwentsim import npc_balance, tuning
    saved = v8.VARIANT, v8.NPC_SEAT, npc_balance.GENOME, dict(tuning.SEAT_PARAMS)
    yield
    v8.VARIANT, v8.NPC_SEAT, npc_balance.GENOME = saved[:3]
    tuning.SEAT_PARAMS.clear(); tuning.SEAT_PARAMS.update(saved[3]); tuning.reset()
