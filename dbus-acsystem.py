#!/usr/bin/python3
  
VERSION = "0.1"

import sys
import os
import asyncio
import logging
from argparse import ArgumentParser
from collections import defaultdict

# 3rd party
from dbus_next.aio import MessageBus
from dbus_next.constants import BusType

# aiovelib
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'ext', 'aiovelib'))
from aiovelib.service import Service as _Service
from aiovelib.service import IntegerItem, TextItem, DoubleItem
from aiovelib.client import Service as Client
from aiovelib.client import Monitor
from aiovelib.localsettings import SettingsService as SettingsClient
from aiovelib.localsettings import Setting, SETTINGS_SERVICE

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def safe_add(*args):
	args = [x for x in args if x is not None]
	return sum(args) if args else None

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

		# AC summary
		self.add_item(IntegerItem("/Ac/NumberOfAcInputs", None))
		self.add_item(IntegerItem("/Ac/NumberOfPhases", None))
		for phase in range(1, 4):
			for inp in range(1, 3):
				self.add_item(IntegerItem(f"/Ac/In/{inp}/L{phase}/P", None))
				self.add_item(DoubleItem(f"/Ac/In/{inp}/L{phase}/I", None))

			self.add_item(IntegerItem(f"/Ac/Out/L{phase}/P", None))
			self.add_item(IntegerItem(f"/Ac/Out/L{phase}/I", None))

		# Custom Name
		self.add_item(TextItem("/CustomName", None,
			writeable=True, onchange=self._set_customname))

		# Control points
		self.add_item(DoubleItem("/Ac/In/1/CurrentLimit", None,
			writeable=True,
			onchange=lambda v: self._sync_value("/Ac/In/1/CurrentLimit", v)))
		self.add_item(DoubleItem("/Ac/In/2/CurrentLimit", None,
			writeable=True,
			onchange=lambda v: self._sync_value("/Ac/In/2/CurrentLimit", v)))
		self.add_item(IntegerItem("/Settings/Ess/MinimumSoc", None,
			writeable=True, onchange=self._set_minsoc))
		self.add_item(IntegerItem("/Settings/Ess/Mode", None,
			writeable=True, onchange=self._set_mode))
		self.add_item(IntegerItem("/Ess/AcPowerSetpoint", None,
			writeable=True, onchange=self._set_setpoints))
	
	def _set_setting(self, setting, _min, _max, v):
		if _min <= v <= _max:
			return self._sync_value(setting, v)
		return False

	def _sync_value(self, path, v):
		for s in self.subservices:
			if s.get_value(path) != v:
				s.set_value(path, v)
		return True

	def _set_minsoc(self, v):
		return self._set_setting("/Settings/Ess/MinimumSoc", 0, 100, v)

	def _set_mode(self, v):
		return self._set_setting("/Settings/Ess/Mode", 0, 3, v)

	def _set_setpoints(self, v):
		phasecount = self.get_item("/Ac/NumberOfPhases").value
		# Per phase
		try:
			setpoint = v / phasecount
		except (TypeError, ZeroDivisionError):
			pass
		else:
			for service in self.subservices:
				service.setpoint = setpoint
		return True

	def _set_customname(self, v):
		cn = self.settings.get_value(self.settings.alias("customname"))
		if cn != v:
			self.settings.set_value(self.settings.alias("customname"), v)
		return True

	@property
	def acpowersetpoint(self):
		return self.get_item("/Ess/AcPowerSetpoint").value

	def add_service(self, service):
		self.subservices.add(service)
	
	def remove_service(self, service):
		self.subservices.discard(service)

	async def wait_for_settings(self):
		""" Attempt a connection to localsettings. """
		settingsmonitor = await SettingsMonitor.create(self.bus,
			itemsChanged=self.itemsChanged)
		self.settings = await asyncio.wait_for(
			settingsmonitor.wait_for_service(SETTINGS_SERVICE), 5)
		await self.settings.add_settings(
			Setting("/Settings/AcSystem/{}/Customname".format(
				self.systeminstance), "", alias="customname"),
		)

	async def init(self):
		await self.wait_for_settings()
		self.customname = self.settings.get_value(
			self.settings.alias("customname"))

	def itemsChanged(self, service, values):
		try:
			self.customname = values[self.settings.alias('customname')]
		except KeyError:
			pass # Not a customname change

	@property
	def customname(self):
		return self.get_item("/Customname").value

	@customname.setter
	def customname(self, v):
		self.get_item("/CustomName").set_value(v)

class RsService(Client):
	servicetype = "com.victronenergy.multi"
	paths = {
		"/ProductId",
		"/DeviceInstance",
		"/Devices/0/Gateway",
		"/Ac/In/1/L1/P", "/Ac/In/2/L1/P", "/Ac/Out/L1/P",
		"/Ac/In/1/L2/P", "/Ac/In/2/L2/P", "/Ac/Out/L2/P",
		"/Ac/In/1/L3/P", "/Ac/In/2/L3/P", "/Ac/Out/L3/P",
		"/Ac/In/1/L1/I", "/Ac/In/2/L1/I", "/Ac/Out/L1/I",
		"/Ac/In/1/L2/I", "/Ac/In/2/L2/I", "/Ac/Out/L2/I",
		"/Ac/In/1/L3/I", "/Ac/In/2/L3/I", "/Ac/Out/L3/I",
		"/Ac/In/1/CurrentLimit", "/Ac/In/2/CurrentLimit",
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
	def gateway(self):
		return self.get_value("/Devices/0/Gateway") or ""

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

	def ac_currentlimit(self, i):
		return self.get_value(f"/Ac/In/{i}/CurrentLimit")

class SystemMonitor(Monitor):
	synchronised_paths=(
		"/Ac/In/1/CurrentLimit",
		"/Ac/In/2/CurrentLimit",
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
		if instance is None:
			return # Firmware is old, or it is still starting up

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
			gateway = service.gateway.replace(":", "_")
			leader = Service(bus,
				f"com.victronenergy.acsystem.{gateway}_sys{instance}", service)

			# Initialise service to the first found unit
			with leader as s:
				s["/Settings/Ess/MinimumSoc"] = service.minsoc
				s["/Settings/Ess/Mode"] = service.mode
				s["/Ac/In/1/CurrentLimit"] = service.ac_currentlimit(1)
				s["/Ac/In/2/CurrentLimit"] = service.ac_currentlimit(2)

			# Register on dbus, connect to localsettings
			await asyncio.gather(leader.register(), leader.init())
			self._leaders[instance].set_result(leader)
	
	async def serviceRemoved(self, service):
		for leader in list(self.leaders):
			leader.remove_service(service)
			if not leader.subservices:
				leader.__del__()
				del self._leaders[leader.systeminstance]

	async def change_systeminstance(self, service):
		await self.serviceRemoved(service)
		await self.serviceAdded(service)

	def itemsChanged(self, service, values):
		# If the N2kSystemInstance changes, remove and add the service
		# again so it ends up in the right system.
		if '/N2kSystemInstance' in values.keys():
			asyncio.create_task(self.change_systeminstance(service))
			return
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

	@property
	def leaders(self):
		return iter(s.result() for s in self._leaders.values() if s.done())

class SettingsMonitor(Monitor):
	def __init__(self, bus, **kwargs):
		super().__init__(bus, handlers = {
			'com.victronenergy.settings': SettingsClient
		}, **kwargs)

async def calculation_loop(monitor):
	while True:
		for leader in monitor.leaders:
			# Sum power and current values over all units in the system
			values = defaultdict(lambda: None)
			for service in leader.subservices:
				for phase in range(1, 4):
					for inp in range(1, 3):
						b = f"/Ac/In/{inp}/L{phase}/"
						for p in (b + "P", b + "I"):
							values[p] = safe_add(values[p], service.get_value(p))

					b = f"/Ac/Out/L{phase}/"
					for p in (b + "P", b + "I"):
						values[p] = safe_add(values[p], service.get_value(p))

			# Number of inputs/phases
			has_input1 = any(values[f"/Ac/In/1/L{x}/P"] is not None 
				for x in range (1, 4))
			has_input2 = any(values[f"/Ac/In/2/L{x}/P"] is not None 
				for x in range (1, 4))
			values["/Ac/NumberOfAcInputs"] = int(has_input1) + int (has_input2)

			# Number of phases, we will use the outputs to detect that
			values["/Ac/NumberOfPhases"] = sum(int(values[f"/Ac/Out/L{x}/P"] is not None) for x in range(1, 4))

			with leader as s:
				for p, v in values.items():
					s[p] = v

		await asyncio.sleep(1)

async def amain(bus_type):
	bus = await MessageBus(bus_type=bus_type).connect()
	monitor = await SystemMonitor.create(bus,
		lambda: MessageBus(bus_type=bus_type))

	# Fire off update threads
	loop = asyncio.get_event_loop()
	loop.create_task(calculation_loop(monitor))

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