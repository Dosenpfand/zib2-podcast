#!/bin/bash

exec {lock_fd}>/var/lock/cron.sh || exit 1
flock -n "$lock_fd" || { echo "ERROR: flock() failed." >&2; exit 1; }
cd /code
python app/main.py
flock -u "$lock_fd"
