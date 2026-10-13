#!/bin/bash
# split_target.sh "BATTERY ARGS" 'RANGES-JSON' : stdin script for a TARGET pod (logic and spec in
# split.py). Pauses the Lab, queues the same battery, keeps only the given ranges of the new jobs
# and resumes.
cat <<EOS
stty -echo
cd /srv/lab
curl -s -X POST -H 'Content-Type: application/json' -d '{}' 127.0.0.1:8765/api/pause </dev/null >/dev/null
python3 $1 8765 </dev/null | grep -c ok | sed 's/^/QUEUED /'
python3 /srv/lab/lab/remote/split.py target '$2'
curl -s -X POST -H 'Content-Type: application/json' -d '{}' 127.0.0.1:8765/api/resume </dev/null >/dev/null
exit
EOS
