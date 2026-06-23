""" Wiring for the acsystem tests. The reusable doubles (MockMonitor,
	MockSettingsMonitor) live in aiovelib; here we only combine them with the
	acsystem code and provide a fake bus for the produced leader service. """

from conftest import load_acsystem

from aiovelib.test.client import MockMonitor
from aiovelib.test.localsettings import MockSettingsMonitor

acsystem = load_acsystem()


class FakeBus:
	""" No-op bus good enough for the leader's provider Service: it only needs
	    export/unexport, name (de)registration and send. connect() returns the
	    bus itself so it doubles as the make_bus factory's product. """

	def export(self, path, interface):
		pass

	def unexport(self, path):
		pass

	async def request_name(self, name):
		pass

	async def release_name(self, name):
		pass

	def send(self, msg):
		pass

	async def connect(self):
		return self


def make_bus():
	""" Factory matching the make_bus argument SystemMonitor calls as
	    self._make_bus().connect(). """
	return FakeBus()


class MockSystemMonitor(MockMonitor, acsystem.SystemMonitor):
	""" SystemMonitor driven in-process: SystemMonitor.__init__ still runs
	    (wiring handlers and make_bus), but discovery comes from
	    MockMonitor.add_service() instead of a real bus. """
	pass


def patch_settings(monkeypatch):
	""" Make the leader's wait_for_settings() use the in-memory localsettings
	    double instead of a real SettingsMonitor. """
	monkeypatch.setattr(acsystem, "SettingsMonitor", MockSettingsMonitor)


def build_unit_values(instance=1, gateway="aa:bb", deviceinstance=256):
	""" A realistic com.victronenergy.multi value set: the essential paths
	    plus the device-info and control paths the leader reads at startup. """
	return {
		"/N2kSystemInstance": instance,
		"/FirmwareVersion": 0x11713,
		"/ProductId": 0xA442,            # Multi RS range
		"/DeviceInstance": deviceinstance,
		"/Devices/0/Gateway": gateway,
		"/Devices/0/Nad": 0,
		"/Mode": 3,
		"/State": 9,                     # inverting
		"/Ac/ActiveIn/ActiveInput": 0,
		"/Ac/In/1/CurrentLimit": 16.0,
		"/Ac/In/2/CurrentLimit": 16.0,
		"/Ac/In/1/Type": 1,
		"/Ac/In/2/Type": 0,
		"/Settings/Ess/MinimumSocLimit": 10.0,
		"/Settings/Ess/Mode": 1,
		"/Ess/DisableFeedIn": 0,
		"/Ess/UseInverterPowerSetpoint": 0,
	}
