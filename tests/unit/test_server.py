import json
import unittest
from unittest import mock

from tests.unit import _stubs  # noqa: F401
from libgrabsite import server


JOB_DATA = {"ident": "abc", "url": "https://example.com/", "started_at": 1.0}


def make_protocol(mode=None, dashboards=(), grabbers=()):
    """Build a protocol without running autobahn's __init__; only the fields used here are set."""
    proto = server.GrabberServerProtocol.__new__(server.GrabberServerProtocol)
    proto.mode = mode
    proto.peer = "peer"
    proto.factory = mock.Mock()
    clients = set()
    for d in dashboards:
        d.mode = "dashboard"
        clients.add(d)
    for g in grabbers:
        g.mode = "grabber"
        clients.add(g)
    proto.factory.clients = clients | {proto}
    return proto


def make_dashboard(backlog=0):
    d = mock.Mock()
    d.mode = "dashboard"
    d.backlog.return_value = backlog
    d.dropping = False
    return d


def sent_objects(dashboard):
    return [json.loads(c.args[0]) for c in dashboard.sendMessage.call_args_list]


class MalformedInputTests(unittest.TestCase):
    def setUp(self):
        self.dashboard = make_dashboard()
        self.grabber = make_protocol(mode="grabber", dashboards=[self.dashboard])

    def send(self, payload):
        self.grabber.onMessage(payload, False)

    def test_invalid_json_is_ignored(self):
        self.send(b"{not json")
        self.dashboard.sendMessage.assert_not_called()

    def test_invalid_utf8_is_ignored(self):
        self.send(b"\xff\xfe")
        self.dashboard.sendMessage.assert_not_called()

    def test_non_object_json_is_ignored(self):
        self.send(b'["download"]')
        self.dashboard.sendMessage.assert_not_called()

    def test_missing_type_is_ignored(self):
        self.send(json.dumps({"job_data": JOB_DATA}).encode())
        self.dashboard.sendMessage.assert_not_called()

    def test_missing_field_is_ignored(self):
        # 'response_message' is missing, which used to raise KeyError
        self.send(
            json.dumps(
                {
                    "type": "download",
                    "job_data": JOB_DATA,
                    "url": "https://example.com/a",
                    "response_code": 200,
                }
            ).encode()
        )
        self.dashboard.sendMessage.assert_not_called()

    def test_wrong_field_type_is_ignored(self):
        # The dashboard calls .replace() on message, so a non-string would break rendering.
        self.send(
            json.dumps({"type": "stdout", "job_data": JOB_DATA, "message": 5}).encode()
        )
        self.dashboard.sendMessage.assert_not_called()

    def test_bad_job_data_is_ignored(self):
        self.send(
            json.dumps(
                {"type": "stdout", "job_data": {"url": "x"}, "message": "hi"}
            ).encode()
        )
        self.dashboard.sendMessage.assert_not_called()

    def test_connection_survives_bad_message(self):
        self.send(b"{not json")
        self.send(
            json.dumps(
                {"type": "stdout", "job_data": JOB_DATA, "message": "ok"}
            ).encode()
        )
        self.assertEqual(len(sent_objects(self.dashboard)), 1)


class HelloTests(unittest.TestCase):
    def test_hello_without_type_is_ignored(self):
        proto = make_protocol()
        proto.onMessage(json.dumps({"mode": "grabber"}).encode(), False)
        self.assertIsNone(proto.mode)

    def test_hello_with_unknown_mode_is_ignored(self):
        proto = make_protocol()
        proto.onMessage(json.dumps({"type": "hello", "mode": "admin"}).encode(), False)
        self.assertIsNone(proto.mode)

    def test_grabber_hello_without_url_does_not_raise(self):
        proto = make_protocol()
        proto.onMessage(
            json.dumps({"type": "hello", "mode": "grabber"}).encode(), False
        )
        self.assertEqual(proto.mode, "grabber")

    def test_dashboard_hello_sets_mode(self):
        proto = make_protocol()
        proto.onMessage(
            json.dumps({"type": "hello", "mode": "dashboard"}).encode(), False
        )
        self.assertEqual(proto.mode, "dashboard")


class BroadcastTests(unittest.TestCase):
    def test_valid_download_is_forwarded_with_wget_code(self):
        d = make_dashboard()
        grabber = make_protocol(mode="grabber", dashboards=[d])
        grabber.onMessage(
            json.dumps(
                {
                    "type": "download",
                    "job_data": JOB_DATA,
                    "url": "https://example.com/a",
                    "response_code": 200,
                    "response_message": "OK",
                }
            ).encode(),
            False,
        )
        self.assertEqual(
            sent_objects(d),
            [
                {
                    "type": "download",
                    "job_data": JOB_DATA,
                    "url": "https://example.com/a",
                    "response_code": 200,
                    "wget_code": "OK",
                }
            ],
        )

    def test_encodes_once_for_all_dashboards(self):
        dashboards = [make_dashboard() for _ in range(3)]
        grabber = make_protocol(mode="grabber", dashboards=dashboards)
        message = json.dumps(
            {"type": "stdout", "job_data": JOB_DATA, "message": "hi"}
        ).encode()
        with mock.patch.object(server.json, "dumps", wraps=server.json.dumps) as dumps:
            grabber.onMessage(message, False)
        self.assertEqual(dumps.call_count, 1)
        sent = [d.sendMessage.call_args.args[0] for d in dashboards]
        self.assertIs(sent[0], sent[1])
        self.assertIs(sent[1], sent[2])

    def test_only_dashboards_receive_messages(self):
        dashboard = make_dashboard()
        other_grabber = mock.Mock()
        other_grabber.mode = "grabber"
        grabber = make_protocol(mode="grabber", dashboards=[dashboard])
        grabber.factory.clients.add(other_grabber)
        grabber.onMessage(
            json.dumps(
                {"type": "stderr", "job_data": JOB_DATA, "message": "x"}
            ).encode(),
            False,
        )
        other_grabber.sendMessage.assert_not_called()
        self.assertEqual(dashboard.sendMessage.call_count, 1)


class MainDefaultsTests(unittest.TestCase):
    def run_main(self, env):
        loop = mock.Mock()
        with (
            mock.patch.dict(server.os.environ, env, clear=True),
            mock.patch.object(server.asyncio, "new_event_loop", return_value=loop),
            mock.patch.object(server.asyncio, "set_event_loop"),
        ):
            server.main()
        return loop

    def test_binds_loopback_by_default(self):
        loop = self.run_main({})
        args = loop.create_server.call_args.args
        self.assertEqual(args[1], "127.0.0.1")
        self.assertEqual(args[2], 29000)

    def test_interface_can_be_overridden(self):
        loop = self.run_main({"GRAB_SITE_INTERFACE": "0.0.0.0"})
        self.assertEqual(loop.create_server.call_args.args[1], "0.0.0.0")

    def test_multiple_ports(self):
        loop = self.run_main({"GRAB_SITE_PORT": "29000,29001"})
        ports = [c.args[2] for c in loop.create_server.call_args_list]
        self.assertEqual(ports, [29000, 29001])


class BacklogTests(unittest.TestCase):
    def test_backlog_reads_the_transport_write_buffer(self):
        proto = make_protocol(mode="dashboard")
        proto.transport = mock.Mock()
        proto.transport.get_write_buffer_size.return_value = 42
        self.assertEqual(proto.backlog(), 42)

    def test_backlog_is_zero_before_connection(self):
        proto = make_protocol(mode="dashboard")
        self.assertEqual(proto.backlog(), 0)

    def test_stalled_dashboard_is_skipped(self):
        stalled = make_dashboard(backlog=server.MAX_DASHBOARD_BACKLOG + 1)
        healthy = make_dashboard(backlog=0)
        grabber = make_protocol(mode="grabber", dashboards=[stalled, healthy])
        grabber.onMessage(
            json.dumps(
                {"type": "stdout", "job_data": JOB_DATA, "message": "x"}
            ).encode(),
            False,
        )
        stalled.sendMessage.assert_not_called()
        self.assertEqual(healthy.sendMessage.call_count, 1)

    def test_dashboard_resumes_when_backlog_clears(self):
        dashboard = make_dashboard(backlog=server.MAX_DASHBOARD_BACKLOG + 1)
        grabber = make_protocol(mode="grabber", dashboards=[dashboard])
        message = json.dumps(
            {"type": "stdout", "job_data": JOB_DATA, "message": "x"}
        ).encode()
        grabber.onMessage(message, False)
        dashboard.backlog.return_value = 0
        grabber.onMessage(message, False)
        self.assertEqual(dashboard.sendMessage.call_count, 1)


if __name__ == "__main__":
    unittest.main()
