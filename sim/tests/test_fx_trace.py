"""Diagnostic wire format, chunk integrity and observed completion ordering."""
import json
import os
import sys
import tempfile
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import rec_read
import rec_harvest
from fx_analyze import analyze
from build_recorder import edit_fx_trace


def trace(phase, fx_id, frame, clip_frame, time_ms=100):
    return rec_read.parse_record('Y%s:%d:160.%d:%d:%d:%d:43:1:4:2' %
                                 (phase, fx_id, fx_id, time_ms, frame, clip_frame))


def traced_raw_recording():
    lines = (ROOT / 'game/records/raw/g107.txt').read_text().splitlines()
    raw = {k: v.strip('"') for k, v in (line.split('=', 1) for line in lines)}
    chunk_keys = sorted(k for k in raw if k[-4:].isdigit())
    text = ''.join(raw[k] for k in chunk_keys)
    # Insert valid diagnostics into a complete real record and re-chunk at real wire size.
    extra = 'Ystart:12:160.12:100:7:1:43:1:4:2;Yend:12:160.12:800:50:43:43:1:4:1;'
    text = text.replace('Efinal;', extra + 'Efinal;')
    chunks = [text[i:i + rec_read.CHUNK] for i in range(0, len(text), rec_read.CHUNK)]
    raw = {'g107_%04d' % i: chunk for i, chunk in enumerate(chunks)}
    raw['g107_end'] = '%d/%d/final' % (len(chunks), len(chunks))
    return raw


def test_diagnostic_roundtrip_preserves_full_recording():
    info, records, problems = rec_read.load_match(traced_raw_recording(), 107)
    assert not problems, problems
    parsed = rec_read.structure(info, records)
    original = json.loads((ROOT / 'game/records/g107.json').read_text())
    assert parsed['events'] == original['events']
    assert parsed['templates'] == original['templates']
    assert parsed['decks'] == original['decks']
    assert len(parsed['fxTrace']) == 2
    assert all(t['eventIndex'] == len(original['events']) - 1 for t in parsed['fxTrace'])


def test_analysis_keeps_observed_order_and_incomplete_batches():
    rows = [trace('start', 12, 7, 1), trace('start', 24, 7, 1),
            trace('end', 24, 50, 43, 800), trace('end', 12, 50, 43, 800)]
    for row in rows:
        row['eventIndex'] = 4
    batches, errors = analyze(rows)
    assert not errors
    assert batches[0]['completionOrder'] == [2, 1]
    assert batches[0]['order'] == 'first finishes last'
    batches, errors = analyze(rows[:3])
    assert not errors
    assert batches[0]['order'] == 'incomplete'
    assert batches[0]['missing'] == [12]


def test_parser_rejects_malformed_diagnostics():
    for wire in ('Yend:12', 'Ybad:12:160.12:100:7:1:43:1:4:2',
                 'Yend:12:160.12:100:7:44:43:1:4:2'):
        try:
            rec_read.parse_record(wire)
        except rec_read.RecError:
            continue
        raise AssertionError('accepted invalid trace: ' + wire)


def test_trace_patch_preserves_every_original_statement():
    source = (ROOT / 'game/vanilla/as/scripts/red/game/witcher3/menus/gwint/CardFXManager.as').read_text()
    patched = edit_fx_trace(source, '\n')
    block = (ROOT / 'tools/recorder_as/CardFXManager.trace.txt').read_text()
    stripped = patched.replace(block, '')
    for line in ('   import flash.events.Event;\n', '   import flash.utils.getTimer;\n',
                 '   import flash.utils.getQualifiedClassName;\n',
                 '         this.addEventListener(Event.ENTER_FRAME,this.gwaiFrameTick,false,0,true);\n',
                 '         this.gwaiTraceScorch("start",newCardFX);\n',
                 '         this.gwaiTraceScorch("end",cardFX);\n',
                 '         this.gwaiTraceScorch("applied",cardFX);\n'):
        assert stripped.count(line) == 1
        stripped = stripped.replace(line, '')
    assert stripped == source


def test_automatic_harvest_retains_trace_and_backs_up_settings():
    raw = traced_raw_recording()
    with tempfile.TemporaryDirectory() as folder:
        base = Path(folder)
        settings = base / 'dx12user.settings'
        original = ('[Rendering]\r\nVSync=true\r\n\r\n[GwaiRec]\r\ngames="108"\r\n' +
                    ''.join('%s="%s"\r\n' % item for item in sorted(raw.items())))
        settings.write_bytes(original.encode())
        out = base / 'records'
        backups = base / 'backups'
        with patch.multiple(rec_harvest, FILES=[str(settings)], OUT=str(out),
                            BACKUPS=str(backups), LOG=str(out / 'harvest.log')):
            with patch.object(rec_harvest, 'game_running', return_value=False):
                assert rec_harvest.harvest() == 0
        saved = json.loads((out / 'g107.json').read_text())
        expected = json.loads((ROOT / 'game/records/g107.json').read_text())
        assert saved['events'] == expected['events']
        assert len(saved['fxTrace']) == 2
        assert (out / 'raw/g107.txt').exists()
        copies = list(backups.glob('dx12user.settings.*'))
        assert len(copies) == 1 and copies[0].read_bytes() == original.encode()
        cleaned = settings.read_bytes().decode()
        assert 'g107_' not in cleaned and 'games="108"' in cleaned
        assert cleaned.startswith('[Rendering]\r\nVSync=true\r\n')


def test_nested_callback_entry_and_return_orders_are_distinct():
    rows = [trace('start', 12, 7, 1), trace('start', 24, 7, 1),
            trace('end', 12, 50, 43, 800), trace('end', 24, 50, 43, 801),
            trace('applied', 24, 50, 43, 802), trace('applied', 12, 50, 43, 803)]
    for row in rows:
        row['eventIndex'] = 4
    batches, errors = analyze(rows)
    assert not errors
    assert batches[0]['completionOrder'] == [1, 2]
    assert batches[0]['callbackReturnOrder'] == [2, 1]
    assert batches[0]['callbackReturnsMissing'] == []
    partial, errors = analyze(rows[:-1])
    assert not errors and partial[0]['callbackReturnsMissing'] == [12]
    _, errors = analyze(rows[:2] + rows[4:])
    assert len(errors) == 2
