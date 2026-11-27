#!/usr/bin/env python3

import txaio

txaio.use_asyncio()
import os
import json
import asyncio
from autobahn.asyncio.websocket import WebSocketServerFactory, WebSocketServerProtocol


# Fields a grabber must send, per message type, and the Python type each must have.
# Anything else is dropped, so the dashboard never receives a message it
# cannot render.
GRABBER_MESSAGE_FIELDS = {
    "download": {"url": str, "response_code": int, "response_message": str},
    "stdout": {"message": str},
    "stderr": {"message": str},
    "ignore": {"url": str, "pattern": str},
}

JOB_DATA_FIELDS = {"ident": str, "url": str, "started_at": (int, float, str)}


def _has_fields(obj, fields):
    """Return the name of the first field in fields that is missing or has the wrong type, or None."""
    for name, expected in fields.items():
        if name not in obj or not isinstance(obj[name], expected):
            return name
    return None


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

    def onMessage(self, payload, isBinary):
        try:
            obj = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            print(f"{self.peer} sent a message that is not valid JSON; ignoring it")
            return
        if not isinstance(obj, dict):
            print(f"{self.peer} sent a message that is not a JSON object; ignoring it")
            return
        type = obj.get("type")
        if self.mode is None:
            self.handle_hello(obj)
        elif self.mode == "grabber":
            self.handle_grabber_message(type, obj)

    def handle_hello(self, obj):
        if obj.get("type") != "hello":
            return
        mode = obj.get("mode")
        if mode == "grabber":
            self.mode = mode
            print(f"{self.peer} is grabbing {obj.get('url')}")
        elif mode == "dashboard":
            self.mode = mode
            user_agent = obj.get("user_agent", "(no User-Agent)")
            print(f"{self.peer} is dashboarding with {user_agent}")

    def handle_grabber_message(self, type, obj):
        if type not in GRABBER_MESSAGE_FIELDS:
            return
        job_data = obj.get("job_data")
        if not isinstance(job_data, dict):
            print(f"{self.peer} sent {type} without job_data; ignoring it")
            return
        missing = _has_fields(job_data, JOB_DATA_FIELDS)
        if missing is not None:
            print(
                f"{self.peer} sent job_data with bad or missing {missing!r}; ignoring it"
            )
            return
        missing = _has_fields(obj, GRABBER_MESSAGE_FIELDS[type])
        if missing is not None:
            print(
                f"{self.peer} sent {type} with bad or missing {missing!r}; ignoring it"
            )
            return

        if type == "download":
            self.broadcast_to_dashboards(
                {
                    "type": type,
                    "job_data": job_data,
                    "url": obj["url"],
                    "response_code": obj["response_code"],
                    "wget_code": obj["response_message"],
                }
            )
        elif type in ("stdout", "stderr"):
            self.broadcast_to_dashboards(
                {
                    "type": type,
                    "job_data": job_data,
                    "message": obj["message"],
                }
            )
        elif type == "ignore":
            self.broadcast_to_dashboards(
                {
                    "type": type,
                    "job_data": job_data,
                    "url": obj["url"],
                    "pattern": obj["pattern"],
                }
            )

    def broadcast_to_dashboards(self, obj):
        # Encode once, then send the same bytes to every dashboard.
        payload = json.dumps(obj).encode("utf-8")
        for client in self.factory.clients:
            if client.mode == "dashboard":
                client.sendMessage(payload)

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
        response = f"HTTP/1.1 {code} {status}\r\n"
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
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    ports = list(int(p) for p in os.environ.get("GRAB_SITE_PORT", "29000").split(","))
    factory = GrabberServerFactory()
    # Loopback by default: the dashboard has no authentication, so anyone who
    # can reach the port could inject events. Set GRAB_SITE_INTERFACE to expose it.
    interface = os.environ.get("GRAB_SITE_INTERFACE", "127.0.0.1")
    for port in ports:
        coro = loop.create_server(factory, interface, port)
        loop.run_until_complete(coro)
        print(f"grab-site server listening on {interface}:{port}")

    loop.run_forever()


if __name__ == "__main__":
    main()
