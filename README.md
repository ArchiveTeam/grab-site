On Ubuntu 14.04.1 or newer:

```
sudo apt-get install --no-install-recommends build-essential python3-dev python3-pip
pip3 install --user wpull manhole lmdb
git clone https://github.com/ludios/grab-site
cd grab-site
```

Usage:

```
./grab-site URL
./grab-site URL --ignore-sets blogs,forums
./grab-site URL --ignore-sets blogs,forums --no-offsite-links
```

Note: `--ignore-sets=` with `=` will **not** work.

While the crawl is running, you can edit `DIR/ignores` and `DIR/ignore_sets`; the
changes will be applied as soon as the next URL is grabbed.

You can also `touch DIR/igoff` to stop `IGNOR` message spew, and `rm DIR/igoff`
to turn it back on again.

License:

This repo is almost entirely code from ArchiveBot, please see the ArchiveBot license.
