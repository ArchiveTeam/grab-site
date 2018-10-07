#!/usr/bin/env python3

import os
import json
import pprint
import asyncio
from autobahn.asyncio.websocket import WebSocketServerFactory, WebSocketServerProtocol

class GrabberServerProtocol(WebSocketServerProtocol):
	def __init__(self):
		super().__init__()
		self.mode = None

	def onConnect(self, request):
		self.peer = request.peer
		print(f"{self.peer} connected")
		self.factory.clients.add(self)

	def onClose(self, wasClean, code, reason):
		print(f"{self.peer} disconnected")
		self.factory.clients.discard(self)

	def broadcast_to_dashboards(self, obj):
		for client in self.factory.clients:
			if client.mode == "dashboard":
				client.sendMessage(json.dumps(obj).encode("utf-8"))

	def onMessage(self, payload, isBinary):
		obj  = json.loads(payload.decode("utf-8"))
		type = obj["type"]
		if self.mode is None and type == "hello" and obj.get("mode"):
			mode = obj["mode"]
			if mode in ("dashboard", "grabber"):
				self.mode = mode
				if mode == "grabber":
					print(f'{self.peer} is grabbing {obj["url"]}')
				elif mode == "dashboard":
					user_agent = obj.get("user_agent", "(no User-Agent)")
					print(f"{self.peer} is dashboarding with {user_agent}")
		elif self.mode == "grabber":
			if type == "download":
				self.broadcast_to_dashboards({
					"type":          type,
					"job_data":      obj["job_data"],
					"url":           obj["url"],
					"response_code": obj["response_code"],
					"wget_code":     obj["response_message"]
				})
			elif type in ("stdout", "stderr"):
				self.broadcast_to_dashboards({
					"type":     type,
					"job_data": obj["job_data"],
					"message":  obj["message"]
				})
			elif type == "ignore":
				self.broadcast_to_dashboards({
					"type":     type,
					"job_data": obj["job_data"],
					"url":      obj["url"],
					"pattern":  obj["pattern"],
				})

	# Called when we get an HTTP request instead of a WebSocket request
	def sendServerStatus(self, redirectUrl=None, redirectAfter=0):
		requestPath = self.http_request_uri.split("?")[0]
		if requestPath == "/":
			self.send_page("dashboard.html", 200, "OK", "text/html; charset=UTF-8")
		elif requestPath == "/favicon.ico":
			self.send_page("favicon.ico", 200, "OK", "image/x-icon")
		else:
			self.send_page("404.html", 404, "Not Found", "text/html; charset=UTF-8")

	# Based on AutoBahn's WebSocketServerProtocol.sendHtml
	def send_page(self, fname, code, status, content_type):
		with open(os.path.join(os.path.dirname(__file__), fname), "rb") as f:
			response_body = f.read()
		response =  f"HTTP/1.1 {code} {status}\r\n"
		response += f"Content-Type: {content_type}\r\n"
		response += f"Content-Length: {len(response_body)}\r\n"
		response += "X-Frame-Options: DENY\r\n"
		response += "\r\n"
		self.sendData(response.encode("utf-8"))
		self.sendData(response_body)


class GrabberServerFactory(WebSocketServerFactory):
	protocol = GrabberServerProtocol

	def __init__(self):
		super().__init__()
		self.clients = set()


def main():
	loop      = asyncio.get_event_loop()
	ports     = list(int(p) for p in os.environ.get("GRAB_SITE_PORT", "29000").split(","))
	factory   = GrabberServerFactory()
	interface = os.environ.get("GRAB_SITE_INTERFACE", "0.0.0.0")
	for port in ports:
		coro = loop.create_server(factory, interface, port)
		loop.run_until_complete(coro)
		print(f"grab-site server listening on {interface}:{port}")

	loop.run_forever()


if __name__ == "__main__":
	main()
