#!/bin/bash

# Sample script to pause or resume all grab-site processes as your free disk
# space crosses a threshold value.  Modify the values below.

# Default: 80GB
LOW_DISK_KB=$((80 * 1024 * 1024))
PARTITION=/
CHECK_INTERVAL_SEC=60

# Track whether *we* paused the grab-sites to avoid (typically) resuming
# grab-sites that were paused by the user with e.g. ctrl-z
paused=0

while true; do
	left=$(df "$PARTITION" | grep / | sed -r 's/ +/ /g' | cut -f 4 -d ' ')
	if [[ $paused = 1 ]] && (( left >= $LOW_DISK_KB )); then
		echo "Disk OK, resuming all grab-sites"
		paused=0
		killall -CONT grab-site
	fi
	if (( left < $LOW_DISK_KB )); then
		echo "Disk low, pausing all grab-sites"
		paused=1
		killall -STOP grab-site
	fi
	echo -n ". "
	sleep "$CHECK_INTERVAL_SEC"
done
