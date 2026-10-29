# Design notes — revision 12

How the board works, why, and how to test it. `hardware/netlist.py` is the authority on what
connects to what; this document explains it.

**Revision 12** (the files in this repository, not yet ordered) is revision 11 (also never ordered)
with two blocks redrawn around integrated parts, from a passive-to-IC audit:
- **Reader monitor:** U12, an INA226 on I²C (0x40), reading R59, a 0.1 Ω alloy shunt (±1 %,
  ±50 ppm/°C) between the boost's output capacitors and the reader switch U13. It replaces the 0.2 Ω
  low-side shunt with an LMV321 (×21) on IO9 and the R31/R32 rail divider on IO2. The LMV321's offset
  is specified in millivolts against a 30 mV full scale, 5 mA of error per millivolt. On guaranteed
  figures, uncalibrated, the reading is now within about 0.25 mA + 1.5 % of reading (about 2.4 mA at
  150 mA), plus the switch's own operating current, which the shunt also carries (up to 5 mA; its
  datasheet gives no minimum or typical). The firmware subtracts a per-board zero measured with no
  reader connected, and a one-point bench calibration takes out the shunt's 1 % (Bench tests, 4). The
  reader's return is plain ground (the shunt no longer lifts it), and IO2 is free.
  - **Kelvin sensing by construction:** R59's footprint has a small sense tab on each land, net-tied to
    it, and U12's IN+/IN− are on nets of their own (`ISNS_P`/`ISNS_N`), laid by `route.py`. No load
    current can share a sense track. `kelvin.py` checks it.
  - **Inputs never go negative:** the shunt sits on the boost side of U13, where the 44 µF hold
    IN+/IN− up even while the reader is shed. U12's VBUS input reads the reader terminal through R82
    4.7 kΩ, with D27 (BAT54) holding it above the pin's −0.3 V limit when the field wire swings
    negative.
- **Reader switch:** U13, a TPS1H200A-Q1 current-limited high-side switch, replaces the Q11 P-FET
  (and R52). Audit round 5 found that a short on the reader terminal pulled the boost's output down to
  `VSYS` through L3 and D10, which no switch after it could stop, and ran Q11 linear at 1–9 W while
  F1 took seconds to trip or never did. U13 holds the reader current at 0.23–0.36 A, so the boost
  stays in regulation, and retries by itself every second. Its fault output goes to IO9. See *Reader
  supply* below.
- **RS-485:** U9 is a THVD1420, whose receiver has full fail-safe: an idle, open or shorted bus reads
  as a 1, so this node needs no bias of its own. The 20k weak-bias pair is gone; the 390 Ω JP3/JP4
  strong bias stays, for buses whose other nodes need it. R83/R84 (10 Ω) sit between the SM712 and
  U9's A/B, because the SM712 clamps above the transceiver's ±16 V. R85 (1 kΩ) feeds RO to RXD0, so a
  USB-UART on the test pads can override it.
- **Also, from the review of rev 12:** IN1–IN4 have reverse clamps (D28–D31), 10 kΩ (R90–R93)
  between each isolator FET and its GPIO, and 4.7 kΩ pulse-proof series resistors with 47 kΩ pull-ups,
  so a sustained −36 V miswire stays within every part's rating but the GPIO's. R94 bleeds an
  unplugged USB VBUS.
  The green LEDs have 470 Ω resistors. No copper runs under an M3 screw head on the outer layers. The
  ground pour is held 0.4 mm off through-hole pins, and no other-net copper comes within 0.4 mm of a
  through-hole pin JLC solders (audit.py checks it).

**Revision 11** differs from **revision 10** (built and tested; tag `rev-10b`) in three ways:
- **Status pair:** D8 becomes red `FAULT` (IO21, ESPHome's status LED: a slow blink is a warning, a
  fast blink an error), and a new D23 green `OK` (IO47 through R81 1 kΩ) is lit while Home Assistant
  is connected. They sit left of the OLED, so a fitted screen doesn't hide them.
- **Display reset:** `DISP_RST` moves from IO47 to expander P06, which J19 pin 3 now shares. On a
  rev 10 board IO47 only reaches the unfitted J6, so rev 11 firmware is harmless there.
- **Silkscreen:** every label is held clear of pads, outlines, fitted parts and other text, checked by
  `audit.py --silk`. Rev 10 had 41 such problems in 70 labels.

## The property this board must not break

**The board reports; it never unlocks.** Codes and card numbers go to Home Assistant as events. HA
validates them and, if it chooses, operates a lock through a separate, protected actuator. Nothing on
this board is wired to a lock, a strike, or a lock power supply's control inputs.

The reason is where it sits. A reader-side board is within reach of anyone at the door. If it also
switched the lock, then prising it off the wall and shorting two wires would open the door. Kept as a
reporter, taking it off the wall leaves the door exactly as secure as it was.

The **relay footprint (K1, J15/J16) is not fitted by default** and is not defined in the firmware.
It exists for boards used elsewhere, such as an inside unit or a garage. **Do not fit it on a board
mounted at the reader.**

## Security — assume it gets stolen

Anything mounted outside can be unscrewed and carried off. The firmware does not use ESP32 flash
encryption, so the flash can be dumped over USB, or over UART from the test pads. **The dump contains
the Wi-Fi passphrase and the HA API encryption key.** Design around that:

| Measure | Why |
|---|---|
| **Put it on an isolated IoT network** | A dumped passphrase then reaches only that network |
| **Leave HA's "Allow the device to perform Home Assistant actions" OFF** | A spoofed device holding the stolen key can then only submit code guesses, which an HA-side lockout bounds |
| **Check the event's `device_id` in the HA automation** | Events from anything else are ignored |
| **Tamper switch → alert** (IO8) | The board knows when its lid is opened. The response is to rotate the Wi-Fi passphrase and the API key |
| **USB-C only reachable inside the enclosure** | The flashing port doesn't face the public side, and opening the lid trips the tamper switch |
| **Nothing private on the screen** | It faces shared space: never a PIN, card number or name |

**Optional and irreversible:** burning the eFuse that disables USB-Serial-JTAG removes the easy port,
but not UART download mode on the test pads. Disabling that as well means a failed OTA bricks the
board. **Only flash encryption actually protects the secrets**, and it is not set up here yet.

Keep the logger at `INFO` in service. At `DEBUG`, ESPHome logs the Wiegand frames, which are the codes.

## Architecture

```
 6–36 V ─► J2 / J14 ─► F2 PTC ─► D1 ─► +VIN (TVS D2) ─► U2 LMR16020 buck ─► +5V_BUCK ─► D3 ─┐
                                                                                      ├─► +5V ─► D11 ─┬─► VSYS ─► U3 TPS63001 ─► +3V3
 USB-C VBUS ────────────────────────────────────────────────────────────────────► D4 ─┘               │
                                       +5V ─► U5 CN3058E charger ─► LiFePO4 cell ─► Q5 ──────────────┤
                                                                                                      │
                                                   U6 MT3608 boost, 12.6 V (13.2 V with JP1) ◄────────┘
                                                        └─► 0.1 Ω ─► U13 switch (0.29 A limit) ─► F1 PTC ─► J3 reader +12V
                                                                      (U12 INA226 reads the shunt and the J3 voltage, I²C)

 ESP32-S3-WROOM-1-N8R2
   Wiegand D0/D1 ◄─ U4 74LVC2G17 ◄─ 1k + 5.1 V zener + 100 pF ◄─ SM712 ◄─ J10
   LED / BEEP ─► Q1 / Q2 2N7002 open drain ─► SM712 ─► J11
   I²C (IO41/42) ─► OLED J5, Qwiic J18, TCA9535 expander U8 (0x20)
   SPI (IO10–14, RST expander P06) ─► J6 (TFT / e-paper); W5500 header J17 shares SCK/MOSI
   IN1–IN4 (IO15–18) ◄─ 2N7002 isolation ◄─ SMF36CA ◄─ J9/J12/J13
   RS-485 (UART0, DE IO38) ─► THVD1420 ─► SM712 ─► J20
```

**Power sources and what each one runs:**

| Present | ESP32 runs from | Reader runs from | Battery |
|---|---|---|---|
| 6–36 V on J2 or J14 (normal) | buck → `+5V` → `VSYS` | U6 boost, regulated | charging |
| USB-C (bench, first flash) | `VBUS` → `+5V` → `VSYS` | U6 boost, regulated | charging |
| Battery only | cell → Q5 → `VSYS` | U6 boost, until firmware sheds it | discharging |

## Power

- **Input:** J2 (screw terminal) or J14 (5.5 mm barrel jack, centre positive; DC-005-class jacks are
  commonly rated 30 V, so above 30 V use J2), then F2 (2 A PTC). **D1** blocks reverse
  polarity; **D2** (SMAJ36CA) clamps surges *after* D1, so a reversed supply can't forward-bias it
  and short the source. **Do not exceed 36 V**: the TVS starts conducting at about 40 V.
- **U2 LMR16020** (60 V buck) makes `+5V_BUCK`. A wide input range means the board doesn't care about
  cable drop or a sagging shared supply; its PGOOD goes to the expander.
- **`+5V_BUCK` and USB `VBUS` are diode-ORed** (D3, D4), so neither back-feeds the other, including a
  laptop during first flash. R94 (1 kΩ) loads VBUS so D4's reverse leakage can't hold an unplugged
  VBUS up: a Type-C host waits for VBUS under 0.8 V before it attaches. The SS34's 0.5 mA maximum
  (25 °C, 40 V) gives at most 0.5 V. Its 125 °C maximum is 5 mA (about 2 mA at 85 °C, interpolated,
  less at D4's 4.6 V reverse bias), so if a host won't attach to a warm board with 12 V present,
  remove the 12 V first. R94 draws 5 mA (25 mW) on USB.
- **U3 TPS63001** buck-boost makes `+3V3` from `VSYS` (1.8–5.5 V in), so the ESP32 stays up across the
  whole cell range.
- **The reader's supply is always regulated.** U6 (MT3608) boosts `VSYS` to 12.6 V, or 13.2 V with
  JP1 bridged, whichever source is present. U12 (INA226, I²C 0x40) reads the reader current through
  R59 (0.1 Ω, between the boost's capacitors and U13). It also reads the voltage at the reader
  terminal itself (after F1, through R82 4.7 kΩ), so a tripped F1 or a switch in its current limit
  shows as a low supply rather than a missing reader. 0x40 is also the default of several Qwiic parts
  (HTU21D, Si7021, HDC1080, PCA9685): don't fit one of those on J18 without moving its address.
  **Specify the reader at ≤ 150 mA at 12 V** (J3 and J21 together).

### Reader supply

- **U13 (TPS1H200A-Q1)** switches the boost's output to the reader terminals. R95 (6.8 kΩ) sets its
  current limit to 0.294 A, ±20 %: 0.233–0.357 A. The minimum covers the reader's 150 mA, and
  0.2 A at 9 V for a reader that draws constant power. The maximum sets what a fault costs.
- **A short or overload** at J3/J21: U13 holds the limit, so the boost stays in regulation and nothing
  else on the board notices. After 35–45 ms in the limit it switches off for 0.8–1.2 s, then tries
  again (auto-retry, DELAY pulled up by R96). That is up to 4.9 W in U13 per attempt, about 0.26 W on
  average. When the short goes, the reader comes back by itself at the next attempt, within 1.2 s.
  U13's `FAULT` (IO9) reports it, and the firmware's *reader supply overload* sensor combines it with
  the reader voltage.
- **Inrush:** the limit also charges a reader's input capacitors at power-up and when one is plugged
  in, and it must finish within the 35 ms window. That holds for 10–220 µF if the reader's current is
  resistive, or constant power once its regulator starts at 9 V or more. It holds for 10–180 µF if it
  draws a constant 150 mA from 0 V. A reader whose regulator starts below about 8 V at full power
  cannot get past the limit.
- **On battery: Q13, a second FS8205A in parallel with Q6.** While U13 holds 0.36 A at 13.7 V, the
  boost draws up to about 2.9 A from a 3.0 V cell. The DW01A's over-current trip is guaranteed only
  above 130 mV across the protection FETs, after at most 20 ms (no minimum), and every retry window is
  longer than that. One FS8205A (≤ 63 mΩ at 2.5 V gate) would trip from 2.06 A; with Q13 the pair is
  ≤ 31.5 mΩ and the worst case is 88 mV (+32 % margin at 25 °C, +19 % with the board's 1.6 W Wi-Fi
  peak). Neither part gives figures when hot, so the margin there is unproven; typical parts leave
  several times more. Inrush on battery stays in the limit for up to 14 ms (220 µF). The firmware sheds
  the reader on battery after the first overload, so a short costs one retry window, not one a second.
- **USB alone** (bench use): the board, the charger and a 150 mA reader together already draw about
  1 A, twice a 500 mA port's allowance, fault or not. In a short the switch holds it to about
  2–2.3 A for ≤ 45 ms in each 0.85 s. On USB alone, keep the reader under about 50 mA, or run it
  from 12 V.
- **Shedding:** IO48 drives Q4, which pulls U13's `IN` (and `DIAG_EN`) low, so U13 is in standby
  (≤ 3 µA). R51 pulls `IN` up from the boost's output, never above U13's own supply, which its
  rating requires. R18 holds Q4 off through reset, boot and OTA, so the reader stays **on**. The
  firmware sheds the reader only on battery: below 3.0 V, or after an overload. (U6 `EN` is tied high.
  Pulling `EN` low on a non-synchronous boost still leaks `VSYS` through to the output.)
- **F1** (PTC, 0.5 A hold) stays as a fail-safe in case U13 fails short. It never trips in normal
  service: the reader's 150 mA is under its 0.23 A hold at 85 °C. U13's limit is above that hold,
  but only for 45 ms in each 0.85 s.
- **Surges** on the reader pair: D20 holds the terminal between about −3.5 V and 24.4 V. Upward,
  current flows back through F1 and U13 into the boost's capacitors, so `VS` and U12's inputs follow
  it to about 24 V, within their 42 V and 40 V ratings.

### Battery — LiFePO4 only

- **The charger (CN3058E) stops at 3.6 V, which is right only for LiFePO4.** A Li-ion cell on this
  board would be undercharged and its protection thresholds would be wrong.
- J4 is a keyed **4-way JST-XH**: `BAT+`, `BAT−`, thermistor, `GND`. The thermistor's return is `GND`,
  not `BAT−`, which floats when the protection FETs open.
- **Charging is gated by a 10 k B3950 NTC taped to the cell.** No thermistor connected = no charging
  (fail-safe). Bridge **JP5** to use the on-board RT1 instead, which then measures the board, not the cell.
- **Protection:** DW01A + two FS8205A in parallel (Q6, Q13; over-discharge about 2.4 V, over-current,
  short circuit). Q13 is there for the reader-short case (see *Reader supply*).
- **Charge current ~120 mA** (R50 10 k), chosen for a sealed enclosure.
- **Suggested cell:** a 26650 LiFePO4, 2.5–3.3 Ah, with tabs or leads (not a spring holder), and no
  protection board of its own (the board provides it).
- Status lines `CHRG` and `DONE` go to the expander; the cell voltage (÷2) to IO1, and the thermistor
  divider to IO3.

## Reader I/O

**D0/D1:** `74LVC2G17` Schmitt buffer (5.5 V-tolerant inputs at 3.3 V). Each line has 1 kΩ + 5.1 V
zener (12 V on a data wire is clamped to about 5.3 V), 100 pF (RC ≈ 100 ns against 20–100 µs
Wiegand pulses), and 22 kΩ to `+3V3` (so there are no spurious reads with the reader shed or
unplugged). SM712 surge protection sits at the terminals. **The reader's outputs must pull a line to
0.68 V or lower at the terminal**: the node sits 1/23 of the way from there to `+3V3`, against the
buffer's 0.8 V minimum low threshold (with 10 kΩ, before rev 12's round 5, it was 0.54 V). Readers with
open-collector or open-drain outputs meet it. A reader without pull-ups of its own rises through
22 kΩ to `+3V3`: keep its cable under about 6 nF for SIA's 200 µs pulse interval (counted as the gap
between pulses), or about 30 nF at the usual 1 ms (with the datasheet-maximum 16 µA of leakage on the
node and VT+ 2.18 V at 3.24 V; at 130 pF/m about 45 m and 230 m).

**LED and BEEP:** readers take these as active-low inputs with an internal pull-up. The 2N7002 open
drain has a 100 Ω gate resistor and a 100 kΩ gate pull-down, so **the reader stays silent through
boot and OTA**. GPIO high → line low → green / beep. **Confirm the polarity with your reader.**

**Tamper:** SW3, a normally-open tact switch held closed by the lid, on IO8 with a 10 k pull-up.
J8 takes an enclosure-mounted switch in parallel instead.

**Inputs IN1–IN4:** dry contacts to GND. Each has an SMF36CA clamp, 4.7 kΩ series (pulse-proof,
0.33 W) and a 2N7002 with its gate at `+3V3` as an isolator: a 12, 24 or 36 V miswire reads "off"
and nothing conducts. A negative miswire is different. The FET conducts both ways, so a negative wire
drags its source, and once the GPIO too. Since rev 12, a 1N4148W from ground (D28–D31) holds the
FET's input side at about −0.75 V, which also keeps its gate within rating. The 4.7 kΩ then carries
4.9 mA (0.11 W) at −24 V and 7.4 mA (0.26 W) at −36 V, both sustained. The 47 kΩ pull-up sits on the
FET's side, and 10 kΩ (R90–R93) lies between it and the GPIO. A −24 V miswire puts about 30 µA into
the GPIO's own clamp diode, holding the pin a few hundred millivolts below ground. That is
current-limited and survivable, but beyond the ESP32-S3's −0.3 V rating. A closed contact reads
about 0.30 V. The contact's wetting current is about 64 µA: fine for reed switches and sealed
contacts, but an exposed, oxidising contact may want an external pull-up.

**RS-485:** THVD1420 on UART0 (TX/RX), DE/RE on IO38. Its receiver is fully fail-safe, so this board
reads an idle bus correctly whatever the bias. Bridge **JP2** (120 Ω termination) and
**JP3 + JP4** (fail-safe bias) only on the board at the end of the bus. R83/R84 (10 Ω,
pulse-proof) sit between the surge clamp and the transceiver, as in TI's surge reference circuit.
They reduce the guaranteed drive at the terminals into a 54 Ω load from 1.5 V to about 1.1 V, below
TIA-485's 1.5 V. Every receiver on the bus still sees far more than the 0.2 V it needs. J21 carries reader power and
ground for an OSDP reader. ESPHome has no OSDP component yet; the UART is declared so the port can
be tested.

## Pin map

| GPIO | Function | Note |
|---|---|---|
| IO1 | Battery voltage | ADC, ÷2 |
| IO2 | — | free since rev 12 (the reader monitor is on I²C) |
| IO3 | Battery thermistor | ADC; strapping pin, harmless unless JTAG eFuses are burnt |
| IO4 / IO5 | Wiegand D0 / D1 | via U4 |
| IO6 | Reader LED | Q1 |
| IO40 | Reader BEEP | Q2 |
| IO8 | Tamper | low = lid on |
| IO9 | Reader switch fault | U13 `FAULT`, open drain via R98; low = overload, short or open load |
| IO10 / 11 / 12 / 13 | SPI CS / MOSI / SCK / DC | J6 |
| IO14 | TFT backlight **or** e-paper BUSY | J6 |
| IO15–IO18 | IN1–IN4 | via Q7–Q10 |
| IO21 | Status LED, red `FAULT` | sinks D8 |
| IO35 / 36 / 37 | W5500 MISO / CS / INT | J17 |
| IO38 | RS-485 DE/RE | |
| IO39 | Expander interrupt | U8 `INT` |
| IO41 / IO42 | I²C SDA / SCL | |
| IO47 | Green `OK` LED | sinks D23 via R81 (rev 10: display reset to J6) |
| IO48 | Reader shed | high = shed (via Q4); low or undriven = reader on (R18) |
| TXD0 / RXD0 | RS-485 | logs go over USB instead |
| IO19 / IO20 | USB D− / D+ | J1 |

**TCA9535 expander (U8, 0x20):** P00 relay drive (not fitted), P01 `CHRG`, P02 `DONE`, P03 external
power present, P04 5 V power-good, P05 W5500 reset, P06–P17 to the 2×6 expansion header J19. Since
rev 11, P06 is also the display reset (`DISP_RST`, J6 pin 7), shared with J19 pin 3.

## Connectors

| Ref | Type | Pins |
|---|---|---|
| J2 | 5.08 mm screw terminal | `+VIN` 6–36 V, `GND` |
| J14 | 5.5 mm barrel jack | centre positive, in parallel with J2 |
| J3 / J10 / J11 | 5.08 mm screw terminals | reader `+12V`, `GND` · `D0`, `D1` · `LED`, `BEEP` |
| J9 / J12 / J13 | 5.08 mm screw terminals | `IN1`, `IN2` · `GND`, `IN3` · `IN4`, `GND` |
| J20 / J21 | 5.08 mm screw terminals | RS-485 `A`, `B` · `+12V`, `GND` |
| J1 | USB-C | flashing, logs, bench power |
| J4 | JST-XH 4-way | `BAT+`, `BAT−`, thermistor, `GND` |
| J5 | 4-way socket | OLED: `GND`, `VCC`, `SCL`, `SDA` |
| J6 | 8-pin header | TFT / e-paper (SPI) |
| J8 | 2-pin header | external tamper switch |
| J15 / J16 | 5.08 mm screw terminals | relay NO, NC, COM (**not fitted**) |
| J17 | 8-pin header | W5500 module |
| J18 | Qwiic | I²C |
| J19 | 2×6 header | expander spares |

**Wire colours are a convention, not a standard.** Wire to your reader's own leaflet.

### The OLED

A **1.3" 128×64 SH1106, 4-pin I²C** module, address `0x3C`. **Check its pin order before plugging it
in.** J5 is `GND VCC SCL SDA`, but many modules are `VCC GND SCL SDA`, which would reverse the
supply. Some modules have 0 Ω links on the back to swap the first two pins; otherwise use a short
lead with wires 1 and 2 crossed. The firmware blanks the screen after 60 s and wakes it on a key press.
The screen is an optional ESPHome package: uncomment the `packages:` block at the end of
`firmware/wiegand-bridge.yaml` once it is fitted. Without a screen, leave it out, or the missing
display shows as a fault on the status LED.

## Layout

- **4 layers, 90 × 95 mm.** In1 is a GND plane. In2 carries the power rails, which is why the inner
  copper is 1 oz: `+5V` and the battery paths run there at 0.4–0.6 mm.
- **The antenna hangs over the board edge**, with no copper beneath it. Keep metal away from it in the
  enclosure. The OLED sits at least 15 mm from it.
- Switching regulators have windowed paste and thermal vias under their pads.
- Autorouted with Freerouting, with the input, switch and relay nets kept to the outer layers.
- Test pads for UART0, BEEP and GND.

## Bench tests

Use a current-limited bench supply (0.5 A) for the first power-up. Each stage assumes the one before
passed.

**0. Before power (meter only):** resistance from `+VIN`, `+5V`, `VSYS`, `+3V3` and the reader rail to
GND should be over about 1 kΩ; a dead short means a solder bridge. Check J4's polarity against the
silkscreen before a cell is ever connected.

**1. Power, no battery, no reader**
- Reversed supply on J2 → about 0 mA, nothing warm.
- 12 V on J2 → `+5V` ≈ 4.6 V, `+3V3` = 3.3 V, PWR LED on, about 30–60 mA with Wi-Fi idle.
- Sweep 6 → 36 V: the rails hold.
- USB alone → boots and flashes. USB and 12 V together → no back-feed into VBUS. 12 V only, USB
  unplugged → VBUS (C6) under 0.8 V. If a host won't attach to a warm board with 12 V present,
  remove the 12 V and plug in again.

**2. Expander and reader monitor:** an I²C scan shows `0x20` and `0x40` (and `0x3C` with the OLED). Remove 12 V with USB still in:
5 V power-good → off, external power stays on.

**3. Battery** (meter the polarity first)
- With 12 V on: charging on, about 120 mA, the cell stops at 3.6 V, then "charged".
- Unplug the thermistor → charging stops. Warm it past about 44 °C → charging pauses, then resumes
  as it cools.
- Remove all external power → the board stays up on the cell.
- Run it down → reader shed at about 3.0 V (the reader terminal reads about 0 V), then the protection
  cuts off at about 2.4 V. Shedding and restoring the reader produces no spurious reads.

**4. Reader** (12 V, GND, D0, D1 wired; reader in 26-bit Wiegand mode)
- Zero the reader monitor first: set `reader_zero_ma` to 0 in the firmware, and with no reader
  connected and the reader not shed, read the reported reader current. Set `reader_zero_ma` to that
  value (the default is 2.5). It is U13's own operating current, up to 5 mA. The *reader supply
  fault* sensor is on with no reader connected (open load); that is expected.
- Reader current shows its idle draw; ≤ 150 mA with backlight and beep. Unplugging the reader shows
  as a current change, which is your "reader removed" signal.
- Calibrate the reader monitor once: measure the reader's current with a meter in series and
  compare it with the reported value. Add the ratio as a `multiply` filter on the ina226 current in
  the firmware.
- Short the reader's `+12V` to `GND` (12 V supply, limit 1.5 A: each retry draws about 0.9 A) → the
  *reader supply overload* sensor turns on, the reader supply reads near 0 V, and the board stays up
  with `+5V`, `VSYS` and the 12.6 V boost steady. U13 gets warm, not hot. Remove the short → the
  reader is back within about 1.2 s. On the battery alone the board should stay up (Q13 halves the
  protection's sense resistance); try it with a spare cell, since if the DW01A does trip, external
  power is needed to recover (see *Reader supply*).
- With the reader disconnected → no spurious events for ten minutes.
- 50 card reads and 20 PINs with no misses. Reset ten times: the reader neither beeps nor flashes.

**5. Inputs and tamper:** each input to GND → its sensor turns on within about 50 ms; 24 V on an
input damages nothing. Lift the lid → tamper on within a second.

**6. RS-485** (only if used): with termination and bias bridged, idle A−B ≈ +0.24 V; loopback to a
USB-RS485 adapter at 9600 baud.

**7. Soak:** 24 h with Wi-Fi, Wiegand and the OLED running: no resets, heap steady, reader current
steady. Note the temperature inside the closed enclosure.

**In place:** if the board shares a supply with a lock, fire the lock repeatedly and confirm the board
never resets.

## Deliberately left out

- **Any output toward a lock** on a reader-side board (see the top of this document).
- **Flash encryption.** It is the real fix for an outdoor device, but not something to set up casually
  in ESPHome. Network isolation stands in for it.
- **A camera.** It was dropped in revision 8.
- **USB ESD protection.** USB is internal, behind the lid.
- **USB-C Power Delivery.**
