grab-site
===

[![Build status][travis-image]][travis-url]

grab-site is an easy preconfigured web crawler designed for backing up websites.
Give grab-site a URL and it will recursively crawl the site and write
[WARC files](https://www.archiveteam.org/index.php?title=The_WARC_Ecosystem).
Internally, grab-site uses [a fork](https://github.com/ArchiveTeam/ludios_wpull) of
[wpull](https://github.com/chfoo/wpull) for crawling.

grab-site gives you

*	a dashboard with all of your crawls, showing which URLs are being
	grabbed, how many URLs are left in the queue, and more.

*	the ability to add ignore patterns when the crawl is already running.
	This allows you to skip the crawling of junk URLs that would
	otherwise prevent your crawl from ever finishing.  See below.

*	an extensively tested default ignore set ([global](https://github.com/ArchiveTeam/grab-site/blob/master/src/grab_site/ignore_sets/global))
	as well as additional (optional) ignore sets for forums, reddit, etc.

*	duplicate page detection: links are not followed on pages whose
	content duplicates an already-seen page.

The URL queue is kept on disk instead of in memory.  If you're really lucky,
grab-site will manage to crawl a site with ~10M pages.

![dashboard screenshot](https://raw.githubusercontent.com/ArchiveTeam/grab-site/master/images/dashboard.png)

Note: if you have any problems whatsoever installing or getting grab-site to run,
please [file an issue](https://github.com/ArchiveTeam/grab-site/issues) - thank you!

The installation methods below are the only ones supported in our GitHub issues.
Please do not modify the installation steps unless you really know what you're
doing, with both Python packaging and your operating system. grab-site runs
on a specific version of Python (3.9, 3.10, 3.11, 3.12) and with specific dependency versions.

**Contents**

- [Install using Docker](#install-using-docker)
- [Install on Debian](#install-on-debian)
- [Install on NixOS](#install-on-nixos)
- [Install on macOS](#install-on-macos)
- [Install on Windows 10 (experimental)](#install-on-windows-10-experimental)
- [Upgrade an existing install](#upgrade-an-existing-install)
- [Usage](#usage)
  - [`grab-site` options, ordered by importance](#grab-site-options-ordered-by-importance)
  - [Warnings](#warnings)
  - [Tips for specific websites](#tips-for-specific-websites)
- [Changing ignores during the crawl](#changing-ignores-during-the-crawl)
- [Inspecting the URL queue](#inspecting-the-url-queue)
- [Preventing a crawl from queuing any more URLs](#preventing-a-crawl-from-queuing-any-more-urls)
- [Stopping a crawl](#stopping-a-crawl)
- [Advanced `gs-server` options](#advanced-gs-server-options)
- [Viewing the content in your WARC archives](#viewing-the-content-in-your-warc-archives)
- [Inspecting WARC files in the terminal](#inspecting-warc-files-in-the-terminal)
- [Automatically pausing grab-site processes when free disk is low](#automatically-pausing-grab-site-processes-when-free-disk-is-low)
- [Thanks](#thanks)
- [Help](#help)


Install using Docker
---

For quick usage with debug logging and with cleanup of the container:
```shell
docker run --rm --detach --name gs-0 --publish 29000:29000 --volume "${PWD}/data:/tmp/gs" ghcr.io/archiveteam/grab-site:latest
docker exec gs-0 grab-site --debug --no-offsite-links "https://example.org"
docker stop gs-0
```

If you want to extract the list of "done" urls:
```shell
docker exec gs-0 gs-dump-urls "/tmp/gs/<url>-<date>-<hash>/wpull.db" done
```


Install on Debian
---

```
sudo apt-get -y update
sudo apt-get -y install --no-install-recommends build-essential libre2-dev libxml2-dev libxslt-dev pkg-config zlib1g-dev
python3 -m venv .venv
. .venv/bin/activate
pip install --no-binary lxml .
```

`--no-binary lxml` is necessary for the html5-parser build.



Install on NixOS
---

grab-site was removed from nixpkgs master; 23.05 is the last release to contain grab-site.

```
nix-env -f https://github.com/NixOS/nixpkgs/archive/release-23.05.tar.gz -iA grab-site
```



<!-- TODO: update sections below -->
Install on macOS
---

On OS X 10.10 - macOS 11:

1.	Run `locale` in your terminal.  If the output includes "UTF-8", you
	are all set.  If it does not, your terminal is misconfigured and grab-site
	will fail to start.  This can be corrected with:

	-	Terminal.app: Preferences... -> Profiles -> Advanced -> **check** Set locale environment variables on startup

	-	iTerm2: Preferences... -> Profiles -> Terminal -> Environment -> **check** Set locale variables automatically

### Using Homebrew (**Intel Mac**)

For M1 Macs, use the next section instead of this one.

2.	Install Homebrew using the install step on https://brew.sh/

3.	Run:

	```
	brew update
	brew install python@3.8 libxslt re2 pkg-config
	/usr/local/opt/python@3.8/bin/python3 -m venv ~/gs-venv
	PKG_CONFIG_PATH="/usr/local/opt/libxml2/lib/pkgconfig" ~/gs-venv/bin/pip install --no-binary lxml --upgrade git+https://github.com/ArchiveTeam/grab-site
	```

4.	To put the `grab-site` binaries in your PATH, add this to your `~/.zshrc` (macOS 10.15, 11+) or `~/.bash_profile` (earlier):

	```
	PATH="$PATH:$HOME/gs-venv/bin"
	```

	and then restart your shell (e.g. by opening a new terminal tab/window).

### Using Homebrew (**M1 Mac**)

2.	Install Homebrew using the install step on https://brew.sh/

	If you already have a Homebrew install at `/usr/local`, you may need to first remove that old Intel-based Homebrew install.

3.	Run:

	```
	brew update
	brew install python@3.8 libxslt re2 pkg-config
	/opt/homebrew/opt/python@3.8/bin/python3 -m venv ~/gs-venv
	PKG_CONFIG_PATH="/opt/homebrew/opt/libxml2/lib/pkgconfig" ~/gs-venv/bin/pip install --no-binary lxml --upgrade git+https://github.com/ArchiveTeam/grab-site
	```

4.	To put the `grab-site` binaries in your PATH, add this to your `~/.zshrc` (macOS 10.15, 11+) or `~/.bash_profile` (earlier):

	```
	PATH="$PATH:$HOME/gs-venv/bin"
	```

	and then restart your shell (e.g. by opening a new terminal tab/window).



Install on Windows 10 (experimental)
---

On Windows 10 Fall Creators Update (1703) or newer:

1. Start menu -> search "feature" -> Turn Windows features on or off

2. Scroll down, check "Windows Subsystem for Linux" and click OK.

3. Wait for install and click "Restart now"

4. Start menu -> Store

5. Search for "Ubuntu" in the store and install Ubuntu (publisher: Canonical Group Limited).

6. Start menu -> Ubuntu

7. Wait for install and create a user when prompted.

8. Follow the [Ubuntu 18.04, 20.04, 22.04, Debian 10 (buster), Debian 11 (bullseye)](#install-on-ubuntu-1804-2004-2204-debian-10-buster-debian-11-bullseye) steps.



Upgrade an existing install
---

To update grab-site, simply run the `~/gs-venv/bin/pip install ...` or
`nix-env ...` command used to install it originally (see above).

After upgrading, stop `gs-server` with `kill` or ctrl-c, then start it again.
Existing `grab-site` crawls will automatically reconnect to the new server.



Usage
---

First, start the dashboard with:

```
gs-server
```

and point your browser to http://127.0.0.1:29000/

Note: gs-server listens on all interfaces by default, so you can reach the
dashboard by a non-localhost IP as well, e.g. a LAN or WAN IP.  (Sub-note:
no code execution capabilities are exposed on any interface.)

Then, start as many crawls as you want with:

```
grab-site 'URL'
```

Do this inside tmux unless they're very short crawls.

grab-site outputs WARCs, logs, and control files to a new subdirectory in the
directory from which you launched `grab-site`, referred to here as "DIR".
(Use `ls -lrt` to find it.)

You can pass multiple `URL` arguments to include them in the same crawl,
whether they are on the same domain or different domains entirely.

warcprox users: [warcprox](https://github.com/internetarchive/warcprox) breaks the
dashboard's WebSocket; please make your browser skip the proxy for whichever
host/IP you're using to reach the dashboard.

### `grab-site` options, ordered by importance

Options can come before or after the URL.

*	`--1`: grab just `URL` and its page requisites, without recursing.

*	`--igsets=IGSET1,IGSET2`: use ignore sets `IGSET1` and `IGSET2`.

	Ignore sets are used to avoid requesting junk URLs using a pre-made set of
	regular expressions.  See [the full list of available ignore sets](https://github.com/ArchiveTeam/grab-site/tree/master/src/grab_site/ignore_sets).

	The [global](https://github.com/ArchiveTeam/grab-site/blob/master/src/grab_site/ignore_sets/global)
	ignore set is implied and enabled unless `--no-global-igset` is used.

	The ignore sets can be changed during the crawl by editing the `DIR/igsets` file.

*	`--no-global-igset`: don't add the [global](https://github.com/ArchiveTeam/grab-site/blob/master/src/grab_site/ignore_sets/global) ignore set.

*	`--no-offsite-links`: avoid following links to a depth of 1 on other domains.

	grab-site always grabs page requisites (e.g. inline images and stylesheets), even if
	they are on other domains.  By default, grab-site also grabs linked pages to a depth
	of 1 on other domains.  To turn off this behavior, use `--no-offsite-links`.

	Using `--no-offsite-links` may prevent all kinds of useful images, video, audio, downloads,
	etc from being grabbed, because these are often hosted on a CDN or subdomain, and
	thus would otherwise not be included in the recursive crawl.

*	`-i` / `--input-file`: Load list of URLs-to-grab from a local file or from a
	URL; like `wget -i`.  File must be a newline-delimited list of URLs.
	Combine with `--1` to avoid a recursive crawl on each URL.

*	`--igon`: Print all URLs being ignored to the terminal and dashboard.  Can be
	changed during the crawl by `touch`ing or `rm`ing the `DIR/igoff` file.
	This is slower because it needs to find the specific regexp to blame.

*	`--no-video`: Skip the download of videos by both mime type and file extension.
	Skipped videos are logged to `DIR/skipped_videos`.  Can be
	changed during the crawl by `touch`ing or `rm`ing the `DIR/video` file.

*	`--no-sitemaps`: don't queue URLs from `sitemap.xml` at the root of the site.

*	`--max-content-length=N`: Skip the download of any response that claims a
	Content-Length larger than `N`.  (default: -1, don't skip anything).
	Skipped URLs are logged to `DIR/skipped_max_content_length`.  Can be changed
	during the crawl by editing the `DIR/max_content_length` file.

*	`--no-dupespotter`: Disable dupespotter, a plugin that skips the extraction
	of links from pages that look like duplicates of earlier pages.  Disable this
	for sites that are directory listings, because they frequently trigger false
	positives.

*	`--concurrency=N`: Use `N` connections to fetch in parallel (default: 2).
	Can be changed during the crawl by editing the `DIR/concurrency` file.

*	`--delay=N`: Wait `N` milliseconds (default: 0) between requests on each concurrent fetcher.
	Can be a range like X-Y to use a random delay between X and Y.  Can be changed during
	the crawl by editing the `DIR/delay` file.

*	`--import-ignores`: Copy this file to to `DIR/ignores` before the crawl begins.

*	`--warc-max-size=BYTES`: Try to limit each WARC file to around `BYTES` bytes
	before rolling over to a new WARC file (default: 5368709120, which is 5GiB).
	Note that the resulting WARC files may be drastically larger if there are very
	large responses.

*	`--level=N`: recurse `N` levels instead of `inf` levels.

*	`--page-requisites-level=N`: recurse page requisites `N` levels instead of `5` levels.

*	`--ua=STRING`: Send User-Agent: `STRING` instead of pretending to be Firefox on Windows.

*	`--id=ID`: Use id `ID` for the crawl instead of a random 128-bit id. This must be unique for every crawl.

*	`--dir=DIR`: Put control files, temporary files, and unfinished WARCs in `DIR`
	(default: a directory name based on the URL, date, and first 8 characters of the id).

*	`--finished-warc-dir=FINISHED_WARC_DIR`: absolute path to a directory into
	which finished `.warc.gz` and `.cdx` files will be moved.

*	`--permanent-error-status-codes=STATUS_CODES`: A comma-separated list of
	HTTP status codes to treat as a permanent error and therefore **not** retry
	(default: `401,403,404,405,410`).  Other error responses tried another 2
	times for a total of 3 tries (customizable with `--wpull-args=--tries=N`).
	Note that, unlike wget, wpull puts retries at the end of the queue.

*	`--wpull-args=ARGS`: String containing additional arguments to pass to wpull;
	see `wpull --help`.  `ARGS` is split with `shlex.split` and individual
	arguments can contain spaces if quoted, e.g.
	`--wpull-args="--youtube-dl \"--youtube-dl-exe=/My Documents/youtube-dl\""`

	Examples:

	*	`--wpull-args=--no-skip-getaddrinfo` to respect `/etc/hosts` entries.
	*	`--wpull-args=--no-warc-compression` to write uncompressed WARC files.

*	`--which-wpull-args-partial`: Print a partial list of wpull arguments that
	would be used and exit.  Excludes grab-site-specific features, and removes
	`DIR/` from paths.  Useful for reporting bugs on wpull without grab-site involvement.

*	`--which-wpull-command`: Populate `DIR/` but don't start wpull; instead print
	the command that would have been used to start wpull with all of the
	grab-site functionality.

*	`--debug`: print a lot of debug information.

*	`--help`: print help text.

### Warnings

If you pay no attention to your crawls, a crawl may head down some infinite bot
trap and stay there forever.  The site owner may eventually notice high CPU use
or log activity, then IP-ban you.

grab-site does not respect `robots.txt` files, because they frequently
[whitelist only approved robots](https://github.com/robots.txt),
[hide pages embarrassing to the site owner](https://web.archive.org/web/20140401024610/http://www.thecrimson.com/robots.txt),
or block image or stylesheet resources needed for proper archival.
[See also](https://www.archiveteam.org/index.php?title=Robots.txt).
Because of this, very rarely you might run into a robot honeypot and receive
an abuse@ complaint.  Your host may require a prompt response to such a complaint
for your server to stay online.  Therefore, we recommend against crawling the
web from a server that hosts your critical infrastructure.

Don't run grab-site on GCE (Google Compute Engine); as happened to me, your
entire API project may get nuked after a few days of crawling the web, with
no recourse.  Good alternatives include OVH ([OVH](https://www.ovh.com/us/dedicated-servers/),
[So You Start](https://www.soyoustart.com/us/essential-servers/),
[Kimsufi](https://www.kimsufi.com/us/en/index.xml)), and online.net's
[dedicated](https://www.online.net/en/dedicated-server) and
[Scaleway](https://www.scaleway.com/) offerings.

### Tips for specific websites

#### Website requiring login / cookies

Log in to the website in Chrome or Firefox.  Use the cookies.txt extension
[for Chrome](https://github.com/daftano/cookies.txt) or
[for Firefox](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)
extension to copy Netscape-format cookies.  Paste the cookies data into a new
file.  Start grab-site with `--wpull-args=--load-cookies=ABSOLUTE_PATH_TO_COOKIES_FILE`.

#### Static websites; WordPress blogs; Discourse forums

The defaults usually work fine.

#### Blogger / blogspot.com blogs

The defaults work fine except for blogs with a JavaScript-only Dynamic Views theme.

Some blogspot.com blogs use "[Dynamic Views](https://support.google.com/blogger/answer/1229061?hl=en)"
themes that require JavaScript and serve absolutely no HTML content.  In rare
cases, you can get JavaScript-free pages by appending `?m=1`
([example](https://happinessbeyondthought.blogspot.com/?m=1)).  Otherwise, you
can archive parts of these blogs through Google Cache instead
([example](https://webcache.googleusercontent.com/search?q=cache:http://blog.datomic.com/))
or by using https://archive.is/ instead of grab-site.

#### Tumblr blogs

Either don't crawl from Europe (because tumblr redirects to a GDPR `/privacy/consent` page), or add `Googlebot` to the user agent:

```
--ua "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:64.0) Gecko/20100101 Firefox/70.0 but not really nor Googlebot/2.1"
```

Use [`--igsets=singletumblr`](https://github.com/ArchiveTeam/grab-site/blob/master/src/grab_site/ignore_sets/singletumblr)
to avoid crawling the homepages of other tumblr blogs.

If you don't care about who liked or reblogged a post, add `\?from_c=` to the
crawl's `ignores`.

Some tumblr blogs appear to require JavaScript, but they are actually just
hiding the page content with CSS.  You are still likely to get a complete crawl.
(See the links in the page source for https://X.tumblr.com/archive).

#### Subreddits

Use [`--igsets=reddit`](https://github.com/ArchiveTeam/grab-site/blob/master/src/grab_site/ignore_sets/reddit)
and add a `/` at the end of the URL to avoid crawling all subreddits.

When crawling a subreddit, you **must** get the casing of the subreddit right
for the recursive crawl to work.  For example,

```
grab-site https://www.reddit.com/r/Oculus/ --igsets=reddit
```

will crawl only a few pages instead of the entire subreddit.  The correct casing is:

```
grab-site https://www.reddit.com/r/oculus/ --igsets=reddit
```

You can hover over the "Hot"/"New"/... links at the top of the page to see the correct casing.

#### Directory listings ("Index of ...")

Use `--no-dupespotter` to avoid triggering false positives on the duplicate
page detector.  Without it, the crawl may miss large parts of the directory tree.

#### Very large websites

Use `--no-offsite-links` to stay on the main website and avoid crawling linked pages on other domains.

#### Websites that are likely to ban you for crawling fast

Use `--concurrency=1 --delay=500-1500`.

#### MediaWiki sites with English language

Use [`--igsets=mediawiki`](https://github.com/ArchiveTeam/grab-site/blob/master/src/grab_site/ignore_sets/mediawiki).
Note that this ignore set ignores old page revisions.

#### MediaWiki sites with non-English language

You will probably have to add ignores with translated `Special:*` URLs based on
[ignore_sets/mediawiki](https://github.com/ArchiveTeam/grab-site/blob/master/src/grab_site/ignore_sets/mediawiki).

#### Forums that aren't Discourse

Forums require more manual intervention with ignore patterns.
[`--igsets=forums`](https://github.com/ArchiveTeam/grab-site/blob/master/src/grab_site/ignore_sets/forums)
is often useful for non-SMF forums, but you will have to add other ignore
patterns, including one to ignore individual-forum-post pages if there are
too many posts to crawl.  (Generally, crawling the thread pages is enough.)

#### GitHub issues / pull requests

Find the highest issue number from an issues page ([example](https://github.com/rust-lang/rust/issues)) and use:

```
grab-site --1 https://github.com/rust-lang/rust/issues/{1..30000}
```

This relies on your shell to expand the argument to thousands of arguments.
If there are too many arguments, you may have to write the URLs to a file
and use `grab-site -i` instead:

```
for i in {1..30000}; do echo https://github.com/rust-lang/rust/issues/$i >> .urls; done
grab-site --1 -i .urls
```

#### Websites whose domains have just expired but are still up at the webhost

Use a [DNS history](https://www.google.com/search?q=historical+OR+history+dns)
service to find the old IP address (the DNS "A" record) for the domain.  Add a
line to your `/etc/hosts` to point the domain to the old IP.  Start a crawl
with `--wpull-args=--no-skip-getaddrinfo` to make wpull use `/etc/hosts`.

#### twitter.com/user

Use [snscrape](https://github.com/JustAnotherArchivist/snscrape) to get a list
of tweets for a user.  Redirect `snscrape`'s output to a list of URLs with
`> urls` and pass this file to `grab-site --1 -i urls`.

Alternatively, use [webrecorder.io](https://webrecorder.io/) instead of
grab-site.  It has an autoscroll feature and you can download the WARCs.

Keep in mind that scrolling `twitter.com/user` returns a maximum of 3200 tweets,
while a [from:user](https://twitter.com/search?q=from%3Ainternetarchive&src=typd&f=realtime&qf=off&lang=en)
query can return more.



Changing ignores during the crawl
---
While the crawl is running, you can edit `DIR/ignores` and `DIR/igsets`; the
changes will be applied within a few seconds.

`DIR/igsets` is a comma-separated list of ignore sets to use.

`DIR/ignores` is a newline-separated list of [Python 3 regular expressions](https://pythex.org/)
to use in addition to the ignore sets.

You can `rm DIR/igoff` to display all URLs that are being filtered out
by the ignores, and `touch DIR/igoff` to turn it back off.

Note that ignores will not apply to any of the crawl's start URLs.



Inspecting the URL queue
---
Inspecting the URL queue is usually not necessary, but may be helpful
for adding ignores before grab-site crawls a large number of junk URLs.

To dump the queue, run:

```
gs-dump-urls DIR/wpull.db todo
```

Four other statuses can be used besides `todo`:
`done`, `error`, `in_progress`, and `skipped`.

You may want to pipe the output to `sort` and `less`:

```
gs-dump-urls DIR/wpull.db todo | sort | less -S
```



Preventing a crawl from queuing any more URLs
---
`rm DIR/scrape`.  Responses will no longer be scraped for URLs.  Scraping cannot
be re-enabled for a crawl.



Stopping a crawl
---
You can `touch DIR/stop` or press ctrl-c, which will do the same.  You will
have to wait for the current downloads to finish.



Advanced `gs-server` options
---
These environmental variables control what `gs-server` listens on:

*	`GRAB_SITE_INTERFACE` (default `0.0.0.0`)
*	`GRAB_SITE_PORT` (default `29000`)

These environmental variables control which server each `grab-site` process connects to:

*	`GRAB_SITE_HOST` (default `127.0.0.1`)
*	`GRAB_SITE_PORT` (default `29000`)



Viewing the content in your WARC archives
---

Try [ReplayWeb.page](https://replayweb.page/) or [webrecorder-player](https://github.com/webrecorder/webrecorder-player).



Inspecting WARC files in the terminal
---
`zless` is a wrapper over `less` that can be used to view raw WARC content:

```
zless DIR/FILE.warc.gz
```

`zless -S` will turn off line wrapping.

Note that grab-site requests uncompressed HTTP responses to avoid
double-compression in .warc.gz files and to make zless output more useful.
However, some servers will send compressed responses anyway.



Automatically pausing grab-site processes when free disk is low
---

If you automatically upload and remove finished .warc.gz files, you can still
run into a situation where grab-site processes fill up your disk faster than
your uploader process can handle.  To prevent this situation, you can customize
and run [this script](https://github.com/ArchiveTeam/grab-site/blob/master/extra_docs/pause_resume_grab_sites.sh),
which will pause and resume grab-site processes as your free disk space
crosses a threshold value.



Thanks
---

grab-site is made possible only because of [wpull](https://github.com/chfoo/wpull),
written by [Christopher Foo](https://github.com/chfoo) who spent a year
making something much better than wget.  ArchiveTeam's most pressing
issue with wget at the time was that it kept the entire URL queue in memory
instead of on disk.  wpull has many other advantages over wget, including
better link extraction and Python hooks.

Thanks to [David Yip](https://github.com/yipdw), who created
[ArchiveBot](https://github.com/ArchiveTeam/ArchiveBot).  The wpull
hooks in ArchiveBot served as the basis for grab-site.  The original ArchiveBot
dashboard inspired the newer dashboard now used in both projects.

Thanks to [Falcon Darkstar Momot](https://github.com/falconkirtaran) for
the many wpull 2.x fixes that were rolled into
[ArchiveTeam/wpull](https://github.com/ArchiveTeam/wpull).

Thanks to [JustAnotherArchivist](https://github.com/JustAnotherArchivist)
for investigating my wpull issues.

Thanks to [BrowserStack](https://www.browserstack.com/) for providing free
browser testing for grab-site, which we use to make sure the dashboard works
in various browsers.

[<img src="https://user-images.githubusercontent.com/211271/29110431-887941d2-7cde-11e7-8c2f-199d85c5a3b5.png" height="30" alt="BrowserStack Logo">](https://www.browserstack.com/)



Help
---
grab-site bugs and questions are welcome in
[grab-site/issues](https://github.com/ArchiveTeam/grab-site/issues).

Terminal output in your bug report should be surrounded by triple backquotes, like this:

<pre>
```
very
long
output
```
</pre>

Please report security bugs as regular bugs.


[travis-image]: https://img.shields.io/travis/ArchiveTeam/grab-site.svg
[travis-url]: https://travis-ci.org/ArchiveTeam/grab-site
