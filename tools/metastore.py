# Witcher 3 metadata.store (VTM v7) reader/writer, single bundle "blob0.bundle".
import struct

def rcint(d, p):
    b = d[p]; p += 1; v = b & 0x3f; sh = 6; more = b & 0x40
    while more:
        b = d[p]; p += 1; v |= (b & 0x7f) << sh; sh += 7; more = b & 0x80
    return v, p

def cint(v):
    out = bytearray([(v & 0x3f) | (0x40 if v >> 6 else 0)]); v >>= 6
    while v:
        out.append((v & 0x7f) | (0x80 if v >> 7 else 0)); v >>= 7
    return bytes(out)

def fnv1a64(b):
    h = 0xcbf29ce484222325
    for c in b:
        h = ((h ^ c) * 0x100000001b3) & 0xffffffffffffffff
    return h

def read(d):
    n, p = rcint(d, 16); st = d[p:p + n]; p += n
    s = lambda o: st[o:st.index(b'\0', o)].decode()
    c1, p = rcint(d, p); fi = [struct.unpack('<8I', d[p + i*32:p + i*32 + 32]) for i in range(c1)]; p += c1*32
    c2, p = rcint(d, p); fe = [struct.unpack('<6I', d[p + i*24:p + i*24 + 24]) for i in range(c2)]; p += c2*24
    c3, p = rcint(d, p); be = [struct.unpack('<QIIII', d[p + i*24:p + i*24 + 24]) for i in range(c3)]; p += c3*24
    p += 1
    files = []
    for i in range(1, c1):
        path = s(fi[i][0]); e = fe[fi[i][4]]
        files.append(dict(path=path, zsize=fi[i][2], size=fi[i][3], comp=fi[i][7], offset=e[0]))
    return files, be[1]

def build(files, bundle_data_size, header_size):
    """files: list of dict(path, size, zsize, comp, offset) in the order they should be listed."""
    st = bytearray(b'\0') + b'blob0.bundle\0'
    path_off = []
    for f in files:
        path_off.append(len(st)); st += f['path'].encode() + b'\0'
    root_off = len(st); st += b'\0'
    dirs = [(root_off, 0)]; dir_index = {(): 0}
    for f in files:
        parts = f['path'].split('\\')[:-1]
        for k in range(1, len(parts) + 1):
            key = tuple(parts[:k])
            if key not in dir_index:
                dir_index[key] = len(dirs)
                dirs.append((len(st), dir_index[key[:-1]]))
                st += parts[k - 1].encode() + b'\0'
    out = b'\x03VTM' + struct.pack('<III', 7, max(f['zsize'] for f in files), max(f['size'] for f in files))
    out += cint(len(st)) + bytes(st)
    out += cint(len(files) + 1) + b'\0' * 32
    for i, f in enumerate(files):
        out += struct.pack('<8I', path_off[i], 0, f['zsize'], f['size'], i + 1, 0, 0, f['comp'])
    out += cint(len(files) + 1) + b'\0' * 24
    for i, f in enumerate(files):
        out += struct.pack('<6I', f['offset'], 0, f['zsize'], 0, i + 1, 1)
    out += cint(2) + b'\0' * 24 + struct.pack('<QIIII', bundle_data_size, header_size, 1, 1, len(files))
    out += b'\x80'
    out += cint(len(dirs)) + b''.join(struct.pack('<II', a, b) for a, b in dirs)
    out += cint(len(files))
    for i, f in enumerate(files):
        parts = f['path'].split('\\')
        name_off = path_off[i] + len(f['path']) - len(parts[-1])
        out += struct.pack('<III', i + 1, dir_index[tuple(parts[:-1])], name_off)
    hashes = sorted((fnv1a64(f['path'].encode()), i + 1) for i, f in enumerate(files))
    out += cint(len(files))
    for h, idx in hashes:
        out += struct.pack('<QIi', h, idx, 0 if idx == 1 else -1)
    return out
