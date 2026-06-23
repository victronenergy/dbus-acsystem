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
