#!/usr/bin/env python3

import txaio

txaio.use_asyncio()
import os
import json
import asyncio
import logging
from autobahn.asyncio.websocket import WebSocketServerFactory, WebSocketServerProtocol
from libgrabsite import dashboard_assets, log_level, parse_ports

logger = logging.getLogger(__name__)


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
        logger.info("%s connected", self.peer)
        self.factory.clients.add(self)

    def onClose(self, wasClean, code, reason):
        self.factory.clients.discard(self)
        logger.info(
            "%s disconnected (%d connected)", self.peer, len(self.factory.clients)
        )

    def onMessage(self, payload, isBinary):
        try:
            obj = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            logger.warning(
                "%s sent a message that is not valid JSON; ignoring it", self.peer
            )
            return
        if not isinstance(obj, dict):
            logger.warning(
                "%s sent a message that is not a JSON object; ignoring it", self.peer
            )
            return
        type = obj.get("type")
        if self.mode is None:
            self.handle_hello(obj)
        elif self.mode == "grabber":
            self.handle_grabber_message(type, obj)

    def handle_hello(self, obj):
        if obj.get("type") != "hello":
            logger.warning(
                "%s sent %r before hello; ignoring it", self.peer, obj.get("type")
            )
            return
        mode = obj.get("mode")
        if mode == "grabber":
            self.mode = mode
            logger.info("%s is grabbing %s", self.peer, obj.get("url"))
        elif mode == "dashboard":
            self.mode = mode
            user_agent = obj.get("user_agent", "(no User-Agent)")
            logger.info("%s is dashboarding with %s", self.peer, user_agent)
        else:
            logger.warning(
                "%s sent hello with unknown mode %r; ignoring it", self.peer, mode
            )

    def handle_grabber_message(self, type, obj):
        if type not in GRABBER_MESSAGE_FIELDS:
            logger.debug("%s sent unknown type %r; ignoring it", self.peer, type)
            return
        job_data = obj.get("job_data")
        if not isinstance(job_data, dict):
            logger.warning("%s sent %s without job_data; ignoring it", self.peer, type)
            return
        missing = _has_fields(job_data, JOB_DATA_FIELDS)
        if missing is not None:
            logger.warning(
                "%s sent job_data with bad or missing %r; ignoring it",
                self.peer,
                missing,
            )
            return
        missing = _has_fields(obj, GRABBER_MESSAGE_FIELDS[type])
        if missing is not None:
            logger.warning(
                "%s sent %s with bad or missing %r; ignoring it",
                self.peer,
                type,
                missing,
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
        asset = dashboard_assets.lookup(requestPath)
        if asset is not None:
            self.send_page(asset.file, 200, "OK", asset.content_type)
        else:
            self.send_page(
                dashboard_assets.NOT_FOUND_PAGE, 404, "Not Found", dashboard_assets.HTML
            )

    # Based on AutoBahn's WebSocketServerProtocol.sendHtml
    def send_page(self, fname, code, status, content_type):
        with open(os.path.join(os.path.dirname(__file__), fname), "rb") as f:
            response_body = f.read()
        response = f"HTTP/1.1 {code} {status}\r\n"
        response += f"Content-Type: {content_type}\r\n"
        response += f"Content-Length: {len(response_body)}\r\n"
        # Revalidate on every load so an upgrade never leaves a stale module cached.
        response += "Cache-Control: no-cache\r\n"
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
    logging.basicConfig(
        level=log_level(), format="%(asctime)s %(levelname)-7s %(message)s"
    )
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    ports = parse_ports()
    factory = GrabberServerFactory()
    # Loopback by default: the dashboard has no authentication, so anyone who
    # can reach the port could inject events. Set GRAB_SITE_INTERFACE to expose it.
    interface = os.environ.get("GRAB_SITE_INTERFACE", "127.0.0.1")
    for port in ports:
        coro = loop.create_server(factory, interface, port)
        loop.run_until_complete(coro)
        logger.info("grab-site server listening on %s:%s", interface, port)

    loop.run_forever()


if __name__ == "__main__":
    main()
