#!/bin/bash

# Sample script to pause or resume all grab-site processes as your free disk
# space crosses a threshold value.  Modify the values below.

# Default: 80GB
LOW_DISK_KB=$((80 * 1024 * 1024))
PARTITION=/
CHECK_INTERVAL_SEC=60

while true; do
	left=$(df "$PARTITION" | grep / | sed -r 's/ +/ /g' | cut -f 4 -d ' ')
	if (( left >= $LOW_DISK_KB )); then
		echo "Disk OK, resuming all grab-sites"
		killall -CONT grab-site
	fi
	if (( left < $LOW_DISK_KB )); then
		echo "Disk low, pausing all grab-sites"
		killall -STOP grab-site
	fi
	sleep "$CHECK_INTERVAL_SEC"
done
