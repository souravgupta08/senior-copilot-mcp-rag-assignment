---
doc_id: SOP-BFP-001
title: Boiler Feed Pump Operating Procedure
doc_type: operating_procedure
equipment_types: pump
applies_to: Boiler Feed Pump 101, Boiler Feed Pump 102
site: NorthPlant
version: 3.2
---

# Boiler Feed Pump Operating Procedure (SOP-BFP-001)

## Scope

This procedure applies to Boiler Feed Pump 101 and Boiler Feed Pump 102 in NorthPlant Unit 1.
It covers alarm response for discharge pressure, suction pressure, bearing temperature and vibration alarms.
Operators must follow the safety instruction SAF-005 before any field work.

## High Discharge Pressure Alarm Response

A high discharge pressure alarm (alarm code PMP-PH-01) means the pump discharge pressure has gone above the operating limit of 120 bar.

Immediate actions:

1. Check the position of the feedwater control valve FCV-101 on the DCS. A closing or sticking downstream valve is the most common cause of high discharge pressure on the boiler feed pumps.
2. Confirm the reading on the local pressure gauge to rule out a faulty pressure transmitter.
3. Open the minimum flow recirculation line to reduce discharge pressure.
4. Inform the shift supervisor if pressure does not return below the limit within 10 minutes.

Restart rule: Do not reset the trip or restart the pump until the cause of the high discharge pressure has been identified and the shift supervisor has authorised the restart. Repeated restarts against a closed valve can damage the pump.

## Recurring High Discharge Pressure

If the alarm occurs more than three times in a week, raise a maintenance request to inspect FCV-101 (positioner calibration and instrument air supply) and the discharge non-return valve.
Review the alarm history for correlation with valve position deviation alarms.

## Low Suction Pressure Alarm Response

Check the deaerator tank D-101 level. Low deaerator level is the usual cause of low suction pressure.
Check the suction strainer differential pressure. A blocked strainer must be cleaned during the next planned stop.
Never run the pump with suction pressure below the minimum, because this causes cavitation.

## High Bearing Temperature Alarm Response

Check lube oil level in the bearing housing and the oil cooler water flow.
Check bearing vibration. If vibration is above 7.1 mm/s together with high bearing temperature, reduce load and prepare the standby pump.
If bearing temperature exceeds 95 degC, change over to the standby pump and stop the running pump.

## Related Equipment to Inspect

For any boiler feed pump alarm also inspect: the drive motor (BFP Motor 101 or 102), feedwater control valve FCV-101 and deaerator tank D-101.
