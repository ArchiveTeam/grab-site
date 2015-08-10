import re
import os
import sys
import json
import time
import pprint
import signal
import random
import functools
import traceback
import trollius as asyncio
from autobahn.asyncio.websocket import WebSocketClientFactory, WebSocketClientProtocol
from libgrabsite.ignoracle import Ignoracle, parameterize_record_info
import libgrabsite

real_stdout_write = sys.stdout.buffer.write
real_stderr_write = sys.stderr.buffer.write

def print_to_real(s):
	real_stdout_write((s + "\n").encode("utf-8"))
	sys.stdout.buffer.flush()


class GrabberClientProtocol(WebSocketClientProtocol):
	def on_open(self):
		self.factory.client = self
		self.send_object({
			"type": "hello",
			"mode": "grabber",
			"url": job_data["url"]
		})

	def on_close(self, was_clean, code, reason):
		self.factory.client = None
		print_to_real(
			"Disconnected from ws:// server with (was_clean, code, reason): {!r}"
				.format((was_clean, code, reason)))
		asyncio.ensure_future(connect_to_server())

	def send_object(self, obj):
		self.sendMessage(json.dumps(obj).encode("utf-8"))

	onOpen = on_open
	onClose = on_close


class GrabberClientFactory(WebSocketClientFactory):
	protocol = GrabberClientProtocol

	def __init__(self):
		super().__init__()
		self.client = None


ws_factory = GrabberClientFactory()

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


@asyncio.coroutine
def connect_to_server():
	host = os.environ.get('GRAB_SITE_WS_HOST', '127.0.0.1')
	port = int(os.environ.get('GRAB_SITE_WS_PORT', 29001))
	decayer = Decayer(0.25, 1.5, 8)
	while True:
		try:
			yield from loop.create_connection(ws_factory, host, port)
		except OSError:
			delay = decayer.decay()
			print_to_real(
				"Could not connect to ws://{}:{}, retrying in {:.1f} seconds..."
					.format(host, port, delay))
			yield from asyncio.sleep(delay)
		else:
			print_to_real("Connected to ws://{}:{}".format(host, port))
			break

loop = asyncio.get_event_loop()
asyncio.ensure_future(connect_to_server())


def graceful_stop_callback():
	print_to_real("\n^C detected, creating 'stop' file, please wait for exit...")
	with open(os.path.join(working_dir, "stop"), "wb") as f:
		pass


def forceful_stop_callback():
	loop.stop()


loop.add_signal_handler(signal.SIGINT, graceful_stop_callback)
loop.add_signal_handler(signal.SIGTERM, forceful_stop_callback)


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


CONTROL_FILE_CACHE_SEC = 3

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

	print_to_real("Using these %d ignores:" % len(ignores))
	print_to_real(pprint.pformat(ignores))

	ignoracle.set_patterns(ignores)

update_ignoracle()


def should_ignore_url(url, record_info):
	"""
	Returns whether a URL should be ignored.
	"""
	parameters = parameterize_record_info(record_info)
	return ignoracle.ignores(url, **parameters)


def accept_url(url_info, record_info, verdict, reasons):
	update_ignoracle()

	url = url_info['url']

	if url.startswith('data:'):
		# data: URLs aren't something you can grab, so drop them to avoid ignore
		# checking and ignore logging.
		return False

	pattern = should_ignore_url(url, record_info)
	if pattern:
		maybe_log_ignore(url, pattern)
		return False

	# If we get here, none of our ignores apply.	Return the original verdict.
	return verdict


def queued_url(url_info):
	job_data["items_queued"] += 1


def dequeued_url(url_info, record_info):
	job_data["items_downloaded"] += 1


job_data = {
	"ident": open(os.path.join(working_dir, "id")).read().strip(),
	"url": open(os.path.join(working_dir, "start_url")).read().strip(),
	"started_at": os.stat(os.path.join(working_dir, "start_url")).st_mtime,
	"max_content_length": -1,
	"suppress_ignore_reports": True,
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


def handle_result(url_info, record_info, error_info={}, http_info={}):
	#print("url_info", url_info)
	#print("record_info", record_info)
	#print("error_info", error_info)
	#print("http_info", http_info)

	update_igoff()

	response_code = 0
	if http_info.get("response_code"):
		response_code = http_info.get("response_code")
		response_code_str = str(http_info["response_code"])
		if len(response_code_str) == 3 and response_code_str[0] in "12345":
			job_data["r%sxx" % response_code_str[0]] += 1
		else:
			job_data["runk"] += 1

	if http_info.get("body"):
		job_data["bytes_downloaded"] += http_info["body"]["content_size"]

	stop = should_stop()

	response_message = http_info.get("response_message")
	if error_info:
		response_code = 0
		response_message = error_info["error"]

	if ws_factory.client:
		ws_factory.client.send_object({
			"type": "download",
			"job_data": job_data,
			"url": url_info["url"],
			"response_code": response_code,
			"response_message": response_message,
		})

	if stop:
		return wpull_hook.actions.STOP

	return wpull_hook.actions.NORMAL


def handle_response(url_info, record_info, http_info):
	return handle_result(url_info, record_info, http_info=http_info)


def handle_error(url_info, record_info, error_info):
	return handle_result(url_info, record_info, error_info=error_info)


stop_path = os.path.join(working_dir, "stop")
def should_stop():
	return path_exists_with_cache(stop_path)


igoff_path = os.path.join(working_dir, "igoff")
def update_igoff():
	igoff = path_exists_with_cache(igoff_path)
	job_data["suppress_ignore_reports"] = igoff
	return igoff


def maybe_log_ignore(url, pattern):
	if not update_igoff():
		print_to_real("IGNOR %s\n   by %s" % (url, pattern))
		if ws_factory.client:
			ws_factory.client.send_object({
				"type": "ignore",
				"job_data": job_data,
				"url": url,
				"pattern": pattern
			})


ICY_FIELD_PATTERN = re.compile('icy-|ice-|x-audiocast-', re.IGNORECASE)
ICY_VALUE_PATTERN = re.compile('icecast', re.IGNORECASE)

def get_content_length(response_info):
	try:
		return int(list(p for p in response_info["fields"] if p[0] == "Content-Length")[0][1])
	except (IndexError, ValueError):
		return -1


def handle_pre_response(url_info, url_record, response_info):
	url = url_info['url']

	update_max_content_length()
	if job_data["max_content_length"] != -1:
		##pprint.pprint(response_info)
		length = get_content_length(response_info)
		##print((length, job_data["max_content_length"]))
		if length > job_data["max_content_length"]:
			maybe_log_ignore(url, '[content-length %d over limit %d]' % (
				length, job_data["max_content_length"]))
			return wpull_hook.actions.FINISH

	# Check if server version starts with ICY
	if response_info.get('version', '') == 'ICY':
		maybe_log_ignore(url, '[icy version]')
		return wpull_hook.actions.FINISH

	# Loop through all the server headers for matches
	for field, value in response_info.get('fields', []):
		if ICY_FIELD_PATTERN.match(field):
			maybe_log_ignore(url, '[icy field]')
			return wpull_hook.actions.FINISH

		if field == 'Server' and ICY_VALUE_PATTERN.match(value):
			maybe_log_ignore(url, '[icy server]')
			return wpull_hook.actions.FINISH

	# Nothing matched, allow download
	print_to_real(url + " ...")
	return wpull_hook.actions.NORMAL


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


def exit_status(code):
	print()
	print("Finished grab {} {} with exit code {}".format(
		job_data["ident"], job_data["url"], code))
	print("Output is in directory:\n{}".format(working_dir))
	return code


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
		job_data["concurrency"] = int(f.read().strip())
	wpull_hook.factory.get('Engine').set_concurrent(job_data["concurrency"])

update_concurrency()


def wait_time(_):
	update_delay()
	# While we're at it, update the concurrency level
	update_concurrency()

	return random.uniform(job_data["delay_min"], job_data["delay_max"]) / 1000


assert 2 in wpull_hook.callbacks.AVAILABLE_VERSIONS

wpull_hook.callbacks.version = 2
wpull_hook.callbacks.accept_url = accept_url
wpull_hook.callbacks.queued_url = queued_url
wpull_hook.callbacks.dequeued_url = dequeued_url
wpull_hook.callbacks.handle_response = handle_response
wpull_hook.callbacks.handle_error = handle_error
wpull_hook.callbacks.handle_pre_response = handle_pre_response
wpull_hook.callbacks.exit_status = exit_status
wpull_hook.callbacks.wait_time = wait_time

really_swallow_exceptions = True
