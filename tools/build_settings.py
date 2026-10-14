#!/usr/bin/env python3
"""Compile the menu labels (English plus labels.translations.json) into w3strings files.

Builds project artifacts only; never installs files or edits user configuration.
"""
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_ID = 2117500001  # Separate from Gwent Players Map (2117300001+) and Witcher Upgrade Gear Map (2117400001+).
VERSION = '0.9.1-beta'
LANGUAGES = ('ar', 'br', 'cn', 'cz', 'de', 'en', 'es', 'esmx', 'fr', 'hu', 'it', 'jp', 'kr', 'pl', 'ru', 'tr', 'ua', 'zh')


def cint(value):
    result = bytearray([(value & 0x3f) | (0x40 if value >> 6 else 0)])
    value >>= 6
    while value:
        result.append((value & 0x7f) | (0x80 if value >> 7 else 0))
        value >>= 7
    return bytes(result)


def key_hash(key):
    value = 0
    for byte in key.lower().encode('ascii'):
        value = (value * 31 + byte) & 0xffffffff
    return value


def build(labels):
    entries = list(labels.items())
    hashes = [key_hash(key) for key, _ in entries]
    if len(set(hashes)) != len(hashes):
        raise ValueError('menu key hash collision')
    blob, table = bytearray(), []
    for offset, (_, text) in enumerate(entries):
        data = text.encode('utf-8')  # lengths in bytes, as in our map mods
        table.append((BASE_ID + offset, len(blob), len(data)))
        blob.extend(data + b'\0')
    result = bytearray(b'RTSW') + struct.pack('<IH', 164, 0) + cint(len(table))
    for row in table:
        result.extend(struct.pack('<III', *row))
    result.extend(cint(len(entries)))
    for key, sid in sorted((key_hash(key), BASE_ID + i) for i, (key, _) in enumerate(entries)):
        result.extend(struct.pack('<II', key, sid))
    result.extend(cint(len(blob)) + blob + b'\0\0')
    return bytes(result)


def language_labels(language):
    """English labels with this language's translations; missing texts stay in English."""
    labels = json.loads((ROOT / 'mod/settings/menu/labels.en.json').read_text())
    translated = json.loads((ROOT / 'mod/settings/menu/labels.translations.json').read_text(encoding='utf-8'))
    unknown = set(translated.get(language, {})) - set(labels)
    if unknown:
        raise ValueError('%s: unknown label keys %s' % (language, sorted(unknown)))
    out = {key: translated.get(language, {}).get(key, text) for key, text in labels.items()}
    out['panel_gwentai'] = '%s %s' % (labels['panel_gwentai'], VERSION)  # version shown in the options
    return out


def main():
    out = ROOT / 'mod/settings/modGwentAISettings/content'
    out.mkdir(parents=True, exist_ok=True)
    for language in LANGUAGES:
        (out / (language + '.w3strings')).write_bytes(build(language_labels(language)))
    print('%d languages; project artifacts only' % len(LANGUAGES))


if __name__ == '__main__':
    main()
