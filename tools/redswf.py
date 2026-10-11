#!/usr/bin/env python3
# redswf and bundle helpers, shared with the Gwent Players Map project (same formats).
#   split_redswf(red)                 -> (swf, trailer)
#   patch_redswf(red, swf, trailer)   -> new redswf bytes
#   build_bundle([(path, data, compress)]) -> (blob0.bundle bytes, metadata.store bytes)
import os, struct, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import metastore  # noqa: E402


def split_redswf(red):
    c0 = red.find(b'CFX')
    ln = struct.unpack('<I', red[c0 + 4:c0 + 8])[0]
    full = b'FWS' + red[c0 + 3:c0 + 8] + zlib.decompressobj().decompress(red[c0 + 8:])
    swf, trailer = full[:ln], full[ln:]
    assert swf.endswith(b'\0\0'), 'SWF does not end with an End tag at the header length'
    return swf, trailer


def patch_redswf(red, new_swf, trailer):
    tables = [list(struct.unpack('<III', red[0x28 + 12 * i:0x28 + 12 * i + 12])) for i in range(10)]
    chunk_off, chunk_cnt = tables[4][0], tables[4][1]
    chunks = [list(struct.unpack('<HHIIIII', red[chunk_off + 24 * i:chunk_off + 24 * i + 24])) for i in range(chunk_cnt)]
    c0_size, c0_off = chunks[0][3], chunks[0][4]
    cfx = red.find(b'CFX', c0_off, c0_off + c0_size)
    old_len = struct.unpack('<I', red[cfx - 4:cfx])[0]

    # The header length covers the SWF only; Scaleform keeps a symbol name table after it.
    gfx = b'CFX' + new_swf[3:4] + struct.pack('<I', len(new_swf)) + zlib.compress(new_swf[8:] + trailer, 9)
    delta = len(gfx) - old_len
    out = bytearray(red[:cfx - 4] + struct.pack('<I', len(gfx)) + gfx + red[cfx + old_len:])

    chunks[0][3] += delta
    for c in chunks[1:]:
        c[4] += delta
    table = b''.join(struct.pack('<HHIIIII', *c) for c in chunks)
    out[chunk_off:chunk_off + len(table)] = table
    tables[4][2] = zlib.crc32(table)
    struct.pack_into('<III', out, 0x28 + 12 * 4, *tables[4])
    struct.pack_into('<II', out, 0x18, len(out), len(out))   # file size, buffer size
    return bytes(out)


def fnv1a64(b):
    h = 0xcbf29ce484222325
    for c in b:
        h = ((h ^ c) * 0x100000001b3) & 0xffffffffffffffff
    return h


def cint(v):
    out = bytearray([(v & 0x3f) | (0x40 if v >> 6 else 0)])
    v >>= 6
    while v:
        out.append((v & 0x7f) | (0x80 if v >> 7 else 0))
        v >>= 7
    return bytes(out)


def build_bundle(files):
    """files: list of (path, data, compress). Returns (bundle bytes, metadata.store bytes)."""
    toc_size = 0x130 * len(files)
    data_off = 0x20 + toc_size
    entries, body, meta_files = b'', bytearray(), []
    for path, data, compress in files:
        payload = zlib.compress(data, 9) if compress else data
        offset = data_off + len(body)
        entry = bytearray(0x130)
        entry[:len(path)] = path.encode()
        struct.pack_into('<IIIIII', entry, 0x110, offset, 0, len(data), len(payload), zlib.crc32(data), 1 if compress else 0)
        entries += bytes(entry)
        body += payload + b'\0' * (-len(payload) % 16)
        meta_files.append(dict(path=path, size=len(data), zsize=len(payload), comp=1 if compress else 0, offset=offset))
    hdr = b'POTATO70' + struct.pack('<III', data_off + len(body), 0, toc_size) + struct.pack('<HI', 5, data_off) + b'\0' * 6
    assert len(hdr) == 0x20
    meta = metastore.build(meta_files, len(body), data_off)
    return hdr + entries + bytes(body), meta
