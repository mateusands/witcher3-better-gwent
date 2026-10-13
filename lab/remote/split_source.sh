#!/bin/bash
# split_source.sh K : stdin script for the SOURCE pod (logic and spec in split.py). It keeps the
# first of K chunks of every active job's pending tasks and prints RANGES for chunks 1..K-1.
cat <<EOS
stty -echo
python3 /srv/lab/lab/remote/split.py source $1
exit
EOS
