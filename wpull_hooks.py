import re
import os
import json
import pprint
import trollius as asyncio
from urllib.request import urlopen
from autobahn.asyncio.websocket import WebSocketClientFactory, WebSocketClientProtocol
from ignoracle import Ignoracle, parameterize_record_info

class MyClientProtocol(WebSocketClientProtocol):
	def onOpen(self):
		self.factory.client = self
		print("\n{} connected to WebSocket server".format(self.__class__.__name__))

	def onClose(self, wasClean, code, reason):
		self.factory.client = None
		print("\n{} disconnected from WebSocket server".format(self.__class__.__name__))
		# TODO: exponentially increasing delay (copy Decayer from dashboard)
		asyncio.ensure_future(connectToServer())

	def report(self, url, response_code, response_message):
		self.sendMessage(json.dumps({
			"ident": grabId,
			"type": "download",
			"url": url,
			"response_code": response_code,
			"response_message": response_message,
		}).encode('utf8'))


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


grabId = open(os.path.join(workingDir, "id")).read().strip()
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


def shouldIgnoreURL(url, record_info):
	"""
	Returns whether a URL should be ignored.
	"""
	parameters = parameterize_record_info(record_info)
	return ignoracle.ignores(url, **parameters)


def acceptUrl(url_info, record_info, verdict, reasons):
	if igsetsWatcher.has_changed() or ignoresWatcher.has_changed():
		updateIgnoracle()

	url = url_info['url']

	if url.startswith('data:'):
		# data: URLs aren't something you can grab, so drop them to avoid ignore
		# checking and ignore logging.
		return False

	pattern = shouldIgnoreURL(url, record_info)
	if pattern:
		if not os.path.exists(os.path.join(workingDir, "igoff")):
			print("IGNOR %s by %s" % (url, pattern))
		return False

	# If we get here, none of our ignores apply.	Return the original verdict.
	return verdict


def handleResult(url_info, record_info, error_info={}, http_info={}):
	#print("url_info", url_info)
	#print("record_info", record_info)
	#print("error_info", error_info)
	#print("http_info", http_info)
	if wsFactory.client:
		wsFactory.client.report(
			url_info['url'],
			http_info.get("response_code"),
			http_info.get("response_message")
		)


def handleResponse(url_info, record_info, http_info):
	return handleResult(url_info, record_info, http_info=http_info)


def handleError(url_info, record_info, error_info):
	return handleResult(url_info, record_info, error_info=error_info)


# Regular expressions for server headers go here
ICY_FIELD_PATTERN = re.compile('Icy-|Ice-|X-Audiocast-')
ICY_VALUE_PATTERN = re.compile('icecast', re.IGNORECASE)

def handlePreResponse(url_info, url_record, response_info):
	url = url_info['url']

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


assert 2 in wpull_hook.callbacks.AVAILABLE_VERSIONS

wpull_hook.callbacks.version = 2
wpull_hook.callbacks.accept_url = acceptUrl
wpull_hook.callbacks.handle_response = handleResponse
wpull_hook.callbacks.handle_error = handleError
wpull_hook.callbacks.handle_pre_response = handlePreResponse
