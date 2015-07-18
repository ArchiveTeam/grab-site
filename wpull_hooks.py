import re
import os
import sys
import json
import pprint
import trollius as asyncio
from urllib.request import urlopen
from autobahn.asyncio.websocket import WebSocketClientFactory, WebSocketClientProtocol
from ignoracle import Ignoracle, parameterize_record_info

real_stdout_write = sys.stdout.write
real_stderr_write = sys.stderr.write

def getJobData():
	return {
		"ident": ident,
		"started_at": started_at,
		"bytes_downloaded": stats["bytes_downloaded"],
		"url": start_url
	}

class MyClientProtocol(WebSocketClientProtocol):
	def onOpen(self):
		self.factory.client = self
		print("\n{} connected to WebSocket server".format(self.__class__.__name__))
		self.sendMessage(json.dumps({"type": "hello", "mode": "grabber"}).encode('utf-8'))

	def onClose(self, wasClean, code, reason):
		self.factory.client = None
		print("\n{} disconnected from WebSocket server".format(self.__class__.__name__))
		# TODO: exponentially increasing delay (copy Decayer from dashboard)
		asyncio.ensure_future(connectToServer())

	def report(self, url, response_code, response_message):
		self.sendMessage(json.dumps({
			"job_data": getJobData(),
			"type": "download",
			"url": url,
			"response_code": response_code,
			"response_message": response_message,
		}).encode('utf-8'))


class MyClientFactory(WebSocketClientFactory):
	protocol = MyClientProtocol

	def __init__(self):
		super().__init__()
		self.client = None


wsFactory = MyClientFactory()

@asyncio.coroutine
def connectToServer():
	port = int(os.environ.get('GRAB_SITE_WS_PORT', 29001))

	while True:
		try:
			coro = yield from loop.create_connection(wsFactory, '127.0.0.1', port)
		except OSError:
			print("\nCould not connect to WebSocket server, retrying in 2 seconds...")
			yield from asyncio.sleep(2)
		else:
			break

loop = asyncio.get_event_loop()
asyncio.ensure_future(connectToServer())


igsetCache = {}
def getPatternsForIgnoreSet(name):
	assert name != "", name
	if name in igsetCache:
		return igsetCache[name]
	print("Fetching ArchiveBot/master/db/ignore_patterns/%s.json" % name)
	igsetCache[name] = json.loads(urlopen(
		"https://raw.githubusercontent.com/ArchiveTeam/ArchiveBot/" +
		"master/db/ignore_patterns/%s.json" % name).read().decode("utf-8")
	)["patterns"]
	return igsetCache[name]

workingDir = os.environ['GRAB_SITE_WORKING_DIR']

def mtime(f):
	return os.stat(f).st_mtime


class FileChangedWatcher(object):
	def __init__(self, fname):
		self.fname = fname
		self.last_mtime = mtime(fname)

	def has_changed(self):
		now_mtime = mtime(self.fname)
		changed = mtime(self.fname) != self.last_mtime
		self.last_mtime = now_mtime
		return changed


ident = open(os.path.join(workingDir, "id")).read().strip()
start_url = open(os.path.join(workingDir, "start_url")).read().strip()
started_at = os.stat(os.path.join(workingDir, "start_url")).st_mtime
igsetsWatcher = FileChangedWatcher(os.path.join(workingDir, "igsets"))
ignoresWatcher = FileChangedWatcher(os.path.join(workingDir, "ignores"))

ignoracle = Ignoracle()

def updateIgnoracle():
	with open(os.path.join(workingDir, "igsets"), "r") as f:
		igsets = f.read().strip("\r\n\t ,").split(',')

	with open(os.path.join(workingDir, "ignores"), "r") as f:
		ignores = set(ig for ig in f.read().strip("\r\n").split('\n') if ig != "")

	for igset in igsets:
		ignores.update(getPatternsForIgnoreSet(igset))

	print("Using these %d ignores:" % len(ignores))
	pprint.pprint(ignores)

	ignoracle.set_patterns(ignores)

updateIgnoracle()


def shouldIgnoreURL(url, recordInfo):
	"""
	Returns whether a URL should be ignored.
	"""
	parameters = parameterize_record_info(recordInfo)
	return ignoracle.ignores(url, **parameters)


def acceptUrl(urlInfo, recordInfo, verdict, reasons):
	if igsetsWatcher.has_changed() or ignoresWatcher.has_changed():
		updateIgnoracle()

	url = urlInfo['url']

	if url.startswith('data:'):
		# data: URLs aren't something you can grab, so drop them to avoid ignore
		# checking and ignore logging.
		return False

	pattern = shouldIgnoreURL(url, recordInfo)
	if pattern:
		if not os.path.exists(os.path.join(workingDir, "igoff")):
			print("IGNOR %s by %s" % (url, pattern))
		return False

	# If we get here, none of our ignores apply.	Return the original verdict.
	return verdict


stats = {"bytes_downloaded": 0}

def handleResult(urlInfo, recordInfo, errorInfo={}, httpInfo={}):
	#print("urlInfo", urlInfo)
	#print("recordInfo", recordInfo)
	#print("errorInfo", errorInfo)
	#print("httpInfo", httpInfo)

	if httpInfo.get("body"):
		stats["bytes_downloaded"] += httpInfo["body"]["content_size"]

	if wsFactory.client:
		wsFactory.client.report(
			urlInfo['url'],
			httpInfo.get("response_code"),
			httpInfo.get("response_message")
		)


def handleResponse(urlInfo, recordInfo, httpInfo):
	return handleResult(urlInfo, recordInfo, httpInfo=httpInfo)


def handleError(urlInfo, recordInfo, errorInfo):
	return handleResult(urlInfo, recordInfo, errorInfo=errorInfo)


# Regular expressions for server headers go here
ICY_FIELD_PATTERN = re.compile('Icy-|Ice-|X-Audiocast-')
ICY_VALUE_PATTERN = re.compile('icecast', re.IGNORECASE)

def handlePreResponse(urlInfo, url_record, response_info):
	url = urlInfo['url']

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
	return wpull_hook.actions.NORMAL


def stdoutWriteToBoth(message):
	try:
		real_stdout_write(message)
		if wsFactory.client:
			wsFactory.client.sendMessage({
				"type": "stdout",
				"job_data": getJobData(),
				"message": message
			})
	except Exception as e:
		real_stderr_write(str(e) + "\n")

def stderrWriteToBoth(message):
	try:
		real_stderr_write(message)
		if wsFactory.client:
			wsFactory.client.sendMessage({
				"type": "stderr",
				"job_data": getJobData(),
				"message": message
			})
	except Exception as e:
		real_stderr_write(str(e) + "\n")

sys.stdout.write = stdoutWriteToBoth
sys.stderr.write = stderrWriteToBoth


assert 2 in wpull_hook.callbacks.AVAILABLE_VERSIONS

wpull_hook.callbacks.version = 2
wpull_hook.callbacks.accept_url = acceptUrl
wpull_hook.callbacks.handle_response = handleResponse
wpull_hook.callbacks.handle_error = handleError
wpull_hook.callbacks.handle_pre_response = handlePreResponse
