# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Wiegand bridge LITE, revision 1 -- the netlist, as data.

Source of truth for build_pcb.py. A stripped-down sibling of ../wiegand-bridge (rev 10/11): the
smallest board that puts an ESP32 on a Wiegand reader (the author, 2026-10-21). It assumes the reader is
powered already, runs from 12 V +-4 V (8-16 V), and keeps USB-C for programming (and bench power).
Dropped: battery, screens, relay, switch inputs IN1-4, the reader 12 V boost/shed, the I/O expander,
the W5500/Qwiic headers, the reader current sense.

- One pluggable 3.5 mm terminal block, 8 ways: 12V GND D0 D1 LED BEEP A B.
- Four BIDIRECTIONAL open-drain 5 V lines (D0, D1, LED, BEEP): each has rev 10's input cell
  (1k + 5.1 V zener + 100 pF + 10k pull-up -> 74LVC2G17 Schmitt buffer -> GPIO) AND rev 10's
  output cell (2N7002 open drain, 100 ohm gate, 100k pull-down) on the same wire. Reader mode:
  read D0/D1, drive LED/BEEP. Reader-emulation mode (toward an access controller): pulse D0/D1,
  read LED/BEEP. The 10k pull-up keeps the wiegand component quiet with nothing attached.
- RS-485/OSDP port kept (SP3485 on UART0), minus rev 10's strong-bias jumpers and node-power terminal.
- ESP32-S3-MINI-1 (15.4 x 20.5 mm; the N4R2 variant is what JLCPCB stocks, 2026-10-21). Same chip
  family as rev 10, so the firmware carries over with a pin remap (firmware/wiegand-bridge-lite.yaml).
- 3.3 V straight from the input: AP63203 (fixed 3.3 V, 3.8-32 V in, TSOT-26), per its datasheet
  figure 21: 10 uF in, 2x 22 uF out, 100 nF BST, 4.7 uH, EN tied to VIN, FB tied to VOUT.
  USB VBUS feeds the same buck through one SS34, so the board flashes and runs from the cable alone.
- Part numbers reused from rev 10 wherever the cell is the same, so Basic parts stay Basic.
- Diode pads: on the EasyEDA SMA footprints pad 1 = K (SS34, SMAJ18A C19077538 -- the same "-RD"
  footprint family as rev 10's SMAJ15A; checked against the symbol and the silk band). The first
  draft used SMAJ18A C499735 on the mirrored "-R-RD" footprint (pad 2 = K); swapped 2026-10-21 for
  the Preferred part (no JLCPCB loading fee, 350x the stock). Verify polarised parts in the CPL
  preview regardless.
- JLCPCB "Preferred" Extended parts carry no loading fee on Economic assembly (their FAQ, 2026-09):
  the MMSZ5231B zeners and the SMAJ18A are Preferred. The other Extended parts (module, AP63203,
  LVC2G17, USB-C, inductor, PTC, terminal) have no Basic or Preferred equivalent in JLCPCB's
  library (searched 2026-10-21).
- SW1/SW2 use pads 1 and 4 only: diagonal pads are always across the switch.
"""

STD = "/usr/share/kicad/footprints"
WB = "wb"  # ../lib/wb.pretty (symlinked as lib/), from easyeda2kicad

# Footprints: (library, name)
FP = {
    "esp32mini": (WB, "BULETM-SMD_ESP32-S3-MINI-1-N8"),
    "tsot26": (WB, "TSOT-26_L2.9-W1.6-P0.95-LS2.8-BL"),
    "sot6bl": (WB, "SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL"),
    "sot23_2n7002": (WB, "SOT-23-3_L2.9-W1.3-P1.90-LS2.4-BR"),
    "sma_ss34": (WB, "SMA_L4.3-W2.6-LS5.2-RD"),
    "sma_tvs": (WB, "SMA_L4.3-W2.6-LS5.0-RD"),
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
    "sj": ("Jumper", "SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm"),
    "hole": ("MountingHole", "MountingHole_3.2mm_M3"),
}

# Passive part numbers (all JLCPCB Basic)
R = {"100": "C22775", "1k": "C21190", "5.1k": "C23186", "10k": "C25804", "100k": "C25803",
     "20k": "C4184", "120": "C22787"}
C = {"100p": ("c0603", "C14858"), "100n": ("c0603", "C14663"), "1u": ("c0603", "C15849"),
     "10u25": ("c0805", "C15850"), "22u25": ("c0805", "C45783"), "22u6": ("c0603", "C59461")}

PARTS = []  # (ref, footprint key, value, lcsc or None (= hand-fitted / not placed), {pad: net})


def part(ref, fp, value, lcsc, pads):
    PARTS.append((ref, fp, value, lcsc, pads))


def res(ref, value, a, b):
    part(ref, "r0603", value, R[value], {"1": a, "2": b})


def cap(ref, value, a, b="GND"):
    fp, lcsc = C[value]
    part(ref, fp, value.replace("25", "").replace("u6", "u"), lcsc, {"1": a, "2": b})


# --- Block 1: terminal block and 8-16 V input ------------------------------------------------------
part("J3", "term8", "12V GND D0 D1 LED BEEP A B", "C441177",
     {"1": "+VIN_RAW", "2": "GND", "3": "D0_RAW", "4": "D1_RAW", "5": "RDR_LED", "6": "RDR_BEEP",
      "7": "RS485_A", "8": "RS485_B"})   # mating plug KF2EDGK-3.5-8P, bought separately
part("F1", "f1812", "0.5A 24V", "C516067", {"1": "+VIN_RAW", "2": "+VIN_F"})   # rev 10's reader fuse part
part("D1", "sma_ss34", "SS34", "C8678", {"1": "+VIN", "2": "+VIN_F"})   # series reverse-polarity; 1 = K
part("D2", "sma_tvs", "SMAJ18A", "C19077538", {"1": "+VIN", "2": "GND"})   # 18 V standoff > 16 V max in; 1 = K. JLCPCB Preferred (no loading fee), 54k stock
cap("C1", "10u25", "+VIN")

# --- Block 2: buck to 3.3 V (AP63203, datasheet figure 21) ---------------------------------------
part("U2", "tsot26", "AP63203", "C780769",
     {"1": "+3V3", "2": "+VIN", "3": "+VIN", "4": "GND", "5": "U2_SW", "6": "U2_BST"})   # FB = VOUT, EN = VIN
cap("C2", "10u25", "+VIN")
cap("C3", "100n", "U2_BST", "U2_SW")
part("L1", "ind5040", "4.7uH", "C305174", {"1": "U2_SW", "2": "+3V3"})   # rev 10's L3
cap("C4", "22u25", "+3V3")
cap("C5", "22u25", "+3V3")
res("R3", "1k", "+3V3", "D7_A")
part("D7", "led_r", "green", "C2297", {"1": "D7_A", "2": "GND"})  # PWR; C2297: 1 = A

# --- Block 3: USB-C (programming, and bench power through D3) ---------------------------------------
part("J1", "usbc", "USB-C", "C2765186",
     {"A1B12": "GND", "B1A12": "GND", "A4B9": "VBUS", "B4A9": "VBUS", "A5": "CC1", "B5": "CC2",
      "A6": "USB_DP", "B6": "USB_DP", "A7": "USB_DN", "B7": "USB_DN", "13": "GND", "14": "GND"})
cap("C6", "10u25", "VBUS")
res("R1", "5.1k", "CC1", "GND")
res("R2", "5.1k", "CC2", "GND")
part("D3", "sma_ss34", "SS34", "C8678", {"1": "+VIN", "2": "VBUS"})   # 4.6 V into the buck (min 3.8); off when 12 V is present

# --- Block 4: MCU, buttons, status LEDs -------------------------------------------------------------
# ESP32-S3-MINI-1 pad -> GPIO from its symbol: 4 IO0, 8-15 IO4-IO11, 23 IO19, 24 IO20, 25 IO21,
# 27 IO47, 34 IO38, 39 TXD0 (IO43), 40 RXD0 (IO44), 45 EN. 7 IO3, 41 IO45, 44 IO46 strapping and
# 26 IO26 (PSRAM on N4R2): no connect. 42, 43, 46-60 and the nine centre pads are GND.
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
res("R4", "10k", "+3V3", "EN")
cap("C13", "1u", "EN")
part("SW2", "tact", "RESET", "C318884", {"1": "EN", "4": "GND"})
res("R5", "10k", "+3V3", "IO0")
part("SW1", "tact", "BOOT", "C318884", {"1": "IO0", "4": "GND"})
res("R8", "1k", "IO21", "D8_K")
part("D8", "led", "red", "C84256", {"1": "D8_K", "2": "+3V3"})  # FAULT (ESPHome status LED); C84256: 1 = -
res("R81", "1k", "IO47", "D23_K")
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
    res(rp, "10k", "+3V3", node)
    gate = q + "_G"
    res(rg, "100", tx, gate)
    res(rgd, "100k", gate, "GND")
    part(q, "sot23_2n7002", "2N7002", "C8545", {"1": gate, "2": "GND", "3": raw})

# --- Block 6: RS-485 / OSDP on UART0 (rev 10 block 14, less the strong-bias jumpers) ---------------
part("U9", "soic8", "SP3485", "C8963",
     {"1": "RS485_RO", "2": "RS485_DE", "3": "RS485_DE", "4": "RS485_DI", "5": "GND",
      "6": "RS485_A", "7": "RS485_B", "8": "+3V3"})
cap("C37", "100n", "+3V3")
res("R65", "10k", "RS485_DE", "GND")      # receive by default, and through boot (ROM prints on TXD0)
res("R75", "10k", "RS485_RO", "+3V3")     # RO is high-Z while transmitting (/RE tied to DE)
res("R66", "20k", "RS485_A", "+3V3")      # weak fail-safe bias
res("R67", "20k", "RS485_B", "GND")
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
