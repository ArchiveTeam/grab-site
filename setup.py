#!/usr/bin/env python3

try:
	from setuptools import setup
except ImportError:
	from distutils.core import setup

import os
import sys
import libgrabsite

install_requires = [
	"click>=4.1",
	"wpull>=1.2.2",
	"manhole>=1.0.0",
	"lmdb>=0.86",
	"autobahn>=0.10.4",
	"trollius>=2"
]

# aiohttp 0.18.0 removed support for Python 3.4.0
# https://github.com/KeepSafe/aiohttp/issues/676
if sys.version_info[:3] < (3, 4, 1):
	install_requires.append("aiohttp>=0.16.6,<0.18.0")
else:
	install_requires.append("aiohttp>=0.16.6")

if 'GRAB_SITE_NO_CCHARDET' not in os.environ:
	install_requires.append("cchardet>=0.3.5")

setup(
	name="grab-site",
	version=libgrabsite.__version__,
	description="The archivist's web crawler: WARC output, dashboard for all crawls, dynamic ignore patterns",
	url="https://github.com/ludios/grab-site",
	author="Ivan Kozik",
	author_email="ivan@ludios.org",
	classifiers=[
		"Programming Language :: Python :: 3",
		"Development Status :: 3 - Alpha",
		"Intended Audience :: End Users/Desktop",
		"License :: OSI Approved :: MIT License",
		"Topic :: Internet :: WWW/HTTP",
	],
	scripts=["grab-site", "gs-server", "gs-dump-urls"],
	packages=["libgrabsite"],
	package_data={"libgrabsite": ["*.html", "*.txt", "ignore_sets/*"]},
	install_requires=install_requires
)
