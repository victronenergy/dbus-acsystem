""" First in-process tests for the acsystem aggregator: a com.victronenergy.multi
	unit appearing should create a leader and publish a new
	com.victronenergy.acsystem.* service. """

from helpers import (
	MockSystemMonitor, make_bus, patch_settings, build_unit_values, FakeBus)

MULTI = "com.victronenergy.multi.test"


async def test_leader_created_for_new_unit(monkeypatch):
	patch_settings(monkeypatch)

	monitor = await MockSystemMonitor.create(FakeBus(), make_bus)
	rs = await monitor.add_service(MULTI, build_unit_values(instance=1))

	leader = monitor.get_leader(1)
	assert leader is not None
	# gateway "aa:bb" -> "aa_bb" in the service name
	assert leader.name == "com.victronenergy.acsystem.aa_bb_sys1"
	assert rs in leader.subservices


async def test_acsystem_service_customname(monkeypatch):
	patch_settings(monkeypatch)

	monitor = await MockSystemMonitor.create(FakeBus(), make_bus)
	await monitor.add_service(MULTI, build_unit_values(instance=1))

	leader = monitor.get_leader(1)
	# init() resolved the in-memory localsettings double and applied the
	# default (empty) CustomName, falling back to the generated name.
	assert leader.customname == "AC system (1)"


class NameBus(FakeBus):
	""" FakeBus that models dbus name ownership: a second request for a name
	    that is still owned is queued, as with the real daemon. """
	owners = {}

	async def request_name(self, name):
		self.owners.setdefault(name, self)

	async def release_name(self, name):
		if self.owners.get(name) is self:
			del self.owners[name]


async def test_readded_unit_replaces_leader_on_dbus(monkeypatch):
	patch_settings(monkeypatch)
	NameBus.owners = {}

	monitor = await MockSystemMonitor.create(FakeBus(), lambda: NameBus())
	rs = await monitor.add_service(MULTI, build_unit_values(instance=1))
	old = monitor.get_leader(1)

	# Same path dbus-acsystem takes when /N2kSystemInstance changes
	await monitor.systemInstanceChanged(rs)
	new = monitor.get_leader(1)
	assert new is not old

	# The new leader must own the name, not the torn-down one
	assert NameBus.owners[new.name] is new.bus

	monitor.update_service(MULTI, {"/Ess/ActiveSocLimit": 10.0})
	assert new.get_item("/Ess/ActiveSocLimit").value == 10.0
