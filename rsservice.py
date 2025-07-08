import asyncio
from aiovelib.client import Service as Client
from aiovelib.client import Item as ClientItem
from aiovelib.service import DoubleItem
from summary import (SummaryAll, SummaryAny, SummaryFirst, SummaryMax,
	SummaryOptionalAlarm, SummaryDeviceState)

class RsItem(ClientItem):
	""" Subclass to allow us to wait for an item to turn valid. """
	def __init__(self):
		super().__init__()
		self._valid = asyncio.Future()

	def update(self, value):
		super().update(value)
		if self.value is not None and not self._valid.done():
			self._valid.set_result(None)

	async def wait_for_valid(self):
		return await self._valid

class RsService(Client):
	make_item = RsItem
	servicetype = "com.victronenergy.multi"
	synchronised_paths=(
		"/Ac/In/1/CurrentLimit",
		"/Ac/In/2/CurrentLimit",
		"/Ac/In/1/Type",
		"/Ac/In/2/Type",
		"/Settings/Ess/MinimumSocLimit",
		"/Settings/Ac/In/CurrentLimitEnergyMeter",
		"/Settings/Ess/Mode",
		"/Ac/Control/IgnoreAcIn1",
		"/Pv/Disable",
		"/Ess/DisableDischarge",
		"/Ess/DisableCharge",
	)
	alarm_settings=(
		"/Settings/AlarmLevel/HighTemperature",
		"/Settings/AlarmLevel/HighVoltage",
		"/Settings/AlarmLevel/HighVoltageAcOut",
		"/Settings/AlarmLevel/LowSoc",
		"/Settings/AlarmLevel/LowVoltage",
		"/Settings/AlarmLevel/LowVoltageAcOut",
		"/Settings/AlarmLevel/Overload",
		"/Settings/AlarmLevel/Ripple",
		"/Settings/AlarmLevel/ShortCircuit"
	)
	# All items set
	summaries={p: SummaryAll(p) for p in (
		"/Capabilities/HasAcPassthroughSupport",
		"/Ac/In/1/CurrentLimitIsAdjustable",
		"/Ac/In/2/CurrentLimitIsAdjustable")}
	# Any item set
	summaries.update({p: SummaryAny(p) for p in (
		"/Ess/Sustain",)})
	# Max of items set
	summaries.update({p: SummaryMax(p) for p in (
		"/Alarms/PhaseRotation",
		"/Alarms/HighTemperature",
		"/Alarms/Overload")})
	# First/any
	summaries.update({p: SummaryFirst(p, DoubleItem) for p in (
		"/Ess/ActiveSocLimit",)})

	# System state
	summaries.update({p: SummaryDeviceState(p) for p in (
		"/State", )})

	# Controlled by settings
	for p, s in [("/Alarms/GridLost", "/Settings/Alarm/System/GridLost"),]:
		summaries[p] = SummaryOptionalAlarm(s, p)

	paths = {
		"/ProductId",
		"/FirmwareVersion",
		"/DeviceInstance",
		"/Devices/0/Gateway",
		"/Devices/0/Nad",
		"/Ac/In/1/L1/P", "/Ac/In/2/L1/P", "/Ac/Out/L1/P",
		"/Ac/In/1/L2/P", "/Ac/In/2/L2/P", "/Ac/Out/L2/P",
		"/Ac/In/1/L3/P", "/Ac/In/2/L3/P", "/Ac/Out/L3/P",
		"/Ac/In/1/L1/I", "/Ac/In/2/L1/I", "/Ac/Out/L1/I",
		"/Ac/In/1/L2/I", "/Ac/In/2/L2/I", "/Ac/Out/L2/I",
		"/Ac/In/1/L3/I", "/Ac/In/2/L3/I", "/Ac/Out/L3/I",
		"/Ac/In/1/L1/V", "/Ac/In/2/L1/V", "/Ac/Out/L1/V",
		"/Ac/In/1/L2/V", "/Ac/In/2/L2/V", "/Ac/Out/L2/V",
		"/Ac/In/1/L3/V", "/Ac/In/2/L3/V", "/Ac/Out/L3/V",
		"/Ac/In/1/L1/F", "/Ac/In/2/L1/F", "/Ac/Out/L1/F",
		"/Ac/In/1/L2/F", "/Ac/In/2/L2/F", "/Ac/Out/L2/F",
		"/Ac/In/1/L3/F", "/Ac/In/2/L3/F", "/Ac/Out/L3/F",
		"/Dc/0/Voltage", "/Dc/0/Current", "/Dc/0/Power",
		"/Soc",
		"/N2kSystemInstance", "/State", "/Mode",
		"/Ac/ActiveIn/ActiveInput",
		"/Ess/AcPowerSetpoint", "/Ess/InverterPowerSetpoint",
		"/Ess/DisableFeedIn", "/Ess/UseInverterPowerSetpoint"
	}.union(synchronised_paths).union(alarm_settings).union(summaries)

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self._max_ac_currentlimit = [None, None]

	async def wait_for_valid(self, *paths):
		# This will create the items (but mark them unseen) when you access
		# the dictionary entry
		await asyncio.gather(*(self.values[p].wait_for_valid() for p in paths))

	async def wait_for_essential_paths(self):
		# We need these paths valid before we can do anything
		await self.wait_for_valid(
			"/N2kSystemInstance",
			"/FirmwareVersion",
			"/Mode",
			"/Ac/In/1/CurrentLimit",
			"/Settings/Ess/MinimumSocLimit",
			"/Settings/Ess/Mode",
			"/Ess/DisableFeedIn",
		)

	async def fetch_ac_max_limits(self):
		l1 = await self.fetch_max("/Ac/In/1/CurrentLimit") or None
		l2 = await self.fetch_max("/Ac/In/2/CurrentLimit") or None
		self._max_ac_currentlimit = [l1, l2]

	@property
	def deviceinstance(self):
		return self.get_value("/DeviceInstance")

	@property
	def firmwareversion(self):
		return self.get_value("/FirmwareVersion")

	@property
	def productid(self):
		return self.get_value("/ProductId")

	@property
	def systeminstance(self):
		return self.get_value("/N2kSystemInstance")

	@property
	def gateway(self):
		return self.get_value("/Devices/0/Gateway") or ""

	@property
	def nad(self):
		return self.get_value("/Devices/0/Nad")

	@property
	def mode(self):
		return self.get_value("/Mode")

	@mode.setter
	def mode(self, v):
		self.set_value_async("/Mode", v)

	@property
	def minsoc(self):
		return self.get_value("/Settings/Ess/MinimumSocLimit")

	@minsoc.setter
	def minsoc(self, v):
		self.set_value_async("/Settings/Ess/MinimumSocLimit", v)

	@property
	def essmode(self):
		return self.get_value("/Settings/Ess/Mode")

	@essmode.setter
	def essmode(self, v):
		self.set_value_async("/Settings/Ess/Mode", v)

	@property
	def disable_feedin(self):
		return self.get_value("/Ess/DisableFeedIn")

	@disable_feedin.setter
	def disable_feedin(self, v):
		self.set_value_async("/Ess/DisableFeedIn", v)

	@property
	def use_inverter_setpoint(self):
		return self.get_value("/Ess/UseInverterPowerSetpoint")

	@use_inverter_setpoint.setter
	def use_inverter_setpoint(self, v):
		self.set_value_async("/Ess/UseInverterPowerSetpoint", v)

	@property
	def setpoint(self):
		return self.get_value("/Ess/AcPowerSetpoint")

	@setpoint.setter
	def setpoint(self, v):
		self.set_value_async("/Ess/AcPowerSetpoint", v)

	@property
	def inverter_setpoint(self):
		return self.get_value("/Ess/InverterPowerSetpoint")

	@inverter_setpoint.setter
	def inverter_setpoint(self, v):
		self.set_value_async("/Ess/InverterPowerSetpoint", v)

	@property
	def ignore_acin1(self):
		return self.get_value("/Ac/Control/IgnoreAcIn1")

	def ac_currentlimit(self, i):
		return self.get_value(f"/Ac/In/{i}/CurrentLimit")

	def input_type(self, i):
		return self.get_value(f"/Ac/In/{i}/Type")

	def max_ac_currentlimit(self, i):
		return self._max_ac_currentlimit[i-1]
