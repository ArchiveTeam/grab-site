#!/usr/bin/env python3

import os
import json
import pprint
# Can't use trollius because then onConnect never gets called
# https://github.com/tavendo/AutobahnPython/issues/426
import asyncio
import aiohttp.web
from autobahn.asyncio.websocket import WebSocketServerFactory, WebSocketServerProtocol

class MyServerProtocol(WebSocketServerProtocol):
	def __init__(self):
		super().__init__()
		self.mode = "dashboard"

	def onConnect(self, request):
		self.peer = request.peer
		print("{} connected".format(self.peer))
		self.factory.clients.add(self)

	def onClose(self, wasClean, code, reason):
		print("{} disconnected".format(self.peer))
		self.factory.clients.remove(self)

	def broadcastToDashboards(self, obj):
		for client in self.factory.clients:
			if client.mode == "dashboard":
				##print("Broadcasting", pprint.pformat(obj))
				client.sendMessage(json.dumps(obj).encode("utf-8"))

	def onMessage(self, payload, isBinary):
		##print(payload)
		obj = json.loads(payload.decode('utf-8'))
		type = obj["type"]
		if type == "hello" and obj.get("mode"):
			mode = obj['mode']
			if mode in ('dashboard', 'grabber'):
				print("{} set mode {}".format(self.peer, mode))
				if mode == "grabber":
					print("{} is grabbing {}".format(self.peer, obj['url']))
				self.mode = mode
		elif type == "download":
			self.broadcastToDashboards({
				"type": type,
				"job_data": obj["job_data"],
				"url": obj["url"],
				"response_code": obj["response_code"],
				"wget_code": obj["response_message"]
			})
		elif type in ("stdout", "stderr"):
			self.broadcastToDashboards({
				"type": type,
				"job_data": obj["job_data"],
				"message": obj["message"]
			})
		elif type == "ignore":
			self.broadcastToDashboards({
				"type": type,
				"job_data": obj["job_data"],
				"url": obj["url"],
				"pattern": obj["pattern"],
			})


class MyServerFactory(WebSocketServerFactory):
	protocol = MyServerProtocol

	def __init__(self):
		super().__init__()
		self.clients = set()


@asyncio.coroutine
def dashboard(request):
	with open(os.path.join(os.path.dirname(__file__), "dashboard.html"), "rb") as f:
		dashboardHtml = f.read()
		return aiohttp.web.Response(body=dashboardHtml)


@asyncio.coroutine
def httpServer(loop, interface, port):
	app = aiohttp.web.Application(loop=loop)
	app.router.add_route('GET', '/', dashboard)

	srv = yield from loop.create_server(app.make_handler(), interface, port)
	return srv


def main():
	loop = asyncio.get_event_loop()

	httpPort = int(os.environ.get('GRAB_SITE_HTTP_PORT', 29000))
	httpInterface = os.environ.get('GRAB_SITE_HTTP_INTERFACE', '0.0.0.0')
	wsPort = int(os.environ.get('GRAB_SITE_WS_PORT', 29001))
	wsInterface = os.environ.get('GRAB_SITE_WS_INTERFACE', '0.0.0.0')

	httpCoro = httpServer(loop, httpInterface, httpPort)
	loop.run_until_complete(httpCoro)

	wsFactory = MyServerFactory()
	wsCoro = loop.create_server(wsFactory, wsInterface, wsPort)
	loop.run_until_complete(wsCoro)

	print("     HTTP server started on {}:{}".format(httpInterface, httpPort))
	print("WebSocket server started on {}:{}".format(wsInterface, wsPort))

	loop.run_forever()


if __name__ == '__main__':
	main()
