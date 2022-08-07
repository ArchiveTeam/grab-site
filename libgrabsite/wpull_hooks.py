import re
import re2
import os
import sys
import time
import signal
import random
import functools
import traceback
import asyncio
import urllib.parse

from wpull.application.hook import Actions
from wpull.application.plugin import WpullPlugin, PluginFunctions, hook, event
from wpull.pipeline.app import AppSession
from wpull.pipeline.item import URLRecord
from wpull.pipeline.session import ItemSession
from wpull.url import URLInfo

from libgrabsite import wpull_tweaks, dashboard_client
import libgrabsite


working_dir = os.environ["GRAB_SITE_WORKING_DIR"]
def cf(fname):
	return os.path.join(working_dir, fname)

def re_compile(regexp):
	# Validate with re first, because re2 may be more prone to segfaulting on
	# bad regexps, and because re returns useful errors.
	re.compile(regexp)
	try:
		return re2.compile(regexp)
	except re.error:
		# Regular expressions with lookaround expressions cannot be compiled with
		# re2, so on error try compiling with re.
		return re.compile(regexp)

def compile_combined_regexp(patterns):
	regexp = "|".join(map(lambda pattern: f"({pattern})", patterns))
	return re_compile(regexp)

def include_ignore_line(line):
	return line and not line.startswith("#")

ignore_sets_path = os.path.join(os.path.dirname(libgrabsite.__file__), "ignore_sets")
def get_patterns_for_ignore_set(name: str):
	assert name != "", name
	with open(os.path.join(ignore_sets_path, name), "r", encoding="utf-8") as f:
		return f.read().strip("\n").split("\n")

def swallow_exception(f):
	@functools.wraps(f)
	def wrapper(*args, **kwargs):
		try:
			return f(*args, **kwargs)
		except Exception:
			traceback.print_exc()
	return wrapper

CONTROL_FILE_CACHE_SEC = 1.5

def caching_decorator(f):
	cache = {}
	@functools.wraps(f)
	def wrapper(path):
		timestamp, val = cache.get(path, (-CONTROL_FILE_CACHE_SEC, None))
		if timestamp > (time.monotonic() - CONTROL_FILE_CACHE_SEC):
			#print(f"returning cached value {path} {val}")
			return val
		val = f(path)
		cache[path] = (time.monotonic(), val)
		#print(f"returning new value {path} {val}")
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
		now_mtime       = mtime_with_cache(self.fname)
		changed         = now_mtime != self.last_mtime
		self.last_mtime = now_mtime
		if changed:
			print(f"Imported {self.fname}")
		return changed


ICY_FIELD_PATTERN = re2.compile("(?i)^icy-|ice-|x-audiocast-")
ICY_VALUE_PATTERN = re2.compile("(?i)^icecast")

def get_content_length(response) -> int:
	try:
		return int(list(p for p in response.fields.get_all() if p[0] == "Content-Length")[0][1])
	except (IndexError, ValueError):
		return -1

def has_content_type_video(response) -> bool:
	try:
		t = list(p for p in response.fields.get_all() if p[0] == "Content-Type")[0][1]
		return t.lower().startswith("video/")
	except (IndexError, ValueError):
		return False

def response_status_code(response) -> int:
	statcode = 0

	try:
		# duck typing: assume the response is
		# wpull.protocol.http.request.Response
		statcode = response.status_code
	except (AttributeError, KeyError):
		pass

	try:
		# duck typing: assume the response is
		# wpull.protocol.ftp.request.Response
		statcode = response.reply.code
	except (AttributeError, KeyError):
		pass

	return statcode

# Excluded vob, mpeg, mpg, avi because they are not found on the general web
video_exts = set("webm mp4 m4v mkv ts 3gp 3g2 flv mov wmv ogv ogm".split(" "))

def has_video_ext(url: str) -> bool:
	ext = url.rsplit(".")[-1]
	return ext.lower() in video_exts

class GrabSitePlugin(WpullPlugin):
	def activate(self):
		wpull_tweaks.activate(self.app_session)
		self.loop = asyncio.get_event_loop()
		self.enable_stdio_capture()
		self.add_signal_handlers()
		self.init_job_data()
		self.init_ws()
		self.setup_watchers()
		self.all_start_urls             = open(cf("all_start_urls")).read().rstrip("\n").split("\n")
		self.all_start_netlocs          = set(urllib.parse.urlparse(url).netloc for url in self.all_start_urls)
		self.skipped_videos             = open(cf("skipped_videos"),             "w", encoding="utf-8")
		self.skipped_max_content_length = open(cf("skipped_max_content_length"), "w", encoding="utf-8")
		self.update_ignores()
		super().activate()

	def enable_stdio_capture(self):
		self.real_stdout_write  = sys.stdout.buffer.write
		self.real_stderr_write  = sys.stderr.buffer.write
		sys.stdout.buffer.write = self.stdout_write_both
		sys.stderr.buffer.write = self.stderr_write_both

	def print_to_terminal(self, s):
		self.real_stdout_write((s + "\n").encode("utf-8"))
		sys.stdout.buffer.flush()

	def graceful_stop_callback(self):
		self.print_to_terminal("\n^C detected, creating 'stop' file, please wait for exit...")
		with open(cf("stop"), "wb") as _f:
			pass

	def forceful_stop_callback(self):
		self.loop.stop()

	def add_signal_handlers(self):
		try:
			self.loop.add_signal_handler(signal.SIGINT,  self.graceful_stop_callback)
			self.loop.add_signal_handler(signal.SIGTERM, self.forceful_stop_callback)
		except NotImplementedError:
			# Not supported on Windows
			pass

	def setup_watchers(self):
		self.watchers = {}
		for f in ["igsets", "ignores", "delay", "concurrency", "max_content_length"]:
			self.watchers[f] = FileChangedWatcher(cf(f))

	def put_ws_queue(self, obj):
		try:
			self.ws_queue.put_nowait(obj)
		except asyncio.QueueFull:
			pass

	def stdout_write_both(self, message):
		assert isinstance(message, bytes), message
		try:
			self.real_stdout_write(message)
			self.put_ws_queue({
				"type":     "stdout",
				"job_data": self.job_data,
				"message":  message.decode("utf-8")
			})
		except Exception as e:
			self.real_stderr_write((str(e) + "\n").encode("utf-8"))

	def stderr_write_both(self, message):
		assert isinstance(message, bytes), message
		try:
			self.real_stderr_write(message)
			self.put_ws_queue({
				"type":     "stderr",
				"job_data": self.job_data,
				"message":  message.decode("utf-8")
			})
		except Exception as e:
			self.real_stderr_write((str(e) + "\n").encode("utf-8"))

	def init_job_data(self):
		self.job_data = {
			"ident":                   open(cf("id")).read().strip(),
			"url":                     open(cf("start_url")).read().strip(),
			"started_at":              os.stat(cf("start_url")).st_mtime,
			"max_content_length":      -1,
			"suppress_ignore_reports": True,
			"video":                   True,
			"scrape":                  True,
			"concurrency":             2,
			"bytes_downloaded":        0,
			"items_queued":            0,
			"items_downloaded":        0,
			"delay_min":               0,
			"delay_max":               0,
			"r1xx":                    0,
			"r2xx":                    0,
			"r3xx":                    0,
			"r4xx":                    0,
			"r5xx":                    0,
			"runk":                    0,
		}

	def init_ws(self):
		self.ws_queue = asyncio.Queue(maxsize=250)

		ws_host = os.environ.get("GRAB_SITE_HOST", "127.0.0.1")
		ws_port = int(os.environ.get("GRAB_SITE_PORT", 29000))
		ws_url  = f"ws://{ws_host}:{ws_port}"

		self.loop.create_task(dashboard_client.sender(self, ws_url))

	@swallow_exception
	def update_max_content_length(self):
		if not self.watchers["max_content_length"].has_changed():
			return
		with open(self.watchers["max_content_length"].fname, "r") as f:
			self.job_data["max_content_length"] = int(f.read().strip())

	@swallow_exception
	def update_delay(self):
		if not self.watchers["delay"].has_changed():
			return
		with open(self.watchers["delay"].fname, "r") as f:
			content = f.read().strip()
			if "-" in content:
				self.job_data["delay_min"], self.job_data["delay_max"] = list(int(s) for s in content.split("-", 1))
			else:
				self.job_data["delay_min"] = self.job_data["delay_max"] = int(content)

	@swallow_exception
	def update_concurrency(self):
		if not self.watchers["concurrency"].has_changed():
			return
		with open(self.watchers["concurrency"].fname, "r") as f:
			concurrency = int(f.read().strip())
			if concurrency < 1:
				print(f"Warning: using 1 for concurrency instead of {concurrency} because it cannot be < 1")
				concurrency = 1
			self.job_data["concurrency"] = concurrency
		self.app_session.factory["PipelineSeries"].concurrency = concurrency

	stop_path = cf("stop")
	def should_stop(self):
		return path_exists_with_cache(self.stop_path)

	def should_ignore_url(self, url, record_info):
		return self.combined_ignore_regexp.search(url)

	igoff_path = cf("igoff")
	def update_igoff(self):
		self.job_data["suppress_ignore_reports"] = path_exists_with_cache(self.igoff_path)

	video_path = cf("video")
	def update_video(self):
		self.job_data["video"] = path_exists_with_cache(self.video_path)

	scrape_path = cf("scrape")
	@swallow_exception
	def update_scrape(self):
		scrape = path_exists_with_cache(self.scrape_path)
		self.job_data["scrape"] = scrape
		if not scrape:
			# Empty the list of scrapers, which will stop scraping for new URLs
			# but still keep going through what is already in the queue.
			self.app_session.factory["DemuxDocumentScraper"]._document_scrapers = []

	@swallow_exception
	def update_ignores(self):
		if not (self.watchers["igsets"].has_changed() or self.watchers["ignores"].has_changed()):
			return

		ignores = set()

		with open(cf("igsets"), "r") as f:
			igsets = f.read().strip("\r\n\t ,").split(',')
			if igsets == [""]:
				igsets = []

		for igset in igsets:
			for pattern in get_patterns_for_ignore_set(igset):
				if include_ignore_line(pattern):
					ignores.update(self.ignore_pattern_to_regexp_strings(pattern))

		with open(cf("ignores"), "r") as f:
			lines = f.read().strip("\n").split("\n")
			for pattern in lines:
				if include_ignore_line(pattern):
					ignores.update(self.ignore_pattern_to_regexp_strings(pattern))

		self.print_to_terminal(f"Using these {len(ignores)} ignores:")
		for ig in sorted(ignores):
			self.print_to_terminal(f"\t{ig}")

		self.compiled_ignores       = [(ig, re_compile(ig)) for ig in ignores]
		self.combined_ignore_regexp = compile_combined_regexp(ignores)

	def ignore_pattern_to_regexp_strings(self, pattern):
		if "{any_start_netloc}" not in pattern:
			return [pattern]

		return [pattern.replace("{any_start_netloc}", re.escape(netloc)) for netloc in self.all_start_netlocs]

	def get_specific_ignore_pattern(self, url):
		for pattern, regexp in self.compiled_ignores:
			if regexp.search(url):
				# We can't use regexp.pattern because that quickly causes segfaults
				return pattern

	@hook(PluginFunctions.accept_url)
	def accept_url(self, item_session: ItemSession, verdict: bool, reasons: dict):
		record_info = item_session.url_record
		url_info    = item_session.request.url_info
		url         = url_info.raw

		self.update_ignores()

		if url.startswith("data:"):
			# data: URLs aren't something you can grab, so drop them to avoid ignore
			# checking and ignore logging.
			return False

		# Don't apply ignores to any of the start URLs
		if url in self.all_start_urls:
			# Return original verdict instead of True to avoid infinite retries
			return verdict

		should_ignore = self.should_ignore_url(url, record_info)
		if should_ignore:
			if not self.job_data["suppress_ignore_reports"]:
				pattern = self.get_specific_ignore_pattern(url)
				self.maybe_log_ignore(url, pattern)
			return False

		# If we get here, none of our ignores apply. Return the original verdict.
		return verdict

	def handle_result(self, url_info, record_info, error_info, response):
		self.update_igoff()

		self.job_data["bytes_downloaded"] += wpull_tweaks.response_body_size(response)

		response_code    = 0
		response_message = ""
		if error_info:
			response_message = str(error_info)
		elif response:
			response_code    = response_status_code(response)
			response_message = response.reason
		response_code_str = str(response_code)

		if len(response_code_str) == 3 and response_code_str[0] in "12345":
			self.job_data[f"r{response_code_str[0]}xx"] += 1
		else:
			self.job_data["runk"] += 1

		self.put_ws_queue({
			"type":             "download",
			"job_data":         self.job_data,
			"url":              url_info.raw,
			"response_code":    response_code,
			"response_message": response_message,
		})

		if self.should_stop():
			return Actions.STOP

		return Actions.NORMAL

	def maybe_log_ignore(self, url, pattern):
		if not self.job_data["suppress_ignore_reports"]:
			self.print_to_terminal(f"IGNOR {url}\n   by {pattern}")
			self.put_ws_queue({
				"type":     "ignore",
				"job_data": self.job_data,
				"url":      url,
				"pattern":  pattern
			})

	@event(PluginFunctions.queued_url)
	def queued_url(self, _url_info: URLInfo):
		self.job_data["items_queued"] += 1

	@event(PluginFunctions.dequeued_url)
	def dequeued_url(self, _url_info: URLInfo, _record_info: URLRecord):
		self.job_data["items_downloaded"] += 1

	@hook(PluginFunctions.handle_response)
	def handle_response(self, item_session: ItemSession):
		url_info    = item_session.request.url_info
		record_info = item_session.url_record
		response    = item_session.response
		error_info  = None
		return self.handle_result(url_info, record_info, error_info, response)

	@hook(PluginFunctions.handle_error)
	def handle_error(self, item_session: ItemSession, error_info: BaseException):
		url_info    = item_session.request.url_info
		record_info = item_session.url_record
		response    = item_session.response
		return self.handle_result(url_info, record_info, error_info, response)

	@hook(PluginFunctions.handle_pre_response)
	def handle_pre_response(self, item_session: ItemSession):
		url_info = item_session.request.url_info
		response = item_session.response
		self.update_scrape()

		url = url_info.raw

		self.update_max_content_length()
		limit = self.job_data["max_content_length"]
		if limit != -1:
			length = get_content_length(response)
			if length > limit:
				self.skipped_max_content_length.write(url + "\n")
				self.skipped_max_content_length.flush()
				self.maybe_log_ignore(url, f"[content-length {length} over limit {limit}]")
				return Actions.FINISH

		self.update_video()
		if not self.job_data["video"]:
			if has_content_type_video(response) or has_video_ext(url):
				self.skipped_videos.write(url + "\n")
				self.skipped_videos.flush()
				self.maybe_log_ignore(url, "[video]")
				return Actions.FINISH

		# Check if server version starts with ICY
		if response.version == "ICY":
			self.maybe_log_ignore(url, "[icy version]")
			return Actions.FINISH

		# Loop through all the server headers for matches
		for field, value in response.fields.get_all():
			if ICY_FIELD_PATTERN.match(field):
				self.maybe_log_ignore(url, "[icy field]")
				return Actions.FINISH

			if field == "Server" and ICY_VALUE_PATTERN.match(value):
				self.maybe_log_ignore(url, "[icy server]")
				return Actions.FINISH

		# Nothing matched, allow download
		self.print_to_terminal(url + " ...")
		return Actions.NORMAL

	@hook(PluginFunctions.exit_status)
	def exit_status(self, _app_session: AppSession, code: int) -> int:
		print()
		print(f'Finished grab {self.job_data["ident"]} {self.job_data["url"]} with exit code {code}')
		print(f"Output is in directory:\n{working_dir}")
		return code

	@hook(PluginFunctions.wait_time)
	def wait_time(self, _seconds: float, _item_session: ItemSession, _error):
		self.update_delay()
		self.update_concurrency()
		return random.uniform(self.job_data["delay_min"], self.job_data["delay_max"]) / 1000

	@event(PluginFunctions.get_urls)
	def get_urls(self, item_session: ItemSession):
		url_info   = item_session.request.url_info
		url        = url_info.raw
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
