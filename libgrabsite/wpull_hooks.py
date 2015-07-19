import re
import os
import sys
import json
import pprint
import signal
import trollius as asyncio
from urllib.request import urlopen
from autobahn.asyncio.websocket import WebSocketClientFactory, WebSocketClientProtocol
from libgrabsite.ignoracle import Ignoracle, parameterize_record_info

realStdoutWrite = sys.stdout.buffer.write
realStderrWrite = sys.stderr.buffer.write

def printToReal(s):
	realStdoutWrite((s + "\n").encode("utf-8"))
	sys.stdout.buffer.flush()


class GrabberClientProtocol(WebSocketClientProtocol):
	def onOpen(self):
		self.factory.client = self
		printToReal("{} connected to WebSocket server".format(self.__class__.__name__))
		self.sendMessage(json.dumps({
			"type": "hello",
			"mode": "grabber",
			"url": jobData["url"]
		}).encode('utf-8'))

	def onClose(self, wasClean, code, reason):
		self.factory.client = None
		printToReal("{} disconnected from WebSocket server".format(self.__class__.__name__))
		# TODO: exponentially increasing delay (copy Decayer from dashboard)
		asyncio.ensure_future(connectToServer())

	def sendObject(self, obj):
		self.sendMessage(json.dumps(obj).encode("utf-8"))


class GrabberClientFactory(WebSocketClientFactory):
	protocol = GrabberClientProtocol

	def __init__(self):
		super().__init__()
		self.client = None


wsFactory = GrabberClientFactory()

@asyncio.coroutine
def connectToServer():
	host = os.environ.get('GRAB_SITE_WS_HOST', '127.0.0.1')
	port = int(os.environ.get('GRAB_SITE_WS_PORT', 29001))
	while True:
		try:
			coro = yield from loop.create_connection(wsFactory, host, port)
		except OSError:
			printToReal("Could not connect to WebSocket server, retrying in 2 seconds...")
			yield from asyncio.sleep(2)
		else:
			break

loop = asyncio.get_event_loop()
asyncio.ensure_future(connectToServer())

def gracefulStopCallback():
	printToReal("\n^C detected, creating 'stop' file, please wait for exit...")
	with open(os.path.join(workingDir, "stop"), "wb") as f:
		pass

def forcefulStopCallback():
	loop.stop()

loop.add_signal_handler(signal.SIGINT, gracefulStopCallback)
loop.add_signal_handler(signal.SIGTERM, forcefulStopCallback)


igsetCache = {}
def getPatternsForIgnoreSet(name):
	assert name != "", name
	if name in igsetCache:
		return igsetCache[name]
	printToReal("Fetching ArchiveBot/master/db/ignore_patterns/%s.json" % name)
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
		self.lastModificationTime = mtime(fname)

	def hasChanged(self):
		nowModificationTime = mtime(self.fname)
		changed = mtime(self.fname) != self.lastModificationTime
		self.lastModificationTime = nowModificationTime
		return changed


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

	printToReal("Using these %d ignores:" % len(ignores))
	printToReal(pprint.pformat(ignores))

	ignoracle.set_patterns(ignores)

updateIgnoracle()


def shouldIgnoreURL(url, recordInfo):
	"""
	Returns whether a URL should be ignored.
	"""
	parameters = parameterize_record_info(recordInfo)
	return ignoracle.ignores(url, **parameters)


def acceptURL(urlInfo, recordInfo, verdict, reasons):
	if igsetsWatcher.hasChanged() or ignoresWatcher.hasChanged():
		updateIgnoracle()

	url = urlInfo['url']

	if url.startswith('data:'):
		# data: URLs aren't something you can grab, so drop them to avoid ignore
		# checking and ignore logging.
		return False

	pattern = shouldIgnoreURL(url, recordInfo)
	if pattern:
		maybeLogIgnore(url, pattern)
		return False

	# If we get here, none of our ignores apply.	Return the original verdict.
	return verdict


def queuedURL(urlInfo):
	jobData["items_queued"] += 1


def dequeuedURL(urlInfo, recordInfo):
	jobData["items_downloaded"] += 1


jobData = {
	"ident": open(os.path.join(workingDir, "id")).read().strip(),
	"url": open(os.path.join(workingDir, "start_url")).read().strip(),
	"started_at": os.stat(os.path.join(workingDir, "start_url")).st_mtime,
	"suppress_ignore_reports": True,
	"concurrency": int(open(os.path.join(workingDir, "concurrency")).read().strip()),
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

def handleResult(urlInfo, recordInfo, errorInfo={}, httpInfo={}):
	#print("urlInfo", urlInfo)
	#print("recordInfo", recordInfo)
	#print("errorInfo", errorInfo)
	#print("httpInfo", httpInfo)

	updateIgoffInJobData()

	response_code = 0
	if httpInfo.get("response_code"):
		response_code = httpInfo.get("response_code")
		response_code_str = str(httpInfo["response_code"])
		if len(response_code_str) == 3 and response_code_str[0] in "12345":
			jobData["r%sxx" % response_code_str[0]] += 1
		else:
			jobData["runk"] += 1

	if httpInfo.get("body"):
		jobData["bytes_downloaded"] += httpInfo["body"]["content_size"]

	stop = shouldStop()

	response_message = httpInfo.get("response_message")
	if errorInfo:
		response_code = 0
		response_message = errorInfo["error"]

	if wsFactory.client:
		wsFactory.client.sendObject({
			"type": "download",
			"job_data": jobData,
			"url": urlInfo["url"],
			"response_code": response_code,
			"response_message": response_message,
		})

	if stop:
		return wpull_hook.actions.STOP

	return wpull_hook.actions.NORMAL


def handleResponse(urlInfo, recordInfo, httpInfo):
	return handleResult(urlInfo, recordInfo, httpInfo=httpInfo)


def handleError(urlInfo, recordInfo, errorInfo):
	return handleResult(urlInfo, recordInfo, errorInfo=errorInfo)


# TODO: check only every 5 seconds max
def shouldStop():
	return os.path.exists(os.path.join(workingDir, "stop"))


# TODO: check only every 5 seconds max
def updateIgoffInJobData():
	igoff = os.path.exists(os.path.join(workingDir, "igoff"))
	jobData["suppress_ignore_reports"] = igoff
	return igoff


def maybeLogIgnore(url, pattern):
	if not updateIgoffInJobData():
		printToReal("IGNOR %s by %s" % (url, pattern))
		if wsFactory.client:
			wsFactory.client.sendObject({
				"type": "ignore",
				"job_data": jobData,
				"url": url,
				"pattern": pattern
			})


# Regular expressions for server headers go here
ICY_FIELD_PATTERN = re.compile('icy-|ice-|x-audiocast-', re.IGNORECASE)
ICY_VALUE_PATTERN = re.compile('icecast', re.IGNORECASE)

def handlePreResponse(urlInfo, urlRecord, responseInfo):
	url = urlInfo['url']

	# Check if server version starts with ICY
	if responseInfo.get('version', '') == 'ICY':
		maybeLogIgnore(url, '[icy version]')
		return wpull_hook.actions.FINISH

	# Loop through all the server headers for matches
	for field, value in responseInfo.get('fields', []):
		if ICY_FIELD_PATTERN.match(field):
			maybeLogIgnore(url, '[icy field]')
			return wpull_hook.actions.FINISH

		if field == 'Server' and ICY_VALUE_PATTERN.match(value):
			maybeLogIgnore(url, '[icy server]')
			return wpull_hook.actions.FINISH

	# Nothing matched, allow download
	printToReal(url + " ...")
	return wpull_hook.actions.NORMAL


def stdoutWriteToBoth(message):
	assert isinstance(message, bytes), message
	try:
		realStdoutWrite(message)
		if wsFactory.client:
			wsFactory.client.sendObject({
				"type": "stdout",
				"job_data": jobData,
				"message": message.decode("utf-8")
			})
	except Exception as e:
		realStderrWrite((str(e) + "\n").encode("utf-8"))


def stderrWriteToBoth(message):
	assert isinstance(message, bytes), message
	try:
		realStderrWrite(message)
		if wsFactory.client:
			wsFactory.client.sendObject({
				"type": "stderr",
				"job_data": jobData,
				"message": message.decode("utf-8")
			})
	except Exception as e:
		realStderrWrite((str(e) + "\n").encode("utf-8"))

sys.stdout.buffer.write = stdoutWriteToBoth
sys.stderr.buffer.write = stderrWriteToBoth


def exitStatus(code):
	print()
	print("Finished grab {} {} with exit code {}".format(jobData["ident"], jobData["url"], code))
	print("Output is in directory:\n{}".format(workingDir))
	return code


assert 2 in wpull_hook.callbacks.AVAILABLE_VERSIONS

wpull_hook.callbacks.version = 2
wpull_hook.callbacks.accept_url = acceptURL
wpull_hook.callbacks.queued_url = queuedURL
wpull_hook.callbacks.dequeued_url = dequeuedURL
wpull_hook.callbacks.handle_response = handleResponse
wpull_hook.callbacks.handle_error = handleError
wpull_hook.callbacks.handle_pre_response = handlePreResponse
wpull_hook.callbacks.exit_status = exitStatus
