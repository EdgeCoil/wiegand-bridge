# Roadmap: after revision 12 — planned, not designed

Revision 12 (INA226 reader monitor, eFuse reader switch, fail-safe RS-485) is designed and audited
separately. This file lists what comes after it.

Two new uses, found after rev 10 worked: a **standalone access controller** (the relay was fitted
for this, for future-proofing) and a **smart alarm**. Neither changes the rule at the top: **a board
mounted at the reader never gets the relay.** Standalone means the board is mounted somewhere
secure, inside, with only the reader outside.

**Standalone access controller**
- **The relay must work on battery.** The K1 coil runs from `+5V`, which is unpowered when only the
  cell is up (cell → Q5 → `VSYS`; D11 blocks `VSYS` from feeding `+5V`). Today a power cut drops the
  relay, so a fail-secure lock can't be opened from the keypad until power returns. Power the coil
  from a rail that survives on battery, or use a lower-voltage or latching relay. Then choose fail-safe
  or fail-secure behaviour on purpose, and write it down.
- **Local code checking.** The firmware has to check PINs and cards itself and keep its own lockout,
  so the door works without Home Assistant or the network. HA stays the place codes are managed.
- **Reader-line security.** Wiegand is unencrypted: anyone who reaches the reader cable can replay a
  card number. The fix is OSDP's encrypted mode on the RS-485 port, which needs OSDP support that
  ESPHome doesn't have yet.

**Smart alarm**
- **Supervised zones.** IN1–IN4 are plain contacts to GND with no end-of-line resistors, so shorting
  the wires of a normally-closed loop reads as secure. Alarm zones need EOL or DEOL resistors read as
  analogue levels: normal, alarm, tamper (cut), tamper (short).
- **A siren output** with its own fused supply from the input, not the reader rail.
- **Detector power** (PIRs and similar) with a budget, ideally kept up on battery. The reader rail is
  specified at ≤ 150 mA and is shed on battery, so it can't be used.
- **Alarm logic that runs locally**, so detection and the siren don't depend on HA or Wi-Fi. HA handles
  arming, notifications and history.

**Proposed split: alarm zones on an expansion board, not the main board.** J19 as it stands can't
carry them: it has only `+3V3`, `GND` and expander GPIOs (digital only, no I²C, no input power). So a later revision
widens it to carry I²C, an interrupt line, `+VIN` and `GND`. A zone board can then stack on it with its
own ADC (supervised zones), input protection, siren driver and detector supply. IN1–IN4 stay on the
main board for a door contact and an exit button. Not yet decided.
