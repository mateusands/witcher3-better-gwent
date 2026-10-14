"""Frame-time records (Q) from the recorder of 14 October 2026.

Spec: recorder builds of 14 October 2026 wrote the Gwent screen's frame times as Q records
(Q<think|idle>:<frames>:<totalMs>:<maxMs>:<over33ms>:<over50ms>). The measurement was removed the
same day: the Gwent screen ticks at its own 24 frames per second, so it never shows the game's
frame rate (MangoHud does). Matches g173-g175 hold Q records, so the reader still parses them and
keeps them out of the replay events.

Given a Q record, when the reader parses and structures it, then it is a frame window outside
the replay events; a malformed window is rejected.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import rec_read  # noqa: E402


def test_q_record_parses_and_stays_out_of_replay_events():
    record = rec_read.parse_record('Qthink:12:450:61:9:4')
    assert record == {'k': 'Q', 'phase': 'think', 'frames': 12, 'totalMs': 450, 'maxMs': 61,
                      'over33': 9, 'over50': 4}
    for bad in ('Qthink:1:2', 'Qbusy:1:2:3:4:5', 'Qidle:2:10:20:0:0', 'Qidle:-1:0:0:0:0'):
        with pytest.raises((rec_read.RecError, ValueError)):
            rec_read.parse_record(bad)
    structured = rec_read.structure({}, [{'k': 'F', 'first': 0}, record, {'k': 'E', 'reason': 'final'}])
    assert [e['k'] for e in structured['events']] == ['F', 'E']
    assert structured['frames'] == [dict(phase='think', frames=12, totalMs=450, maxMs=61, over33=9,
                                         over50=4, eventIndex=1)]
