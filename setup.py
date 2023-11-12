#!/usr/bin/env python3

try:
	from setuptools import setup
except ImportError:
	from distutils.core import setup

import os
import sys
import libgrabsite

install_requires = [
	"click>=6.3",
	"wpull @ https://github.com/locriacyber/wpull/tarball/master#egg=wpull",
	"manhole>=1.0.0",
	"lmdb>=0.89",
	"autobahn>=0.12.1",
	"fb-re2>=1.0.6",
	"websockets>=6.0",
]

if 'GRAB_SITE_NO_CCHARDET' not in os.environ:
	install_requires.append("cchardet>=1.0.0")

setup(
	name="grab-site",
	version=libgrabsite.__version__,
	description="The archivist's web crawler: WARC output, dashboard for all crawls, dynamic ignore patterns",
	url="https://ludios.org/grab-site/",
	author="Ivan Kozik",
	author_email="ivan@ludios.org",
	classifiers=[
		"Programming Language :: Python :: 3",
		"Development Status :: 5 - Production/Stable",
		"Intended Audience :: End Users/Desktop",
		"License :: OSI Approved :: MIT License",
		"Topic :: Internet :: WWW/HTTP",
	],
	scripts=["grab-site", "gs-server", "gs-dump-urls"],
	packages=["libgrabsite"],
	package_data={"libgrabsite": ["*.html", "*.ico", "*.txt", "ignore_sets/*"]},
	install_requires=install_requires,
)
