# dbus-acsystem

This reads data from Multi-RS systems (and potentially also others in future)
and combines/summarises data for three-phase (and later parallel) units that
are part of the same system.

Right now it keeps the ESS parameters (minsoc, mode) the same for the whole
system. It keeps the AC input limit the same. It can be configured with
a Custom Name.


## dBus paths
### Settings
This (mostly) mirrors the paths from the Multi-RS service

Notes:
* In the current version, the AC power setpoint
  is simply divided by the phase count and distributed to the individual
  units.  A better implementation will be added to the Multi-RS firmware in
  future.
* The ESS mode values are:
  * 0 = Optimised with BatteryLife
  * 1 = Optimised without BatteryLife
  * 2 = Keep Batteries Charged
  * 3 = External Control
* The MinimumSocLimit is simply copied to all individual units so they
  all start/stop discharging at the same SOC.

```
/Ess/AcPowerSetpoint          <--- AC power setpoint
/Settings/Ess/MinimumSocLimit <--- Minimum SOC limit for ESS
/Settings/Ess/Mode            <--- ESS mode
```

## Data
The following summary data is calculated from the information provided
by the individual units.

```
/Ac/In/n/CurrentLimit <--- AC input current limit for input n
/Ac/In/n/Lx/I         <--- Total current drawn on phase x, input n
/Ac/In/n/Lx/P         <--- Total power drawn on phase x, input n
/Ac/In/n/P            <--- Total power drawn over all phases
/Ac/NumberOfAcInputs  <--- Number of AC inputs
/Ac/NumberOfPhases    <--- Number of phases
/Ac/Out/Lx/I          <--- Total current drawn on output
/Ac/Out/Lx/P          <--- Total power drawn on output
```
