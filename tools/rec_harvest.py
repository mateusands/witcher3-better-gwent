#!/usr/bin/env python3
# Automatic harvest of recorded matches (run by the gwai-harvest systemd user timer).
#
# While the game is closed: every match in [GwaiRec] of dx12user.settings is saved to
# game/records/ (parsed JSON + the raw chunks), then removed from the settings file, keeping
# only the "games" counter so the numbering continues. Nothing is done while witcher3.exe runs:
# the game keeps the settings in memory and would write the removed keys back.
#
# Saved per match:
#   game/records/gNNN.json         parsed match (closed normally: final, or quit = surrender)
#   game/records/raw/gNNN.txt      raw [GwaiRec] lines of the match
#   game/records/broken/gNNN-*.txt raw lines of a match that cannot be parsed (crash, etc.)
# Every run that changes the settings first copies them to backups/settings/ (last 20 kept).
import glob, json, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rec_read  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, '..'))
DOCS = os.environ.get('GWAI_DOCS') or os.path.expanduser(
    '~/.local/share/Steam/steamapps/compatdata/292030/pfx/drive_c/users/steamuser/Documents/The Witcher 3')
FILES = [os.path.join(DOCS, 'dx12user.settings'), os.path.join(DOCS, 'dx12user.settings.bak')]
# GWAI_OUT / GWAI_BACKUPS are only for testing on copies.
OUT = os.environ.get('GWAI_OUT') or os.path.join(ROOT, 'game', 'records')
BACKUPS = os.environ.get('GWAI_BACKUPS') or os.path.join(ROOT, 'backups', 'settings')
LOG = os.path.join(OUT, 'harvest.log')
SECTION = 'GwaiRec'


def log(msg):
    os.makedirs(OUT, exist_ok=True)
    with open(LOG, 'a') as f:
        f.write('%s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg))
    print(msg)


def game_running():
    return subprocess.run(['pgrep', '-x', 'witcher3.exe'], capture_output=True).returncode == 0


def split_section(text):
    """Returns (lines outside [GwaiRec], {key: raw line} inside it). Line ends are CRLF."""
    outside, inside, cur = [], {}, None
    for line in text.split('\r\n'):
        if line.startswith('['):
            cur = line.strip()
        if cur == '[%s]' % SECTION:
            if '=' in line:
                inside[line.split('=', 1)[0]] = line
        else:
            outside.append(line)
    return outside, inside


def rebuild(outside, games_line):
    # The section goes back at the end of the file with only the counter.
    lines = list(outside)
    while lines and lines[-1] == '':
        lines.pop()
    lines += ['', '[%s]' % SECTION, games_line, '']
    return '\r\n'.join(lines)


def harvest():
    if game_running():
        return 0
    path = FILES[0]
    if not os.path.exists(path):
        return 0
    text = open(path, 'rb').read().decode('utf-8')
    outside, inside = split_section(text)
    match_ids = sorted({int(m.group(1)) for k in inside for m in [re.match(r'g(\d{3})_', k)] if m})
    if not match_ids:
        return 0

    raw = rec_read.read_section(path, SECTION)
    for d in ('raw', 'broken'):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S')
    saved = broken = 0
    for g in match_ids:
        prefix = 'g%03d_' % g
        lines = '\r\n'.join(inside[k] for k in sorted(inside) if k.startswith(prefix)) + '\r\n'
        info, records, problems = rec_read.load_match(raw, g)
        # A surrender ("quit") is a normal way for a played match to end.
        problems = [p for p in problems if not p.startswith('reason=quit')]
        data = None
        if not problems:
            try:
                data = rec_read.structure(info, records)
            except rec_read.RecError as e:
                problems.append(str(e))
        if data is None:
            open(os.path.join(OUT, 'broken', 'g%03d-%s.txt' % (g, stamp)), 'w').write(lines)
            log('g%03d BROKEN (raw kept in records/broken): %s' % (g, '; '.join(problems)[:300]))
            broken += 1
            continue
        target = os.path.join(OUT, 'g%03d.json' % g)
        if os.path.exists(target):
            target = os.path.join(OUT, 'g%03d.dup-%s.json' % (g, stamp))
        json.dump(data, open(target, 'w'), indent=1)
        open(os.path.join(OUT, 'raw', os.path.basename(target)[:-5] + '.txt'), 'w').write(lines)
        log('g%03d saved %s (%s, %d chunks)' % (g, os.path.basename(target), info.get('reason'), info['chunksFound']))
        saved += 1

    if game_running():
        log('game started during the harvest: settings left untouched')
        return 0
    os.makedirs(BACKUPS, exist_ok=True)
    shutil.copy2(path, os.path.join(BACKUPS, 'dx12user.settings.%s' % stamp))
    for old in sorted(glob.glob(os.path.join(BACKUPS, 'dx12user.settings.*')))[:-20]:
        os.remove(old)
    games_line = inside.get('games', 'games="%d"' % (max(match_ids) + 1))
    new_text = rebuild(outside, games_line)
    # Safety check: everything outside the section is unchanged (apart from trailing blank lines).
    def strip_tail(lines):
        lines = list(lines)
        while lines and lines[-1] == '':
            lines.pop()
        return lines
    if strip_tail(split_section(new_text)[0]) != strip_tail(outside):
        log('safety check failed: settings left untouched')
        return 1
    for f in FILES:
        if os.path.exists(f):
            other_outside, _ = split_section(open(f, 'rb').read().decode('utf-8'))
            if f != path and strip_tail(other_outside) != strip_tail(outside):
                # The .bak differs from the main file outside our section: keep it as it is.
                log('%s differs from the main settings file, not cleaned' % os.path.basename(f))
                continue
            tmp = f + '.gwai-tmp'
            open(tmp, 'wb').write(new_text.encode('utf-8'))
            os.replace(tmp, f)
    log('harvest done: %d saved, %d broken, settings %d -> %d bytes' % (
        saved, broken, len(text.encode('utf-8')), len(new_text.encode('utf-8'))))
    return 0


if __name__ == '__main__':
    sys.exit(harvest())
