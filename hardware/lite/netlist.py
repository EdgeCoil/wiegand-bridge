# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Wiegand bridge LITE, revision 2 -- the netlist, as data.

Source of truth for build_pcb.py. A stripped-down sibling of ../wiegand-bridge (rev 10/11): the
smallest board that puts an ESP32 on a Wiegand reader (the author, 2026-10-21). It assumes the reader is
powered already, runs from 12 V +-4 V (8-16 V), and keeps USB-C for programming (and bench power).
Dropped: battery, screens, relay, switch inputs IN1-4, the reader 12 V boost/shed, the I/O expander,
the W5500/Qwiic headers, the reader current sense.

- One pluggable 3.5 mm terminal block, 8 ways: 12V GND D0 D1 LED BEEP A B.
- Four BIDIRECTIONAL open-drain 5 V lines (D0, D1, LED, BEEP): each has rev 10's input cell
  (1k + 5.1 V zener + 100 pF + pull-up -> 74LVC2G17 Schmitt buffer -> GPIO) AND rev 10's
  output cell (open-drain FET, 100 ohm gate, 100k pull-down) on the same wire. Reader mode:
  read D0/D1, drive LED/BEEP. Reader-emulation mode (toward an access controller): pulse D0/D1,
  read LED/BEEP. The pull-up (22k since rev 2 round 3; the FET an AO3400A since rev 2) keeps the
  wiegand component quiet with nothing attached.
- RS-485/OSDP port kept (THVD1420 on UART0 since rev 2), minus rev 10's strong-bias jumpers and
  node-power terminal.
- ESP32-S3-MINI-1 (15.4 x 20.5 mm; the N4R2 variant is what JLCPCB stocks, 2026-10-21). Same chip
  family as rev 10, so the firmware carries over with a pin remap (firmware/wiegand-bridge-lite.yaml).
- 3.3 V straight from the input: AP63203 (fixed 3.3 V, 3.8-32 V in, TSOT-26), per its datasheet
  figure 21: 10 uF in, 2x 22 uF out, 100 nF BST, 4.7 uH, EN tied to VIN, FB tied to VOUT.
  USB VBUS feeds the same buck through one SS34, so the board flashes and runs from the cable alone.
- Part numbers reused from rev 10 wherever the cell is the same, so Basic parts stay Basic.
- Diode pads: on the EasyEDA SMA footprints pad 1 = K (SS34, SS56; checked against the symbol and
  the silk band). D2 is bidirectional since rev 2 (SMAJ18CA, C19077539) on the same land without the
  band. The first draft used SMAJ18A C499735 on the mirrored "-R-RD" footprint (pad 2 = K). Verify
  polarised parts in the CPL preview regardless.
- JLCPCB "Preferred" Extended parts carry no loading fee on Economic assembly (their FAQ, 2026-09):
  the MMSZ5231B zeners, the SMAJ18CA and the SS56 are Preferred. The other Extended parts (module, AP63203,
  LVC2G17, USB-C, inductor, PTC, terminal) have no Basic or Preferred equivalent in JLCPCB's
  library (searched 2026-10-21).
- SW1/SW2 use pads 1 and 4 only: diagonal pads are always across the switch.

Revision 2 (2026-10-27), from the rev 1 review's open items and a passive-to-IC audit:
- U9 THVD1420 (C3235215) in place of the SP3485: its receiver has full fail-safe (an idle,
  shorted or open bus reads as a 1), so an idle TERMINATED bus is defined. Rev 1's 20k bias pair
  (R66/R67) gave only ~10 mV once JP2 was bridged, and is gone.
- U3 TPS3808G30 (C189211) on EN: open-drain, 2.79 V threshold, 20 ms delay (CT open). EN is
  released only once +3V3 is good, so a start from a pre-biased or slowly rising rail is defined.
  The RESET button moves to its MR input (debounced by the delay). R4 stays as RESET's pull-up.
- Q1-Q4 AO3400A (C20917, Basic, same SOT-23 pinout as the 2N7002): fully on at a 3.3 V gate, so a
  line sinks a controller's 1k pull-up to 12 V (the 2N7002's 2.5 V worst-case threshold did not).
- D26 BAT54 (C22466368, Preferred) feeds the four line pull-ups (+3V3_PU) from +3V3: a reader
  powered while the board is not no longer back-feeds the dead 3.3 V rail through 1k + pull-up per line.
- C1/C2 1206 50 V (C13585): the 0805 25 V parts held 40-55 % of 10 uF at 12-16 V bias.

Rev 2 audit round 1 (2026-10-27), with the board grown from 42 x 44 to 42 x 47 mm to fit them:
- R86 1k between U3's RESET and EN: U3 discharged C13 (1 uF) with no limit, ~35 mA against its
  5 mA absolute maximum (TPS3808 6.1). EN low is then <= 0.71 V on guaranteed figures (U3's VOL 0.4 V plus 1k/11k of
  the rest), against the ESP32's VIL of 0.81 V.
- C45 10 nF on MR (28 mm of route beside other signals; the chip reacts to ~1 ns pulses).
- C46 100 nF on +3V3_PU (59 mm of 0.2 mm track fed through the BAT54).
- R87 100k bleed on VBUS: D3's reverse leakage charged an unplugged VBUS toward +VIN.
- R88/R89 10 ohm between the bus (SM712, termination) and U9's A/B: the SM712 clamps above the
  THVD1420's +-16 V (TI's surge reference circuit, THVD1420 fig. 8-5).
- D2 is an SMAJ18CA (bidirectional, C19077539, Preferred) on +VIN_F, ahead of D1: a negative surge
  now meets the TVS, not D1's 40 V reverse rating; a reversed 12 V supply (under the 18 V standoff)
  is still blocked by D1.
- R3/R81 470 ohm: green Vf up to 3.1 V left 0.3-0.7 mA through 1k.
"""

STD = "/usr/share/kicad/footprints"
WB = "wb"  # ../lib/wb.pretty (symlinked as lib/), from easyeda2kicad

# Footprints: (library, name)
FP = {
    "esp32mini": (WB, "BULETM-SMD_ESP32-S3-MINI-1-N8"),   # EasyEDA names the N8 footprint; every MINI-1 variant shares the land pattern
    "tsot26": (WB, "TSOT-26_L2.9-W1.6-P0.95-LS2.8-BL"),
    "sot6bl": (WB, "SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL"),
    "sot6br": (WB, "SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BR"),        # TPS3808 (EasyEDA C189211)
    "sot23_bat54": (WB, "SOT-23-3_L2.9-W1.4-P1.90-LS2.5-BR"),   # BAT54 (EasyEDA C22466368): 1 = A, 3 = K
    "soic8_thvd": (WB, "SOIC-8_L4.9-W3.9-P1.27-LS6.0-BL"),      # THVD1420DR (EasyEDA C3235215)
    "sot23_2n7002": (WB, "SOT-23-3_L2.9-W1.3-P1.90-LS2.4-BR"),
    "sma_ss34": (WB, "SMA_L4.3-W2.6-LS5.2-RD"),
    "sma56": (WB, "SMA_L4.3-W2.6-LS5.0-RD"),                      # the full board's SS56 land
    "sma_tvs": (WB, "SMA_L4.3-W2.6-LS5.0-RD"),
    "sma_tvs_bi": (WB, "SMA_L4.3-W2.6-LS5.0-BI"),                # the same land without the cathode band
    "sod123": (WB, "SOD-123_L2.8-W1.6-LS3.7-RD"),
    "led_r": (WB, "LED0805-R-RD"),
    "led": (WB, "LED0805-RD"),
    "f1812": (WB, "F1812"),
    "ind5040": (WB, "IND-SMD_L5.0-W5.0"),
    "tact": (WB, "SW-SMD_4P-L5.1-W5.1-P3.70-LS6.5-TL_H1.5"),
    "usbc": (WB, "USB-C-SMD_TYPE-C-16PIN-2MD-073"),
    "term8": (WB, "CONN-TH_8P-P3.50_KF2EDGR-3.5-8P"),
    "soic8": (WB, "SOIC-8_L5.0-W4.0-P1.27-LS6.0-BL"),
    "sot23_712": (WB, "SOT-23-3_L3.0-W1.7-P0.95-LS2.9-BR"),
    "r0603": ("Resistor_SMD", "R_0603_1608Metric"),
    "c0603": ("Capacitor_SMD", "C_0603_1608Metric"),
    "c0805": ("Capacitor_SMD", "C_0805_2012Metric"),
    "c1206": ("Capacitor_SMD", "C_1206_3216Metric"),
    "sj": ("Jumper", "SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm"),
    "hole": ("MountingHole", "MountingHole_3.2mm_M3"),
}

# Passive part numbers (all JLCPCB Basic)
R = {"100": "C22775", "1k": "C21190", "5.1k": "C23186", "10k": "C25804", "100k": "C25803",
     "20k": "C4184", "120": "C22787", "470": "C23179", "10": "C22859", "4.7k": "C23162", "1.5k": "C22843",
     "22k": "C31850"}
C = {"100p": ("c0603", "C14858"), "100n": ("c0603", "C14663"), "1u": ("c0603", "C15849"), "10n": ("c0603", "C57112"),
     "10u25": ("c0805", "C15850"), "22u25": ("c0805", "C45783"), "22u6": ("c0603", "C59461"),
     "10u50_1206": ("c1206", "C13585")}

PARTS = []  # (ref, footprint key, value, lcsc or None (= hand-fitted / not placed), {pad: net})


def part(ref, fp, value, lcsc, pads):
    PARTS.append((ref, fp, value, lcsc, pads))


def res(ref, value, a, b):
    part(ref, "r0603", value, R[value], {"1": a, "2": b})


def cap(ref, value, a, b="GND"):
    fp, lcsc = C[value]
    part(ref, fp, value.replace("50_1206", "").replace("25", "").replace("u6", "u"), lcsc, {"1": a, "2": b})


# --- Block 1: terminal block and 8-16 V input ------------------------------------------------------
part("J3", "term8", "12V GND D0 D1 LED BEEP A B", "C441177",
     {"1": "+VIN_RAW", "2": "GND", "3": "D0_RAW", "4": "D1_RAW", "5": "RDR_LED", "6": "RDR_BEEP",
      "7": "RS485_A", "8": "RS485_B"})   # mating plug KF2EDGK-3.5-8P, bought separately
part("F1", "f1812", "0.5A 24V", "C516067", {"1": "+VIN_RAW", "2": "+VIN_F"})   # rev 10's reader fuse part
# rev 2 (audit round 2): in a negative surge D2 holds +VIN_F at -29 V while C1/C2 hold +VIN at up to
# 16 V, 45 V across D1: the SS34's 40 V was short. The full board's SS56 (60 V, Preferred, no fee).
part("D1", "sma56", "SS56", "C18199169", {"1": "+VIN", "2": "+VIN_F"})   # series reverse-polarity; 1 = K
part("D2", "sma_tvs_bi", "SMAJ18CA", "C19077539", {"1": "+VIN_F", "2": "GND"})   # rev 2: bidirectional, ahead of D1; 18 V standoff > 16 V max in; Preferred
cap("C1", "10u50_1206", "+VIN")   # rev 2: 1206 50 V, ~9 uF at 16 V

# --- Block 2: buck to 3.3 V (AP63203, datasheet figure 21) ---------------------------------------
part("U2", "tsot26", "AP63203", "C780769",
     {"1": "+3V3", "2": "+VIN", "3": "+VIN", "4": "GND", "5": "U2_SW", "6": "U2_BST"})   # FB = VOUT, EN = VIN
cap("C2", "10u50_1206", "+VIN")
cap("C3", "100n", "U2_BST", "U2_SW")
part("L1", "ind5040", "4.7uH", "C305174", {"1": "U2_SW", "2": "+3V3"})   # rev 10's L3
cap("C4", "22u25", "+3V3")
cap("C5", "22u25", "+3V3")
res("R3", "470", "+3V3", "D7_A")
part("D7", "led_r", "green", "C2297", {"1": "D7_A", "2": "GND"})  # PWR; C2297: 1 = A

# --- Block 3: USB-C (programming, and bench power through D3) ---------------------------------------
part("J1", "usbc", "USB-C", "C2765186",
     {"A1B12": "GND", "B1A12": "GND", "A4B9": "VBUS", "B4A9": "VBUS", "A5": "CC1", "B5": "CC2",
      "A6": "USB_DP", "B6": "USB_DP", "A7": "USB_DN", "B7": "USB_DN", "13": "GND", "14": "GND"})
cap("C6", "10u25", "VBUS")
# rev 2: bleeds D3's reverse leakage off an unplugged VBUS. Round 2: 100k held VBUS low only below
# ~45 C (typical); the SS34 is guaranteed only to 0.5 mA, and a Type-C source waits for VBUS < 0.8 V.
# 1k: <= 0.5 V at 0.5 mA (25 C). MDD also guarantees <= 5 mA at 125 C; ~2 mA at 85 C interpolated, so
# a hot board with 12 V present may hold VBUS near 2 V (documented: remove 12 V). 5 mA from USB.
res("R87", "1k", "VBUS", "GND")
res("R1", "5.1k", "CC1", "GND")
res("R2", "5.1k", "CC2", "GND")
part("D3", "sma_ss34", "SS34", "C8678", {"1": "+VIN", "2": "VBUS"})   # 4.6 V into the buck (min 3.8); off when 12 V is present

# --- Block 4: MCU, buttons, status LEDs -------------------------------------------------------------
# ESP32-S3-MINI-1 pad -> GPIO from its symbol: 4 IO0, 8-15 IO4-IO11, 23 IO19, 24 IO20, 25 IO21,
# 27 IO47, 34 IO38, 39 TXD0 (IO43), 40 RXD0 (IO44), 45 EN. 7 IO3, 41 IO45, 44 IO46 strapping and
# 26 IO26 (PSRAM on N4R2): no connect. 42, 43, 46-60 and the 13 pads the footprint names "GND"
# (nine centre + four corners = module pins 61-65) are GND.
part("U1", "esp32mini", "ESP32-S3-MINI-1-N4R2", "C3013941", {
    "1": "GND", "2": "GND", "3": "+3V3", "4": "IO0",
    "8": "WG_D0", "9": "WG_D1",             # IO4 / IO5: buffered D0 / D1 (as rev 10)
    "10": "D0_TX", "11": "D1_TX",           # IO6 / IO7: D0 / D1 open-drain drive (reader emulation)
    "12": "LED_TX", "13": "BEEP_TX",        # IO8 / IO9: LED / BEEP open-drain drive (reader mode)
    "14": "LED_RX", "15": "BEEP_RX",        # IO10 / IO11: buffered LED / BEEP (emulation mode)
    "23": "USB_DN", "24": "USB_DP", "25": "IO21", "27": "IO47",
    "34": "RS485_DE", "39": "RS485_DI", "40": "RS485_RO", "45": "EN",
    "42": "GND", "43": "GND", "GND": "GND",
    **{str(n): "GND" for n in range(46, 61)}})
cap("C11", "22u6", "+3V3")
cap("C12", "100n", "+3V3")
res("R4", "10k", "+3V3", "EN")    # the supervisor's open-drain RESET needs it
cap("C13", "1u", "EN")
# rev 2: TPS3808G30 holds EN low until +3V3 > 2.79 V, then 20 ms more (CT open). SW2 on MR.
part("U3", "sot6br", "TPS3808G30", "C189211",
     {"1": "U3_RST", "2": "GND", "3": "RST_MR", "5": "+3V3", "6": "+3V3"})   # 4 = CT, open
cap("C44", "100n", "+3V3")
res("R86", "1k", "U3_RST", "EN")       # limits U3's discharge of C13 (5 mA abs max on RESET)
cap("C45", "10n", "RST_MR")            # MR filter
part("SW2", "tact", "RESET", "C318884", {"1": "RST_MR", "4": "GND"})   # MR has a 90k internal pull-up
res("R5", "10k", "+3V3", "IO0")
part("SW1", "tact", "BOOT", "C318884", {"1": "IO0", "4": "GND"})
res("R8", "1k", "IO21", "D8_K")
part("D8", "led", "red", "C84256", {"1": "D8_K", "2": "+3V3"})  # FAULT (ESPHome status LED); C84256: 1 = -
res("R81", "470", "IO47", "D23_K")
part("D23", "led_r", "green", "C2297", {"1": "+3V3", "2": "D23_K"})  # OK (API connected); C2297: 1 = A

# --- Block 5: reader lines D0, D1, LED, BEEP -- bidirectional cells ---------------------------------
part("U4", "sot6bl", "SN74LVC2G17", "C10429",
     {"1": "D0_IN", "2": "GND", "3": "D1_IN", "4": "WG_D1", "5": "+3V3", "6": "WG_D0"})
cap("C16", "100n", "+3V3")
part("U11", "sot6bl", "SN74LVC2G17", "C10429",
     {"1": "LED_IN", "2": "GND", "3": "BEEP_IN", "4": "BEEP_RX", "5": "+3V3", "6": "LED_RX"})
cap("C41", "100n", "+3V3")
# (raw wire, buffered node, drive GPIO, series R, zener, 100p, pull-up, FET, gate R, gate pull-down)
CELLS = (("D0_RAW", "D0_IN", "D0_TX", "R9", "D5", "C14", "R11", "Q3", "R24", "R25"),
         ("D1_RAW", "D1_IN", "D1_TX", "R10", "D6", "C15", "R12", "Q4", "R26", "R27"),
         ("RDR_LED", "LED_IN", "LED_TX", "R20", "D24", "C42", "R22", "Q1", "R6", "R13"),
         ("RDR_BEEP", "BEEP_IN", "BEEP_TX", "R21", "D25", "C43", "R23", "Q2", "R7", "R14"))
for raw, node, tx, rs, z, c, rp, q, rg, rgd in CELLS:
    res(rs, "1k", raw, node)
    part(z, "sod123", "MMSZ5231B", "C19077422", {"1": node, "2": "GND"})  # 1 = K
    cap(c, "100p", node)
    # rev 2 (audit round 3): 22k, was 10k. The buffer node is the reader's VOL plus 1/23 (was 1/11) of
    # the difference to the rail, so the reader's low level has ~0.14 V more room (see R95 below).
    res(rp, "22k", "+3V3_PU", node)
    gate = q + "_G"
    res(rg, "100", tx, gate)
    res(rgd, "100k", gate, "GND")
    part(q, "sot23_2n7002", "AO3400A", "C20917", {"1": gate, "2": "GND", "3": raw})   # rev 2: on at 3.3 V
# rev 2: the pull-ups' supply, so a powered reader cannot back-feed a dead +3V3 through them
part("D26", "sot23_bat54", "BAT54", "C22466368", {"1": "+3V3", "3": "+3V3_PU"})
# rev 2 (audit round 2, S1): D26 sources but cannot sink, so a reader's own 5 V pull-ups (or a
# controller's 12 V) lifted +3V3_PU to ~4.9 V through each cell's 1k + pull-up, and C46 held it through a
# 50 us pulse: the buffer node then needed the reader at <= ~0.4 V. R95 4.7k (in C46's land; C46
# removed) holds the rail down, for 0.7 mA. With the 22k pull-ups the line's low limit is
# (0.8 x 23 - 3.36) / 22 = 0.684 V at the highest rail (D26 drop 0), so 0.65 V at the terminal holds
# whatever is attached; idle-high leaves room for ~31-38 uA leakage per node (audit rounds 3-4).
res("R95", "4.7k", "+3V3_PU", "GND")

# --- Block 6: RS-485 / OSDP on UART0 (rev 10 block 14, less the bias network) ----------------------
# rev 2: THVD1420, full fail-safe receiver, so no bias resistors are needed on this node
part("U9", "soic8_thvd", "THVD1420", "C3235215",
     {"1": "RS485_RO", "2": "RS485_DE", "3": "RS485_DE", "4": "RS485_DI", "5": "GND",
      "6": "U9_A", "7": "U9_B", "8": "+3V3"})
part("R88", "r0603", "10", "C844519", {"1": "RS485_A", "2": "U9_A"})   # rev 2: surge resistors between the SM712 and the
part("R89", "r0603", "10", "C844519", {"1": "RS485_B", "2": "U9_B"})   # transceiver; pulse-proof Vishay CRCW...HP (TI's BOM)
cap("C37", "100n", "+3V3")
res("R65", "10k", "RS485_DE", "GND")      # receive by default, and through boot (ROM prints on TXD0)
res("R75", "10k", "RS485_RO", "+3V3")     # RO is high-Z while transmitting (/RE tied to DE)
res("R68", "120", "RS485_A", "JP2_A")     # 120 ohm termination, bridge JP2 at the end of the line
part("JP2", "sj", "TERM", None, {"1": "JP2_A", "2": "RS485_B"})

# --- Block 7: surge/ESD on every field wire (SM712: +12 / -7 V standoff) ---------------------------
for ref, a, b in (("D15", "D0_RAW", "D1_RAW"), ("D16", "RDR_LED", "RDR_BEEP"), ("D19", "RS485_A", "RS485_B")):
    part(ref, "sot23_712", "SM712", "C32677", {"1": a, "2": b, "3": "GND"})

for i in (1, 2):
    part(f"H{i}", "hole", "M3", None, {})

if __name__ == "__main__":
    from collections import Counter
    refs = Counter(p[0] for p in PARTS)
    assert all(v == 1 for v in refs.values()), [k for k, v in refs.items() if v > 1]
    nets = Counter(n for p in PARTS for n in p[4].values())
    print(len(PARTS), "parts,", len(nets), "nets")
    print("single-pad nets:", sorted(n for n, c in nets.items() if c == 1))
    ext = sorted({p[3] for p in PARTS if p[3]})
    print(len(ext), "distinct LCSC parts")
