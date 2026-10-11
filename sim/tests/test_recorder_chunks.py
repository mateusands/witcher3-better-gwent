"""Cancelled quits flush short chunks; arbitrary truncation remains invalid."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import rec_read


def raw(chunks):
    result = {'g000_%04d' % i: chunk for i, chunk in enumerate(chunks)}
    result['g000_end'] = '%d/%d/final' % (len(chunks), len(chunks))
    return result


def test_cancelled_quit_flushes_can_be_followed_by_more_events():
    _, records, problems = rec_read.load_match(raw(['RFL1:0;Equit;', 'Equit;', 'RFL1:1;Efinal;']), 0)
    assert not problems
    assert [r['k'] for r in records] == ['R', 'E', 'E', 'R', 'E']


def test_unexplained_short_chunk_and_early_final_are_rejected():
    for chunks in (['RFL1:0;', 'Efinal;'], ['Efinal;', 'Efinal;'], ['', 'Efinal;']):
        assert rec_read.load_match(raw(chunks), 0)[2]


def test_missing_chunks_and_bad_end_counts_still_fail():
    record = raw(['Equit;', 'Equit;', 'Efinal;'])
    del record['g000_0001']
    assert rec_read.load_match(record, 0)[2]
    record = raw(['Equit;', 'Efinal;'])
    record['g000_end'] = '3/3/final'
    assert rec_read.load_match(record, 0)[2]
