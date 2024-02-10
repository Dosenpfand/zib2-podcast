#!/bin/bash

(
    flock -w 1 200 || exit 1
    cd /code
    python app/main.py
) 200>/var/lock/.cron.sh
