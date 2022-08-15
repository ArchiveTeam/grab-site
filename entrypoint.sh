#!/usr/bin/env sh
set -eax

# If running any scripts we recognize, step-down to "grab-site" user.
for v in grab-site gs-server gs-dump-urls; do
    if [ "$1" = "$v" -a "$(id -u)" = '0' ]; then
        find /app \! -user grab-site -exec chown grab-site '{}' +
        exec su-exec "$v" "$@"
    fi
done

exec "$@"