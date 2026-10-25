# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Placement for build_pcb.py: ref -> (x mm, y mm, rotation deg, side).

Board 90 x 95 mm at (100, 100) since revision 10 (70 x 75 in revision 9) -- grown from the guide's ~65 x 70 on 2026-10-11 so the autorouter has
room; the enclosure is 3D-printed to fit the board, so nothing else depends on the outline.

Top-left: the ESP32, antenna over the top edge. Left edge: USB-C, then the input terminals. Bottom
edge, left to right: reader LED/BEEP, D0/D1, reader power, 12 V in. Switchers bottom-right, away from
the antenna. OLED socket J5 top-right; a plugged-in OLED covers roughly x 125-161, y 101-136, so only
low parts go there. Test pads are on the bottom side.
"""
BOARD = (100.0, 100.0, 90.0, 95.0)
HOLES = []
TERM_Y = 195.0 - 5.4          # bottom terminals: body edge flush with the board edge
TERM_X = 100.0 + 5.3          # left terminals

P = {}


def at(ref, x, y, rot=0, side="F"):
    P[ref] = (x, y, rot, side)


# --- MCU (antenna overhangs y = 100) ----------------------------------------------------------
at("U1", 117.0, 110.36)
at("C11", 105.2, 102.6, 90)
at("C12", 105.2, 105.6, 90)
at("R4", 105.2, 108.6, 90)
at("C13", 105.2, 111.6, 90)

# --- USB-C, reset/boot (below the module) ------------------------------------------------------
at("J1", 104.6, 127.0, 270)
at("R1", 108.8, 122.8, 90)
at("R2", 108.6, 133.4, 270)   # below J1: CC2 is pre-routed to it (route.py): the only reachable spot
at("C6", 110.6, 126.6, 90)
at("D4", 113.0, 131.0, 0)
at("SW2", 115.6, 124.6)          # RESET
at("SW1", 123.6, 124.6)          # BOOT
at("R5", 128.6, 124.6, 90)

# --- inputs (left edge) ------------------------------------------------------------------------
at("J9", TERM_X, 141.0, 270)
at("J12", TERM_X, 151.16, 270)
at("J13", TERM_X, 161.32, 270)
for n, (q, rs, rp, c) in enumerate((("Q7", "R40", "R44", "C27"), ("Q8", "R41", "R45", "C28"),
                                   ("Q9", "R42", "R46", "C29"), ("Q10", "R43", "R47", "C30"))):
    y = 137.5 + n * 5.5
    at(rs, 114.4, y, 0)   # rev 11: 1 mm right, so the IN labels clear its pad
    at(q, 116.9, y, 0)
    at(rp, 120.4, y - 0.9, 0)
    at(c, 120.4, y + 0.9, 0)

# --- bottom terminals: LED/BEEP, D0/D1, reader power, 12 V in -----------------------------------
at("J11", 122.0, TERM_Y)
at("J10", 132.16, TERM_Y)
at("J3", 142.32, TERM_Y)
at("J20", 152.48, TERM_Y)       # RS-485 A/B, beside the reader block
at("J21", 162.64, TERM_Y)      # RS-485 node power: +12V and sensed ground
at("J2", 177.0, TERM_Y)         # power in, set apart from the reader terminals

# --- reader LED / BEEP -------------------------------------------------------------------------
at("Q1", 114.0, 177.0, 0)
at("R6", 114.0, 179.5, 0)
at("R13", 117.3, 177.4, 90)
at("Q2", 121.0, 177.0, 0)
at("R7", 121.0, 179.5, 0)
at("R14", 124.3, 177.4, 90)

# --- Wiegand D0/D1 protection + buffer ---------------------------------------------------------
at("U4", 131.5, 166.0, 0)
at("C16", 128.0, 166.0, 90)
at("R11", 129.0, 169.0, 0)
at("R12", 134.0, 169.0, 0)
at("C14", 129.0, 171.0, 0)
at("C15", 134.0, 171.0, 0)
at("D5", 129.0, 174.0, 0)
at("D6", 134.4, 174.0, 0)
at("R9", 129.0, 177.0, 0)
at("R10", 134.0, 177.0, 0)

# --- tamper ------------------------------------------------------------------------------------
at("SW3", 117.0, 162.0, 0)
at("R35", 121.8, 158.6, 0)
at("J8", 113.6, 168.6, 90)     # rev 11: down 1.1 mm so the TAMPER label clears it

# --- 3.3 V buck-boost (under the OLED; all low parts) -------------------------------------------
at("U3", 137.0, 131.0, 0)
at("L2", 132.2, 131.0, 90)
at("C8", 135.6, 134.6, 0)
at("C9", 135.8, 127.4, 0)
at("C10", 135.6, 125.3, 0)
at("R3", 133.0, 137.4, 0)
at("D7", 136.6, 137.4, 180)

# --- screens, status LED, I2C pull-ups (top right) ----------------------------------------------
at("J5", 158.4, 103.5, 0)     # rev 11: +2.4 mm so its legend clears J6. OLED module hangs x 141-176: >= 15 mm from the antenna (layout review)
at("J6", 152.0, 109.6, 270)
# rev 11 (2026-10-20): a green OK / red FAULT pair, stacked left of a plugged-in OLED (x < 138.5)
# so it stays visible; labels to their right, above J6. I2C pull-ups moved under the OLED (low parts).
at("D23", 130.0, 102.9, 180)   # green, IO47
at("D8", 130.0, 105.9, 180)    # red, IO21 (ESPHome status LED)
at("R81", 130.0, 110.2, 0)
at("R8", 130.0, 112.2, 0)
at("R36", 146.0, 102.6, 0)
at("R37", 146.0, 104.4, 0)

# --- 5 V OR, VSYS, ext sense ---------------------------------------------------------------------
at("D3", 157.0, 152.0, 0)      # +5V_BUCK pad (2) on the right, beside the output caps
at("D11", 150.5, 135.0, 180)
at("C7", 146.0, 135.0, 90)
at("R15", 145.0, 130.0, 90)
at("R16", 147.0, 130.0, 90)

# --- reader boost, shed switch, fuse, rail monitor ----------------------------------------------
at("L3", 144.0, 152.5, 180)    # switch-node pad toward D10 (layout review S2)
at("C17", 139.2, 151.0, 90)
at("U6", 144.0, 158.0, 0)
at("R21", 140.0, 157.2, 90)
at("D10", 149.0, 156.0, 90)
at("C18", 151.8, 161.0, 90)
at("C19", 149.4, 161.3, 90)
at("R19", 145.2, 161.6, 90)
at("R20", 142.6, 161.6, 90)
at("R30", 140.4, 162.6, 90)
at("JP1", 140.6, 165.6, 0)
at("Q11", 148.6, 165.6, 0)
at("R52", 152.0, 165.6, 90)
at("R51", 145.4, 165.6, 90)
at("Q4", 144.6, 169.2, 0)
at("R17", 141.2, 169.6, 0)
at("R18", 141.2, 171.6, 0)
at("F1", 150.8, 170.4, 0)
at("R31", 138.8, 170.6, 90)
at("R32", 136.8, 170.6, 90)
at("C24", 138.2, 166.4, 90)

# --- 6-36 V in, protection, LMR16020 buck to 5 V (bottom right) ----------------------------------
at("J14", 179.35, 151.5, 180)   # DC jack, mouth at the right edge
at("F2", 185.0, 176.6, 90)
at("D1", 181.2, 170.2, 0)      # input chain in a line: F2 -> D1 -> +VIN caps -> U2
at("D2", 180.4, 175.6, 270)    # +VIN on top, GND below
at("C31", 177.3, 176.0, 270)   # +VIN on top (174.5), GND below: GND runs unbroken to D13
at("C32", 174.6, 176.0, 270)
at("C33", 171.9, 176.0, 270)
at("U2", 172.0, 166.0, 0)
at("C2", 168.6, 171.2, 180)    # +VIN pad beside U2 VIN, GND pad beside D13 anode (layout review S3)
at("C34", 172.4, 171.2, 0)
at("C3", 168.7, 166.0, 90)
at("R55", 176.8, 167.4, 0)
at("R56", 176.8, 163.6, 0)
at("R57", 176.8, 165.4, 0)
at("R58", 172.6, 161.2, 0)
at("D13", 166.6, 166.0, 270)
at("L1", 163.5, 158.0, 270)    # switch-node pad (1) beside D13 (layout review S1)
at("C4", 161.6, 151.6, 90)     # output caps between L1 and D3
at("C5", 164.0, 151.6, 90)
at("C35", 166.4, 151.6, 90)

# --- relay (NOT FITTED; spare boards only) ---------------------------------------------------------
at("K1", 170.4, 127.5, 90)
at("J15", 184.7, 124.4, 90)   # rev 11: down 0.4 mm for J4's + - T T legend
at("J16", 184.7, 134.56, 90)
at("Q12", 166.0, 141.0, 0)
at("D14", 171.5, 141.0, 0)
at("R63", 161.8, 139.9, 0)
at("R64", 161.8, 141.7, 0)

# --- battery (right edge, upper middle) ---------------------------------------------------------
at("J4", 187.5, 113.5, 180)    # 4-way XH (cell + thermistor), pins 1..4 run right -> left
at("U5", 158.0, 124.0, 0)
at("R50", 153.6, 121.4, 90)
at("C20", 153.6, 125.0, 90)
at("C21", 161.4, 121.0, 90)   # clear of the relay body
at("R24", 153.6, 128.6, 90)
at("D12", 157.6, 129.4, 0)
at("U7", 158.0, 115.0, 0)
at("R25", 154.0, 114.4, 90)
at("C22", 154.0, 117.6, 90)
at("R26", 160.6, 116.8, 90)
at("Q6", 164.6, 113.6, 0)
at("Q5", 150.6, 130.8, 0)
at("R27", 157.0, 133.5, 0)
at("R28", 148.0, 125.0, 90)
at("R29", 146.0, 125.0, 90)
at("C23", 144.0, 125.0, 90)

# --- test pads, bottom side, under J6 (TP1 TX, TP2 RX = RS-485 UART0, TP3 IO40, TP4 GND) ---------
for i, x in enumerate((131.0, 133.6, 136.2, 138.8), 1):
    at(f"TP{i}", x, 115.4, 0, "B")

# --- expander, RS-485, ESD, reader current sense, headers (revision 10) ----------------------------
at("U8", 136.5, 120.0, 0)
at("C36", 131.7, 121.6, 90)
at("R60", 143.4, 117.6, 0)
at("R61", 143.1, 119.4, 0)
at("R62", 143.1, 121.2, 0)
at("J19", 129.5, 146.0, 90)    # expansion header, 1x12, pins run left -> right
at("J17", 157.1, 110.1, 90)    # W5500 module header, 1x8, not usable with the OLED plugged in (rev 11: down, clear of J5's legend)
at("J18", 160.0, 145.0, 0)      # Qwiic
at("U9", 162.0, 178.0, 0)       # SP3485, beside J20
at("C37", 166.4, 178.0, 90)
at("R65", 158.4, 172.8, 90)
at("R66", 157.6, 176.6, 90)
at("R67", 156.0, 176.6, 90)
at("R68", 166.4, 174.6, 90)
at("JP2", 168.6, 179.0, 90)
at("D19", 157.6, 180.2, 0)
at("R72", 149.9, 177.4, 0)    # rev 11: horizontal, so JP3/JP4 can move up clear of the A/B labels
at("JP3", 150.4, 180.4, 90)   # rev 11: up 0.8 mm, clear of the A/B labels
at("R73", 153.5, 177.4, 0)
at("JP4", 153.0, 180.4, 90)
at("D15", 131.5, 180.0, 0)      # D0/D1 at J10
at("D16", 127.0, 180.2, 0)      # LED/BEEP at J11 (rev 11: up, clear of the terminal labels)
at("D17", 124.6, 137.5, 90)     # IN1/IN2
at("D18", 124.6, 143.0, 90)     # IN3/IN4
at("R59", 146.6, 180.7, 0)      # reader shunt at J3
at("U10", 142.5, 178.6, 0)
at("R69", 142.5, 175.4, 0)
at("R70", 138.8, 175.4, 0)
at("R71", 138.8, 177.2, 0)
at("C38", 138.8, 179.0, 0)
at("C39", 145.8, 175.4, 0)

# --- datasheet-review additions (rev 10) -----------------------------------------------------------
at("D21", 124.6, 148.5, 90)
at("D22", 124.6, 154.0, 90)
at("D20", 151.2, 174.6, 0)
at("R74", 146.2, 177.3, 0)
at("R75", 155.2, 170.0, 90)
at("R76", 169.6, 113.8, 0)
at("RN1", 146.2, 121.0, 90)
at("RN2", 129.4, 116.6, 90)
at("RN3", 129.4, 120.7, 90)

# --- mounting holes ----------------------------------------------------------------------------
at("H1", 103.5, 116.5)
at("H2", 186.5, 103.5)
at("H3", 104.0, 191.5, 0)
at("H4", 186.5, 191.5, 0)

PLACE = P

# --- battery thermistor (2026-10-11): divider beside U5's TEMP pin, fallback NTC beside J4 -------
at("R77", 161.6, 127.6, 90)
at("R78", 161.6, 131.0, 90)
at("R79", 161.6, 134.4, 90)
at("R80", 159.6, 137.0, 0)
at("RT1", 174.6, 112.6, 0)
at("JP5", 174.4, 115.2, 0)
at("C40", 110.8, 122.4, 90)     # ADC filter at U1 pad 15 (IO3)
