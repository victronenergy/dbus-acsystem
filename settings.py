from aiovelib.client import Monitor
from aiovelib.localsettings import SettingsService as _SettingsClient

class SettingsClient(_SettingsClient):
	paths = {
		"/Settings/Alarm/System/GridLost",
	}

class SettingsMonitor(Monitor):
	def __init__(self, bus, **kwargs):
		super().__init__(bus, handlers = {
			'com.victronenergy.settings': SettingsClient
		}, **kwargs)

