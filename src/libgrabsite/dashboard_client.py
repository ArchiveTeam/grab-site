import json
import asyncio
import logging
import websockets

logger = logging.getLogger(__name__)


class Decayer:
    def __init__(self, initial, multiplier, maximum):
        """
        initial    - initial number to return
        multiplier - multiply number by this value after each call to decay()
        maximum    - cap number at this value
        """
        self.initial = initial
        self.multiplier = multiplier
        self.maximum = maximum
        self.reset()

    def reset(self):
        # First call to .decay() will multiply, but we want to get the `intitial`
        # value on the first call to .decay(), so divide.
        self.current = self.initial / self.multiplier
        return self.current

    def decay(self):
        self.current = min(self.current * self.multiplier, self.maximum)
        return self.current


async def send_object(ws, obj):
    await ws.send(json.dumps(obj).encode("utf-8"))


async def sender(plugin, uri):
    decayer = Decayer(0.25, 1.5, 8)
    # A message already taken from the queue but not yet sent. It is kept across
    # reconnects, so a failed send is retried rather than lost.
    pending = None
    while True:
        try:
            async with websockets.connect(uri) as ws:
                logger.info("Connected to %s", uri)
                decayer.reset()
                await send_object(
                    ws,
                    {"type": "hello", "mode": "grabber", "url": plugin.job_data["url"]},
                )
                while True:
                    if pending is None:
                        obj = await plugin.ws_queue.get()
                        try:
                            pending = json.dumps(obj).encode("utf-8")
                        except (TypeError, ValueError):
                            # Retrying can't help, so drop it rather than loop on it.
                            logger.exception("Dropping message that cannot be encoded")
                            plugin.ws_queue.task_done()
                            continue
                    await ws.send(pending)
                    pending = None
                    plugin.ws_queue.task_done()
        except Exception as e:
            delay = decayer.decay()
            logger.warning("Disconnected from ws:// server: %r", e)
            logger.info("Reconnecting in %.2f s", delay)
            await asyncio.sleep(delay)
