"""Match ids in the recorder's settings section (tools/rec_harvest.py).

Spec: the game names matches g100, g101, ... and, from the thousandth on, g1000 and up. The
harvest removes every match it reads from the settings file, so it must read every match id,
however many digits, or a match would be deleted without being saved.

Given recorder keys of a 3-digit and a 4-digit match and the counter,
when the harvest lists the matches,
then both ids are listed and the counter is not.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))

import rec_harvest  # noqa: E402


def test_every_match_id_is_listed():
    inside = {'g157_c0': '', 'g157_c1': '', 'g1000_c0': '', 'games': ''}
    assert rec_harvest.match_ids(inside) == [157, 1000]
