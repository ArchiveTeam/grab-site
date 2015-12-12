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

@click.option('--igon/--igoff', default=False,
	help=
		'--igon (default: false) to print all URLs being ignored to the terminal '
		'and dashboard.')

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

@click.option('--ua', default="Mozilla/5.0 (Windows NT 6.3; WOW64; rv:43.0) Gecko/20100101 Firefox/43.0",
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
	help='Move finished .warc.gz and .cdx files to this directory.')

@click.option('--version', is_flag=True, callback=print_version,
	expose_value=False, is_eager=True, help='Print version and exit.')

@click.argument('start_url', nargs=-1, required=False)

def main(concurrency, concurrent, delay, recursive, offsite_links, igsets,
ignore_sets, igon, video, level, page_requisites_level, max_content_length,
sitemaps, dupespotter, warc_max_size, ua, input_file, wpull_args, start_url,
id, dir, finished_warc_dir):
	if not (input_file or start_url):
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
	ymd = datetime.datetime.utcnow().isoformat()[:10]
	no_proto_no_trailing = claim_start_url.split('://', 1)[1].rstrip('/')[:100]
	warc_name = "{}-{}-{}".format(re.sub('[^-_a-zA-Z0-9%\.,;@+=]', '-', no_proto_no_trailing), ymd, id[:8])

	# make absolute because wpull will start in temp/
	if not dir:
		working_dir = os.path.abspath(warc_name)
	else:
		working_dir = os.path.abspath(dir)
	os.makedirs(working_dir)
	temp_dir = os.path.join(working_dir, "temp")
	os.makedirs(temp_dir)

	def get_base_wpull_args():
		return ["-U", ua,
			"--header=Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
			"--header=Accept-Language: en-US,en;q=0.5",
			"--no-check-certificate",
			"--no-robots",
			"--inet4-only",
			"--timeout", "20",
			"--tries", "3",
			"--waitretry", "5",
			"--max-redirect", "8",
			"--quiet"
		]

	if input_file is not None:
		# wpull -i doesn't support URLs, so download the input file ourselves if necessary
		DIR_input_file = os.path.join(working_dir, "input_file")
		if input_file_is_remote:
			# TODO: use wpull with correct user agent instead of urllib.request
			# wpull -O fails: https://github.com/chfoo/wpull/issues/275
			u = urllib.request.urlopen(input_file)
			with open(DIR_input_file, "wb") as f:
				while True:
					s = u.read(1024*1024)
					if not s:
						break
					f.write(s)
		else:
			shutil.copyfile(input_file, DIR_input_file)

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
		f.write("global,{}".format(igsets))

	if video:
		with open("{}/video".format(working_dir), "w") as f:
			pass

	if not igon:
		with open("{}/igoff".format(working_dir), "w") as f:
			pass

	with open("{}/ignores".format(working_dir), "w") as f:
		pass

	with open("{}/delay".format(working_dir), "w") as f:
		f.write(delay)

	LIBGRABSITE = os.path.dirname(libgrabsite.__file__)
	args = get_base_wpull_args() + [
		"-o", "{}/wpull.log".format(working_dir),
		"--database", "{}/wpull.db".format(working_dir),
		"--plugin-script", "{}/plugin.py".format(LIBGRABSITE),
		"--python-script", "{}/wpull_hooks.py".format(LIBGRABSITE),
		"--save-cookies", "{}/cookies.txt".format(working_dir),
		"--delete-after",
		"--page-requisites",
		"--no-parent",
		"--concurrent", str(concurrency),
		"--warc-file", "{}/{}".format(working_dir, warc_name),
		"--warc-max-size", str(warc_max_size),
		"--warc-cdx",
		"--strip-session-id",
		"--escaped-fragment",
		"--level", level,
		"--page-requisites-level", page_requisites_level,
		"--span-hosts-allow", span_hosts_allow,
		"--load-cookies", "{}/default_cookies.txt".format(LIBGRABSITE)
	]

	# psutil is not available on Windows and therefore wpull's --monitor-*
	# options are also not available.
	if os.name != "nt" and sys.platform != "cygwin":
		# psutil may also just be not installed
		try:
			import psutil
		except ImportError:
			psutil = None
		if psutil is not None:
			args += [
				"--monitor-disk", "400m",
				"--monitor-memory", "10k",
			]
		args += [
			"--debug-manhole"
		]

	if finished_warc_dir is not None:
		args += ["--warc-move", finished_warc_dir]

	if sitemaps:
		args += ["--sitemaps"]

	if recursive:
		args += ["--recursive"]

	if wpull_args:
		args += shlex.split(wpull_args)

	if start_url:
		args.extend(start_url)
	else:
		args += ["--input-file", DIR_input_file]

	# Mutate argv, environ, cwd before we turn into wpull
	sys.argv[1:] = args
	os.environ["GRAB_SITE_WORKING_DIR"] = working_dir
	os.environ["DUPESPOTTER_ENABLED"] = "1" if dupespotter else "0"
	# We can use --warc-tempdir= to put WARC-related temporary files in a temp
	# directory, but wpull also creates non-WARC-related "resp_cb" temporary
	# files in the cwd, so we must start wpull in temp/ anyway.
	os.chdir(temp_dir)

	from wpull.app import Application
	def noop_setup_signal_handlers(self):
		pass

	# Don't let wpull install a handler for SIGINT or SIGTERM,
	# because we install our own in wpull_hooks.py.
	Application.setup_signal_handlers = noop_setup_signal_handlers

	import wpull.__main__
	wpull.__main__.main()


if __name__ == '__main__':
	main()
