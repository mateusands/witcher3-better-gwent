#!/bin/bash
# pulldb.sh SSH_USER OUT.sqlite3 : consistent Lab DB snapshot over the Runpod SSH proxy in hash-checked parts.
# Stops with an error (and writes nothing) when the server cannot prepare the snapshot.
U=$1; OUT=$2; W=$(mktemp -d); mkdir $W/parts
printf 'stty -echo\npython3 -c "import sqlite3;s=sqlite3.connect(\\"/srv/data/db/lab.sqlite3\\");d=sqlite3.connect(\\"/srv/data/pull.sqlite3\\");s.backup(d);d.close()"\ncd /srv/data && gzip -c pull.sqlite3 > pull.sqlite3.gz && rm -rf parts && mkdir parts && base64 -w 76 pull.sqlite3.gz | split -l 1500 -d -a 3 - parts/p && echo NPARTS $(ls parts | wc -l) DBSHA $(sha256sum pull.sqlite3 | cut -c1-64)\nexit\n' > $W/prep.txt
read -r _ N _ DBSHA < <(timeout 300 ssh -tt -o ConnectTimeout=20 $U@ssh.runpod.io < $W/prep.txt 2>/dev/null | tr -d '\r' | grep -a "^NPARTS")
[[ "$N" =~ ^[0-9]+$ && "$N" -gt 0 ]] || { echo "snapshot not prepared on $U (no NPARTS answer)"; exit 1; }
for ((i=0;i<N;i++)); do p=$(printf 'p%03d' $i); ok=0
  for t in 1 2 3 4 5; do
    printf 'stty -echo\necho PSHA $(sha256sum /srv/data/parts/%s | cut -c1-64)\necho PSTART; cat /srv/data/parts/%s; echo PEND\nexit\n' $p $p > $W/get.txt
    timeout 300 ssh -tt -o ConnectTimeout=20 $U@ssh.runpod.io < $W/get.txt 2>/dev/null | tr -d '\r' > $W/raw
    R=$(grep -a "^PSHA" $W/raw | cut -c6-); sed -n '/^PSTART/,/^PEND/p' $W/raw | grep -v "^PSTART\|^PEND" > $W/parts/$p
    [ "$R" = "$(sha256sum $W/parts/$p | cut -c1-64)" ] && { ok=1; break; }
  done; [ $ok = 1 ] || { echo "FAILED $p"; exit 1; }
done
cat $W/parts/p* | base64 -d | gunzip > "$OUT"
[ "$(sha256sum "$OUT" | cut -c1-64)" = "$DBSHA" ] && echo "OK $N parts $DBSHA" || { echo "DB HASH MISMATCH"; exit 1; }
