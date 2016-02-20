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
		if self in self.factory.clients:
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
				
	def sendHtml(self, dummy):
		with open(os.path.join(os.path.dirname(__file__), "dashboard.html"), "r") as f:
			dashboardHtml = f.read()
			super().sendHtml(dashboardHtml)


class GrabberServerFactory(WebSocketServerFactory):
	protocol = GrabberServerProtocol

	def __init__(self):
		super().__init__()
		self.clients = set()


def main():
	loop = asyncio.get_event_loop()

	Port = int(os.environ.get('GRAB_SITE_PORT', 29000))
	Interface = os.environ.get('GRAB_SITE_INTERFACE', '0.0.0.0')

	Factory = GrabberServerFactory()
	Coro = loop.create_server(Factory, Interface, Port)
	loop.run_until_complete(Coro)

	print("grab-site server started on {}:{}".format(Interface, Port))

	loop.run_forever()


if __name__ == '__main__':
	main()
