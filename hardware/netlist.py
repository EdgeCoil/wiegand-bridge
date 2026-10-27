# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Wiegand reader bridge, revision 12 -- the netlist, as data.

Source of truth for build_pcb.py. See docs/design.md for the reasoning; pad numbers are
taken from each part's EasyEDA symbol/footprint (lib/wb.*) or the KiCad stock footprint.

Changes from the guide's text, made while assigning real parts (2026-10-11):
- R19 191k and R50 4.02k are Extended at JLCPCB. R19 -> 200k (12.6 V reader rail), R30 -> 200k
  (JP1 bridged -> 13.2 V), R50 -> 4.7k (~260 mA charge), then 10k (122 mA,
  thermal review 2026-10-11). All Basic. (The US$3.07 Extended fee these
  swaps avoided is Economic PCBA's; Standard charges US$1.53 per line, Basic or Extended alike.)
- The guide's C1a-c are C31/C32/C33: JLCPCB's BOM parser counts 0 placements for designators ending in a letter.
- J3 and J9 are each three 2-way blocks: J3/J10/J11 (reader) and J9/J12/J13 (inputs).
- Revision 10 (2026-10-11): 6-36 V input (LMR16020 60 V buck, SS56, SMAJ36CA, 60 V input
  PTC, 50 V caps), DC barrel jack, relay footprint (not fitted), TCA9535 expander (charge status,
  ext power, 5 V power-good, relay drive, W5500 reset, spares), RS-485 port (SP3485), SM712 surge
  protection on every field wire, reader current sense (0.2 ohm + LMV321), W5500 / Qwiic /
  expansion headers, J5 OLED socket fitted by JLCPCB.
- Revision 11 (2026-10-20): a red + green status pair. D8 becomes red (IO21, ESPHome's
  status LED: blinks on warning/error); D23 green on IO47 (firmware: healthy/connected). IO47 was
  DISP_RST to J6 (TFT/EPD, never fitted): DISP_RST moves to expander P06, so J19-3 now shares it.
- SW1-SW3 use pads 1 and 4 only: diagonal pads are always across the switch, whichever way the
  part pairs its pins internally.
- Revision 12 (2026-10-27, rev 11 never ordered), from a passive-to-IC audit:
  * Reader monitor: U12 INA226 (I2C 0x40) reading R59, a 0.1 ohm alloy shunt between the boost's
    output capacitors and the shed switch Q11 (Block 16 has the requirements and the budget), with
    Kelvin sense tabs. It replaces the 0.2 ohm low-side shunt + LMV321 x21 (IO9) and the R31/R32 rail
    divider (IO2). VBUS reads the reader terminal through R82 4.7k with a BAT54 clamp. The reader's
    return is plain GND. IO2 and IO9 are free.
  * U9 THVD1420 in place of the SP3485: a full fail-safe receiver (idle, open or shorted bus reads
    1), so an idle terminated bus is defined on this node without bias. The 20k weak-bias pair
    (R66/R67) is gone; the 390 ohm JP3/JP4 bias stays for buses whose other nodes need it.
"""

STD = "/usr/share/kicad/footprints"
WB = "wb"  # lib/wb.pretty, from easyeda2kicad

# Footprints: (library, name)
FP = {
    "esp32": (WB, "WIRELM-SMD_ESP32-S3-WROOM-1"),
    "tsot6": (WB, "TSOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL"),
    "sot6bl": (WB, "SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL"),
    "sot6br": (WB, "SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BR"),
    "vson10": ("Package_SON", "Texas_DRC0010J"),
    "soic8ep": (WB, "SOIC-8_L4.9-W3.9-P1.27-LS6.0-BL-EP3.3"),
    "sot23_2n7002": (WB, "SOT-23-3_L2.9-W1.3-P1.90-LS2.4-BR"),
    "sot23_ao3401": (WB, "SOT-23_L2.9-W1.3-P1.90-LS2.4-BR"),
    "sma_ss34": (WB, "SMA_L4.3-W2.6-LS5.2-RD"),
    "sma_tvs": (WB, "SMA_L4.3-W2.6-LS5.0-RD"),
    "sma_tvs_bi": (WB, "SMA_L4.3-W2.6-LS5.0-BI"),                # the same land without the cathode band
    "sod123": (WB, "SOD-123_L2.8-W1.6-LS3.7-RD"),
    "led_r": (WB, "LED0805-R-RD"),
    "led": (WB, "LED0805-RD"),
    "f1812": (WB, "F1812"),
    "ind5040": (WB, "IND-SMD_L5.0-W5.0"),
    "ind4030": (WB, "IND-SMD_L4.0-W4.0"),
    "tact": (WB, "SW-SMD_4P-L5.1-W5.1-P3.70-LS6.5-TL_H1.5"),
    "usbc": (WB, "USB-C-SMD_TYPE-C-16PIN-2MD-073"),
    "kf128": (WB, "CONN-TH_P5.08_KF128-5.08-2P"),
    "r0603": ("Resistor_SMD", "R_0603_1608Metric"),
    "c0603": ("Capacitor_SMD", "C_0603_1608Metric"),
    "c0805": ("Capacitor_SMD", "C_0805_2012Metric"),
    "c1206": ("Capacitor_SMD", "C_1206_3216Metric"),
    "xh2": ("Connector_JST", "JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical"),
    "xh4": ("Connector_JST", "JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical"),
    "sock4": ("Connector_PinSocket_2.54mm", "PinSocket_1x04_P2.54mm_Vertical"),
    "hdr8": ("Connector_PinHeader_2.54mm", "PinHeader_1x08_P2.54mm_Vertical"),
    "hdr2": ("Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical"),
    "tp": ("TestPoint", "TestPoint_Pad_D1.5mm"),
    "sj": ("Jumper", "SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm"),
    "hole": ("MountingHole", "MountingHole_3.2mm_M3"),
    # revision 10
    "lmr16020": (WB, "SOIC-8_L4.9-W3.9-P1.27-LS6.0-BL-EP"),
    "sma56": (WB, "SMA_L4.3-W2.6-LS5.0-RD"),
    "ind0630": (WB, "IND-SMD_L7.0-W6.6_FXL0630"),
    "tssop24": (WB, "TSSOP-24_L7.8-W4.4-P0.65-LS6.4-BL"),
    "soic8": (WB, "SOIC-8_L5.0-W4.0-P1.27-LS6.0-BL"),
    "sot23_712": (WB, "SOT-23-3_L3.0-W1.7-P0.95-LS2.9-BR"),
    "sod123f": (WB, "SOD-123F_L2.7-W1.6-LS3.8-RD"),
    "sot235": (WB, "SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR"),
    "relay": (WB, "RELAY-TH_SRD-XXVDC-XL-C"),
    "dcjack": (WB, "DC-IN-TH_DC-005-5.5-2.0"),
    "qwiic": (WB, "CONN-SMD_BM04B-SRSS-TB"),
    "sock4jlc": (WB, "HDR-TH_4P-P2.54-V-F"),
    "r1206": ("Resistor_SMD", "R_1206_3216Metric"),
    "hdr2x6": ("Connector_PinHeader_2.54mm", "PinHeader_2x06_P2.54mm_Vertical"),
    "f2920": (WB, "F2920"),
    "sod123fl_bi": (WB, "SOD-123FL_L2.7-W1.8-LS3.8-BI"),
    "rarray4": (WB, "RES-ARRAY-SMD_0603-8P-L3.2-W1.6-BL"),
    # revision 12
    "msop10": (WB, "MSOP-10_L3.0-W3.0-P0.50-LS5.0-BL"),        # INA226AIDGSR (EasyEDA C49851)
    "soic8_thvd": (WB, "SOIC-8_L4.9-W3.9-P1.27-LS6.0-BL"),      # THVD1420DR (EasyEDA C3235215)
    "sot23_bat54": (WB, "SOT-23-3_L2.9-W1.4-P1.90-LS2.5-BR"),   # BAT54 (EasyEDA C22466368): 1 = A, 3 = K
    "r1206k": (WB, "R_1206_Kelvin"),                            # KiCad R_1206 + net-tied sense pads 3/4
}

# Passive part numbers (all JLCPCB Basic)
R = {"100": "C22775", "1k": "C21190", "4.7k": "C23162", "5.1k": "C23186", "10k": "C25804",
     "15k": "C22809", "100k": "C25803", "200k": "C25811", "39k": "C23153", "47k": "C25819",
     "8.2k": "C25981", "20k": "C4184", "120": "C22787", "390": "C23151", "68k": "C23231",
     "10": "C22859", "470": "C23179", "1.5k": "C22843"}
C = {"100p": ("c0603", "C14858"), "10n": ("c0603", "C57112"), "100n": ("c0603", "C14663"),
     "1u": ("c0603", "C15849"), "10u": ("c0603", "C19702"), "10u25": ("c0805", "C15850"),
     "22u25": ("c0805", "C45783"), "22u25_1206": ("c1206", "C12891"), "22u6": ("c0603", "C59461"),
     "10u50_1206": ("c1206", "C13585")}

PARTS = []  # (ref, footprint key, value, lcsc or None (= hand-fitted / not placed), {pad: net})


def part(ref, fp, value, lcsc, pads):
    PARTS.append((ref, fp, value, lcsc, pads))


def res(ref, value, a, b):
    part(ref, "r0603", value, R[value], {"1": a, "2": b})


def cap(ref, value, a, b="GND"):
    fp, lcsc = C[value]
    part(ref, fp, value.replace("50_1206", "").replace("25_1206", "").replace("25", "").replace("u6", "u"), lcsc, {"1": a, "2": b})


# --- Block 1: 6-36 V input -----------------------------------------------------------------------
part("J2", "kf128", "6-36V IN", "C474952", {"1": "+VIN_RAW", "2": "GND"})
part("J14", "dcjack", "DC IN", None, {"4": "+VIN_RAW", "3": "GND", "2": "GND"})  # 4 = centre pin (+); 2 = plug switch
part("F2", "f2920", "2A 60V", "C49326266", {"1": "+VIN_RAW", "2": "+VIN_F"})   # 2 A hold: ~1.05 A at 6 V in, derated warm
part("D1", "sma56", "SS56", "C18199169", {"1": "+VIN", "2": "+VIN_F"})
part("D2", "sma_tvs_bi", "SMAJ36CA", "C19077551", {"1": "+VIN", "2": "GND"})  # bidirectional: no band
for r in ("C31", "C32", "C33"):   # the guide's C1a-c
    cap(r, "10u50_1206", "+VIN")

# --- Block 2: buck to 5 V (LMR16020, 60 V; datasheet SNVSAH8A sec. 8.2) --------------------------
part("U2", "lmr16020", "LMR16020", "C190006",
     {"1": "U2_BST", "2": "+VIN", "3": "+VIN", "4": "U2_RT", "5": "U2_FB", "6": "PGOOD5", "7": "GND",
      "8": "U2_SW", "9": "GND"})   # EN tied to VIN (abs max 65 V); pad 9 = exposed pad + its 4 vias
cap("C2", "10u50_1206", "+VIN")
cap("C34", "100n", "+VIN")
cap("C3", "100n", "U2_BST", "U2_SW")
res("R55", "39k", "U2_RT", "GND")              # RT = 42904 * f^-1.088 -> ~620 kHz
res("R56", "47k", "+5V_BUCK", "U2_FB")         # 0.75 V * (1 + 47/8.2) = 5.05 V
res("R57", "8.2k", "U2_FB", "GND")
res("R58", "100k", "PGOOD5", "+5V_BUCK")    # not 3V3: with no VIN, PGOOD is undefined and a 3V3 pull-up reads "good"
part("D13", "sma56", "SS56", "C18199169", {"1": "U2_SW", "2": "GND"})   # catch diode, 60 V
part("L1", "ind0630", "15uH", "C177243", {"1": "U2_SW", "2": "+5V_BUCK"})
cap("C4", "22u25", "+5V_BUCK")
cap("C5", "22u25", "+5V_BUCK")
cap("C35", "22u25", "+5V_BUCK")

# --- Block 3: USB-C, +5V, VSYS ------------------------------------------------------------------
part("J1", "usbc", "USB-C", "C2765186",
     {"A1B12": "GND", "B1A12": "GND", "A4B9": "VBUS", "B4A9": "VBUS", "A5": "CC1", "B5": "CC2",
      "A6": "USB_DP", "B6": "USB_DP", "A7": "USB_DN", "B7": "USB_DN", "13": "GND", "14": "GND"})
cap("C6", "10u25", "VBUS")
res("R1", "5.1k", "CC1", "GND")
res("R2", "5.1k", "CC2", "GND")
part("D3", "sma_ss34", "SS34", "C8678", {"1": "+5V", "2": "+5V_BUCK"})
part("D4", "sma_ss34", "SS34", "C8678", {"1": "+5V", "2": "VBUS"})
# rev 12 (audit round 3): with USB unplugged and +5V up, D4's reverse leakage charges VBUS (C6), and
# nothing loaded it, so a Type-C source could find VBUS above vSafe0V (0.8 V) and refuse to attach.
# SS34 IR <= 0.5 mA guaranteed (40 V, 25 C): 1k holds VBUS <= 0.5 V, with margin for a warm board
# (no hot figure is guaranteed; audit round 4). It draws 5 mA (25 mW) on USB.
res("R94", "1k", "VBUS", "GND")
part("D11", "sma_ss34", "SS34", "C8678", {"1": "VSYS", "2": "+5V"})
cap("C7", "22u25", "VSYS")
res("R15", "10k", "+5V", "EXT_SENSE")
res("R16", "15k", "EXT_SENSE", "GND")

# --- Block 4: 3.3 V buck-boost ------------------------------------------------------------------
part("U3", "vson10", "TPS63001", "C28060",
     {"1": "+3V3", "2": "U3_L2", "3": "GND", "4": "U3_L1", "5": "VSYS", "6": "VSYS",
      "7": "GND", "8": "VSYS", "9": "GND", "10": "+3V3", "11": "GND"})
part("L2", "ind4030", "2.2uH", "C279948", {"1": "U3_L1", "2": "U3_L2"})
cap("C8", "10u", "VSYS")
cap("C9", "22u25", "+3V3")
cap("C10", "22u25", "+3V3")
res("R3", "470", "+3V3", "D7_A")   # rev 12: green Vf up to 3.1 V left 0.2-0.7 mA through 1k
part("D7", "led_r", "green", "C2297", {"1": "D7_A", "2": "GND"})  # C2297: 1 = A

# --- Block 5: MCU -------------------------------------------------------------------------------
part("U1", "esp32", "ESP32-S3-WROOM-1-N8R2", "C2913204", {
    "1": "GND", "2": "+3V3", "3": "EN", "4": "WG_D0", "5": "WG_D1", "6": "IO6",   # 7 (IO7) unused since rev 10
    "8": "IN1", "9": "IN2", "10": "IN3", "11": "IN4", "12": "TAMPER", "13": "USB_DN", "14": "USB_DP", "15": "TEMP_ADC",
    "18": "SPI_CS", "19": "SPI_MOSI", "20": "SPI_SCK", "21": "SPI_DC",
    "22": "SPI_BL_BUSY", "23": "IO21", "24": "IO47",   # IO47 = green status LED since rev 11
    "25": "IO48", "27": "IO0",
    "28": "ETH_MISO", "29": "ETH_CS", "30": "ETH_INT", "31": "RS485_DE", "32": "EXP_INT", "33": "IO40",   # IO40 = reader BEEP since rev 10 (IO7 could not be routed out)
    "34": "I2C_SDA", "35": "I2C_SCL", "36": "RS485_RXD", "37": "RS485_DI",
    "39": "BAT_SENSE", "40": "GND", "41": "GND"})
# 15 IO3, 16 IO46, 26 IO45: strapping, no connect. 17 IO9 and 38 IO2: free since rev 12 (reader monitor on I2C)
cap("C11", "22u6", "+3V3")
cap("C12", "100n", "+3V3")
res("R4", "10k", "+3V3", "EN")
cap("C13", "1u", "EN")
part("SW2", "tact", "RESET", "C318884", {"1": "EN", "4": "GND"})
res("R5", "10k", "+3V3", "IO0")
part("SW1", "tact", "BOOT", "C318884", {"1": "IO0", "4": "GND"})
res("R8", "1k", "IO21", "D8_K")
part("D8", "led", "red", "C84256", {"1": "D8_K", "2": "+3V3"})  # rev 11: red (was yellow C2296); C84256: 1 = -
res("R81", "470", "IO47", "D23_K")   # rev 12: as R3
part("D23", "led_r", "green", "C2297", {"1": "+3V3", "2": "D23_K"})  # rev 11: green status; C2297: 1 = A
for i, n in enumerate(["RS485_DI", "RS485_RXD", "IO40", "GND"], 1):   # TX/RX are UART0 = RS-485 now
    part(f"TP{i}", "tp", n, None, {"1": n})

# --- Block 6: Wiegand inputs --------------------------------------------------------------------
part("U4", "sot6bl", "SN74LVC2G17", "C10429",
     {"1": "D0_IN", "2": "GND", "3": "D1_IN", "4": "WG_D1", "5": "+3V3", "6": "WG_D0"})
cap("C16", "100n", "+3V3")
for d, rs, z, c, rp, raw, node in (("0", "R9", "D5", "C14", "R11", "D0_RAW", "D0_IN"),
                                   ("1", "R10", "D6", "C15", "R12", "D1_RAW", "D1_IN")):
    res(rs, "1k", raw, node)
    part(z, "sod123", "MMSZ5231B", "C19077422", {"1": node, "2": "GND"})  # 1 = K
    cap(c, "100p", node)
    res(rp, "10k", "+3V3", node)

# --- Block 7: LED and BEEP ----------------------------------------------------------------------
res("R6", "100", "IO6", "LED_GATE")
res("R13", "100k", "LED_GATE", "GND")
part("Q1", "sot23_2n7002", "2N7002", "C8545", {"1": "LED_GATE", "2": "GND", "3": "RDR_LED"})
res("R7", "100", "IO40", "BEEP_GATE")
res("R14", "100k", "BEEP_GATE", "GND")
part("Q2", "sot23_2n7002", "2N7002", "C8545", {"1": "BEEP_GATE", "2": "GND", "3": "RDR_BEEP"})

# Tamper
res("R35", "10k", "+3V3", "TAMPER")
part("SW3", "tact", "TAMPER", "C318884", {"1": "TAMPER", "4": "GND"})
part("J8", "hdr2", "TAMPER EXT", None, {"1": "TAMPER", "2": "GND"})

# --- Block 8: reader supply ---------------------------------------------------------------------
part("U6", "sot6bl", "MT3608", "C84817",
     {"1": "BOOST_SW", "2": "GND", "3": "BOOST_FB", "4": "U6_EN", "5": "VSYS"})
res("R21", "100k", "VSYS", "U6_EN")
cap("C17", "22u25", "VSYS")
part("L3", "ind5040", "4.7uH", "C305174", {"1": "VSYS", "2": "BOOST_SW"})
part("D10", "sma_ss34", "SS34", "C8678", {"1": "BOOST_OUT", "2": "BOOST_SW"})
cap("C18", "22u25", "BOOST_OUT")
cap("C19", "22u25", "BOOST_OUT")
res("R19", "200k", "BOOST_OUT", "BOOST_FB")
res("R20", "10k", "BOOST_FB", "GND")
res("R30", "200k", "BOOST_FB", "JP1_A")
part("JP1", "sj", "13.2V", None, {"1": "JP1_A", "2": "GND"})
part("Q11", "sot23_ao3401", "AO3401A", "C15127", {"1": "Q11_G", "2": "BOOST_SNS", "3": "RDR_SW"})   # rev 12: source after the shunt
res("R52", "100k", "Q11_G", "BOOST_SNS")
res("R51", "100k", "Q11_G", "Q4_D")
part("Q4", "sot23_2n7002", "2N7002", "C8545", {"1": "Q4_G", "2": "GND", "3": "Q4_D"})
res("R17", "100", "IO48", "Q4_G")
res("R18", "10k", "Q4_G", "+3V3")   # 10k so an S3 reset pull-down cannot win
part("F1", "f1812", "0.5A", "C516067", {"1": "RDR_SW", "2": "+12V_RDR"})   # rev 9 part: 24 V, 0.5 A hold
part("J3", "kf128", "READER PWR", "C474952", {"1": "+12V_RDR", "2": "GND"})   # rev 12: return is plain GND
part("J10", "kf128", "READER D0 D1", "C474952", {"1": "D0_RAW", "2": "D1_RAW"})
part("J11", "kf128", "READER LED BEEP", "C474952", {"1": "RDR_LED", "2": "RDR_BEEP"})

# --- Block 9: battery ---------------------------------------------------------------------------
part("U5", "soic8ep", "CN3058E", "C112011",
     {"1": "BAT_TEMP", "2": "ISET", "3": "GND", "4": "+5V", "5": "BAT+", "6": "DONE_N", "7": "CHRG",
      "8": "BAT+", "9": "GND"})
res("R50", "10k", "ISET", "GND")       # 1218 V / 10k = 122 mA; halves U5 heat in a sealed box
cap("C20", "10u", "+5V")
cap("C21", "10u", "BAT+")
res("R24", "1k", "CHRG", "D12_K")
part("D12", "led", "red", "C84256", {"1": "D12_K", "2": "+5V"})  # C84256: 1 = -
# Battery: off-board LiFePO4 cell on a keyed 4-way JST-XH, with a 10k B3950 thermistor on the cell
# (pins 3-4; its return is GND, not BAT-, which floats when the protection FETs open). Added
# 2026-10-11, after the thermal review. U5 charges only while TEMP is 45-80 % of +5V:
# 5.1k from +5V, 68k across the thermistor and the 300k ADC divider -> charging ~1 to 44 C.
# No thermistor connected -> TEMP ~91 % -> charging stops (fail safe). JP5 bridged = use RT1 on the
# board instead (a cell with no thermistor). Both at once read hot -> charging stops earlier, safe.
part("J4", "xh4", "LiFePO4 + NTC", "C144395", {"1": "BAT+", "2": "BAT-", "3": "BAT_TEMP", "4": "GND"})
res("R77", "5.1k", "+5V", "BAT_TEMP")
res("R78", "68k", "BAT_TEMP", "GND")
part("RT1", "r0603", "10k NTC B3950", "C2892547", {"1": "RT1_A", "2": "GND"})   # on-board fallback
part("JP5", "sj", "NTC ON BOARD", None, {"1": "BAT_TEMP", "2": "RT1_A"})
res("R79", "100k", "BAT_TEMP", "TEMP_ADC")     # 2/3 divider: TEMP reaches 4.55 V open, ADC sees 3.03 V
res("R80", "200k", "TEMP_ADC", "GND")
cap("C40", "100n", "TEMP_ADC")
part("U7", "sot6bl", "DW01A", "C351410",
     {"1": "OD", "2": "VM", "3": "OC", "5": "U7_VCC", "6": "BAT-"})
res("R25", "100", "BAT+", "U7_VCC")
cap("C22", "100n", "U7_VCC", "BAT-")
res("R26", "1k", "VM", "GND")
part("Q6", "sot6br", "FS8205A", "C2830320",
     {"1": "BAT-", "2": "Q6_D", "3": "GND", "4": "OC", "5": "Q6_D", "6": "OD"})
part("Q5", "sot23_ao3401", "AO3401A", "C15127", {"1": "+5V", "2": "VSYS", "3": "BAT+"})
res("R27", "100k", "+5V", "GND")
res("R28", "100k", "BAT+", "BAT_SENSE")
res("R29", "100k", "BAT_SENSE", "GND")
cap("C23", "100n", "BAT_SENSE")

# --- Block 10: screens --------------------------------------------------------------------------
part("J5", "sock4jlc", "OLED SOCKET", "C2718488", {"1": "GND", "2": "+3V3", "3": "I2C_SCL", "4": "I2C_SDA"})   # rev 10: fitted by JLCPCB
res("R36", "4.7k", "+3V3", "I2C_SDA")
res("R37", "4.7k", "+3V3", "I2C_SCL")
part("J6", "hdr8", "TFT/EPD", None,
     {"1": "+3V3", "2": "GND", "3": "SPI_SCK", "4": "SPI_MOSI", "5": "SPI_CS", "6": "SPI_DC",
      "7": "DISP_RST", "8": "SPI_BL_BUSY"})

# --- Block 11: inputs ---------------------------------------------------------------------------
# Requirements (rev 12, audit round 3): dry contacts to GND. Closed (<= 1k contact) reads <= 0.5 V
# (VIL 0.825 V), open reads >= VIH 2.475 V. Positive miswire to +36 V sustained: reads "off", nothing
# conducts into +3V3. Negative miswire to -36 V sustained (the SMF36CA's standoff): every part within
# its rating except the GPIO, whose own clamp takes <= ~25 uA with the pin at about -0.4 to -0.6 V
# (S3: -0.3 V, no injection rating): current-limited, documented, not rated.
# R40-R43 were 1k 0603 (0.1 W): at -24 V they carried ~23 mA, 0.53 W. At 4.7k (Vishay CRCW-HP,
# pulse-proof, P70 0.33 W) it is 4.9 mA, 0.11 W; -36 V is 7.4 mA, 0.26 W. The pull-up goes to 47k so the
# closed level stays low (3.3 x 4.7/51.7 = 0.30 V); wetting current is ~64 uA (was ~0.3 mA).
part("J9", "kf128", "IN1 IN2", "C474952", {"1": "IN1_RAW", "2": "IN2_RAW"})
part("J12", "kf128", "GND IN3", "C474952", {"1": "GND", "2": "IN3_RAW"})
part("J13", "kf128", "IN4 GND", "C474952", {"1": "IN4_RAW", "2": "GND"})
for n, (q, rs, rp, c) in enumerate((("Q7", "R40", "R44", "C27"), ("Q8", "R41", "R45", "C28"),
                                   ("Q9", "R42", "R46", "C29"), ("Q10", "R43", "R47", "C30")), 1):
    part(rs, "r0603", "4.7k", "C844791", {"1": f"IN{n}_RAW", "2": f"IN{n}_D"})   # CRCW06034K70FKEAHP
    part(q, "sot23_2n7002", "2N7002", "C8545", {"1": "+3V3", "2": f"IN{n}_S", "3": f"IN{n}_D"})
    res(rp, "47k", "+3V3", f"IN{n}_S")   # rev 12 round 2: pull-up on the FET side, so the series R is no divider
    # rev 12 (audit round 2, S1): the 2N7002 conducts both ways, so a negative INx_D drags its source
    # (and the GPIO) with it; only a series resistor limits what reaches the pin. -24 V on the wire puts
    # ~30 uA into the pin's own clamp, the pin a few hundred mV below ground (audit round 3: -0.44 V).
    # A BAT54 clamp at the pin was declined: its hot leakage through 57k erodes the open-high level.
    res(f"R{89 + n}", "10k", f"IN{n}_S", f"IN{n}")
    cap(c, "10n", f"IN{n}")
    # rev 12 (audit round 1, S4): a negative miswire pulled INx_D (and through the conducting FET, the
    # GPIO) far below ground. This 75 V clamp holds INx_D at about -0.75 V (4.9 mA at -24 V), which also
    # keeps the FET's gate within +-20 V; R90-R93 then limit what reaches the GPIO. +36 V is within its
    # 75 V reverse rating.
    part(f"D{27 + n}", "sod123f", "1N4148W", "C81598", {"1": f"IN{n}_D", "2": "GND"})   # 1 = K

# --- Block 12 (rev 10): I/O expander, TCA9535 at 0x20 ----------------------------------------------
part("U8", "tssop24", "TCA9535", "C130204", {
    "1": "EXP_INT", "2": "GND", "3": "GND", "21": "GND", "12": "GND", "24": "+3V3",
    "22": "I2C_SCL", "23": "I2C_SDA",
    "4": "RELAY_DRV", "5": "CHRG", "6": "DONE_N", "7": "EXT_SENSE", "8": "PGOOD5", "9": "ETH_RST",
    "10": "DISP_RST",   # rev 11: P06 = TFT/EPD reset (IO47 is the green LED)
     "11": "EXP07", "13": "EXP10", "14": "EXP11", "15": "EXP12", "16": "EXP13",
    "17": "EXP14", "18": "EXP15", "19": "EXP16", "20": "EXP17"})
cap("C36", "100n", "+3V3")
res("R60", "10k", "EXP_INT", "+3V3")
res("R61", "100k", "CHRG", "+3V3")       # CHRG also sinks D12 (from +5V); reads ~3.3 V when idle
res("R62", "100k", "DONE_N", "+3V3")
# spare expander pins tied low (datasheet: unused I/O to VCC or GND through ~10k); ETH_RST pulled up
# RN1-1 also holds DISP_RST low, so a fitted TFT stays in reset until firmware drives P06
for ref, nets in (("RN1", ("DISP_RST", "EXP07", "EXP10", "EXP11")), ("RN2", ("EXP12", "EXP13", "EXP14", "EXP15")),
                  ("RN3", ("EXP16", None, None, None))):   # EXP17: no room to route; firmware drives it low
    pads = {}
    for k, n in enumerate(nets, 1):      # resistors are pin k <-> pin 9-k
        if n:
            pads[str(k)] = n
            pads[str(9 - k)] = "GND"
    part(ref, "rarray4", "4x10k", "C29718", pads)
res("R76", "10k", "ETH_RST", "+3V3")
part("J19", "hdr2x6", "EXPANSION", None,
     {"1": "+3V3", "2": "GND", "3": "DISP_RST", "4": "EXP07", "5": "EXP10", "6": "EXP11", "7": "EXP12",
      "8": "EXP13", "9": "EXP14", "10": "EXP15", "11": "EXP16", "12": "EXP17"})

# --- Block 13 (rev 10): relay -- driver fitted, relay and terminals NOT fitted ------------------
# NOT FOR A READER-SIDE BOARD: a board at the door must have no path to a strike. Spare boards only.
res("R63", "1k", "RELAY_DRV", "Q12_G")
res("R64", "100k", "Q12_G", "GND")
part("Q12", "sot23_2n7002", "AO3400A", "C20917", {"1": "Q12_G", "2": "GND", "3": "RELAY_COIL"})   # fully on at 3.3 V gate
part("D14", "sod123f", "1N4148W", "C81598", {"1": "+5V", "2": "RELAY_COIL"})   # flyback, 1 = K
part("K1", "relay", "SRD-05VDC-SL-C", None,
     {"1": "+5V", "4": "RELAY_COIL", "5": "RELAY_COM", "2": "RELAY_NO", "3": "RELAY_NC"})  # coil 1-4, COM 5, NO 2, NC 3
part("J15", "kf128", "RELAY NC NO", None, {"1": "RELAY_NC", "2": "RELAY_NO"})   # top to bottom: NO, NC
part("J16", "kf128", "RELAY COM", None, {"2": "RELAY_COM"})   # then COM; pin 1 spare

# --- Block 14 (rev 10): RS-485 / OSDP on UART0 ----------------------------------------------------
# rev 12: THVD1420 (full fail-safe receiver), so this node needs no bias of its own
part("U9", "soic8_thvd", "THVD1420", "C3235215",
     {"1": "RS485_RO", "2": "RS485_DE", "3": "RS485_DE", "4": "RS485_DI", "5": "GND",
      "6": "U9_A", "7": "U9_B", "8": "+3V3"})
# rev 12 (audit round 1): the SM712 clamps at up to 19 V, past the THVD1420's +-16 V bus-pin limit; TI's
# surge reference circuit puts 10 ohm between the clamp and A/B (THVD1420 datasheet, fig. 8-5)
part("R83", "r0603", "10", "C844519", {"1": "RS485_A", "2": "U9_A"})   # Vishay CRCW0603...HP, pulse-proof (TI's BOM)
part("R84", "r0603", "10", "C844519", {"1": "RS485_B", "2": "U9_B"})
# With R83 + R84 in the loop the driver's guaranteed 1.5 V into 54 ohm becomes ~1.1 V at the terminals
# (TIA-485 asks 1.5 V); receivers need 0.2 V, so a bus of THVD1420-class nodes is fine (audit round 2).
cap("C37", "100n", "+3V3")
res("R65", "10k", "RS485_DE", "GND")      # receive by default, and through boot (ROM prints on TXD0)
res("R75", "10k", "RS485_RXD", "+3V3")    # RO is high-Z while transmitting (/RE tied to DE)
# rev 12 (audit round 1): U9 drives RO whenever it receives, so a USB-UART on TP2 for recovery fought it
res("R85", "1k", "RS485_RO", "RS485_RXD")
res("R68", "120", "RS485_A", "JP2_A")     # 120 ohm termination, bridge JP2 at the end of the line
# strong fail-safe bias for one node per bus (bridge JP3+JP4 here): 240 mV idle with both ends
# terminated (sim/rs485_term.cir). This board's own receiver no longer needs it (THVD1420, rev 12);
# other nodes on the bus may.
res("R72", "390", "RS485_A", "JP3_A")
part("JP3", "sj", "BIAS", None, {"1": "JP3_A", "2": "+3V3"})
res("R73", "390", "RS485_B", "JP4_A")
part("JP4", "sj", "BIAS", None, {"1": "JP4_A", "2": "GND"})
part("JP2", "sj", "TERM", None, {"1": "JP2_A", "2": "RS485_B"})
part("J20", "kf128", "RS485 A B", "C474952", {"1": "RS485_A", "2": "RS485_B"})
part("J21", "kf128", "RS485 12V GND", "C474952", {"1": "+12V_RDR", "2": "GND"})   # power + ground for an OSDP reader

# --- Block 15 (rev 10): surge/ESD on every field wire (SM712: +12 / -7 V standoff) --------------
for ref, a, b in (("D15", "D0_RAW", "D1_RAW"), ("D16", "RDR_LED", "RDR_BEEP"), ("D19", "RS485_A", "RS485_B")):
    part(ref, "sot23_712", "SM712", "C32677", {"1": a, "2": b, "3": "GND"})
# IN1-4: 36 V bidirectional, so a 24-36 V miswire is survived (an SM712 would conduct from 13.3 V)
for ref, n in (("D17", "IN1_RAW"), ("D18", "IN2_RAW"), ("D21", "IN3_RAW"), ("D22", "IN4_RAW")):
    part(ref, "sod123fl_bi", "SMF36CA", "C19077521", {"1": n, "2": "GND"})
# reader power pair, at J3
part("D20", "sma_tvs", "SMAJ15A", "C19077535", {"1": "+12V_RDR", "2": "GND"})   # 1 = K

# --- Block 16 (rev 12): reader monitor, INA226 on I2C (0x40) -------------------------------------
# Requirements (guaranteed figures): reader current 0-150 mA (spec), readable to F1's 0.5 A hold,
# within 0.25 mA + 1.5 % of reading over 25 +- 35 C before calibration; the reader terminal's voltage;
# every pin within -0.3..40 V on the worst transient of its net; reader return solid.
# R59: alloy 0.1 ohm, 1 %, +-50 ppm/C (Walter STE1206, C201308; audit round 1: the thick-film C25334 was
# +-800 ppm/C, 4 mA of drift at 150 mA). 819 mA full scale, 25 uA LSB. Budget (audit round 2), worst
# case: offset 0.1 mA + drift 0.035 mA + leakage <= 0.003 mA, plus the constant 0.078 mA the shunt also
# carries (R52/R51 gate drive 63 uA with Q11 on, VBUS ~15 uA), which the firmware subtracts; gain
# 0.1 % + 0.175 % drift + shunt 1 % + 0.18 % drift (+ <= 0.3 % tab position, estimated). At 150 mA
# that is about 2.4 mA against 2.5 mA allowed; the tab estimate would take it to ~2.8 mA, over. A
# one-point gain calibration on the bench (firmware multiply) takes out the shunt's 1 % and the tab
# term, and R82's 0.57 % on the voltage.
# The shunt sits between the boost's output capacitors and Q11 (audit round 1, S3): IN+ and IN- are
# on BOOST_OUT / BOOST_SNS, which the 44 uF hold up and which never go negative, even while Q11 sheds
# the reader. (Between Q11 and F1 they followed the reader cable through F1 whenever Q11 was off.)
# Kelvin connection by net tie (audit round 1, S2): R59's footprint carries a small sense pad inside
# each land (pads 3/4, net_tie_pad_groups "1, 3" "2, 4"), and U12's sense pins are on nets of their
# own (ISNS_P / ISNS_N), so no load current can share a sense track. kelvin.py checks the structure.
part("R59", "r1206k", "0.1R", "C201308", {"1": "BOOST_OUT", "2": "BOOST_SNS", "3": "ISNS_P", "4": "ISNS_N"})
part("U12", "msop10", "INA226", "C49851",
     {"1": "GND", "2": "GND", "4": "I2C_SDA", "5": "I2C_SCL", "6": "+3V3", "7": "GND",
      "8": "RDR_VBUS", "9": "ISNS_N", "10": "ISNS_P"})   # A1 = A0 = GND -> 0x40; 3 = ALERT, open
# VBUS reads the reader terminal (after F1), so a tripped F1 shows as a low supply. That net is a field
# wire: D20 lets it swing to about -0.8 V (-3.5 V at surge current), and VBUS's limit is -0.3 V. R82
# 4.7k + D27 (BAT54, <= 0.24 V at 0.1 mA) hold the pin above -0.3 V; 4.7k against VBUS's 830k
# input is a 0.57 % gain error (a bench calibration takes it out; see the firmware).
res("R82", "4.7k", "+12V_RDR", "RDR_VBUS")
part("D27", "sot23_bat54", "BAT54", "C22466368", {"1": "GND", "3": "RDR_VBUS"})   # 1 = A, 3 = K
cap("C39", "100n", "+3V3")                 # U12 VS

# --- Block 17 (rev 10): W5500 module header and Qwiic, not fitted -------------------------------------
part("J17", "hdr8", "W5500", None,
     {"1": "+3V3", "2": "GND", "3": "SPI_SCK", "4": "SPI_MOSI", "5": "ETH_MISO", "6": "ETH_CS",
      "7": "ETH_INT", "8": "ETH_RST"})
part("J18", "qwiic", "QWIIC", None, {"1": "GND", "2": "+3V3", "3": "I2C_SDA", "4": "I2C_SCL"})

for i in range(1, 5):
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
