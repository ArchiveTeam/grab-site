import faulthandler
faulthandler.enable()

import re
import os
import sys
import binascii
import datetime
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

@click.option('--offsite-links/--no-offsite-links', default=False,
	help=
		'--offsite-links (default: true) to grab all links to a depth of 1 '
		'on other domains, or --no-offsite-links to disable.')

@click.option('--igsets', default="", metavar='LIST',
	help='Comma-separated list of ignore sets to use in addition to "global".')

@click.option('--ignore-sets', default="", metavar='LIST',
	help='Alias for --igsets.')

@click.option('--level', default="inf", metavar='NUM',
	help='Recurse this many levels (default: inf).')

@click.option('--page-requisites-level', default="5", metavar='NUM',
	help='Recursive this many levels for page requisites (default: 5).')

@click.option('--sitemaps/--no-sitemaps', default=True,
	help=
		'--sitemaps (default: true) to queue URLs from sitemap.xml '
		'at the root of the site, or --no-sitemaps to disable.')

@click.option('--version', is_flag=True, callback=print_version,
	expose_value=False, is_eager=True, help='Print version and exit.')

@click.argument('start_url')

def main(concurrency, concurrent, delay, recursive, offsite_links, igsets,
ignore_sets, level, page_requisites_level, sitemaps, start_url):
	span_hosts_allow = "page-requisites,linked-pages"
	if not offsite_links:
		span_hosts_allow = "page-requisites"

	if concurrent != -1:
		concurrency = concurrent

	if ignore_sets != "":
		igsets = ignore_sets

	id = binascii.hexlify(os.urandom(16)).decode('utf-8')
	ymd = datetime.datetime.utcnow().isoformat()[:10]
	no_proto_no_trailing = start_url.split('://', 1)[1].rstrip('/')[:100]
	warc_name = "{}-{}-{}".format(re.sub('[^-_a-zA-Z0-9%\.,;@+=]', '-', no_proto_no_trailing), ymd, id[:8])

	# make absolute because wpull will start in temp/
	working_dir = os.path.abspath(warc_name)
	os.makedirs(working_dir)
	temp_dir = os.path.join(working_dir, "temp")
	os.makedirs(temp_dir)

	with open("{}/id".format(working_dir), "w") as f:
		f.write(id)

	with open("{}/start_url".format(working_dir), "w") as f:
		f.write(start_url)

	with open("{}/concurrency".format(working_dir), "w") as f:
		f.write(str(concurrency))

	with open("{}/igsets".format(working_dir), "w") as f:
		f.write("global,{}".format(igsets))

	with open("{}/igoff".format(working_dir), "w") as f:
		pass

	with open("{}/ignores".format(working_dir), "w") as f:
		pass

	with open("{}/delay".format(working_dir), "w") as f:
		f.write(delay)

	LIBGRABSITE = os.path.dirname(libgrabsite.__file__)
	args = [
		"-U", "Mozilla/5.0 (Windows NT 6.3; WOW64; rv:39.0) Gecko/20100101 Firefox/39.0",
		"--header=Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
		"--header=Accept-Language: en-US,en;q=0.5",
		"-o", "{}/wpull.log".format(working_dir),
		"--database", "{}/wpull.db".format(working_dir),
		"--plugin-script", "{}/plugin.py".format(LIBGRABSITE),
		"--python-script", "{}/wpull_hooks.py".format(LIBGRABSITE),
		"--save-cookies", "{}/cookies.txt".format(working_dir),
		"--no-check-certificate",
		"--delete-after",
		"--no-robots",
		"--page-requisites",
		"--no-parent",
		"--inet4-only",
		"--timeout", "20",
		"--tries", "3",
		"--concurrent", str(concurrency),
		"--waitretry", "5",
		"--warc-file", "{}/{}".format(working_dir, warc_name),
		"--warc-max-size", "5368709120",
		"--warc-cdx",
		"--debug-manhole",
		"--strip-session-id",
		"--escaped-fragment",
		"--monitor-disk", "400m",
		"--monitor-memory", "10k",
		"--max-redirect", "8",
		"--level", level,
		"--page-requisites-level", page_requisites_level,
		"--span-hosts-allow", span_hosts_allow,
		"--quiet",
	]

	if sitemaps:
		args += ["--sitemaps"]

	if recursive:
		args += ["--recursive"]

	args += [start_url]

	# Mutate argv, environ, cwd before we turn into wpull
	sys.argv[1:] = args
	os.environ["GRAB_SITE_WORKING_DIR"] = working_dir
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
