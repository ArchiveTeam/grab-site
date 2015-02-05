On Ubuntu 14.04.1 or newer:

```
sudo apt-get install --no-install-recommends git build-essential python3-dev python3-pip
pip3 install --user wpull manhole lmdb
git clone https://github.com/ludios/grab-site
cd grab-site
```

Usage:

```
./grab-site URL
./grab-site URL --ignore-sets=blogs,forums
./grab-site URL --ignore-sets=blogs,forums --no-offsite-links
```

Note: `--ignore-sets=` must have the `=`.

Just as with ArchiveBot, the `global` ignore set is implied and enabled.

While the crawl is running, you can edit `DIR/ignores` and `DIR/ignore_sets`; the
changes will be applied as soon as the next URL is grabbed.

`DIR/ignore_sets` is a comma-separated list of ignore sets to use.
[See this list of available ignore sets](https://github.com/ArchiveTeam/ArchiveBot/tree/master/db/ignore_patterns).

`DIR/ignores` is a newline-separated list of [Python 3 regular expressions](http://pythex.org/)
to use in addition to the ignore sets.

You can `touch DIR/igoff` to stop `IGNOR` message spew, and `rm DIR/igoff`
to turn it back on again.

License:

This repo is almost entirely code from ArchiveBot, please see the ArchiveBot license.
