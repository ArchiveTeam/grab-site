#!/bin/bash

set -e

url="$1"
domain="$(echo -n "$url" | awk -F/ '{print $3}')"
dir="$domain"
self=$(dirname "$0")

mkdir -p "$dir"

# Note: we use the default html5lib parser instead of lxml (as ArchiveBot does)

PYTHONPATH="$self" ~/.local/bin/wpull3 \
	-U "Mozilla/5.0 (Windows NT 6.3; WOW64; rv:35.0) Gecko/20100101 Firefox/35.0" \
	--header="Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8" \
	-o "$dir/wpull.log" \
	--database "$dir/wpull.db" \
	--plugin-script "$self/plugin.py" \
	--plugin-args " --dupes-db $dir/dupes_db" \
	--save-cookies "$dir/cookies" \
	--no-check-certificate \
	--delete-after \
	--no-robots \
	--page-requisites \
	--no-parent \
	--sitemaps \
	--inet4-only \
	--no-skip-getaddrinfo \
	--timeout 20 \
	--tries 3 \
	--waitretry 5 \
	--warc-file "$dir/$dir" \
	--warc-max-size 5368709120 \
	--debug-manhole \
	--strip-session-id \
	--escaped-fragment \
	--recursive \
	--span-hosts-allow page-requisites,linked-pages \
	"$url"
