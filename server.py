#!/usr/bin/env python3

import os
import asyncio
import aiohttp.web
from autobahn.asyncio.websocket import WebSocketServerFactory, WebSocketServerProtocol

class MyServerProtocol(WebSocketServerProtocol):
	def onConnect(self, request):
		print("Client connecting: {}".format(request.peer))

	def onMessage(self, payload, isBinary):
		print(payload)
		#self.sendMessage(payload, isBinary)


dashboardHtml = open(os.path.join(os.path.dirname(__file__), "dashboard.html"), "rb").read()

@asyncio.coroutine
def dashboard(request):
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

	wsFactory = WebSocketServerFactory()
	wsFactory.protocol = MyServerProtocol
	wsCoro = loop.create_server(wsFactory, wsInterface, wsPort)
	loop.run_until_complete(wsCoro)

	print("HTTP server started on {}:{}".format(httpInterface, httpPort))
	print("WebSocket server started on {}:{}".format(wsInterface, wsPort))

	loop.run_forever()


if __name__ == '__main__':
	main()
