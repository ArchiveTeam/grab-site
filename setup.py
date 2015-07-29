#!/usr/bin/python3

try:
	from setuptools import setup
except ImportError:
	from distutils.core import setup

import libgrabsite

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
	package_data={"libgrabsite": ["*.html"]},
	install_requires=["click", "wpull", "cchardet", "manhole", "lmdb", "autobahn", "aiohttp", "trollius"],
)
