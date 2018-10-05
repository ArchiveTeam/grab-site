import re
import os
import sys
import json
import time
import signal
import random
import hashlib
import functools
import traceback
import asyncio

from libgrabsite.ignoracle import Ignoracle, parameterize_record_info
import libgrabsite

from wpull.application.hook import Actions
from wpull.application.plugin import WpullPlugin, PluginFunctions, hook, event
from wpull.database.sqltable import SQLiteURLTable
from wpull.document.html import HTMLReader
from wpull.protocol.http.request import Response as HTTPResponse
import wpull.processor.rule

from libgrabsite import dupespotter
from libgrabsite.dupes import DupesOnDisk


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
		if response.body.size() < 30 * 1024 * 1024:
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
				print("DUPE {}\n  OF {}".format(response.request.url, dupe_of))
				return
			else:
				if dupes_db is not None:
					dupes_db.set_old_url(digest, response.request.url)

		super().scrape_document(request, response, url_item)


wpull_plugin.factory.class_map['URLTableImplementation'] = NoFsyncSQLTable
if int(os.environ["DUPESPOTTER_ENABLED"]):
	wpull_plugin.factory.class_map['ProcessingRule'] = functools.partial(
		DupeSpottingProcessingRule,
		dupes_db=DupesOnDisk(
			os.path.join(os.environ["GRAB_SITE_WORKING_DIR"], "dupes_db"))
	)


real_stdout_write = sys.stdout.buffer.write
real_stderr_write = sys.stderr.buffer.write

def print_to_terminal(s):
	real_stdout_write((s + "\n").encode("utf-8"))
	sys.stdout.buffer.flush()


class Decayer(object):
	def __init__(self, initial, multiplier, maximum):
		"""
		initial - initial number to return
		multiplier - multiply number by this value after each call to decay()
		maximum - cap number at this value
		"""
		self.initial = initial
		self.multiplier = multiplier
		self.maximum = maximum
		self.reset()

	def reset(self):
		# First call to .decay() will multiply, but we want to get the `intitial`
		# value on the first call to .decay(), so divide.
		self.current = self.initial / self.multiplier
		return self.current

	def decay(self):
		self.current = min(self.current * self.multiplier, self.maximum)
		return self.current


class GrabberClientFactory(WebSocketClientFactory):
	#protocol = GrabberClientProtocol

	def __init__(self):
		super().__init__()
		self.client = None


ws_factory = GrabberClientFactory()


def graceful_stop_callback():
	print_to_terminal("\n^C detected, creating 'stop' file, please wait for exit...")
	with open(os.path.join(working_dir, "stop"), "wb") as f:
		pass


loop = asyncio.get_event_loop()

def forceful_stop_callback():
	loop.stop()


try:
	loop.add_signal_handler(signal.SIGINT, graceful_stop_callback)
	loop.add_signal_handler(signal.SIGTERM, forceful_stop_callback)
except NotImplementedError:
	# Not supported on Windows
	pass


ignore_sets_path = os.path.join(os.path.dirname(libgrabsite.__file__), "ignore_sets")

def get_patterns_for_ignore_set(name):
	assert name != "", name
	with open(os.path.join(ignore_sets_path, name), "r", encoding="utf-8") as f:
		lines = f.read().strip("\n").split("\n")
		lines = filter(lambda line: line and not line.startswith("# "), lines)
		return lines

working_dir = os.environ['GRAB_SITE_WORKING_DIR']


# Don't swallow during startup
really_swallow_exceptions = False

def swallow_exception(f):
	@functools.wraps(f)
	def wrapper(*args, **kwargs):
		global really_swallow_exceptions
		try:
			return f(*args, **kwargs)
		except Exception:
			if not really_swallow_exceptions:
				raise
			traceback.print_exc()
	return wrapper


CONTROL_FILE_CACHE_SEC = 1.5

def caching_decorator(f):
	cache = {}
	@functools.wraps(f)
	def wrapper(path):
		timestamp, val = cache.get(path, (-CONTROL_FILE_CACHE_SEC, None))
		if timestamp > (time.monotonic() - CONTROL_FILE_CACHE_SEC):
			#print("returning cached value {} {}".format(path, val))
			return val
		val = f(path)
		cache[path] = (time.monotonic(), val)
		#print("returning new value {} {}".format(path, val))
		return val
	return wrapper


@caching_decorator
def path_exists_with_cache(path):
	return os.path.exists(path)


@caching_decorator
def mtime_with_cache(path):
	return os.stat(path).st_mtime


class FileChangedWatcher(object):
	def __init__(self, fname):
		self.fname = fname
		# Use a bogus mtime so that has_changed() returns True
		# at least once
		self.last_mtime = -1

	def has_changed(self):
		now_mtime = mtime_with_cache(self.fname)
		changed = now_mtime != self.last_mtime
		self.last_mtime = now_mtime
		if changed:
			print("Imported %s" % self.fname)
		return changed


igsets_watcher = FileChangedWatcher(os.path.join(working_dir, "igsets"))
ignores_watcher = FileChangedWatcher(os.path.join(working_dir, "ignores"))
delay_watcher = FileChangedWatcher(os.path.join(working_dir, "delay"))
concurrency_watcher = FileChangedWatcher(os.path.join(working_dir, "concurrency"))
max_content_length_watcher = FileChangedWatcher(os.path.join(working_dir, "max_content_length"))

ignoracle = Ignoracle()

@swallow_exception
def update_ignoracle():
	if not (igsets_watcher.has_changed() or ignores_watcher.has_changed()):
		return

	with open(os.path.join(working_dir, "igsets"), "r") as f:
		igsets = f.read().strip("\r\n\t ,").split(',')

	with open(os.path.join(working_dir, "ignores"), "r") as f:
		ignores = set(ig for ig in f.read().strip("\r\n").split('\n') if ig != "")

	for igset in igsets:
		patterns = get_patterns_for_ignore_set(igset)
		ignores.update(patterns)

	print_to_terminal("Using these %d ignores:" % len(ignores))
	for ig in sorted(ignores):
		print_to_terminal("\t" + ig)

	ignoracle.set_patterns(ignores)

update_ignoracle()


def should_ignore_url(url, record_info):
	"""
	Returns whether a URL should be ignored.
	"""
	parameters = parameterize_record_info(record_info)
	return ignoracle.ignores(url, **parameters)


all_start_urls = open(os.path.join(working_dir, "all_start_urls")).read().rstrip("\n").split("\n")

def accept_url(url_info, record_info, verdict, reasons):
	update_ignoracle()

	url = url_info.raw

	if url.startswith('data:'):
		# data: URLs aren't something you can grab, so drop them to avoid ignore
		# checking and ignore logging.
		return False

	# Don't apply ignores to any of the start URLs
	if url in all_start_urls:
		return True

	pattern = should_ignore_url(url, record_info)
	if pattern:
		maybe_log_ignore(url, pattern)
		return False

	# If we get here, none of our ignores apply.	Return the original verdict.
	return verdict


job_data = {
	"ident": open(os.path.join(working_dir, "id")).read().strip(),
	"url": open(os.path.join(working_dir, "start_url")).read().strip(),
	"started_at": os.stat(os.path.join(working_dir, "start_url")).st_mtime,
	"max_content_length": -1,
	"suppress_ignore_reports": True,
	"video": True,
	"scrape": True,
	"concurrency": 2,
	"bytes_downloaded": 0,
	"items_queued": 0,
	"items_downloaded": 0,
	"delay_min": 0,
	"delay_max": 0,
	"r1xx": 0,
	"r2xx": 0,
	"r3xx": 0,
	"r4xx": 0,
	"r5xx": 0,
	"runk": 0,
}


def handle_result(url_info, record_info, error_info, response):
	update_igoff()

	response_code = response.status_code
	response_code_str = str(response_code)
	if len(response_code_str) == 3 and response_code_str[0] in "12345":
		job_data["r%sxx" % response_code_str[0]] += 1
	else:
		job_data["runk"] += 1

	job_data["bytes_downloaded"] += response.body.size

	stop = should_stop()

	response_message = response.status_reason
	if error_info:
		response_code = 0
		response_message = str(error_info)

	if ws_factory.client:
		ws_factory.client.send_object({
			"type": "download",
			"job_data": job_data,
			"url": url_info.raw,
			"response_code": response_code,
			"response_message": response_message,
		})

	if stop:
		return Actions.STOP

	return Actions.NORMAL


stop_path = os.path.join(working_dir, "stop")

def should_stop():
	return path_exists_with_cache(stop_path)


igoff_path = os.path.join(working_dir, "igoff")

def update_igoff():
	job_data["suppress_ignore_reports"] = path_exists_with_cache(igoff_path)

update_igoff()


video_path = os.path.join(working_dir, "video")

def update_video():
	job_data["video"] = path_exists_with_cache(video_path)

update_video()


scrape_path = os.path.join(working_dir, "scrape")

def update_scrape():
	scrape = path_exists_with_cache(scrape_path)
	job_data["scrape"] = scrape
	if not scrape:
		# Empty the list of scrapers, which will stop scraping for new URLs
		# but still keep going through what is already in the queue.
		wpull_hook.factory.get('DemuxDocumentScraper')._document_scrapers = []

update_scrape()


def maybe_log_ignore(url, pattern):
	update_igoff()
	if not job_data["suppress_ignore_reports"]:
		print_to_terminal("IGNOR %s\n   by %s" % (url, pattern))
		if ws_factory.client:
			ws_factory.client.send_object({
				"type": "ignore",
				"job_data": job_data,
				"url": url,
				"pattern": pattern
			})


ICY_FIELD_PATTERN = re.compile('icy-|ice-|x-audiocast-', re.IGNORECASE)
ICY_VALUE_PATTERN = re.compile('icecast', re.IGNORECASE)

def get_content_length(response):
	try:
		return int(list(p for p in response.fields.get_all() if p[0] == "Content-Length")[0][1])
	except (IndexError, ValueError):
		return -1


def has_content_type_video(response):
	try:
		t = list(p for p in response.fields.get_all() if p[0] == "Content-Type")[0][1]
		return t.lower().startswith("video/")
	except (IndexError, ValueError):
		return False


# Excluded vob, mpeg, mpg, avi because they are not found on the general web
video_exts = set("webm mp4 m4v mkv ts 3gp 3g2 flv mov wmv ogv ogm".split(" "))

def has_video_ext(url):
	ext = url.rsplit('.')[-1]
	return ext.lower() in video_exts


skipped_videos_path = os.path.join(working_dir, "skipped_videos")
skipped_videos = open(skipped_videos_path, "w", encoding="utf-8")

skipped_max_content_length_path = os.path.join(working_dir, "skipped_max_content_length")
skipped_max_content_length = open(skipped_max_content_length_path, "w", encoding="utf-8")

def handle_pre_response(url_info, response):
	url = url_info.raw

	update_scrape()

	update_max_content_length()
	if job_data["max_content_length"] != -1:
		length = get_content_length(response)
		if length > job_data["max_content_length"]:
			skipped_max_content_length.write(url + "\n")
			skipped_max_content_length.flush()
			maybe_log_ignore(url, '[content-length %d over limit %d]' % (
				length, job_data["max_content_length"]))
			return Actions.FINISH

	update_video()
	if not job_data["video"]:
		if has_content_type_video(response) or has_video_ext(url):
			skipped_videos.write(url + "\n")
			skipped_videos.flush()
			maybe_log_ignore(url, '[video]')
			return Actions.FINISH

	# Check if server version starts with ICY
	if response.version == 'ICY':
		maybe_log_ignore(url, '[icy version]')
		return Actions.FINISH

	# Loop through all the server headers for matches
	for field, value in response.fields.get_all():
		if ICY_FIELD_PATTERN.match(field):
			maybe_log_ignore(url, '[icy field]')
			return Actions.FINISH

		if field == 'Server' and ICY_VALUE_PATTERN.match(value):
			maybe_log_ignore(url, '[icy server]')
			return Actions.FINISH

	# Nothing matched, allow download
	print_to_terminal(url + " ...")
	return Actions.NORMAL


def stdout_write_both(message):
	assert isinstance(message, bytes), message
	try:
		real_stdout_write(message)
		if ws_factory.client:
			ws_factory.client.send_object({
				"type": "stdout",
				"job_data": job_data,
				"message": message.decode("utf-8")
			})
	except Exception as e:
		real_stderr_write((str(e) + "\n").encode("utf-8"))


def stderr_write_both(message):
	assert isinstance(message, bytes), message
	try:
		real_stderr_write(message)
		if ws_factory.client:
			ws_factory.client.send_object({
				"type": "stderr",
				"job_data": job_data,
				"message": message.decode("utf-8")
			})
	except Exception as e:
		real_stderr_write((str(e) + "\n").encode("utf-8"))

sys.stdout.buffer.write = stdout_write_both
sys.stderr.buffer.write = stderr_write_both


@swallow_exception
def update_max_content_length():
	if not max_content_length_watcher.has_changed():
		return
	with open(max_content_length_watcher.fname, "r") as f:
		job_data["max_content_length"] = int(f.read().strip())

update_max_content_length()


@swallow_exception
def update_delay():
	if not delay_watcher.has_changed():
		return
	with open(delay_watcher.fname, "r") as f:
		content = f.read().strip()
		if "-" in content:
			job_data["delay_min"], job_data["delay_max"] = list(int(s) for s in content.split("-", 1))
		else:
			job_data["delay_min"] = job_data["delay_max"] = int(content)

update_delay()


@swallow_exception
def update_concurrency():
	if not concurrency_watcher.has_changed():
		return
	with open(concurrency_watcher.fname, "r") as f:
		concurrency = int(f.read().strip())
		if concurrency < 1:
			print("Warning: using 1 for concurrency instead of %r because it cannot be < 1" % (concurrency,))
			concurrency = 1
		job_data["concurrency"] = concurrency
	wpull_hook.factory.get('Engine').set_concurrent(concurrency)

update_concurrency()


def get_urls(url_info):
	url = url_info.raw
	extra_urls = None
	# If we see this URL, also queue the URL for the :orig quality image
	if url.startswith("https://pbs.twimg.com/media/"):
		new_url = re.sub(":[a-z]{1,10}$", "", url) + ":orig"
		# see wpull/item.py:LinkType
		extra_urls = [dict(url=new_url, link_type="media", inline=True)]
	# Quora shows login-required screen unless you add ?share=1
	elif url.startswith("https://www.quora.com/") and not "?" in url:
		new_url = url + "?share=1"
		extra_urls = [dict(url=new_url, link_type="html")]
	return extra_urls


class GrabSitePlugin(WpullPlugin):
	@hook(PluginFunctions.accept_url)
	def accept_url(self, item_session: ItemSession, verdict: bool, reasons: dict):
        url_info = item_session.request.url_info
        record_info = item_session.url_record
		return accept_url(url_info, record_info, verdict, reasons)

    @event(PluginFunctions.queued_url)
    def queued_url(self, _url_info: URLInfo):
		job_data["items_queued"] += 1

    @event(PluginFunctions.dequeued_url)
    def dequeued_url(self, _url_info: URLInfo, _record_info: URLRecord):
    	job_data["items_downloaded"] += 1

	@hook(PluginFunctions.handle_response)
	def handle_response(self, item_session: ItemSession):
		url_info = item_session.request.url_info
		record_info = item_session.url_record
		response = item_session.response
		error_info = None
		return handle_result(url_info, record_info, error_info, response)

	@hook(PluginFunctions.handle_error)
	def handle_error(self, item_session: ItemSession, error_info: BaseException):
		url_info = item_session.request.url_info
		record_info = item_session.url_record
		response = item_session.response
		return handle_result(url_info, record_info, error_info, response)

	@hook(PluginFunctions.handle_pre_response)
	def handle_pre_response(self, item_session: ItemSession):
		url_info = item_session.request.url_info
		response = item_session.response
		return handle_pre_response(url_info, response)

	@hook(PluginFunctions.exit_status)
    def exit_status(self, _app_session: AppSession, _exit_code: int):
		print()
		print(f"Finished grab {job_data["ident"]} {job_data["url"]} with exit code {code}")
		print(f"Output is in directory:\n{working_dir}")
		return code

    @hook(PluginFunctions.wait_time)
    def wait_time(self, _seconds: float, _item_session: ItemSession, _error):
		update_delay()
		update_concurrency()
		return random.uniform(job_data["delay_min"], job_data["delay_max"]) / 1000

    @event(PluginFunctions.get_urls)
    def get_urls(self, item_session: ItemSession):
    	url_info = item_session.request.url_info
    	return get_urls(url_info)

really_swallow_exceptions = True
