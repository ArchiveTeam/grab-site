import re
import os
import sys
import binascii
import datetime
import subprocess
import click
import libgrabsite

@click.command()
@click.option('--concurrency', default=2, help='TODO')
@click.option('--concurrent', default=None, help='Alias for --concurrency')
@click.option('--recursive/--1', default=True, help='TODO')
@click.option('--offsite-links/--no-offsite-links', default=False, help='TODO')
@click.option('--igsets', default="", help='TODO')
@click.option('--ignore-sets', default="", help='Alias for --igsets')
@click.option('--level', default="inf", help='TODO')
@click.option('--page-requisites-level', default="5", help='TODO')
@click.argument('start_url')
def main(concurrency, concurrent, recursive, offsite_links, igsets, ignore_sets, level, page_requisites_level, start_url):
	span_hosts_allow = "page-requisites,linked-pages"
	if not offsite_links:
		span_hosts_allow = "page-requisites"

	id = binascii.hexlify(os.urandom(16)).decode('utf-8')

	ymd = datetime.datetime.utcnow().isoformat()[:10]
	# remove protocol, remove trailing slashes, convert slashes to "-"es
	working_dir = re.sub('[/\?&]', '-', start_url.split('://', 1)[1].rstrip('/')) + "-" + ymd + "-" + id[:8]
	os.makedirs(working_dir)

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
		"--sitemaps",
		"--inet4-only",
		"--timeout", "20",
		"--tries", "3",
		"--concurrent", str(concurrency),
		"--waitretry", "5",
		"--warc-file", "{}/{}".format(working_dir, working_dir),
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

	if recursive:
		args += ["--recursive"]

	args += [start_url]

	env = os.environ.copy()
	env["GRAB_SITE_WORKING_DIR"] = working_dir
	p = subprocess.Popen(args, env=env)
	sys.exit(p.wait())


if __name__ == '__main__':
	main()
