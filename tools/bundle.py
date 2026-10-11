import struct, sys, zlib, os
def lz4_block(src, usize):
    dst = bytearray(); i = 0; n = len(src)
    while i < n:
        tok = src[i]; i += 1
        l = tok >> 4
        if l == 15:
            while True:
                b = src[i]; i += 1; l += b
                if b != 255: break
        dst += src[i:i+l]; i += l
        if i >= n: break
        off = src[i] | (src[i+1] << 8); i += 2
        m = tok & 15
        if m == 15:
            while True:
                b = src[i]; i += 1; m += b
                if b != 255: break
        m += 4
        s = len(dst) - off
        for k in range(m): dst.append(dst[s+k])
    return bytes(dst)
def toc(path):
    f = open(path, 'rb'); h = f.read(0x20)
    assert h[:8] == b'POTATO70', h[:8]
    info = struct.unpack('<I', h[16:20])[0]
    data = f.read(info); out = []
    for k in range(info // 0x130):
        e = data[k*0x130:(k+1)*0x130]
        name = e[:0x100].split(b'\0')[0].decode(errors='replace')
        off, _z, size, zsize, _c, comp = struct.unpack('<IIIIII', e[0x110:0x128])
        out.append((name, size, zsize, off, comp))
    return out
def extract(path, ent):
    name, size, zsize, off, comp = ent
    with open(path, 'rb') as f:
        f.seek(off); raw = f.read(zsize)
    if comp == 0: return raw
    if comp == 1: return zlib.decompress(raw)
    if comp in (4, 5): return lz4_block(raw, size)
    raise Exception('comp %d' % comp)
if __name__ == '__main__':
    b = sys.argv[1]
    for e in toc(b):
        if len(sys.argv) < 3 or sys.argv[2] in e[0]: print(e)
