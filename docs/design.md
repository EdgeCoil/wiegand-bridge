# Design notes — revision 10

How the board works, why, and how to test it. `hardware/netlist.py` is the authority on what
connects to what; this document explains it.

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
                                                        └─► Q11 shed switch ─► F1 PTC ─► J3 reader +12V
                                                                               (return via 0.2 Ω shunt → LMV321 → IO9)

 ESP32-S3-WROOM-1-N8R2
   Wiegand D0/D1 ◄─ U4 74LVC2G17 ◄─ 1k + 5.1 V zener + 100 pF ◄─ SM712 ◄─ J10
   LED / BEEP ─► Q1 / Q2 2N7002 open drain ─► SM712 ─► J11
   I²C (IO41/42) ─► OLED J5, Qwiic J18, TCA9535 expander U8 (0x20)
   SPI (IO10–14, RST IO47) ─► J6 (TFT / e-paper); W5500 header J17 shares SCK/MOSI
   IN1–IN4 (IO15–18) ◄─ 2N7002 isolation ◄─ SMF36CA ◄─ J9/J12/J13
   RS-485 (UART0, DE IO38) ─► SP3485 ─► SM712 ─► J20
```

**Power sources and what each one runs:**

| Present | ESP32 runs from | Reader runs from | Battery |
|---|---|---|---|
| 6–36 V on J2 or J14 (normal) | buck → `+5V` → `VSYS` | U6 boost, regulated | charging |
| USB-C (bench, first flash) | `VBUS` → `+5V` → `VSYS` | U6 boost, regulated | charging |
| Battery only | cell → Q5 → `VSYS` | U6 boost, until firmware sheds it | discharging |

## Power

- **Input:** J2 (screw terminal) or J14 (5.5 mm barrel jack, centre positive), then F2 (2 A PTC). **D1** blocks reverse
  polarity; **D2** (SMAJ36CA) clamps surges *after* D1, so a reversed supply can't forward-bias it
  and short the source. **Do not exceed 36 V**: the TVS starts conducting at about 40 V.
- **U2 LMR16020** (60 V buck) makes `+5V_BUCK`. A wide input range means the board doesn't care about
  cable drop or a sagging shared supply; its PGOOD goes to the expander.
- **`+5V_BUCK` and USB `VBUS` are diode-ORed** (D3, D4), so neither back-feeds the other, including a
  laptop during first flash.
- **U3 TPS63001** buck-boost makes `+3V3` from `VSYS` (1.8–5.5 V in), so the ESP32 stays up across the
  whole cell range.
- **The reader's supply is always regulated.** U6 (MT3608) boosts `VSYS` to 12.6 V, or 13.2 V with
  JP1 bridged, whichever source is present. IO2 reads the rail (÷7.67), and the 0.2 Ω shunt plus
  LMV321 (gain 21) report reader current on IO9. **Specify the reader at ≤ 150 mA at 12 V**: U6
  could supply more, but the battery path, the DW01A over-current trip and F1's hot-enclosure
  derating all assume ≤ 150 mA.
- **Reader shedding:** Q11, a high-side P-FET after U6, driven by Q4 from IO48. R18 (10 k to `+3V3`)
  holds it **on** through reset, boot and OTA; firmware sheds the reader only on battery. (U6 `EN` is
  tied high. Pulling `EN` low on a non-synchronous boost still leaks `VSYS` through to the output.)
- **F1** (PTC) limits a short on the reader lead, so it can't take the board down.

### Battery — LiFePO4 only

- **The charger (CN3058E) stops at 3.6 V, which is right only for LiFePO4.** A Li-ion cell on this
  board would be undercharged and its protection thresholds would be wrong.
- J4 is a keyed **4-way JST-XH**: `BAT+`, `BAT−`, thermistor, `GND`. The thermistor's return is `GND`,
  not `BAT−`, which floats when the protection FETs open.
- **Charging is gated by a 10 k B3950 NTC taped to the cell.** No thermistor connected = no charging
  (fail-safe). Bridge **JP5** to use the on-board RT1 instead, which then measures the board, not the cell.
- **Protection:** DW01A + FS8205A (over-discharge about 2.4 V, over-current, short circuit).
- **Charge current ~120 mA** (R50 10 k), chosen for a sealed enclosure.
- **Suggested cell:** a 26650 LiFePO4, 2.5–3.3 Ah, with tabs or leads (not a spring holder), and no
  protection board of its own (the board provides it).
- Status lines `CHRG` and `DONE` go to the expander; the cell voltage (÷2) to IO1, and the thermistor
  divider to IO3.

## Reader I/O

**D0/D1:** `74LVC2G17` Schmitt buffer (5.5 V-tolerant inputs at 3.3 V). Each line has 1 kΩ + 5.1 V
zener (12 V on a data wire is clamped to about 5.3 V), 100 pF (RC ≈ 100 ns against 20–100 µs
Wiegand pulses), and 10 kΩ to `+3V3` (so there are no spurious reads with the reader shed or
unplugged). SM712 surge protection sits at the terminals.

**LED and BEEP:** readers take these as active-low inputs with an internal pull-up. The 2N7002 open
drain has a 100 Ω gate resistor and a 100 kΩ gate pull-down, so **the reader stays silent through
boot and OTA**. GPIO high → line low → green / beep. **Confirm the polarity with your reader.**

**Tamper:** SW3, a normally-open tact switch held closed by the lid, on IO8 with a 10 k pull-up.
J8 takes an enclosure-mounted switch in parallel instead.

**Inputs IN1–IN4:** dry contacts to GND. Each has an SMF36CA clamp, 1 kΩ series and a 2N7002 with its
gate at `+3V3` as an isolator: a 12 or 24 V miswire reads "off" and damages nothing.

**RS-485:** SP3485 on UART0 (TX/RX), DE/RE on IO38. Bridge **JP2** (120 Ω termination) and
**JP3 + JP4** (fail-safe bias) only on the board at the end of the bus. J21 carries reader power and
ground for an OSDP reader. ESPHome has no OSDP component yet; the UART is declared so the port can
be tested.

## Pin map

| GPIO | Function | Note |
|---|---|---|
| IO1 | Battery voltage | ADC, ÷2 |
| IO2 | Reader rail voltage | ADC, ÷7.67 |
| IO3 | Battery thermistor | ADC; strapping pin, harmless unless JTAG eFuses are burnt |
| IO4 / IO5 | Wiegand D0 / D1 | via U4 |
| IO6 | Reader LED | Q1 |
| IO40 | Reader BEEP | Q2 |
| IO8 | Tamper | low = lid on |
| IO9 | Reader current | LMV321 output, 4.2 mV per mA |
| IO10 / 11 / 12 / 13 | SPI CS / MOSI / SCK / DC | J6 |
| IO14 | TFT backlight **or** e-paper BUSY | J6 |
| IO15–IO18 | IN1–IN4 | via Q7–Q10 |
| IO21 | Status LED | sinks D8 |
| IO35 / 36 / 37 | W5500 MISO / CS / INT | J17 |
| IO38 | RS-485 DE/RE | |
| IO39 | Expander interrupt | U8 `INT` |
| IO41 / IO42 | I²C SDA / SCL | |
| IO47 | Display reset | J6 |
| IO48 | Reader shed | high (default) = reader on |
| TXD0 / RXD0 | RS-485 | logs go over USB instead |
| IO19 / IO20 | USB D− / D+ | J1 |

**TCA9535 expander (U8, 0x20):** P00 relay drive (not fitted), P01 `CHRG`, P02 `DONE`, P03 external
power present, P04 5 V power-good, P05 W5500 reset, P06–P17 to the 2×6 expansion header J19.

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
- USB alone → boots and flashes. USB and 12 V together → no back-feed into VBUS.

**2. Expander:** an I²C scan shows `0x20` (and `0x3C` with the OLED). Remove 12 V with USB still in:
5 V power-good → off, external power stays on.

**3. Battery** (meter the polarity first)
- With 12 V on: charging on, about 120 mA, the cell stops at 3.6 V, then "charged".
- Unplug the thermistor → charging stops. Warm it past about 44 °C → charging pauses, then resumes
  as it cools.
- Remove all external power → the board stays up on the cell.
- Run it down → reader shed at about 3.0 V (the reader terminal reads about 0 V), then the protection
  cuts off at about 2.4 V. Shedding and restoring the reader produces no spurious reads.

**4. Reader** (12 V, GND, D0, D1 wired; reader in 26-bit Wiegand mode)
- Reader current shows its idle draw; ≤ 150 mA with backlight and beep. Unplugging the reader shows
  as a current change, which is your "reader removed" signal.
- Short the reader's `+12V` to `GND` → F1 or U6 limits, and the board stays up.
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
