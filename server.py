#!/usr/bin/env python3

import os
import asyncio
from autobahn.asyncio.websocket import WebSocketServerFactory, WebSocketServerProtocol

class MyServerProtocol(WebSocketServerProtocol):
	def onConnect(self, request):
		print("Client connecting: {}".format(request.peer))

	def onMessage(self, payload, isBinary):
		print(payload)
		#self.sendMessage(payload, isBinary)


def main():
	factory = WebSocketServerFactory()
	factory.protocol = MyServerProtocol

	loop = asyncio.get_event_loop()
	port = int(os.environ.get('GRAB_SITE_WS_PORT', 29000))
	coro = loop.create_server(factory, '127.0.0.1', port)
	server = loop.run_until_complete(coro)
	loop.run_forever()


if __name__ == '__main__':
	main()
