import re
import os
import sys
import binascii
import datetime
import subprocess
import signal
import click
import libgrabsite

def print_version(ctx, param, value):
	if not value or ctx.resilient_parsing:
		return
	click.echo(libgrabsite.__version__)
	ctx.exit()


@click.command()

@click.option('--concurrency', default=2, metavar='NUM',
	help='Use this many connections to fetch in parallel')

@click.option('--concurrent', default=-1, metavar='NUM',
	help='Alias for --concurrency')

@click.option('--recursive/--1', default=True,
	help=
		'--recursive (default: true) to crawl under last /path/ component '
		'recursively, or --1 to get just START_URL')

@click.option('--offsite-links/--no-offsite-links', default=False,
	help=
		'--offsite-links (default: true) to grab all links to a depth of 1 '
		'on other domains, or --no-offsite-links to disable')

@click.option('--igsets', default="", metavar='LIST',
	help='Comma-separated list of ignore sets to use in addition to "global"')

@click.option('--ignore-sets', default="", metavar='LIST',
	help='Alias for --igsets')

@click.option('--level', default="inf", metavar='NUM',
	help='Recurse this many levels (default: inf)')

@click.option('--page-requisites-level', default="5", metavar='NUM',
	help='Recursive this many levels for page requisites (default: 5)')

@click.option('--sitemaps/--no-sitemaps', default=True,
	help=
		'--sitemaps (default: true) to queue URLs from sitemap.xml '
		'at the root of the site, or --no-sitemaps to disable')

@click.option('--version', is_flag=True, callback=print_version,
	expose_value=False, is_eager=True, help='Print version and exit.')

@click.argument('start_url')

def main(concurrency, concurrent, recursive, offsite_links, igsets,
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
	# remove protocol, remove trailing slashes, convert slashes to "-"es
	warc_name = re.sub('[/\?&]', '-', start_url.split('://', 1)[1].rstrip('/')) + "-" + ymd + "-" + id[:8]
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

	LIBGRABSITE = os.path.dirname(libgrabsite.__file__)
	args = [
		"{}/patched-wpull".format(LIBGRABSITE),
		"-U", "Mozilla/5.0 (Windows NT 6.3; WOW64; rv:39.0) Gecko/20100101 Firefox/39.0",
		"--header=Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
		"--header=Accept-Language: en-US,en;q=0.5",
		"-o", "{}/wpull.log".format(working_dir),
		"--database", "{}/wpull.db".format(working_dir),
		"--plugin-script", "{}/plugin.py".format(LIBGRABSITE),
		"--python-script", "{}/wpull_hooks.py".format(LIBGRABSITE),
		"--plugin-args", " --dupes-db {}/dupes_db".format(working_dir),
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

	env = os.environ.copy()
	env["GRAB_SITE_WORKING_DIR"] = working_dir
	# We can use --warc-tempdir= to put WARC-related temporary files in a temp
	# directory, but wpull also creates non-WARC-related "resp_cb" temporary
	# files in the cwd, so we must start wpull in temp/ anyway.
	p = subprocess.Popen(args, env=env, cwd=temp_dir)

	# wpull child process handles ctrl-c; we want to ignore so that we don't quit
	# before wpull on ctrl-c
	signal.signal(signal.SIGINT, lambda x, y: None)

	sys.exit(p.wait())


if __name__ == '__main__':
	main()
