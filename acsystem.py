#!/usr/bin/python3
  
VERSION = "0.1"

import sys
import os
import asyncio
import logging
from argparse import ArgumentParser

# 3rd party
from dbus_next.aio import MessageBus
from dbus_next.constants import BusType

# aiovelib
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'ext', 'aiovelib'))
from aiovelib.service import Service as _Service
from aiovelib.service import IntegerItem, TextItem
from aiovelib.client import Service as Client
from aiovelib.client import Monitor
from aiovelib.localsettings import SettingsService as SettingsClient
from aiovelib.localsettings import Setting, SETTINGS_SERVICE

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class Service(_Service):
	def __init__(self, bus, name, service):
		super().__init__(bus, name)
		self.systeminstance = service.systeminstance
		self.subservices = { service }
		self.settings = None

		# Compulsory paths
		self.add_item(IntegerItem("/DeviceInstance",
			512 if self.systeminstance is None else self.systeminstance))
		self.add_item(TextItem("/Mgmt/ProcessName", __file__))
		self.add_item(TextItem("/Mgmt/ProcessVersion", VERSION))
		self.add_item(TextItem("/Mgmt/Connection", "local"))
		self.add_item(IntegerItem("/Connected", 1))

		# Control points
		self.add_item(IntegerItem("/Settings/Ess/MinimumSoc", None,
			writeable=True, onchange=self._set_minsoc))
		self.add_item(IntegerItem("/Settings/Ess/Mode", None,
			writeable=True, onchange=self._set_mode))
		self.add_item(IntegerItem("/Ess/AcPowerSetpoint", None,
			writeable=True))
	
	def _set_setting(self, setting, _min, _max, v):
		if _min <= v <= _max:
			for s in self.subservices:
				if s.get_value(setting) != v:
					s.set_value(setting, v)
			return True
		return False

	def _set_minsoc(self, v):
		return self._set_setting("/Settings/Ess/MinimumSoc", 0, 100, v)

	def _set_mode(self, v):
		return self._set_setting("/Settings/Ess/Mode", 0, 3, v)

	def add_service(self, service):
		self.subservices.add(service)
	
	def remove_service(self, service):
		self.subservices.discard(service)

	async def wait_for_settings(self):
		""" Attempt a connection to localsettings. """
		settingsmonitor = await SettingsMonitor.create(self.bus)
		self.settings = await asyncio.wait_for(
			settingsmonitor.wait_for_service(SETTINGS_SERVICE), 5)
		await self.settings.add_settings(
			Setting("/Settings/AcSystem/{}/AcPowerSetpoint".format(
				self.systeminstance), 0, alias="acpowersetpoint"),
			Setting("/Settings/AcSystem/{}/MultiPhaseRegulation".format(
				self.systeminstance), 0, 0, 1, alias="multiphaseregulation")
		)

	@property
	def acpowersetpoint(self):
		return self.settings.get_value(
			self.settings.alias("acpowersetpoint"))

	@property
	def multiphaseregulation(self):
		return self.settings.get_value(
			self.settings.alias("multiphaseregulation"))


class RsService(Client):
	servicetype = "com.victronenergy.multi"
	paths = {
		"/ProductId",
		"/DeviceInstance",
		"/Ac/In/1/L1/P",
		"/N2kSystemInstance",
		"/Settings/Ess/MinimumSoc",
		"/Settings/Ess/Mode",
		"/Ess/AcPowerSetpoint",
	}

	@property
	def deviceinstance(self):
		return self.get_value("/DeviceInstance")

	@property
	def systeminstance(self):
		return self.get_value("/N2kSystemInstance")

	@property
	def minsoc(self):
		return self.get_value("/Settings/Ess/MinimumSoc")

	@minsoc.setter
	def minsoc(self, v):
		self.set_value("/Settings/Ess/MinimumSoc", v)

	@property
	def mode(self):
		return self.get_value("/Settings/Ess/Mode")

	@mode.setter
	def mode(self, v):
		self.set_value("/Settings/Ess/Mode", v)

	@property
	def setpoint(self):
		return self.get_value("/Ess/AcPowerSetpoint")

	@setpoint.setter
	def setpoint(self, v):
		self.set_value("/Ess/AcPowerSetpoint", v)

class SystemMonitor(Monitor):
	synchronised_paths=(
		"/Settings/Ess/MinimumSoc",
		"/Settings/Ess/Mode"
	)

	def __init__(self, bus, make_bus):
		super().__init__(bus, handlers = {
			'com.victronenergy.multi': RsService
		})
		self._leaders = {}
		self._make_bus = make_bus

	async def serviceAdded(self, service):
		instance = service.systeminstance
		if instance in self._leaders:
			leader = await self._leaders[instance]
			leader.add_service(service)

			# Synchronise with the other units
			for p in self.synchronised_paths:
				v = leader.get_item(p).value
				if v != service.get_value(p):
					service.set_value(p, v)
		else:
			self._leaders[instance] = asyncio.Future()
			bus = await self._make_bus().connect()
			leader = Service(bus,
				"com.victronenergy.acsystem.I{}".format(instance), service)

			# Initialise service to the first found unit
			with leader as s:
				s["/Settings/Ess/MinimumSoc"] = service.minsoc
				s["/Settings/Ess/Mode"] = service.mode

			# Register on dbus, connect to localsettings
			await asyncio.gather(leader.register(), leader.wait_for_settings())
			self._leaders[instance].set_result(leader)
	
	async def serviceRemoved(self, service):
		try:
			leader = await self._leaders[service.systeminstance]
		except KeyError:
			pass
		else:
			leader.remove_service(service)
			if not leader.subservices:
				leader.__del__()
				del self._leaders[service.systeminstance]

	def itemsChanged(self, service, values):
		try:
			leader = self._leaders[service.systeminstance].result()
		except (KeyError, asyncio.InvalidStateError):
			pass
		else:
			for p, v in values.items():
				if p not in self.synchronised_paths: continue
				for s in leader.subservices:
					if s is not service:
						if s.get_value(p) != v:
							s.set_value(p, v)
				if leader.get_item(p).value != v:
					with leader as s:
						s[p] = v

class SettingsMonitor(Monitor):
	def __init__(self, bus):
		super().__init__(bus, handlers = {
			'com.victronenergy.settings': SettingsClient
		})

async def calculation_loop(monitor):
	while True:
		#for service in monitor.services:
		#	print ("name =", service.name)
		await asyncio.sleep(1)

async def settings_loop(monitor):
	while True:
		# Do something
		await asyncio.sleep(2)

async def amain(bus_type):
	bus = await MessageBus(bus_type=bus_type).connect()
	monitor = await SystemMonitor.create(bus,
		lambda: MessageBus(bus_type=bus_type))

	# Fire off update threads
	loop = asyncio.get_event_loop()
	loop.create_task(calculation_loop(monitor))
	loop.create_task(settings_loop(monitor))

	await bus.wait_for_disconnect()


def main():
	parser = ArgumentParser(description=sys.argv[0])
	parser.add_argument('--dbus', help='dbus bus to use, defaults to system',
			default='system')
	parser.add_argument('--debug', help='Turn on debug logging',
			default=False, action='store_true')
	args = parser.parse_args()

	logging.basicConfig(format='%(levelname)-8s %(message)s',
			level=(logging.DEBUG if args.debug else logging.INFO))

	bus_type = {
		"system": BusType.SYSTEM,
		"session": BusType.SESSION
	}.get(args.dbus, BusType.SYSTEM)

	mainloop = asyncio.get_event_loop()
	logger.info("Starting main loop")
	try:
		asyncio.get_event_loop().run_until_complete(amain(bus_type))
	except KeyboardInterrupt:
		logger.info("Terminating")
		pass

if __name__ == "__main__":
	main()
