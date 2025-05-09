import faulthandler
faulthandler.enable()

import re
import os
import sys
import urllib.request
import shutil
import binascii
import datetime
import shlex
import click
import libgrabsite

def print_version(ctx, param, value):
	if not value or ctx.resilient_parsing:
		return
	click.echo(libgrabsite.__version__)
	ctx.exit()

def replace_2arg(args, arg, replacement):
	idx = args.index(arg)
	if idx == -1:
		return
	args.pop(idx)
	args.pop(idx)
	for r in reversed(replacement):
		args.insert(idx, r)

def patch_dns_inet_is_multicast():
	"""
	Patch dnspython's dns.inet.is_multicast to not raise ValueError:
	https://github.com/ArchiveTeam/grab-site/issues/111
	"""
	import dns.inet
	is_multicast_dnspython = dns.inet.is_multicast
	def is_multicast(text):
		try:
			return is_multicast_dnspython(text)
		except Exception:
			return False
	dns.inet.is_multicast = is_multicast

@click.command()

@click.option('--concurrency', default=2, metavar='NUM',
	help='Use this many connections to fetch in parallel (default: 2).')

@click.option('--concurrent', default=-1, metavar='NUM',
	help='Alias for --concurrency.')

@click.option('--delay', default="0", metavar='DELAY',
	help=
		'Time to wait between requests, in milliseconds (default: 0).  '
		'Can be "NUM", or "MIN-MAX" to use a random delay between MIN and MAX '
		'for each request.  Delay applies to each concurrent fetcher, not globally.')

@click.option('--recursive/--1', default=True,
	help=
		'--recursive (default: true) to crawl under last /path/ component '
		'recursively, or --1 to get just START_URL.')

@click.option('--offsite-links/--no-offsite-links', default=True,
	help=
		'--offsite-links (default: true) to grab all links to a depth of 1 '
		'on other domains, or --no-offsite-links to disable.')

@click.option('--igsets', default="", metavar='LIST',
	help='Comma-separated list of ignore sets to use in addition to "global".')

@click.option('--ignore-sets', default="", metavar='LIST',
	help='Alias for --igsets.')

@click.option('--no-global-igset', is_flag=True,
	help='Do not add the "global" ignore set.')

@click.option('--import-ignores', default=None, metavar='FILE',
	help='Copy this file to DIR/ignores before the crawl begins.')

@click.option('--igon/--igoff', default=False,
	help=
		'--igon (default: false) to print all URLs being ignored to the terminal '
		'and dashboard.')

@click.option('--debug', is_flag=True, help='Print a lot of debugging information.')

@click.option('--video/--no-video', default=True,
	help=
		'--no-video (default: false) to skip the download of videos by both '
		'mime type and file extension.  Skipped videos are logged to '
		'DIR/skipped_videos')

@click.option('-i', '--input-file', default=None, type=str,
	help=
		'Load list of URLs-to-grab from a local file or from a URL; like wget -i. '
		'File must be a newline-delimited list of URLs. '
		'Combine with --1 to avoid a recursive crawl on each URL.')

@click.option('--max-content-length', default=-1, metavar='N',
	help=
		"Skip the download of any response that claims a Content-Length "
		"larger than N (default: -1, don't skip anything).")

@click.option('--level', default="inf", metavar='NUM',
	help='Recurse this many levels (default: inf).')

@click.option('--page-requisites-level', default="5", metavar='NUM',
	help='Recursive this many levels for page requisites (default: 5).')

@click.option('--warc-max-size', default=5368709120, metavar='BYTES',
	help=
		'Try to limit each WARC file to around BYTES bytes before rolling over '
		'to a new WARC file (default: 5368709120, which is 5GiB).')

@click.option('--ua', default="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:103.0) Gecko/20100101 Firefox/103.0",
	metavar='STRING', help='Send User-Agent: STRING instead of pretending to be Firefox on Windows.')

@click.option('--wpull-args', default="",
	metavar='ARGS', help=
		r'String containing additional arguments to pass to wpull; '
		r'see ~/.local/bin/wpull --help.  ARGS is split with shlex.split '
		r'and individual arguments can contain spaces if quoted, e.g. '
		r'--wpull-args="--youtube-dl \"--youtube-dl-exe=/My Documents/youtube-dl\""')

@click.option('--sitemaps/--no-sitemaps', default=True,
	help=
		'--sitemaps (default: true) to queue URLs from sitemap.xml '
		'at the root of the site, or --no-sitemaps to disable.')

@click.option('--dupespotter/--no-dupespotter', default=True,
	help=
		'--dupespotter (default: true) to skip the extraction of links '
		'from pages that look like duplicates of earlier pages, or '
		'--no-dupespotter to disable.  Disable this for sites that are '
		'directory listings.')

@click.option('--id', default=None, type=str, metavar='ID',
	help=
		'Use id ID for the crawl instead of a random 128-bit id. '
		'This must be unique for every crawl.')

@click.option('--dir', default=None, type=str, metavar='DIR', help=
	'Put control files, temporary files, and unfinished WARCs in DIR '
	'(default: a directory name based on the URL, date, and first 8 '
	'characters of the id).')

@click.option('--finished-warc-dir', default=None, type=str, metavar='FINISHED_WARC_DIR',
	help=
		'Absolute path to a directory into which finished .warc.gz and .cdx '
		'files will be moved.')

@click.option('--permanent-error-status-codes', default='401,403,404,405,410', type=str,
	metavar='STATUS_CODES',
	help=
		'A comma-separated list of HTTP status codes to treat as a permanent '
		'error and therefore *not* retry (default: 401,403,404,405,410)')

@click.option('--which-wpull-args-partial', is_flag=True,
	help=
		'Print a partial list of wpull arguments that would be used and exit.  '
		'Excludes grab-site-specific features, and removes DIR/ from paths.  '
		'Useful for reporting bugs on wpull without grab-site involvement.')

@click.option('--which-wpull-command', is_flag=True,
	help=
		"Populate DIR/ but don't start wpull; instead print the command that would "
		"have been used to start wpull with all of the grab-site functionality.")

@click.option('--resume', is_flag=True,
	help='Resume a crawl that was previously stopped. Use with --dir to specify the crawl directory.')

@click.option('--version', is_flag=True, callback=print_version,
	expose_value=False, is_eager=True, help='Print version and exit.')

@click.argument('start_url', nargs=-1, required=False)

def main(concurrency, concurrent, delay, recursive, offsite_links, igsets,
ignore_sets, no_global_igset, import_ignores, igon, debug, video, level,
page_requisites_level, max_content_length, sitemaps, dupespotter, warc_max_size,
ua, input_file, wpull_args, start_url, id, dir, finished_warc_dir, resume,
permanent_error_status_codes, which_wpull_args_partial, which_wpull_command):
	"""
	Runs a crawl on one or more URLs.  For additional help, see

	https://github.com/ArchiveTeam/grab-site/blob/master/README.md#usage
	"""
	if resume and not dir:
		print("Error: --resume requires --dir to specify the crawl directory", file=sys.stderr)
		sys.exit(1)

	if resume and not os.path.exists(dir):
		print(f"Error: Crawl directory {dir} does not exist", file=sys.stderr)
		sys.exit(1)

	if not resume and not (input_file or start_url):
		print("Neither a START_URL or --input-file= was specified; see --help", file=sys.stderr)
		sys.exit(1)
	elif input_file and start_url:
		print("Can't specify both START_URL and --input-file=; see --help", file=sys.stderr)
		sys.exit(1)

	span_hosts_allow = "page-requisites,linked-pages"
	if not offsite_links:
		span_hosts_allow = "page-requisites"

	if concurrent != -1:
		concurrency = concurrent

	if ignore_sets != "":
		igsets = ignore_sets

	if start_url:
		claim_start_url = start_url[0]
	else:
		input_file_is_remote = bool(re.match("^(ftp|https?)://", input_file))
		if input_file_is_remote:
			claim_start_url = input_file
		else:
			claim_start_url = 'file://' + os.path.abspath(input_file)

	if not id:
		id = binascii.hexlify(os.urandom(16)).decode('utf-8')
	ymd                  = datetime.datetime.utcnow().isoformat()[:10]
	no_proto_no_trailing = claim_start_url.split('://', 1)[1].rstrip('/')[:100]
	unwanted_chars_re    = r'[^-_a-zA-Z0-9%\.,;@+=]'
	warc_name            = "{}-{}-{}".format(re.sub(unwanted_chars_re, '-', no_proto_no_trailing).lstrip('-'), ymd, id[:8])

	# make absolute because wpull will start in temp/
	if not dir:
		working_dir = os.path.abspath(warc_name)
	else:
		working_dir = os.path.abspath(dir)

	LIBGRABSITE = os.path.dirname(libgrabsite.__file__)
	args = [
		"--debug" if debug else "--quiet",
		"-U",                      ua,
		"--header",                "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
		"--header",                "Accept-Language: en-US,en;q=0.5",
		"--no-check-certificate",
		"--no-robots",
		"--inet4-only",
		"--dns-timeout",           "20",
		"--connect-timeout",       "20",
		"--read-timeout",          "900",
		"--session-timeout",       str(86400 * 2),
		"--tries",                 "3",
		"--waitretry",             "5",
		"--max-redirect",          "8",
		"--output-file",           "{}/wpull.log".format(working_dir),
		"--database",              "{}/wpull.db".format(working_dir),
		"--plugin-script",         "{}/wpull_hooks.py".format(LIBGRABSITE),
		"--save-cookies",          "{}/cookies.txt".format(working_dir),
		"--delete-after",
		"--page-requisites",
		"--no-parent",
		"--concurrent",            str(concurrency),
		"--warc-file",             "{}/{}".format(working_dir, warc_name),
		"--warc-max-size",         str(warc_max_size),
		"--warc-cdx",
		"--strip-session-id",
		"--escaped-fragment",
		"--level",                 level,
		"--page-requisites-level", page_requisites_level,
		"--span-hosts-allow",      span_hosts_allow,
		"--load-cookies",          "{}/default_cookies.txt".format(LIBGRABSITE),
	]

	if os.name != "nt" and sys.platform != "cygwin":
		args += [
			"--debug-manhole"
		]

	if finished_warc_dir is not None:
		args += ["--warc-move", finished_warc_dir]

	if sitemaps:
		args += ["--sitemaps"]

	if recursive:
		args += ["--recursive"]

	if resume:
		# Add --warc-append to wpull_args if not already present
		if "--warc-append" not in wpull_args:
			wpull_args = ("--warc-append " + wpull_args).strip()

	if wpull_args:
		args += shlex.split(wpull_args)

	DIR_input_file = os.path.join(working_dir, "input_file")
	if start_url:
		args.extend(start_url)
	else:
		args += ["--input-file", DIR_input_file]

	if which_wpull_args_partial:
		replace_2arg(args, "--output-file",   ["--output-file",  "wpull.log"])
		replace_2arg(args, "--database",      ["--database",     "wpull.db"])
		replace_2arg(args, "--plugin-script", [])
		replace_2arg(args, "--save-cookies",  ["--save-cookies", "cookies.txt"])
		replace_2arg(args, "--load-cookies",  [])
		replace_2arg(args, "--warc-file",     ["--warc-file",    warc_name])
		try:
			args.remove("--quiet")
		except ValueError:
			pass
		print(" ".join(shlex.quote(a) for a in args))
		return

	# Create DIR and DIR files only after which_wpull_args_* checks
	if resume:
		temp_dir = os.path.join(working_dir, "temp")
		if not os.path.exists(temp_dir):
			os.makedirs(temp_dir)
	else:
		os.makedirs(working_dir)
		temp_dir = os.path.join(working_dir, "temp")
		os.makedirs(temp_dir)

	if input_file is not None and not resume:
		# wpull -i doesn't support URLs, so download the input file ourselves if necessary
		if input_file_is_remote:
			# TODO: use wpull with correct user agent instead of urllib.request
			# wpull -O fails: https://github.com/chfoo/wpull/issues/275
			u = urllib.request.urlopen(input_file)
			with open(DIR_input_file, "wb") as f:
				while True:
					s = u.read(1024 * 1024)
					if not s:
						break
					f.write(s)
		else:
			shutil.copyfile(input_file, DIR_input_file)

	if not resume:
		with open("{}/id".format(working_dir), "w") as f:
			f.write(id)

		with open("{}/start_url".format(working_dir), "w") as f:
			f.write(claim_start_url)

		with open("{}/all_start_urls".format(working_dir), "w") as f:
			for u in start_url:
				f.write(u + "\n")

	with open("{}/concurrency".format(working_dir), "w") as f:
		f.write(str(concurrency))

	with open("{}/max_content_length".format(working_dir), "w") as f:
		f.write(str(max_content_length))

	with open("{}/igsets".format(working_dir), "w") as f:
		f.write("{}{}".format("" if no_global_igset else "global,", igsets))

	if video:
		with open("{}/video".format(working_dir), "w") as f:
			pass

	if not igon:
		with open("{}/igoff".format(working_dir), "w") as f:
			pass

	with open("{}/ignores".format(working_dir), "w") as f:
		if import_ignores is not None:
			f.write(open(import_ignores, "r").read())

	with open("{}/delay".format(working_dir), "w") as f:
		f.write(delay)

	with open("{}/scrape".format(working_dir), "w") as f:
		pass

	# For resume mode, remove the stop file if it exists
	if resume and os.path.exists("{}/stop".format(working_dir)):
		os.unlink("{}/stop".format(working_dir))

	# We don't actually need to write control files for this mode to work, but the
	# only reason to use this is if you're starting wpull manually with modified
	# arguments, and wpull_hooks.py requires the control files.
	if which_wpull_command:
		bin = sys.argv[0].replace("/grab-site", "/wpull") # TODO
		print("GRAB_SITE_WORKING_DIR={} DUPESPOTTER_ENABLED={} {} {}".format(
			working_dir, int(dupespotter), bin, " ".join(shlex.quote(a) for a in args)))
		return

	patch_dns_inet_is_multicast()

	# Mutate argv, environ, cwd before we turn into wpull
	sys.argv[1:] = args
	os.environ["GRAB_SITE_WORKING_DIR"] = working_dir
	os.environ["DUPESPOTTER_ENABLED"]   = "1" if dupespotter else "0"
	# We can use --warc-tempdir= to put WARC-related temporary files in a temp
	# directory, but wpull also creates non-WARC-related "resp_cb" temporary
	# files in the cwd, so we must start wpull in temp/ anyway.
	os.chdir(temp_dir)

	# Modify NO_DOCUMENT_STATUS_CODES
	# https://github.com/chfoo/wpull/issues/143
	from wpull.processor.web import WebProcessor
	WebProcessor.NO_DOCUMENT_STATUS_CODES = \
		tuple(int(code) for code in permanent_error_status_codes.split(","))

	import wpull.application.main
	# Don't let wpull install a handler for SIGINT or SIGTERM,
	# because we install our own in wpull_hooks.py.
	wpull.application.main.main(use_signals=False)


if __name__ == '__main__':
	main()
