"""
Make libgrabsite importable for unit tests.

Third-party packages (wpull, click, re2, websockets, ...) are replaced with
minimal stand-ins *only if they are not installed*, so the pure-Python logic can
be tested without the full crawler stack.  When the real packages are present
they are used as-is.
"""

import importlib
import os
import re
import sys
import tempfile
import types

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
_WORKING_DIR = tempfile.mkdtemp(prefix="grabsite-unit-")


def _available(name):
	try:
		importlib.import_module(name)
		return True
	except ImportError:
		return False


def _module(name, **attrs):
	mod = types.ModuleType(name)
	mod.__dict__.update(attrs)
	sys.modules[name] = mod
	parent, _, child = name.rpartition(".")
	if parent and parent in sys.modules:
		setattr(sys.modules[parent], child, mod)
	return mod


def _identity_decorator(*_args, **_kwargs):
	return lambda f: f


def install():
	if _SRC not in sys.path:
		sys.path.insert(0, _SRC)

	os.environ.setdefault("GRAB_SITE_WORKING_DIR", _WORKING_DIR)
	os.environ.setdefault("DUPESPOTTER_ENABLED", "0")

	if not _available("click"):
		_module("click",
			command=_identity_decorator, option=_identity_decorator,
			argument=_identity_decorator, echo=print,
			Choice=lambda *a, **k: None)

	if not _available("re2"):
		_module("re2", compile=re.compile, error=re.error)

	if not _available("websockets"):
		_module("websockets", connect=None)

	if not _available("wpull"):
		class Actions:
			NORMAL = "NORMAL"
			FINISH = "FINISH"
			STOP = "STOP"
			RETRY = "RETRY"

		class PluginFunctions:
			accept_url = "accept_url"
			queued_url = "queued_url"
			dequeued_url = "dequeued_url"
			handle_response = "handle_response"
			handle_error = "handle_error"
			handle_pre_response = "handle_pre_response"
			exit_status = "exit_status"
			wait_time = "wait_time"
			get_urls = "get_urls"

		class WpullPlugin:
			def activate(self):
				pass

		class SQLiteURLTable:
			@classmethod
			def _apply_pragmas_callback(cls, connection, record):
				pass

		class ProcessingRule:
			def __init__(self, *args, **kwargs):
				pass

			def scrape_document(self, item_session):
				pass

		class HTMLReader:
			@staticmethod
			def is_response(response):
				return False

		for name in ("wpull", "wpull.application", "wpull.pipeline",
				"wpull.database", "wpull.document", "wpull.processor"):
			_module(name)
		_module("wpull.application.hook", Actions=Actions)
		_module("wpull.application.plugin", WpullPlugin=WpullPlugin,
			PluginFunctions=PluginFunctions, hook=_identity_decorator,
			event=_identity_decorator)
		_module("wpull.pipeline.app", AppSession=object)
		_module("wpull.pipeline.item", URLRecord=object)
		_module("wpull.pipeline.session", ItemSession=object)
		_module("wpull.url", URLInfo=object)
		_module("wpull.database.sqltable", SQLiteURLTable=SQLiteURLTable)
		_module("wpull.document.html", HTMLReader=HTMLReader)
		_module("wpull.processor.rule", ProcessingRule=ProcessingRule)


install()
