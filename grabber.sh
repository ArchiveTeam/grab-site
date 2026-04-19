#!/usr/bin/env bash
#
# grabber.sh: this script helps to reliably get an offline website copy
#  using the grab-site utility by ArchiveTeam with an unofficial patch
#  for "--resume" feature ( see https://github.com/mikebdp2/grab-site ).
# OpenVPN can be used to securely obtain a website copy in a private way,
#  and - if there is any prolonged connection problem (often causes the
#  grab-site processes to stall even if a reconnect is successful) then
#  it kills the openvpn/grab-site/gs-server processes and restarts them.
#
# CURRENT KNOWN LIMITATIONS: 1) in case of any connection problems etc.,
#  it kills ALL the grab-site processes as well as gs-server and openvpn;
# 2) connection test uses wget, relying on 3rd-party page uptime/content,
#  you may pick a page that could not be accesses by you without openvpn;
# 3) there is only one state file to remember the dynamic directory name,
# so only one instance of a "fresh start" (non-resume) crawl is supported.
#
# TO OVERCOME THEM (i.e. you need more than one crawling processes running
# simultaneously): you need to either slightly modify the source code (just
# like you would have to do if you don't need OpenVPN), inserting the extra
# GRAB_SITE_STATE_FILE_ vars and launch_grab_site_with_auto_discovery calls,
# or to create a standalone virtual machine to isolate this script instance.
#
# CONFIGURING: look through this script, change the variables, enable the
# sound alarm in case of a critical problem by a "touch ./sound" command.
#
# NOTE: if you terminate this script, kill the leftover processes manually!
#
#      Please send your feedback to Mike Banon <mikebdp2@gmail.com>.
#    Released under the terms of GNU GPL v3 by Free Software Foundation.
#

#
# Main configs
#
USERNAME="username"
ROOTNAME="root"
TEST_URL="https://blockedwithoutvpn.org/coolpage.html"
TEST_FILE="coolpage.html"
TEST_EXPECTED_SIZE_AT_LEAST="68900"
ALARM_SOUND="./UFO-landing.wav"
ALARM_REPEATS="10"
RESET_FILE="./reset"

#
# Grab configs
#
# 4 GB minus 16 MB: fits on a DVD and is FAT32-compatible
WARC_MAX_SIZE="4278190080"
GRAB_SITE_DELAY="500-600"
GRAB_SITE_URL="https://topsecretwebsite.net/"
GRAB_SITE_URL_BODY="topsecretwebsite"
GRAB_SITE_CONCURRENCY="1"
GRAB_SITE_NO_DUPESPOTTER="--no-dupespotter"
GRAB_SITE_NO_OFFSITE_LINKS="--no-offsite-links"
GRAB_SITE_NO_OFFSITE_LINKS_IGNORES_FILE="./ignores"
GRAB_SITE_WPULL_ARGS="--read-timeout=5 --connect-timeout=5 --dns-timeout=5 --tries=5 --waitretry=5 --timeout=5 --retry-connrefused --retry-dns-error --session-timeout=21600"
# State file to remember the dynamic directory name
GRAB_SITE_STATE_FILE="./grab-site-dir.txt"

#
# OpenVPN configs
#
OPENVPN_ENABLED=1
OPENVPN_USES_ST=5
OPENVPN_USES_ND=10
OPENVPN_USES_RD=15
OPENVPN_CONF_ST="./openvpn-conf-1st.ovpn"
OPENVPN_CONF_ND="./openvpn-conf-2nd.ovpn"
OPENVPN_CONF_RD="./openvpn-conf-3rd.ovpn"
OPENVPN_AUTH_ST="./openvpn-auth-1st.txt"
OPENVPN_AUTH_ND="./openvpn-auth-2nd.txt"
OPENVPN_AUTH_RD="./openvpn-auth-3rd.txt"
OPENVPN_TRIES="$OPENVPN_USES_RD"

#
# Sleep intervals
#
TEST_INTERVAL=15
PROC_INTERVAL=10
STOP_INTERVAL=5
OVPN_INTERVAL=30

#
# Executables
#
GRAB_SITE_EXEC="/home/$USERNAME/.local/bin/grab-site"
GS_SERVER_EXEC="/home/$USERNAME/.local/bin/gs-server"
# custom_wget is just a copy of your /usr/bin/wget
CUSTOM_WGET_PROC="custom_wget"
CUSTOM_WGET_EXEC="./$CUSTOM_WGET_PROC"
OPENVPN_EXEC="/usr/bin/openvpn"

#
# Logs
#
GRABBER_LOG_DIR="./logs"
GRABBER_LOG_DIR_OLD="./OLD-logs"
WGET_LOG="$GRABBER_LOG_DIR/wget.log"
OPENVPN_LOG="$GRABBER_LOG_DIR/openvpn.log"
GS_SERVER_LOG="$GRABBER_LOG_DIR/gs-server.log"

#
# States
#
CONCT_RO="REST"
CONCT_ST="NORM"
CONCT_ND="WARN"
CONCT_RD="CRIT"
CONCT_FA="FAIL"
STATE_RO="STATE 0ro ($CONCT_RO)"
STATE_ST="STATE 1st ($CONCT_ST)"
STATE_ND="STATE 2nd ($CONCT_ND)"
STATE_RD="STATE 3rd ($CONCT_RD)"

#
# Kills the '$1' processes owned by a '$2' user.
#
kill_processes() {
    local PROC_NAME="$1"
    local PROC_USER="$2"
    echo "Killing the $PROC_NAME processes owned by $PROC_USER..." >&2
    # Loop continues as long as pgrep finds at least one process
    while pgrep -u "$PROC_USER" -n -x "$PROC_NAME" > /dev/null ; do
        # Get all PIDs currently running
        local PROCESS_PIDS=$(pgrep -u "$PROC_USER" -n -x "$PROC_NAME")
        if [ -z "$PROCESS_PIDS" ] ; then
            break
        fi
        echo "Found $PROC_NAME processes: $PROCESS_PIDS, killing..." >&2
        # Kill them forcefully
        local TEMP_PROCESS_PID=""
        for TEMP_PROCESS_PID in $PROCESS_PIDS ; do
            # Check if still alive before killing
            if kill -0 "$TEMP_PROCESS_PID" 2>/dev/null ; then
                kill -SIGSTOP "$TEMP_PROCESS_PID" 2>/dev/null
                sleep "$STOP_INTERVAL"
                kill -SIGKILL "$TEMP_PROCESS_PID" 2>/dev/null
            fi
        done
        # Wait briefly to let the kernel update the process table
        sleep 1
    done
    echo "All the $PROC_NAME processes owned by $PROC_USER have been killed" >&2
    return 0
}

#
# Checks if OpenVPN process is running, returns 0 if YES and 1 if NOT.
#
check_openvpn_proc() {
    local CHECK_OPENVPN_PROC_PID=$(pgrep -u "$ROOTNAME" -n -x "openvpn")
    if [ -z "$CHECK_OPENVPN_PROC_PID" ] ; then
        return 1
    fi
    return 0
}

#
# Tests the connection quality by trying to download a known page with a known size
# (i.e. a page that cannot be downloaded for some reason without using the OpenVPN).
# Returns:
# 0 - Size is at least the expected size (i.e. the online page got larger)
# 1 - Size is smaller than the expected size, but a file is not empty (> 0 bytes)
# 2 - Size mismatch and a file is empty (0 bytes)
# 3 - If OpenVPN is enabled but its process has disappeared
# Currently, the cases 1 and 2 are treated as erroneous.
#
test_connection_quality() {
    # 1. Remove the existing files
    rm -f "$TEST_FILE"
    rm -f "./wget-log"
    rm -f "$WGET_LOG"
    # If OpenVPN is enabled - check that it is still running
    if [ "$OPENVPN_ENABLED" -eq 1 ] && ! check_openvpn_proc ; then
        return 3
    fi
    # 2. Launch custom_wget in the background
    # setsid creates a new session, detaching from the terminal completely
    sudo -u "$USERNAME" setsid "$CUSTOM_WGET_EXEC" --no-check-certificate -O "$TEST_FILE" "$TEST_URL" </dev/null >"$WGET_LOG" 2>&1 &
    sleep 1
    # If OpenVPN is enabled - check that it is still running
    if [ "$OPENVPN_ENABLED" -eq 1 ] && ! check_openvpn_proc ; then
        return 3
    fi
    # 3. Wait loop: checks every second if a process is still alive, up to $TEST_INTERVAL seconds
    local TEST_CONNECTION_COUNTER=1
    local WGET_PID=""
    while [ $TEST_CONNECTION_COUNTER -le $TEST_INTERVAL ] ; do
        # Check if wget is running (get the newest instance matching the name)
        # Since setsid detaches, the parent might exit immediately
        WGET_PID=$(pgrep -u "$USERNAME" -n -x "$CUSTOM_WGET_PROC")
        # If PID is empty - the process finished naturally or crashed immediately
        if [ -z "$WGET_PID" ] ; then
            break
        fi
        # Otherwise, sleep 1 second and increment counter
        sleep 1
        TEST_CONNECTION_COUNTER=$((TEST_CONNECTION_COUNTER + 1))
        # If OpenVPN is enabled - check that it is still running
        if [ "$OPENVPN_ENABLED" -eq 1 ] && ! check_openvpn_proc ; then
            return 3
        fi
    done
    # 4. Kill the process ONLY if we have a valid PID and it is still running
    # This handles the case where WGET_PID is empty (early exit) gracefully
    if [ -n "$WGET_PID" ] && kill -0 "$WGET_PID" 2>/dev/null ; then
        echo "Timeout reached, killing custom_wget (PID: $WGET_PID)..." >&2
        kill -SIGKILL "$WGET_PID" 2>/dev/null
        sleep 1
        # If OpenVPN is enabled - check that it is still running
        if [ "$OPENVPN_ENABLED" -eq 1 ] && ! check_openvpn_proc ; then
            return 3
        fi
    fi
    # 5. Check file size
    local TEST_CURRENT_SIZE=0
    if [ -f "$TEST_FILE" ] ; then
        # Capture output of stat. If stat fails for any reason, this might be empty, so we default to 0 again.
        local SIZE_OUTPUT=$(stat -c%s "$TEST_FILE" 2>/dev/null)
        if [ -n "$SIZE_OUTPUT" ] ; then
            TEST_CURRENT_SIZE="$SIZE_OUTPUT"
        fi
    fi
    echo "Downloaded size: $TEST_CURRENT_SIZE bytes (expected: at least $TEST_EXPECTED_SIZE_AT_LEAST)" >&2
    if [ "$TEST_CURRENT_SIZE" -ge "$TEST_EXPECTED_SIZE_AT_LEAST" ] ; then
        return 0
    elif [ "$TEST_CURRENT_SIZE" -gt 0 ] ; then
        return 1
    else
        return 2
    fi
}

#
# Tries connecting OpenVPN with the '$1' config file and '$2' auth file.
#
launch_openvpn() {
    rm -f "$OPENVPN_LOG"
    # setsid creates a new session, detaching from the terminal completely
    sudo -u "$ROOTNAME" setsid "$OPENVPN_EXEC" --config "$1" --auth-user-pass "$2" </dev/null >"$OPENVPN_LOG" 2>&1 &
    sleep "$OVPN_INTERVAL"
    # Since setsid detaches, the parent might exit immediately
    local OPENVPN_PID=$(pgrep -u "$ROOTNAME" -n -x "openvpn")
    if [ -z "$OPENVPN_PID" ] ; then
        echo "ERROR: openvpn has failed to start!" >&2
        return 1
    fi
    echo "$OPENVPN_PID"
    return 0
}

#
# OpenVPN launcher goes through the config+auth pairs until something works.
#
openvpn_launcher() {
    kill_processes "openvpn" "$ROOTNAME"
    local OPENVPN_ATTEMPT=1
    local OPENVPN_RESULT=0
    echo "Starting OpenVPN launcher (max tries: $OPENVPN_TRIES)..." >&2
    while true ; do
        # Reset counter if max tries exceeded (under a current design we never exit)
        if [ $OPENVPN_ATTEMPT -gt $OPENVPN_TRIES ] ; then
            if [ -f "./sound" ] && [ -f "$ALARM_SOUND" ] ; then
                local ALARM_REPEATS_COUNTER=1
                while [ $ALARM_REPEATS_COUNTER -le $ALARM_REPEATS ] ; do
                    paplay "$ALARM_SOUND"
                    ALARM_REPEATS_COUNTER=$((ALARM_REPEATS_COUNTER + 1))
                done
            fi
            OPENVPN_ATTEMPT=1
        fi
        echo "--- Attempt $OPENVPN_ATTEMPT of $OPENVPN_TRIES ---" >&2
        # 1. Determine which config to use based on attempt and file existence
        local OPENVPN_CONF=""
        local OPENVPN_AUTH=""
        if [ $OPENVPN_ATTEMPT -le $OPENVPN_USES_ST ] ; then
            # Attempts 1-5: use the 1st config+auth
            OPENVPN_CONF="$OPENVPN_CONF_ST"
            OPENVPN_AUTH="$OPENVPN_AUTH_ST"            
        elif [ $OPENVPN_ATTEMPT -le $OPENVPN_USES_ND ] ; then
            # Attempts 6-10: try the 2nd config+config, fallback to 1st if missing
            if [ -f "$OPENVPN_CONF_ND" ] && [ -f "$OPENVPN_AUTH_ND" ] ; then
                OPENVPN_CONF="$OPENVPN_CONF_ND"
                OPENVPN_AUTH="$OPENVPN_AUTH_ND"
            else
                echo "WARNING: 2nd config files missing. Falling back to 1st config" >&2
                OPENVPN_CONF="$OPENVPN_CONF_ST"
                OPENVPN_AUTH="$OPENVPN_AUTH_ST"
            fi
        else
            # Attempts 11-15: try the 3rd config+auth, fallback to 2nd, then 1st
            if [ -f "$OPENVPN_CONF_RD" ] && [ -f "$OPENVPN_AUTH_RD" ] ; then
                OPENVPN_CONF="$OPENVPN_CONF_RD"
                OPENVPN_AUTH="$OPENVPN_AUTH_RD"
            elif [ -f "$OPENVPN_CONF_ND" ] && [ -f "$OPENVPN_AUTH_ND" ] ; then
                echo "WARNING: 3rd config files missing. Falling back to 2nd config" >&2
                OPENVPN_CONF="$OPENVPN_CONF_ND"
                OPENVPN_AUTH="$OPENVPN_AUTH_ND"
            else
                echo "WARNING: 3rd and 2nd config files missing. Falling back to 1st config" >&2
                OPENVPN_CONF="$OPENVPN_CONF_ST"
                OPENVPN_AUTH="$OPENVPN_AUTH_ST"
            fi
        fi
        echo "OPENVPN: using files: $OPENVPN_CONF + $OPENVPN_AUTH" >&2
        # Launch OpenVPN
        OPENVPN_PID=$(launch_openvpn "$OPENVPN_CONF" "$OPENVPN_AUTH")
        LAUNCH_STATUS=$?
        # If a launch failed, retry
        if [ $LAUNCH_STATUS -ne 0 ] ; then
            echo "OPENVPN: launch failed on attempt $OPENVPN_ATTEMPT" >&2
            OPENVPN_ATTEMPT=$((OPENVPN_ATTEMPT + 1))
            continue
        fi
        echo "OpenVPN started with PID: $OPENVPN_PID" >&2
        # 2. Test the connection quality
        test_connection_quality
        OPENVPN_RESULT=$?
        # 3. Check our result
        if [ $OPENVPN_RESULT -eq 0 ] ; then
            echo "SUCCESS: openvpn connection test" >&2
            echo "$OPENVPN_PID"
            return 0
        else
            echo "WARNING: openvpn attempt $OPENVPN_ATTEMPT - bad result $OPENVPN_RESULT of a connection test" >&2
            # Kill the openvpn process before retrying
            if [ -n "$OPENVPN_PID" ] && kill -0 "$OPENVPN_PID" 2>/dev/null ; then
                echo "Killing previous OpenVPN instance (PID: $OPENVPN_PID)..." >&2
                kill -SIGKILL "$OPENVPN_PID" 2>/dev/null
                sleep 1
            fi
            OPENVPN_ATTEMPT=$((OPENVPN_ATTEMPT + 1))
        fi
    done
    # Unreachable due to infinite loop, but kept for logic completeness
    echo "ERROR: exceeded maximum OpenVPN attempts ($OPENVPN_TRIES)" >&2
    return 1
}

#
# Does a clean start of gs-server.
#
launch_gs_server() {
    kill_processes "gs-server" "$USERNAME"
    rm -f "$GS_SERVER_LOG"
    # setsid creates a new session, detaching from the terminal completely
    sudo -u "$USERNAME" setsid "$GS_SERVER_EXEC" </dev/null >"$GS_SERVER_LOG" 2>&1 &
    sleep "$PROC_INTERVAL"
    # Since setsid detaches, the parent might exit immediately
    local GSSERVER_PID=$(pgrep -u "$USERNAME" -n -x "gs-server")
    if [ -z "$GSSERVER_PID" ] ; then
        echo "ERROR: gs-server has failed to start!" >&2
        return 1
    fi
    echo "$GSSERVER_PID"
    return 0
}

#
# Waits for the directory to appear, finds the newest plausibly-looking one and saves it.
#
discover_newest_directory() {
    echo "INFO: Background task started. Waiting for new directory creation..." >&2
    sleep "$PROC_INTERVAL"
    # Find the newest directory in the current folder (excluding the hidden ones)
    # This identifies the newly created crawl directory according to its name pattern
    local NEWEST_DIR=$(find . -maxdepth 1 -mindepth 1 -type d -name "*$GRAB_SITE_URL_BODY*" -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -n 1 | cut -d' ' -f2-)
    if [ -n "$NEWEST_DIR" ] ; then
        echo "$NEWEST_DIR"
        echo "INFO: auto-discovered directory: $NEWEST_DIR" >&2
    else
        echo "ERROR: could not auto-discover directory!" >&2
        return 1
    fi
    return 0
}

#
# Removes the leftover temporary files from a resume directory '$1'.
#
grab_site_resume_dir_cleanup() {
    local GRAB_SITE_DIR_FOR_CLEANUP="$1"
    echo "Removing the temporary files from a resume directory $GRAB_SITE_DIR_FOR_CLEANUP ..." >&2
    rm -f "$GRAB_SITE_DIR_FOR_CLEANUP"/*warc.gz-wpullinc
    rm -f "$GRAB_SITE_DIR_FOR_CLEANUP"/temp/*
}

#
# Wise grab-site launcher with "--resume" and "--import-ignores" support:
# 1) if RESUME_DIR is passed - use it; else - check state file; else - discover
# 2) "--no-offsite-links" is buggy, so we compliment it by "--import-ignores"
# Arguments:
# '$1' - username
# '$2' - website url
# '$3' - url body keyword (for ignore rule)
# '$4' - log file
# '$5' - extra "--no-offsite-links" argument (may be set to "")
# '$6' - extra "--no-dupespotter"   argument (may be set to "")
# '$7' - extra ordinary argument (usually set to "")
# '$8' - extra resume dir argument (optional; if empty, the auto-discovery may trigger)
#
launch_grab_site_with_auto_discovery() {
    local GRAB_SITE_USER="$1"
    local GRAB_SITE_URL_ARG="$2"
    local GRAB_SITE_URL_BODY_ARG="$3"
    local GRAB_SITE_LOG_FILE="$4"
    local GRAB_SITE_NO_OFFSITE_LINKS_ARG="$5"
    local GRAB_SITE_NO_DUPESPOTTER_ARG="$6"
    local GRAB_SITE_EXTRA_ARG_INPUT="$7"
    local GRAB_SITE_RESUME_DIR_INPUT="$8"
    local GRAB_SITE_RESUME_DIR=""
    local GRAB_SITE_NEED_DISCOVERY=0
    local GRAB_SITE_NO_OFFSITE_LINKS_IGNORES_FILE_ARGS=()
    local GRAB_SITE_AUTO_DISCOVERED_DIR=""
    # LOGIC: determine the resume directory
    if [ -n "$GRAB_SITE_RESUME_DIR_INPUT" ] ; then
        # Case A: directory explicitly passed as argument
        GRAB_SITE_RESUME_DIR="$GRAB_SITE_RESUME_DIR_INPUT"
        echo "INFO: using explicitly provided resume directory: $GRAB_SITE_RESUME_DIR" >&2
        grab_site_resume_dir_cleanup "$GRAB_SITE_RESUME_DIR"
    elif [ -f "$GRAB_SITE_STATE_FILE" ] ; then
        # Case B: no argument passed, but we have a saved state
        GRAB_SITE_RESUME_DIR=$(cat "$GRAB_SITE_STATE_FILE")
        echo "INFO: resuming using saved directory from state file: $GRAB_SITE_RESUME_DIR" >&2
        grab_site_resume_dir_cleanup "$GRAB_SITE_RESUME_DIR"
    else
        # Case C: no argument, no state file, that means a first run
        echo "INFO: no resume directory provided or found. Starting fresh to discover directory..." >&2
        GRAB_SITE_NEED_DISCOVERY=1
        if [ -n "$GRAB_SITE_NO_OFFSITE_LINKS_ARG" ] ; then
            # Create the ignores file in the current directory for import
            rm -f "./ignores"
            # Construct the ignore regex dynamically
            local GRAB_SITE_URL_ONLY='^(?!.*'"${GRAB_SITE_URL_BODY_ARG}"').*$'
            echo "$GRAB_SITE_URL_ONLY" > "$GRAB_SITE_NO_OFFSITE_LINKS_IGNORES_FILE"
            # Set the import argument for NEW crawls only
            GRAB_SITE_NO_OFFSITE_LINKS_IGNORES_FILE_ARGS=(--import-ignores "$GRAB_SITE_NO_OFFSITE_LINKS_IGNORES_FILE")
            echo "INFO: created ./ignores and will pass --import-ignores to grab-site" >&2
        fi
    fi
    # 1. Prepare Resume Options
    local GRAB_SITE_RESUME_ARGS=()
    if [ -n "$GRAB_SITE_RESUME_DIR" ] ; then
        if [ -d "$GRAB_SITE_RESUME_DIR" ] ; then
            GRAB_SITE_RESUME_ARGS=(--resume --dir "$GRAB_SITE_RESUME_DIR")
        else
            echo "ERROR: cannot find $GRAB_SITE_RESUME_DIR (GRAB_SITE_RESUME_DIR)" >&2
            return 1
        fi
    fi
    # 2. Prepare Extra Argument
    local GRAB_SITE_EXTRA_ARG=""
    if [ -n "$GRAB_SITE_EXTRA_ARG_INPUT" ] && [ "$GRAB_SITE_EXTRA_ARG_INPUT" != " " ] ; then
        GRAB_SITE_EXTRA_ARG="$GRAB_SITE_EXTRA_ARG_INPUT"
    fi
    # 3. Print the command
    echo "Will execute the command:" >&2
    echo "$GRAB_SITE_EXEC ${GRAB_SITE_RESUME_ARGS[@]} --concurrency=$GRAB_SITE_CONCURRENCY --delay=$GRAB_SITE_DELAY --warc-max-size=$WARC_MAX_SIZE ${GRAB_SITE_NO_OFFSITE_LINKS_ARG:+$GRAB_SITE_NO_OFFSITE_LINKS_ARG} ${GRAB_SITE_NO_OFFSITE_LINKS_IGNORES_FILE_ARGS[@]} ${GRAB_SITE_NO_DUPESPOTTER_ARG:+$GRAB_SITE_NO_DUPESPOTTER_ARG} ${GRAB_SITE_EXTRA_ARG:+$GRAB_SITE_EXTRA_ARG} --wpull-args=\"$GRAB_SITE_WPULL_ARGS\" $GRAB_SITE_URL_ARG" >&2
    # 4. Execute the command
    # setsid creates a new session, detaching from the terminal completely
    sudo -u "$GRAB_SITE_USER" setsid "$GRAB_SITE_EXEC" \
        "${GRAB_SITE_RESUME_ARGS[@]}" \
        --concurrency="$GRAB_SITE_CONCURRENCY" \
        --delay="$GRAB_SITE_DELAY" \
        --warc-max-size="$WARC_MAX_SIZE" \
        ${GRAB_SITE_NO_OFFSITE_LINKS_ARG:+"$GRAB_SITE_NO_OFFSITE_LINKS_ARG"} \
        "${GRAB_SITE_NO_OFFSITE_LINKS_IGNORES_FILE_ARGS[@]}" \
        ${GRAB_SITE_NO_DUPESPOTTER_ARG:+"$GRAB_SITE_NO_DUPESPOTTER_ARG"} \
        ${GRAB_SITE_EXTRA_ARG:+"$GRAB_SITE_EXTRA_ARG"} \
        --wpull-args="$GRAB_SITE_WPULL_ARGS" \
        "$GRAB_SITE_URL_ARG" </dev/null >"$GRAB_SITE_LOG_FILE" 2>&1 &
    # 5. Trigger Discovery ONLY if we didn't have a directory (Case C)
    if [ $GRAB_SITE_NEED_DISCOVERY -eq 1 ] ; then
        GRAB_SITE_AUTO_DISCOVERED_DIR=$(discover_newest_directory)
        if [ $? -eq 1 ] ; then
            echo "ERROR: discover_newest_directory failure!" >&2
            return 1
        else
            echo "$GRAB_SITE_AUTO_DISCOVERED_DIR"
        fi
    fi
    return 0
}

#
# Main launcher function, may launch multiple grab-site instances if you carefully improve this function.
#
grab_site_launcher() {
    local GRAB_SITE_AUTO_DISCOVERED_DIR=""
    kill_processes "grab-site" "$USERNAME"
    # Instance 1: Start NEW (empty dir arg). LOGIC:
    # 1st Run: $8 is empty, no state file -> Launches fresh with --import-ignores, triggers discovery, saves dir to state file.
    # Later Runs: $8 is empty, BUT state file exists -> Reads dir from state file, resumes naturally (ignores loaded from dir).
    GRAB_SITE_AUTO_DISCOVERED_DIR=$(launch_grab_site_with_auto_discovery "$USERNAME" "$GRAB_SITE_URL" "$GRAB_SITE_URL_BODY" "$GRABBER_LOG_DIR/grab-site.log" "$GRAB_SITE_NO_OFFSITE_LINKS" "$GRAB_SITE_NO_DUPESPOTTER" "" "")
    if [ $? -eq 1 ] ; then
        echo "ERROR: launch_grab_site_with_auto_discovery failure!" >&2
        return 1
    else
        if [ -n "$GRAB_SITE_AUTO_DISCOVERED_DIR" ] ; then
            rm -f "$GRAB_SITE_STATE_FILE"
            echo "$GRAB_SITE_AUTO_DISCOVERED_DIR" > "$GRAB_SITE_STATE_FILE"
            chown "$USERNAME" "$GRAB_SITE_STATE_FILE"
        fi
    fi
    sleep "$PROC_INTERVAL"
    # Since setsid detaches, the parent might exit immediately
    local GRAB_SITE_PIDS=$(pgrep -u "$USERNAME" -n -x "grab-site")
    if [ -z "$GRAB_SITE_PIDS" ] ; then
        echo "ERROR: grab-site has failed to start!" >&2
        return 1
    fi
    echo "$GRAB_SITE_PIDS"
    ### Instance 2: Resume with a known directory (hardcoded path)
    ### GRAB_SITE_AUTO_DISCOVERED_DIR=$(launch_grab_site_with_auto_discovery "$USERNAME" "$GRAB_SITE_URL" "$GRAB_SITE_URL_BODY" "$GRABBER_LOG_DIR/grab-site.log" "$GRAB_SITE_NO_OFFSITE_LINKS" "$GRAB_SITE_NO_DUPESPOTTER" "" "/home/$USERNAME/topsecretwebsite.net-2026-04-18-abcdef12")
    ### Use the code above, but modify it to make sure that we do not break the things (should be different log paths, careful PID check, etc).
    return 0
}

#
# Starts a "new life" after a "great reset".
#
firestarter() {
    echo "FIRESTARTER: STARTED"
    if [ "$OPENVPN_ENABLED" -eq 1 ] ; then
        echo "FIRESTARTER: launching OpenVPN..."
        OPENVPN_PID=$(openvpn_launcher)
        if [ $? -eq 1 ] ; then
            exit 1
        fi
        echo "FIRESTARTER: OPENVPN_PID=$OPENVPN_PID"
    fi
    echo "FIRESTARTER: launching gs-server..."
    GS_SERVER_PID=$(launch_gs_server)
    if [ $? -eq 1 ] ; then
        exit 1
    fi
    echo "FIRESTARTER: GS_SERVER_PID=$GS_SERVER_PID"
    echo "FIRESTARTER: launching grab-site instances..."
    GRAB_SITE_PIDS=$(grab_site_launcher)
    if [ $? -eq 1 ] ; then
        exit 1
    fi
    echo "FIRESTARTER: GRAB_SITE_PIDS=$GRAB_SITE_PIDS"
    echo "FIRESTARTER: COMPLETED"
}

#
# Kills the processes for the purpose of a later restart (triggered if any connection problems).
#
great_reset() {
    echo "GREAT_RESET: STARTED"
    echo "GREAT_RESET: killing the grab-site processes (if any)..."
    kill_processes "grab-site" "$USERNAME"
    echo "GREAT_RESET: killing the gs-server processes (if any)..."
    kill_processes "gs-server" "$USERNAME"
    if [ "$OPENVPN_ENABLED" -eq 1 ] ; then
        echo "GREAT_RESET: killing the   openvpn processes (if any)..."
        kill_processes "openvpn"   "$ROOTNAME"
    fi
    echo "GREAT_RESET: COMPLETED"
}

#
# To avoid killing the unrelated wget instances, we will copy this executable to a custom name.
#
get_wget() {
    # 1. Find the absolute path of 'wget' in the system PATH
    WGET_PATH=$(command -v wget)
    # 2. Check if wget was found
    if [ -z "$WGET_PATH" ] ; then
        echo "ERROR: wget not found in PATH !"
        exit 1
    fi
    echo "Found wget at: $WGET_PATH"
    # 3. Check if "custom_wget" already exists to prevent accidental overwrite (optional)
    if [ -f "$CUSTOM_WGET_EXEC" ] ; then
        echo "WARNING: $CUSTOM_WGET_EXEC already exists. Overwriting..."
    fi
    # 4. Copy the binary to a custom path
    # Using 'cp' preserves the binary content exactly.
    # We do not use 'ln -s' because you specifically requested a "live copy" (duplicate file).
    cp "$WGET_PATH"   "$CUSTOM_WGET_EXEC"
    chown "$USERNAME" "$CUSTOM_WGET_EXEC"
    # 5. Make the new copy executable
    chmod +x "$CUSTOM_WGET_EXEC"
    echo "SUCCESS: created $CUSTOM_WGET_EXEC from $WGET_PATH"
}

#
# Check for required executables and configuration files.
#
check_requirements() {
    local MISSING=0
    echo "Checking system requirements..."
    # 1. Check GS_SERVER_EXEC
    if [ ! -x "$GS_SERVER_EXEC" ] ; then
        echo "ERROR: gs-server executable not found or not executable at: $GS_SERVER_EXEC"
        MISSING=1
    else
        echo "OK: gs-server found at $GS_SERVER_EXEC"
    fi
    # 2. Check GRAB_SITE_EXEC
    if [ ! -x "$GRAB_SITE_EXEC" ] ; then
        echo "ERROR: grab-site executable not found or not executable at: $GRAB_SITE_EXEC"
        MISSING=1
    else
        echo "OK: grab-site found at $GRAB_SITE_EXEC"
    fi
    if [ "$OPENVPN_ENABLED" -eq 1 ] ; then
        # 3. Check OPENVPN_CONF_ST (Primary Config)
        if [ ! -f "$OPENVPN_CONF_ST" ] ; then
            echo "ERROR: primary OpenVPN config file not found: $OPENVPN_CONF_ST"
            MISSING=1
        else
            echo "OK: primary OpenVPN config found at $OPENVPN_CONF_ST"
        fi
        # 4. Check OPENVPN_AUTH_ST (Primary Auth)
        if [ ! -f "$OPENVPN_AUTH_ST" ] ; then
            echo "ERROR: primary OpenVPN auth file not found: $OPENVPN_AUTH_ST"
            MISSING=1
        else
            echo "OK: primary OpenVPN auth found at $OPENVPN_AUTH_ST"
        fi
        # Optional: Check secondary/tertiary configs just to warn, but don't fail if missing 
        # (since the script has fallback logic for them)
        if [ ! -f "$OPENVPN_CONF_ND" ] || [ ! -f "$OPENVPN_AUTH_ND" ] ; then
            echo "WARNING: secondary OpenVPN config/auth files missing, fallback to primary will be used after attempt $OPENVPN_USES_ST"
        fi
        if [ ! -f "$OPENVPN_CONF_RD" ] || [ ! -f "$OPENVPN_AUTH_RD" ] ; then
            echo "WARNING: tertiary OpenVPN config/auth files missing, fallback logic will apply after attempt $OPENVPN_USES_ND"
        fi
    fi
    # Exit if critical requirements are missing
    if [ $MISSING -eq 1 ] ; then
        echo "ERROR: one or more requirements are missing!"
        exit 1
    fi
    echo "SUCCESS: all critical requirements met!"
}

echo "Getting a copy of wget aka $CUSTOM_WGET_EXEC..."
get_wget

echo "Checking requirements..."
check_requirements

echo "Setting up the log directory..."
rm -rf "$GRABBER_LOG_DIR_OLD"
if [ -d "$GRABBER_LOG_DIR" ] ; then
   mv "$GRABBER_LOG_DIR" "$GRABBER_LOG_DIR_OLD"
fi
mkdir -p "$GRABBER_LOG_DIR"

rm -f "$RESET_FILE"
echo "[$STATE_ST] Initial launch..."
great_reset
firestarter
STATE=1

echo "Starting script in STATE 1..."

#
# Main cycle
#
while true ; do
    MAIN_CYCLE_COUNTER=1
    while [ $MAIN_CYCLE_COUNTER -le $TEST_INTERVAL ] ; do
        if [ ! "$STATE" -eq 0 ] && [ "$OPENVPN_ENABLED" -eq 1 ] ; then
            if ! check_openvpn_proc ; then
                echo "ERROR: openvpn process disappeared!"
                STATE=0
            fi
        fi
        if [ "$STATE" -eq 0 ] || [ -f "$RESET_FILE" ] ; then
            rm -f "$RESET_FILE"
            echo "[$STATE_RO] Repeated launch..."
            great_reset
            firestarter
            STATE=1
            break
        else
            sleep 1
        fi
        MAIN_CYCLE_COUNTER=$((MAIN_CYCLE_COUNTER + 1))
    done
    test_connection_quality
    TEST_CONNECTION_RESULT=$?
      if [ "$STATE" -eq 1 ] ; then
        if [ $TEST_CONNECTION_RESULT -eq 0 ] ; then
            echo "[$STATE_ST] connection - $CONCT_ST, remaining..."
            STATE=1
        elif [ $TEST_CONNECTION_RESULT -eq 1 ] || [ $TEST_CONNECTION_RESULT -eq 2 ] ; then
            echo "[$STATE_ST] connection - $CONCT_ND (code: $TEST_CONNECTION_RESULT), going to [$STATE_ND]..."
            STATE=2
        elif [ $TEST_CONNECTION_RESULT -eq 3 ] ; then
            echo "[$STATE_ST] ERROR: openvpn process disappeared!"
            STATE=0
        fi
    elif [ "$STATE" -eq 2 ] ; then
        if [ $TEST_CONNECTION_RESULT -eq 0 ] ; then
            echo "[$STATE_ND] connection - $CONCT_ST, returning to [$STATE_ST]..."
            STATE=1
        elif [ $TEST_CONNECTION_RESULT -eq 1 ] || [ $TEST_CONNECTION_RESULT -eq 2 ] ; then
            echo "[$STATE_ND] connection - $CONCT_RD (code: $TEST_CONNECTION_RESULT), going to [$STATE_RD]..."
            STATE=3
        elif [ $TEST_CONNECTION_RESULT -eq 3 ] ; then
            echo "[$STATE_ND] ERROR: openvpn process disappeared!"
            STATE=0
        fi
    elif [ "$STATE" -eq 3 ] ; then
        if [ $TEST_CONNECTION_RESULT -eq 0 ] ; then
            echo "[$STATE_RD] connection - $CONCT_ND, returning to [$STATE_ND]..."
            STATE=2
        elif [ $TEST_CONNECTION_RESULT -eq 1 ] || [ $TEST_CONNECTION_RESULT -eq 2 ] ; then
            echo "[$STATE_RD] connection - $CONCT_FA (code: $TEST_CONNECTION_RESULT), resetting..."
            STATE=0
        elif [ $TEST_CONNECTION_RESULT -eq 3 ] ; then
            echo "[$STATE_RD] ERROR: openvpn process disappeared!"
            STATE=0
        fi
    fi
done

#
