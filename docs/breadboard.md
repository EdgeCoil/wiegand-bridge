# Breadboard test — before ordering the PCB

Through-hole parts only, from DigiKey. The breadboard uses
**the same GPIO numbers as the PCB**, so `firmware/wiegand-bridge.yaml` runs on it unchanged.

## What it proves, and what it cannot

**Proves:** the reader's real current at 12 V (the board assumes ≤ 150 mA), that ESPHome reads its
cards and PINs, which way its LED/BEEP lines work, the D0/D1 protection with a real reader, the
reader power-cut switch (Q4 + Q11), the four inputs, the tamper input, and the OLED.

**Cannot prove** (SMD-only parts — the prototype board tests these): the three switching regulators
on this layout, the LiFePO4 charger and protection, the antenna on the board edge. The breadboard
runs the reader straight from the 12 V adaptor, not through a boost converter.

## Parts (DigiKey unless noted)

Part numbers checked on DigiKey's listings 2026-10-11. **Stock and lead times vary by regional site —
check your local DigiKey site before ordering.**

| Qty | Part (MPN) | DigiKey # | Stands in for | Note |
|---|---|---|---|---|
| 1 | Espressif **ESP32-S3-DEVKITC-1-N8R2** | 1965-ESP32-S3-DEVKITC-1-N8R2-ND | U1 — the same module | listing showed an 8-week lead time; check stock |
| 1 | RECOM **R-78E5.0-1.0** (12 V → 5 V, 1 A, 3-pin SIP) | 945-2201-ND | U2 buck | backorder on one regional site; Mornsun K7805-1000R3 is the like-for-like |
| 1 | TI **CD4050BE** (hex buffer, DIP-16) | 296-2056-ND | U4 74LVC2G17 | run at 3.3 V; its inputs take up to 15 V, so it level-shifts the reader's 4.7 V lines |
| 4 | onsemi **1N5231B** (5.1 V zener, DO-35) | 1N5231B-ND | D5, D6 | the through-hole twin of MMSZ5231B |
| 10 | onsemi **2N7000** (N-MOSFET, TO-92) | search "2N7000" | Q1, Q2, Q4, Q7–Q10 | 2N7002's through-hole twin |
| 2 | onsemi **FQP27P06** (P-MOSFET, TO-220) | FQP27P06-ND | Q11 reader switch | logic-ish P-FET; fine at the −6.3 V gate drive here |
| 10 each | Stackpole **CF14JT** ¼ W resistors: `CF14JT1K00`, `CF14JT10K0`, `CF14JT100K` | search MPN | R9–R14, R40–R47, R51/52 … | or any ¼ W resistor kit |
| 5 each | `CF14JT100R`, `CF14JT4K70`, `CF14JT15K0` | search MPN | R6/R7/R17, R36/R37, R16 | |
| 4 | TDK **FG28C0G1H101JNT06** (100 pF) | search MPN | C14, C15 | |
| 6 | TDK **FG18X7R1H103KNT06** (10 nF) | search MPN | C27–C30 | |
| 6 | TDK **FG18X7R1H104KNT06** (100 nF) | search MPN | decoupling | |
| 2 | Nichicon **UVR1E101MED** (100 µF 25 V) | search MPN | C1 bulk | one on 12 V, one on 5 V |
| 2 each | Kingbright **WP7113SGD** / **WP7113SRD** (5 mm green / red) | search MPN | D7 / D8 | |
| 3 | Omron **B3F-1000** (6 mm tact switch) | search MPN | SW3 tamper; input test | |
| 2 | Littelfuse **RXEF050** (0.5 A resettable fuse, radial) | search MPN | F1 | optional but cheap |
| 2 | 830-point breadboard, e.g. Twin Industries **TW-E40-1020** | search MPN | — | **two**: the S3 DevKitC is wide; straddle the gap between them |
| 1 | M/M + M/F jumper wire set, e.g. Adafruit **758** / **826** | search MPN | — | |
| 1 | Adafruit **368** (2.1 mm DC jack → screw terminal) | 1528-1386-ND | J2 | long DigiKey lead time; Adafruit resellers stock it |
| 1 | **12 V ≥ 1 A wall adaptor, 2.1 mm centre-positive** — e.g. Mean Well **GE24I12-P1J**, or any 12 V adaptor you have | — | the 12 V supply | |
| 1 | **1.3" SH1106 128×64 I2C OLED, 4-pin** — AliExpress/eBay, ~US$5 | — | the real screen | buy the one the board will use; check its pin order is GND VCC SCL SDA |

**You also need:** a multimeter (current range for the reader), the reader itself, and a USB-C cable.

## Wiring (same GPIOs as the PCB)

**Power.** 12 V adaptor → Adafruit 368 → 12 V rail (+ 100 µF). 12 V → R-78E5.0 → 5 V rail (+ 100 µF)
→ DevKitC **5V** pin. **All grounds common** (reader, adaptor, DevKitC). **Never connect the 5 V rail
and the DevKitC's USB at the same time** — power from USB alone while flashing.

| Function | Wiring | GPIO |
|---|---|---|
| Reader +12 V | 12 V rail → **FQP27P06 source**; drain → (RXEF050) → reader red. Gate: 100k to source, 100k to a 2N7000 drain (Q4); Q4 source GND, gate ← 100 Ω ← GPIO48, 10k gate → 3V3 | IO48 (low = reader off) |
| Reader GND | GND rail | |
| D0 / D1 | reader green / white → 1k → node: 1N5231B to GND (band on the node), 100 pF to GND, 10k to 3V3 → CD4050 input | out → IO4 / IO5 |
| CD4050 | pin 1 VDD = **3V3**, pin 8 GND; buffer pairs 3→2 and 5→4; tie unused inputs (7, 9, 11, 14) to GND | |
| LED / BEEP | reader LED / BEEP wire → 2N7000 drain; source GND; gate ← 100 Ω ← GPIO, 100k gate → GND | IO6 / IO7 |
| Tamper | B3F between IO8 and GND, 10k IO8 → 3V3 | IO8 |
| Ext-power sense | 5 V rail → 10k → node → 15k → GND; node → IO9 | IO9 |
| Input 1 (repeat for 2–4) | switch → 1k → 2N7000 drain; gate 3V3; source → IO15 with 10k to 3V3 and 10 nF to GND | IO15–18 |
| OLED | GND, 3V3, SCL → IO42, SDA → IO41; 4.7k pull-ups to 3V3 on both | IO41 / IO42 |
| Status LED | 3V3 → LED → 1k → IO21 | IO21 |

**DevKitC v1.0 boards have their RGB LED on GPIO48**, the reader-shed pin. Harmless — it is an output
either way — but the RGB LED will flicker when the reader is switched. v1.1 moved it to GPIO38.

## Tests, in order

1. **Reader current**: meter in series with reader +12 V, idle and while beeping with the backlight on.
   **≤ 150 mA** keeps the board design as it is; more means a bigger F1 and a battery-runtime rethink.
2. Flash `firmware/wiegand-bridge.yaml` (with real secrets on CT 113). Cards arrive as `on_tag`, PINs
   as keys + `#`. Note whether the reader sends per-key or buffered PINs.
3. Fire `feedback_granted` from HA: green + one beep. If it is inverted, the board needs the same
   firmware change (`inverted: true` on the outputs), not a hardware change.
4. Pull IO48 low (toggle the output): reader goes dark at 0 V, comes back cleanly, no stray reads.
5. Inputs, tamper, external-power sense, OLED blanking after 60 s.
