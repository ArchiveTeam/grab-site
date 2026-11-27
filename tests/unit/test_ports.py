import os
import unittest
from unittest import mock

import libgrabsite


class ParsePortsTests(unittest.TestCase):
    def test_default(self):
        with mock.patch.dict(os.environ, clear=False):
            os.environ.pop("GRAB_SITE_PORT", None)
            self.assertEqual(libgrabsite.parse_ports(), [29000])

    def test_single(self):
        self.assertEqual(libgrabsite.parse_ports("1234"), [1234])

    def test_list_with_spaces_and_trailing_comma(self):
        self.assertEqual(libgrabsite.parse_ports("29000, 29001,"), [29000, 29001])

    def test_reads_environment(self):
        with mock.patch.dict(os.environ, {"GRAB_SITE_PORT": "29000,29001"}):
            self.assertEqual(libgrabsite.parse_ports(), [29000, 29001])

    def test_empty_is_error(self):
        with self.assertRaises(ValueError):
            libgrabsite.parse_ports(",")

    def test_garbage_is_error(self):
        with self.assertRaises(ValueError):
            libgrabsite.parse_ports("abc")


class InitWsPortTests(unittest.TestCase):
    def test_client_uses_first_port_of_list(self):
        from libgrabsite import wpull_hooks as wh

        p = wh.GrabSitePlugin.__new__(wh.GrabSitePlugin)
        p.loop = mock.Mock()
        env = {"GRAB_SITE_PORT": "29000,29001", "GRAB_SITE_HOST": "h"}
        with (
            mock.patch.dict(os.environ, env),
            mock.patch.object(wh.dashboard_client, "sender") as sender,
        ):
            p.init_ws()
        self.assertEqual(sender.call_args.args[1], "ws://h:29000")
