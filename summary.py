from aiovelib.service import IntegerItem

class Summary(object):
	def __init__(self, path, item=None):
		self.make_item = IntegerItem if item is None else item
		self.path = path

	def summarise(self, leader):
		raise NotImplementedError("summarise")

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

class SummaryOptionalAlarm(SettingMixin, SummaryMax):
	_default = 0
