import os
import hashlib
import functools

from wpull.database.sqltable import SQLiteURLTable
from wpull.document.html import HTMLReader
from wpull.processor.rule import ProcessingRule

from grab_site import dupespotter, __version__
from grab_site.dupes import DupesOnDisk


def response_body_size(response) -> int:
	try:
		return response.body.size()
	except Exception:
		return 0

class NoFsyncSQLTable(SQLiteURLTable):
	@classmethod
	def _apply_pragmas_callback(cls, connection, record):
		super()._apply_pragmas_callback(connection, record)
		connection.execute('PRAGMA synchronous=OFF')


class DupeSpottingProcessingRule(ProcessingRule):
	def __init__(self, *args, **kwargs):
		self.dupes_db = kwargs.pop('dupes_db', None)
		super().__init__(*args, **kwargs)

	def scrape_document(self, item_session):
		response = item_session.response
		url_info = item_session.request.url_info
		url      = url_info.raw

		if response_body_size(response) < 30 * 1024 * 1024:
			dupes_db = self.dupes_db
			body     = response.body.content()
			if HTMLReader.is_response(response):
				body = dupespotter.process_body(body, url)
			digest = hashlib.md5(body).digest()
			if dupes_db is not None:
				dupe_of = dupes_db.get_old_url(digest)
			else:
				dupe_of = None
			if dupe_of is not None:
				# Don't extract links from pages we've already seen
				# to avoid loops that descend a directory endlessly
				print("DUPE {}\n  OF {}".format(url, dupe_of))
				return
			else:
				if dupes_db is not None:
					dupes_db.set_old_url(digest, url)

		super().scrape_document(item_session)


def activate(app_session):
	app_session.factory.class_map['URLTableImplementation'] = NoFsyncSQLTable

	warc_recorder_cls = app_session.factory.class_map['WARCRecorder']
	warc_recorder_cls.DEFAULT_SOFTWARE_STRING = f'grab-site/{__version__} ' + warc_recorder_cls.DEFAULT_SOFTWARE_STRING

	if int(os.environ["DUPESPOTTER_ENABLED"]):
		dupes_db_location = os.path.join(os.environ["GRAB_SITE_WORKING_DIR"], "dupes_db")
		dupes_db = DupesOnDisk(dupes_db_location)
		app_session.factory.class_map['ProcessingRule'] = \
			functools.partial(DupeSpottingProcessingRule, dupes_db=dupes_db)
