import argparse
import functools
import hashlib

from wpull.database.sqltable import SQLiteURLTable
from wpull.document.html import HTMLReader
import wpull.processor.rule

from libgrabsite import dupespotter
from libgrabsite.dupes import DupesInMemory, DupesOnDisk



class NoFsyncSQLTable(SQLiteURLTable):
	@classmethod
	def _apply_pragmas_callback(cls, connection, record):
		super()._apply_pragmas_callback(connection, record)
		connection.execute('PRAGMA synchronous=OFF')


class DupeSpottingProcessingRule(wpull.processor.rule.ProcessingRule):
	def __init__(self, *args, **kwargs):
		self.dupes_db = kwargs.pop('dupes_db', None)
		super().__init__(*args, **kwargs)

	def scrape_document(self, request, response, url_item):
		if response.body.size() < 30*1024*1024:
			dupes_db = self.dupes_db
			body = response.body.content()
			if HTMLReader.is_response(response):
				body = dupespotter.process_body(body, response.request.url)
			digest = hashlib.md5(body).digest()
			if dupes_db is not None:
				dupe_of = dupes_db.get_old_url(digest)
			else:
				dupe_of = None
			if dupe_of is not None:
				# Don't extract links from pages we've already seen
				# to avoid loops that descend a directory endlessly
				print("  DUPE {}\n      OF {}".format(response.request.url, dupe_of))
				return
			else:
				if dupes_db is not None:
					dupes_db.set_old_url(digest, response.request.url)

		super().scrape_document(request, response, url_item)


arg_parser = argparse.ArgumentParser()
arg_parser.add_argument(
	'--dupes-db',
	metavar='DIR',
	default=':memory:',
	help='save dupes db into DIR instead of memory',
)
args = arg_parser.parse_args(wpull_plugin.plugin_args.split())

if args.dupes_db == ':memory:':
	dupes_db = DupesInMemory()
else:
	dupes_db = DupesOnDisk(args.dupes_db)

wpull_plugin.factory.class_map['URLTableImplementation'] = NoFsyncSQLTable
wpull_plugin.factory.class_map['ProcessingRule'] = functools.partial(
	DupeSpottingProcessingRule, dupes_db=dupes_db
)
