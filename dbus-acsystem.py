#!/usr/bin/python3
  
VERSION = "0.22"

import sys
import os
import asyncio
import logging
from argparse import ArgumentParser
from collections import defaultdict

# 3rd party
try:
	from dbus_fast.aio import MessageBus
	from dbus_fast.constants import BusType
except ImportError:
	from dbus_next.aio import MessageBus
	from dbus_next.constants import BusType

# aiovelib
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'ext', 'aiovelib'))
from aiovelib.service import Service as _Service
from aiovelib.service import IntegerItem, TextItem, DoubleItem
from aiovelib.client import Monitor
from aiovelib.localsettings import Setting, SETTINGS_SERVICE

# local
from rsservice import RsService
from settings import SettingsMonitor

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def safe_add(*args):
	args = [x for x in args if x is not None]
	return sum(args) if args else None

def safe_first(*args):
	for a in args:
		if a is not None:
			return a
	return None

# Formatters

format_w = lambda v: f"{v:.0f} W"
format_a = lambda v: f"{v:.1f} A"
format_v = lambda v: f"{v:.2f} V"
format_f = lambda v: f"{v:.1f} Hz"

def format_input_type(v):
	return {
		0: 'Not used',
		1: 'Grid',
		2: 'Genset',
		3: 'Shore'
	}.get(v, 'Unknown')

class ForcedIntegerItem(IntegerItem):
	def __init__(self, onwrite, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.onwrite = onwrite

	def set_value(self, v):
		# Override so we can react on writes even if they don't change
		# the internal value
		self.onwrite(v)
		return super().set_value(v)

class Service(_Service):
	def __init__(self, bus, name, service):
		super().__init__(bus, name)
		self.systeminstance = service.systeminstance
		self.subservices = { service }
		self.settings = None

		# Compulsory paths
		self.add_item(IntegerItem("/ProductId", None))
		self.add_item(TextItem("/ProductName", None))
		self.add_item(IntegerItem("/DeviceInstance",
			512 if self.systeminstance is None else self.systeminstance))
		self.add_item(TextItem("/Mgmt/ProcessName", __file__))
		self.add_item(TextItem("/Mgmt/ProcessVersion", VERSION))
		self.add_item(TextItem("/Mgmt/Connection", "local"))
		self.add_item(IntegerItem("/Connected", 1))

		self.add_item(IntegerItem("/State", None))
		self.add_item(IntegerItem("/Ac/ActiveIn/ActiveInput", None))
		self._add_device_info(service)

		# AC summary
		self.add_item(IntegerItem("/Ac/NumberOfAcInputs", None))
		self.add_item(IntegerItem("/Ac/NumberOfPhases", None))
		for phase in range(1, 4):
			for inp in range(1, 3):
				self.add_item(DoubleItem(f"/Ac/In/{inp}/L{phase}/P", None, text=format_w))
				self.add_item(DoubleItem(f"/Ac/In/{inp}/L{phase}/I", None, text=format_a))
				self.add_item(DoubleItem(f"/Ac/In/{inp}/L{phase}/V", None, text=format_v))
				self.add_item(DoubleItem(f"/Ac/In/{inp}/L{phase}/F", None, text=format_f))

			self.add_item(DoubleItem(f"/Ac/Out/L{phase}/P", None, text=format_w))
			self.add_item(DoubleItem(f"/Ac/Out/L{phase}/I", None, text=format_a))
			self.add_item(DoubleItem(f"/Ac/Out/L{phase}/V", None, text=format_v))
			self.add_item(DoubleItem(f"/Ac/Out/L{phase}/F", None, text=format_f))

		self.add_item(DoubleItem("/Ac/Out/P", None, text=format_w))

		for inp in range(1, 3):
			self.add_item(DoubleItem(f"/Ac/In/{inp}/P", None, text=format_w))

		# AC input types
		self.add_item(IntegerItem("/Ac/In/1/Type", service.input_type(1),
			writeable=True,
			onchange=lambda v: self._sync_value("/Ac/In/1/Type", v),
			text=format_input_type))
		self.add_item(IntegerItem("/Ac/In/2/Type", service.input_type(2),
			writeable=True,
			onchange=lambda v: self._sync_value("/Ac/In/2/Type", v),
			text=format_input_type))

		# Custom Name
		self.add_item(TextItem("/CustomName", None,
			writeable=True, onchange=self._set_customname))

		# Control points
		self.add_item(IntegerItem("/Mode", service.mode,
			writeable=True, onchange=self._set_mode))
		self.add_item(DoubleItem("/Ac/In/1/CurrentLimit",
			service.ac_currentlimit(1), writeable=True,
			onchange=lambda v: self._set_ac_currentlimit(1, v)))
		self.add_item(DoubleItem("/Ac/In/2/CurrentLimit",
			service.ac_currentlimit(2), writeable=True,
			onchange=lambda v: self._set_ac_currentlimit(2, v)))
		self.add_item(DoubleItem("/Settings/Ess/MinimumSocLimit",
			service.minsoc, writeable=True, onchange=self._set_minsoc))
		self.add_item(IntegerItem("/Settings/Ess/Mode", service.essmode,
			writeable=True, onchange=self._set_ess_mode))
		self.add_item(ForcedIntegerItem(self._set_disable_feedin,
			"/Ess/DisableFeedIn", service.disable_feedin, writeable=True))
		self.add_item(ForcedIntegerItem(self._set_setpoints,
			"/Ess/AcPowerSetpoint", None, writeable=True))

		# Paths that are just synchronised
		for item, path in (
			(IntegerItem, "/Ac/Control/IgnoreAcIn1"),
			(DoubleItem, "/Settings/Ac/In/CurrentLimitEnergyMeter")):
			self.add_item(item(path, service.get_value(path), writeable=True,
				onchange=lambda v, path=path: self._sync_value(path, v)))

		# Inverter DC power control
		self.add_item(ForcedIntegerItem(
			lambda v: self._sync_value("/Ess/UseInverterPowerSetpoint", v),
			"/Ess/UseInverterPowerSetpoint",
			service.use_inverter_setpoint, writeable=True))
		self.add_item(ForcedIntegerItem(self._set_inverter_setpoints,
			"/Ess/InverterPowerSetpoint", None, writeable=True))

		# Alarms
		for p in RsService.alarm_settings:
			self.add_item(IntegerItem(p, service.get_value(p),
				writeable=True, onchange=lambda v, p=p: self._sync_value(p, v)))

		# Capabilities, other summarised paths
		self.add_item(IntegerItem("/Capabilities/HasDynamicEssSupport", 0))
		self.update_capabilities()
		for p in RsService.summaries:
			self.add_item(IntegerItem(p, service.get_value(p)))

	def _set_setting(self, setting, _min, _max, v):
		if _min <= v <= _max:
			return self._sync_value(setting, v)
		return False

	def _sync_value(self, path, v):
		for s in self.subservices:
			s.set_value_async(path, v)
		return True

	def _set_mode(self, v):
		if v in (1, 2, 3, 4, 251):
			for s in self.subservices:
				s.mode = v
				return True
		return False

	def _set_ac_currentlimit(self, inp, v):
		if all(s.get_value(f"/Ac/In/{inp}/CurrentLimitIsAdjustable") == 1 \
				for s in self.subservices):
			return self._sync_value(f"/Ac/In/{inp}/CurrentLimit", v)
		return False

	def _set_minsoc(self, v):
		return self._set_setting("/Settings/Ess/MinimumSocLimit", 0, 100, v)

	def _set_ess_mode(self, v):
		return self._set_setting("/Settings/Ess/Mode", 0, 3, v)

	def _set_disable_feedin(self, v):
		return self._set_setting("/Ess/DisableFeedIn", 0, 1, v)

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

	def _set_inverter_setpoints(self, v):
		unitcount = len(self.subservices)
		try:
			setpoint = v / unitcount
		except (TypeError, ZeroDivisionError):
			pass
		else:
			for service in self.subservices:
				service.inverter_setpoint = setpoint
		return True

	def _set_customname(self, v):
		cn = self.settings.get_value(self.settings.alias("customname"))
		if cn != v:
			self.settings.set_value_async(self.settings.alias("customname"), v)
		return True

	def _add_device_info(self, service):
		try:
			self.add_item(TextItem(f"/Devices/{service.nad}/Service", None))
			self.add_item(IntegerItem(f"/Devices/{service.nad}/Instance", None))
		except ValueError:
			pass # Path already exists
		else:
			with self as s:
				s[f"/Devices/{service.nad}/Service"] = service.name
				s[f"/Devices/{service.nad}/Instance"] = service.deviceinstance

	def update_capabilities(self):
		with self as s:
			s["/Capabilities/HasDynamicEssSupport"] = int(all(
				(x.firmwareversion or 0) >= 0x11713 for x in self.subservices))

	def update_summaries(self):
		with self as s:
			for path, summary in RsService.summaries.items():
				s[path] = summary.summarise(self.subservices)

	def _remove_device_info(self, service):
		self.remove_item(f"/Devices/{service.nad}/Service")
		self.remove_item(f"/Devices/{service.nad}/Instance")

	def update_summary(self, path):
		with self as s:
			s[path] = RsService.summaries[path].summarise(self.subservices)

	@property
	def acpowersetpoint(self):
		return self.get_item("/Ess/AcPowerSetpoint").value

	def add_service(self, service):
		self.subservices.add(service)
		self.update_capabilities()
		self.update_summaries()
		self._add_device_info(service)

	def remove_service(self, service):
		self.subservices.discard(service)
		self._remove_device_info(service)

	async def wait_for_settings(self):
		""" Attempt a connection to localsettings. """
		settingsmonitor = await SettingsMonitor.create(self.bus,
			itemsChanged=self.itemsChanged)
		self.settings = await asyncio.wait_for(
			settingsmonitor.wait_for_service(SETTINGS_SERVICE), 5)
		await self.settings.add_settings(
			Setting("/Settings/AcSystem/{}/CustomName".format(
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
		return self.get_item("/CustomName").value

	@customname.setter
	def customname(self, v):
		with self as s:
			s["/CustomName"] = v or f"RS system ({self.systeminstance})"

class SystemMonitor(Monitor):
	synchronised_paths = RsService.synchronised_paths + RsService.alarm_settings

	def __init__(self, bus, make_bus):
		super().__init__(bus, handlers = {
			'com.victronenergy.multi': RsService
		})
		self._leaders = {}
		self._make_bus = make_bus

	async def serviceAdded(self, service):
		# We need these paths valid before we can do anything
		await service.wait_for_valid(
			"/N2kSystemInstance",
			"/FirmwareVersion",
			"/Mode",
			"/Ac/In/1/CurrentLimit",
			"/Settings/Ess/MinimumSocLimit",
			"/Settings/Ess/Mode",
			"/Ess/DisableFeedIn",
		)

		instance = service.systeminstance
		if instance is None:
			return # Firmware is old, or it is still starting up

		if instance in self._leaders:
			leader = await self._leaders[instance]

			# Synchronise with the other units
			for p in self.synchronised_paths:
				try:
					v = leader.get_item(p).value
				except AttributeError:
					pass
				else:
					if v is not None and v != service.get_value(p):
						service.set_value_async(p, v)

			leader.add_service(service)
		else:
			self._leaders[instance] = asyncio.Future()
			bus = await self._make_bus().connect()
			gateway = service.gateway.replace(":", "_")
			leader = Service(bus,
				f"com.victronenergy.acsystem.{gateway}_sys{instance}", service)

			# Register on dbus, connect to localsettings
			await asyncio.gather(leader.register(), leader.init())
			self._leaders[instance].set_result(leader)

	async def serviceRemoved(self, service):
		for leader in list(self.leaders):
			leader.remove_service(service)
			if not leader.subservices:
				leader.__del__()
				del self._leaders[leader.systeminstance]

	async def systemInstanceChanged(self, service):
		await self.serviceRemoved(service)
		await self.serviceAdded(service)

	def itemsChanged(self, service, values):
		# If the N2kSystemInstance changes, remove and add the service
		# again so it ends up in the right system.
		if '/N2kSystemInstance' in values.keys():
			asyncio.create_task(self.systemInstanceChanged(service))
			return
		try:
			leader = self._leaders[service.systeminstance].result()
		except (KeyError, asyncio.InvalidStateError):
			pass
		else:
			# Don't accept updates from services that are not part of the
			# system yet.
			if service not in leader.subservices:
				return
			for p, v in values.items():
				if p in RsService.summaries:
					leader.update_summary(p)
					continue

				if p not in self.synchronised_paths: continue
				for s in leader.subservices:
					if s is not service:
						if s.get_value(p) != v:
							s.set_value_async(p, v)
				if leader.get_item(p).value != v:
					with leader as s:
						s[p] = v

	@property
	def leaders(self):
		return iter(s.result() for s in self._leaders.values() if s.done())

async def calculation_loop(monitor):
	while True:
		for leader in monitor.leaders:
			# Sum power and current values over all units in the system
			values = defaultdict(lambda: None)
			for service in leader.subservices:
				for phase in range(1, 4):
					for inp in range(1, 3):
						a = f"/Ac/In/{inp}/P"
						b = f"/Ac/In/{inp}/L{phase}/"
						for p in (b + "P", b + "I"):
							values[p] = safe_add(values[p], service.get_value(p))
						p = b + "P"
						values[a] = safe_add(values[a], service.get_value(p))

						for p in (b + "V", b + "F"):
							values[p] = safe_first(values[p], service.get_value(p))

					b = f"/Ac/Out/L{phase}/"
					for p in (b + "P", b + "I"):
						values[p] = safe_add(values[p], service.get_value(p))
						values["/Ac/Out/P"] = safe_add(values["/Ac/Out/P"],
							service.get_value(p))

					for p in (b + "V", b + "F"):
						values[p] = safe_first(values[p], service.get_value(p))

			# Number of inputs/phases
			has_input1 = any(values[f"/Ac/In/1/L{x}/P"] is not None 
				for x in range (1, 4))
			has_input2 = any(values[f"/Ac/In/2/L{x}/P"] is not None 
				for x in range (1, 4))
			values["/Ac/NumberOfAcInputs"] = int(has_input1) + int (has_input2)

			# Number of phases, we will use the outputs to detect that
			values["/Ac/NumberOfPhases"] = sum(int(values[f"/Ac/Out/L{x}/P"] is not None) for x in range(1, 4))

			# Determine overall state, all units are expected to have the
			# same state, otherwise it is unknown
			for p in ("/State", ):
				if len(set(s.get_value(p) for s in leader.subservices)) == 1:
					for s in leader.subservices:
						values[p] = s.get_value(p)
						break
				else:
					values[p] = None

			# Determine the active input. This value is 0, 1 or 240. Until
			# we get the Quattro-RS, 1 is not possible, so this is 0 or 240.
			# To keep this simple, use the maximum number reported. If the
			# value is invalid, assume it is disconnected. This is so that
			# dbus-generator does not think there is a communication problem.
			p = "/Ac/ActiveIn/ActiveInput"
			try:
				values[p] = max(s.get_value(p) for s in leader.subservices)
			except (TypeError, ValueError):
				values[p] = 0xF0 # disconnected

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
