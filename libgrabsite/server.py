#!/usr/bin/env python3

import os
import json
import pprint
# Can't use trollius because then onConnect never gets called
# https://github.com/tavendo/AutobahnPython/issues/426
import asyncio
from autobahn.asyncio.websocket import WebSocketServerFactory, WebSocketServerProtocol

class GrabberServerProtocol(WebSocketServerProtocol):
	def __init__(self):
		super().__init__()
		self.mode = None

	def onConnect(self, request):
		self.peer = request.peer
		print("{} connected".format(self.peer))
		self.factory.clients.add(self)

	def onClose(self, wasClean, code, reason):
		print("{} disconnected".format(self.peer))
		self.factory.clients.discard(self)

	def broadcastToDashboards(self, obj):
		for client in self.factory.clients:
			if client.mode == "dashboard":
				##print("Broadcasting", pprint.pformat(obj))
				client.sendMessage(json.dumps(obj).encode("utf-8"))

	def onMessage(self, payload, isBinary):
		##print(payload)
		obj = json.loads(payload.decode('utf-8'))
		type = obj["type"]
		if self.mode is None and type == "hello" and obj.get("mode"):
			mode = obj['mode']
			if mode in ('dashboard', 'grabber'):
				self.mode = mode
				if mode == "grabber":
					print("{} is grabbing {}".format(self.peer, obj['url']))
				elif mode == "dashboard":
					print("{} is dashboarding with {}".format(self.peer, obj['user_agent']))
		elif self.mode == "grabber":
			if type == "download":
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

	# Called when we get an HTTP request instead of a WebSocket request
	def sendServerStatus(self, redirectUrl=None, redirectAfter=0):
		requestPath = self.http_request_uri.split("?")[0]
		if requestPath == "/":
			with open(os.path.join(os.path.dirname(__file__), "dashboard.html"), "r") as f:
				dashboardHtml = f.read()
				self.sendHtml(dashboardHtml)
		else:
			self.send404()
	
	def send404(self):
		with open(os.path.join(os.path.dirname(__file__), "404.html"), "r") as f:
			responseHtml = f.read()
		response = "HTTP/1.1 404 Not Found\x0d\x0a"
		response += "Content-Type: text/html; charset=UTF-8\x0d\x0a"
		response += "Content-Length: {}\x0d\x0a".format(len(responseHtml))
		response += "\x0d\x0a"
		response += responseHtml
		self.sendData(response.encode("utf_8"))

class GrabberServerFactory(WebSocketServerFactory):
	protocol = GrabberServerProtocol

	def __init__(self):
		super().__init__()
		self.clients = set()


def main():
	loop = asyncio.get_event_loop()

	port = int(os.environ.get('GRAB_SITE_PORT', 29000))
	interface = os.environ.get('GRAB_SITE_INTERFACE', '0.0.0.0')

	factory = GrabberServerFactory()
	coro = loop.create_server(factory, interface, port)
	loop.run_until_complete(coro)

	print("grab-site server started on {}:{}".format(interface, port))

	loop.run_forever()


if __name__ == '__main__':
	main()
