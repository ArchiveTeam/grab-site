import asyncio
import json
import types
import unittest
from unittest import mock

from tests.unit import _stubs  # noqa: F401
from libgrabsite import dashboard_client as dc
from libgrabsite.dashboard_client import Decayer


class DecayerTests(unittest.TestCase):
    def test_first_decay_returns_initial(self):
        self.assertAlmostEqual(Decayer(0.25, 1.5, 8).decay(), 0.25)

    def test_multiplies_each_call(self):
        d = Decayer(1, 2, 100)
        self.assertEqual([d.decay() for _ in range(4)], [1, 2, 4, 8])

    def test_capped_at_maximum(self):
        d = Decayer(1, 2, 5)
        self.assertEqual([d.decay() for _ in range(5)], [1, 2, 4, 5, 5])

    def test_reset_restarts_sequence(self):
        d = Decayer(1, 2, 100)
        for _ in range(3):
            d.decay()
        d.reset()
        self.assertEqual(d.decay(), 1)


class FakeConnection:
    def __init__(self, sent, fail_after):
        self.sent = sent
        self.fail_after = fail_after
        self.count = 0

    async def send(self, data):
        if self.fail_after is not None and self.count >= self.fail_after:
            raise OSError("connection reset")
        self.count += 1
        self.sent.append(json.loads(data))


class FakeConnect:
    """Each call is one connection; fail_after says how many sends it allows."""

    def __init__(self, sent, plans):
        self.sent = sent
        self.plans = list(plans)

    def __call__(self, uri):
        fail_after = self.plans.pop(0) if self.plans else None
        conn = FakeConnection(self.sent, fail_after)

        class Ctx:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, *exc):
                return False

        return Ctx()


class SenderRetryTests(unittest.TestCase):
    def run_sender(self, queued, plans):
        sent = []

        async def scenario():
            plugin = types.SimpleNamespace(
                job_data={"url": "http://a.test/"}, ws_queue=asyncio.Queue()
            )
            for obj in queued:
                plugin.ws_queue.put_nowait(obj)
            with mock.patch.object(dc.websockets, "connect", FakeConnect(sent, plans)):
                try:
                    await asyncio.wait_for(dc.sender(plugin, "ws://x"), timeout=1.5)
                except asyncio.TimeoutError:
                    pass

        asyncio.run(scenario())
        return [o for o in sent if o.get("type") != "hello"]

    def test_message_is_resent_after_reconnect(self):
        # Connection 1 sends hello and msg1, then fails on msg2.
        # Connection 2 must send msg2 rather than dropping it.
        delivered = self.run_sender([{"type": "a"}, {"type": "b"}], plans=[2, None])
        self.assertEqual([o["type"] for o in delivered], ["a", "b"])

    def test_unserializable_message_is_dropped_not_retried_forever(self):
        delivered = self.run_sender([object(), {"type": "after"}], plans=[None])
        self.assertEqual([o["type"] for o in delivered], ["after"])


if __name__ == "__main__":
    unittest.main()
