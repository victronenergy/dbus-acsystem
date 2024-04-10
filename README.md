# dbus-acsystem

This reads data from Multi-RS systems (and potentially also others in future)
and combines/summarises data for three-phase (and later parallel) units that
are part of the same system.

Right now it keeps the ESS parameters (minsoc, mode) the same for the whole
system. It keeps the AC input limit the same. It can be configured with
a Custom Name.
