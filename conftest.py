""" Pytest bootstrap for the dbus-acsystem test suite.

	Puts the repo root and the bundled aiovelib on sys.path (the running
	service does the same at startup, see dbus-acsystem.py), and loads the
	hyphenated main module by path so tests can reach Service / SystemMonitor.
"""

import os
import sys
import importlib.util

import pytest

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
AIOVELIB = os.path.join(REPO_ROOT, "ext", "aiovelib")

for path in (REPO_ROOT, AIOVELIB):
	if path not in sys.path:
		sys.path.insert(0, path)

_acsystem_module = None

def load_acsystem():
	""" Import dbus-acsystem.py (hyphen -> not a normal module name) once, by
	    file path, and cache it. """
	global _acsystem_module
	if _acsystem_module is None:
		spec = importlib.util.spec_from_file_location(
			"dbus_acsystem", os.path.join(REPO_ROOT, "dbus-acsystem.py"))
		module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(module)
		_acsystem_module = module
	return _acsystem_module

@pytest.fixture
def acsystem():
	""" The loaded dbus-acsystem module (acsystem.Service, .SystemMonitor). """
	return load_acsystem()
