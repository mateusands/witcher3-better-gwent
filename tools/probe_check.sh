#!/bin/bash
# Lists every file changed after the probe was installed and shows the probe's output.
P=$(cd "$(dirname "$0")/.." && pwd)
D="$HOME/.local/share/Steam/steamapps/compatdata/292030/pfx/drive_c/users/steamuser/Documents/The Witcher 3"
G="$HOME/.local/share/Steam/steamapps/common/The Witcher 3"
PFX="$HOME/.local/share/Steam/steamapps/compatdata/292030/pfx"
echo "== files changed since install"
find "$D" "$G/bin" "$PFX/drive_c/users" -newer "$P/backups/.probe1_marker" -type f 2>/dev/null | grep -v gamesaves
echo "== GwaiProbe in settings"
grep -n "GwaiProbe" -A8 "$D"/*.settings 2>/dev/null | cut -c1-200
echo "== gwaiprobe files"
find "$G" "$PFX" -iname "*gwaiprobe*" 2>/dev/null
