# Wiegand bridge LITE — design notes, revision 1

**Status: under development.** Designed, routed and checked (2026-10-21); the firmware compiles;
**no board has been made.** Nothing here is verified on hardware. Files: [`hardware/lite/`](../hardware/lite/),
[`firmware/wiegand-bridge-lite.yaml`](../firmware/wiegand-bridge-lite.yaml).

![Size comparison](../hardware/lite/fab/size-comparison.png)

## What it is

The smallest board that puts an ESP32 on a Wiegand reader. It assumes the reader has its own supply,
runs from **12 V ± 4 V (8–16 V)**, keeps **USB-C** for programming (and bench power), and has
**two lines for the reader's LED and buzzer**. No battery, screen, relay or switch inputs.

| | Full board (rev 11) | Lite (rev 1) |
|---|---|---|
| Size, layers | 90 × 95 mm, 4 | **42 × 44 mm**, 4 |
| Module | ESP32-S3-WROOM-1-N8R2 | **ESP32-S3-MINI-1-N4R2** (15.4 × 20.5 mm; same chip family) |
| Input | 6–36 V, two regulators, battery, 12 V boost for the reader | **8–16 V → AP63203 → 3.3 V**, one stage; the reader has its own supply |
| USB-C | programming and power | programming, **and bench power through one Schottky diode** |
| Reader lines | D0/D1 inputs, LED/BEEP outputs | **D0, D1, LED, BEEP all bidirectional** |
| RS-485 / OSDP | SP3485, termination and bias jumpers, node-power terminal | SP3485, termination jumper only |
| Connectors | 11 screw terminals, OLED socket, headers | **one 8-way 3.5 mm pluggable block**: `12V GND D0 D1 LED BEEP A B` |
| Status LEDs | PWR, FAULT, OK, CHG | PWR, FAULT (ESPHome status), OK (API connected) |
| Parts | 197 | **75** (29 part numbers) |

The security model is the full board's ([design.md](design.md), *Security*): the board reports
credentials to Home Assistant as events and has no output toward a lock.

## The bidirectional line cell

Each of the four reader wires carries the full board's input cell **and** its output cell:

```
wire ──┬── SM712 (one per pair) ── GND
       ├── 2N7002 drain      gate ← 100 Ω ← GPIO (drive)      100k gate → GND
       └── 1k ──┬── 5.1 V zener ── GND
                ├── 100 pF ── GND
                ├── 10k ── 3V3
                └── 74LVC2G17 Schmitt buffer ── GPIO (sense)
```

- **Reader mode:** the reader drives D0/D1 low; the board senses them on IO4/IO5 (the same pins and
  the same `wiegand:` block as the full board) and drives LED/BEEP low (IO8/IO9).
- **Emulation mode** (the board stands in for a reader at an access controller's terminals): the
  board pulses D0/D1 low (IO6/IO7); the controller drives LED/BEEP, sensed on IO10/IO11.
- The drive FET sits on the raw wire, before the 1k, so it sinks whatever pull-up the far end has;
  the SM712 clamps the wire at 12 V either way. The 10k pull-up to 3.3 V keeps a disconnected line
  idle-high, so `wiegand:` stays quiet.
- The board hears its own pulses: a frame sent in emulation mode also arrives as a tag on IO4/IO5.

ESPHome has no Wiegand transmitter, so `wiegand_tx` in the firmware bit-bangs one in a lambda:
50 µs low per bit, 2 ms between bits, a 1 on D1 and a 0 on D0. `wiegand_send_26` builds the
standard 26-bit frame (even parity over the first 12 bits, odd over the last 12) from a facility
code and a card number. **Both are API actions: leave "allow device actions" OFF once adopted**, or
HA could be talked into replaying a card.

## Power

- **8–16 V in**, terminal pins 1–2: 0.5 A 24 V PTC, SS34 in series for reverse polarity, SMAJ18A
  C19077538 (18 V standoff; it conducts from ~20 V), 10 µF.
- **AP63203** (fixed 3.3 V, 3.8–32 V in, 2 A, TSOT-26) as its datasheet's typical circuit: 10 µF
  in, 2 × 22 µF out, 100 nF bootstrap, 4.7 µH, EN tied to VIN, FB tied to VOUT. The part is
  flagged "not recommended for new designs" at LCSC; check stock before ordering. Fallback: the
  full board's LMR16020 at 3.3 V.
- **USB-C VBUS → SS34 → the buck input.** With 12 V present the diode is reverse-biased; from USB
  alone the buck sees 4.6 V (minimum 3.8).
- Load: the S3 (≤ 0.5 A peaks on Wi-Fi), SP3485, two buffers, three LEDs: ~0.15 A at 12 V.

## Pin map

| GPIO | Function | | GPIO | Function |
|---|---|---|---|---|
| IO4 / IO5 | D0 / D1 sense (buffered) | | IO38 | RS-485 DE (held in receive by R65) |
| IO6 / IO7 | D0 / D1 drive (open drain) | | IO43 / IO44 | RS-485 TX / RX (UART0) |
| IO8 / IO9 | LED / BEEP drive | | IO21 | red FAULT (ESPHome status LED, sink) |
| IO10 / IO11 | LED / BEEP sense (buffered) | | IO47 | green OK (sink) |
| IO0 | BOOT | | IO19 / IO20 | USB D− / D+ |

IO3, IO45, IO46 (strapping) and IO26 (PSRAM on the N4R2) are not connected. The module's pad
numbers → GPIOs come from its EasyEDA symbol and are recorded in `netlist.py`.

**Terminal, left to right:** `12V GND D0 D1 LED BEEP A B` — KF2EDGR-3.5-8P header (C441177);
mating plug KF2EDGK-3.5-8P, not on the BOM. The header's mouth overhangs the board edge by 0.2 mm.

## Layout

- The module's antenna hangs 4.5 mm over the top edge, as on the full board; its EN / UART / IO38
  column faces the right edge, its IO0–IO11 column faces inboard, where the line cells are.
- The four line cells stand in columns above their terminal pins with the surge parts at the
  terminal; the buck and input chain run down the left edge from the top-left hole.
- Silkscreen text is 1.0 mm, JLCPCB's minimum; the only part on the back is the termination jumper.
- **Parts are spaced by pad extents, not courtyards.** The EasyEDA footprints' courtyards stop
  short of their pad ends (SMA, SOT-23 and TSOT pads run up to 0.9 mm past them), so three routing
  attempts failed on pads that overlapped while the courtyard check passed. `padgap.py` measures
  pad-to-pad gaps on the unrouted board (≥ 0.25 mm between different nets) and is part of the
  pre-route checks; ten `courtyards_overlap` DRC warnings between 0603/SOD-123 passives remain
  and are accepted.

## Results, revision 1

- Freerouting (60 passes) after a hand route of the USB-C's VBUS pad pair, which it never joins:
  **0 unconnected**, no clearance, short or starved-thermal items. 12 stitching vias, 0 vias in
  pads, every ground pad on the plane.
- Track widths: 0.5 mm on the input and switch nets (0.12–0.22 mm needed), 0.23 mm minimum on
  3.3 V, 0.4 mm on VBUS; signals 0.2 mm / 0.15 mm clearance (JLCPCB 4-layer allows 0.09).
- Cross-checks from the files: every GPIO in the firmware maps to the intended net and on through
  each cell to its terminal pin; every diode's cathode/anode matches its symbol; every IC pad
  assigned; BOM = CPL (72 placements, top side); gerbers, drills and CPL in one frame; USB D+/D−
  on IO20/IO19; strapping pins open, IO0 pulled up; all 29 part numbers in JLCPCB's library.
- JLCPCB classes (2026-10-21): fee-bearing Extended = the module, AP63203, the LVC2G17s, the PTC,
  the inductor, the USB-C and the terminal (7 types; no Basic or Preferred equivalents exist in
  JLCPCB's library for any of them); Preferred (no loading fee) = the zeners and the SMAJ18A; Basic =
  everything else, including SP3485 and the SM712s.
- Cost, JLCPCB Economic assembly, parts at the lowest tier: about US$9.45 of parts per board (the
  module is US$5), US$21 of Extended fees and US$9.50 set-up and stencil per order, plus the PCB,
  joints and shipping: roughly **US$125 for five boards, US$190 for ten**, before local tax.

## Before ordering

1. Upload the gerbers alone and read JLCPCB's DFM result.
2. In the assembly previewer, check every polarised part: D7/D8/D23 (two LED footprints with
   opposite pin-1 ends), D1/D3 (SS34, pad 1 = cathode), **D2 (SMAJ18A, same SMA
   footprint family as the SS34s, pad 1 = cathode)**, D5/D6/D24/D25, U1, U2, U4/U11, U9, J1.
3. J3 is through-hole: THT assembly, or drop it from the BOM/CPL and hand-fit it.
4. Print `fab/wiegand-bridge-lite-1to1.pdf` at 100 % and lay the plug and cables on it.

## Bench tests (none run yet)

In order: power first with nothing attached (3.3 V, input current); flash over USB alone; then the
reader (reads, keypad, LED and BEEP); then emulation against another controller, or against the
full board acting as the controller, with `wiegand_send_26`; then RS-485 loopback at 9600 baud.
