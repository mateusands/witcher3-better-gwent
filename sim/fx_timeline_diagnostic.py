"""Isolated native-timeline timing hypothesis; never patches shared engine files.

SWF frame labels and the original completion frame scripts supply durations. The
first-frame scheduling offset is not verified in Scaleform. This is diagnostic
only and must pass strict replay before any proposed simulator change.
"""
from contextlib import contextmanager
from pathlib import Path
import re
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]

def native_timelines():
    raw = (ROOT/'game/vanilla/swf/gwint_game.swf').read_bytes()
    body = zlib.decompress(raw[8:]) if raw[:3] == b'CWS' else raw[8:]
    offset = (5 + 4 * (body[0] >> 3) + 7) // 8
    fps = struct.unpack_from('<H', body, offset)[0] / 256
    sprites = {}
    def tags(data, start):
        while start < len(data):
            header = struct.unpack_from('<H', data, start)[0]; start += 2
            kind, length = header >> 6, header & 63
            if length == 63:
                length = struct.unpack_from('<I', data, start)[0]; start += 4
            yield kind, data[start:start+length]
            start += length
    for kind, value in tags(body, offset+4):
        if kind != 39: continue
        symbol, count = struct.unpack_from('<HH', value)
        frame = 1; labels = {}
        for nested, payload in tags(value, 4):
            if nested == 43: labels[payload.split(b'\0')[0].decode()] = frame
            if nested == 1: frame += 1
        sprites[symbol] = (count, labels)
    result = {}
    for name in ('CardFXDeploy','CardFXScorch'):
        source = (ROOT/f'game/vanilla/as/scripts/{name}.as').read_text()
        symbol = int(re.search(r'symbol="symbol(\d+)"', source)[1])
        ending = int(re.search(r'addFrameScript\((\d+),this.frame\d+\)', source)[1])+1
        count, labels = sprites[symbol]
        if 'fxEnded();' not in source or labels.get('play') is None or ending > count:
            raise ValueError('unsupported native FX timeline')
        result[name] = dict(symbol=symbol, fps=fps, playFrame=labels['play'],
            finishFrame=ending, durationMs=round((ending-labels['play'])*1000/fps))
    return result

@contextmanager
def timeline_hook():
    from gwentsim.gwint.headless import CardFX, Scheduler
    timelines = native_timelines(); original = CardFX.play
    def play(fx):
        if fx.className not in timelines: return original(fx)
        scheduler = Scheduler.current(); head = scheduler.fx_batch_head()
        duration = timelines[fx.className]['durationMs']
        scheduler.at(duration//2, fx.midFXPoint, fx_head=head)
        scheduler.at(duration, fx.fxEnded, fx_head=head)
    CardFX.play = play
    try: yield timelines
    finally: CardFX.play = original
