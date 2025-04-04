from aiovelib.service import IntegerItem

# RS states
# generic states:
#N2K_CONVERTER_STATE_UNAVAILABLE = 0xFF
#N2K_CONVERTER_STATE_OFF = 0
N2K_CONVERTER_STATE_FAULT = 2 # non recoverable, needs a power cycle
N2K_CONVERTER_STATE_BLOCKED = 0xFA # firmware update

# inverter is active, charger is not active:
N2K_CONVERTER_STATE_PASSTHRU = 8
N2K_CONVERTER_STATE_INVERTING = 9
N2K_CONVERTER_STATE_ASSISTING = 10

# charger active (mppt active, ac pv present or grid connected):
#N2K_CONVERTER_STATE_WAKEUP = 0xF5 # charger starting
#N2K_CONVERTER_STATE_BULK = 3
#N2K_CONVERTER_STATE_ABSORPTION = 4
#N2K_CONVERTER_STATE_FLOAT = 5
#N2K_CONVERTER_STATE_STORAGE = 6
#N2K_CONVERTER_STATE_EQUALIZE = 7
#N2K_CONVERTER_STATE_PSU = 11
#N2K_CONVERTER_STATE_REPEATED_ABSORPTION = 0xF6
#N2K_CONVERTER_STATE_AUTO_EQUALIZE = 0xF7
#N2K_CONVERTER_STATE_BATTERYSAFE = 0xF8
#N2K_CONVERTER_STATE_EXTERNAL_CONTROL = 0xFC # bms or gx

class Summary(object):
	def __init__(self, path, item=None):
		self.make_item = IntegerItem if item is None else item
		self.path = path

	def summarise(self, leader):
		raise NotImplementedError("summarise")

	def initial(self, v):
		""" Initial value for the summary. Uses `v` as a hunt, but can
		    replace it with something else. This is so we can override
		    the behaviour for some summaries and delay the decision
		    instead of starting with the first value from the first
		    RS device."""
		return v

class SummaryAll(Summary):
	def summarise(self, leader):
		return int(all(x.get_value(self.path) for x in leader.subservices))

class SummaryAny(Summary):
	def summarise(self, leader):
		return int(any(x.get_value(self.path) for x in leader.subservices))

class SummaryMax(Summary):
	def summarise(self, leader):
		try:
			return max(y for y in (x.get_value(self.path) for x in leader.subservices) if y is not None)
		except ValueError:
			return None

class SummaryFirst(Summary):
	def summarise(self, leader):
		for x in leader.subservices:
			return x.get_value(self.path)
		return None

class SettingMixin(object):
	""" Enherit from this, and one of the other Summary methods to make
	    one dependent on a setting.
	    Eg: class SummarySomething(SettingMixin, SummaryMax): pass """
	_default = None
	def __init__(self, setting, path, item=None):
		self.setting = setting
		super().__init__(path, item)

	def summarise(self, leader):
		if leader.settings.get_value(self.setting) == 1:
			return super().summarise(leader)
		return self._default

	def initial(self, v):
		return self._default

class SummaryOptionalAlarm(SettingMixin, SummaryMax):
	_default = 0

class SummaryDeviceState(Summary):
	""" Sumarises the state of multiple RS units, so that the most relevant
	    state is chosen. """
	def summarise(self, leader):
		states = set(x.get_value(self.path) for x in leader.subservices)

		# Just one state? Pass through.
		if len(states) == 1:
			return next(iter(states))

		# if any unit is in such a state, in this order, the whole cluster is
		# considered to be in this state.
		for s in (N2K_CONVERTER_STATE_FAULT, N2K_CONVERTER_STATE_BLOCKED,
				N2K_CONVERTER_STATE_INVERTING, N2K_CONVERTER_STATE_PASSTHRU,
				N2K_CONVERTER_STATE_ASSISTING):
			if s in states:
				return s

		# Otherwise units are in varying levels of charging, and we can just
		# return the min state, typically 3 (bulk)
		try:
			return min(iter(states))
		except ValueError:
			return None
