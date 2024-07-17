# dbus-acsystem

This service has a few features:

1. Aggregrate data from multiple individual inverter/chargers, filtered to be only the Multi RS and the HS19. Inverter RS is not included - will be looked at later.
2. Synchronises certain settings and parameters between the individual devices.

dbus-acsystem has no state keeping and no settings in local settings, aside from the custom name. Everything else is stored on the
RS units themselves, and also configurable via VictronConnect.

## dBus paths
### Mode & Settings

The paths available on the com.victronenergy.multi service are mostly mirrored onto com.victronenergy.acsystem.

Also, dbus-acsystem synchronises them between the individual devices in the system, except where noted below (/Mode, /Ess/AcPowerSetpoint).

In the current version, the AC power setpoint is simply divided by the phase count and distributed to the individual
units. A better implementation will be added to the Multi-RS firmware in future, which is why this is kept simple.

List of paths:
```
/Ac/In/n/Type                 <--- Type of AC input configured in VictronConnect,
                                   1=Grid, 2=Genset, 3=Shore.
/Mode                         <--- Switch position. Sent to one RS only, the RSes sync this themselves
/Ess/AcPowerSetpoint          <--- AC power setpoint
/Ess/DisableFeedIn            <--- Disable grid feedin (at metering point)
/Ess/UseInverterPowerSetpoint <--- InverterPowerSetpoint is used instead of
                                   AcPowerSetpoint. Used by DynamicEss.
/Ess/InverterPowerSetpoint    <--- How much DC to convert from/to AC, positive
                                   values charges the battery, negative
                                   discharges the battery.
/Settings/Ess/MinimumSocLimit <--- Minimum SOC limit for ESS
/Settings/Ess/Mode            <--- ESS mode
                                   * 0 = Optimised with BatteryLife
                                   * 1 = Optimised without BatteryLife
                                   * 2 = Keep Batteries Charged
                                   * 3 = External Control

/Settings/AlarmLevel/...      <--- Disable, warn, or only alarm.
```

## Capabilities
```
/Capabilities/HasAcPassthroughSupport <--- All RS units support passthru
/Capabilities/HasDynamicEssSupport    <--- DynamicEss is supported

```

## Limits
```
/Ac/In/n/CurrentLimit                 <--- AC input current limit for input n
/Ac/In/1/CurrentLimitIsAdjustable     <--- Whether current limit can be adjusted.
                                           All units must be adjustable otherwise
                                           this will be 0.
```

## Data
The following summary data is calculated from the information provided
by the individual units.

```
/State                   <--- Summarised state of the system
/Ac/ActiveIn/ActiveInput <--- Active AC input(s) on RS units. All units are
                              expected to be the same, otherwise this will
                              show invalid.
/Ac/In/n/Lx/I            <--- Total current drawn on phase x, input n
/Ac/In/n/Lx/P            <--- Total power drawn on phase x, input n
/Ac/In/n/P               <--- Total power drawn over all phases
/Ac/NumberOfAcInputs     <--- Number of AC inputs
/Ac/NumberOfPhases       <--- Number of phases
/Ac/Out/Lx/I             <--- Total current drawn on output
/Ac/Out/Lx/P             <--- Total power drawn on output

/Devices/x/Service     <--- List of service/instances that make up this service
/Devices/x/Instance
```
