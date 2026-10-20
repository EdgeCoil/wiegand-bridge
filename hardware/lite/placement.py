# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Placement for build_pcb.py: ref -> (x mm, y mm, rotation deg, side).

Board 42 x 44 mm at (100, 100) -- lite rev 1 (the full board is 90 x 95). Top right: the ESP32-S3-MINI-1
with its antenna over the top edge (its EN / UART / IO38 column faces the right edge, the IO0-IO11
column faces inboard). Right edge below it: USB-C. Top left: M3 hole, the 3.3 V buck under it, then
the BOOT / RESET switches and the status LEDs. Left edge: the 12 V input chain, top to bottom.
Middle: the four reader-line cells in columns above their terminal pins, the two Schmitt buffers
above them. Bottom right: the RS-485 transceiver by terminal pins 7-8, M3 hole in the corner.
Bottom edge: the 8-way pluggable terminal, its mouth 0.2 mm over the edge so the pin legend fits
above the body (silkscreen text is 1.0 mm high, JLCPCB's minimum).

Spacing is set from the courtyards KiCad draws (0603: 3.0 x 1.5 mm, 0805: 3.45 x 2.0, SOT-23:
2.95 x 1.35, SOD-123: 2.85 x 1.65): vertical 0603s on a 3.0 mm pitch, side by side at 2.4 mm.
"""
BOARD = (100.0, 100.0, 42.0, 44.0)
HOLES = []
TERM_Y = 136.2

P = {}


def at(ref, x, y, rot=0, side="F"):
    P[ref] = (x, y, rot, side)


# --- MCU (antenna overhangs y = 100), its decoupling in the column inboard of its left pads ---------
at("U1", 132.9, 108.4)
at("C11", 124.3, 103.2, 90)
at("C12", 124.3, 106.2, 90)
at("R5", 124.3, 109.2, 90)
at("R4", 124.3, 112.2, 90)
at("C13", 124.3, 115.2, 90)

# --- buttons and status LEDs (top, between the buck and the module) ---------------------------------
at("SW1", 113.3, 105.1)          # BOOT, label above
at("SW2", 113.3, 110.6)          # RESET, label below
at("D7", 118.8, 102.5, 180)      # PWR      (labels run vertically to the right of the LEDs)
at("R3", 118.8, 104.8, 90)
at("D8", 118.8, 107.3, 180)      # FAULT
at("R8", 118.8, 109.6, 90)
at("D23", 118.8, 112.1, 180)     # OK
at("R81", 118.8, 114.4, 90)

# --- USB-C (right edge, below the module) -----------------------------------------------------------
at("J1", 137.4, 121.0, 90)
at("C6", 132.4, 118.0, 90)      # the VBUS pad-pair vias (route.py) sit at x 133.9
at("R1", 132.4, 121.3, 90)
at("R2", 132.4, 124.3, 90)
at("D3", 140.3, 134.3, 90)      # VBUS -> +VIN

# --- buck (top left, under the hole's keep-out), then the 12 V input chain down the left edge --------
at("L1", 104.6, 110.5, 0)
at("C4", 108.8, 108.0, 90)
at("C5", 108.8, 111.5, 90)
at("U2", 104.0, 114.9, 0)
at("C3", 101.6, 114.9, 90)      # BST, beside pin 6
at("C2", 106.9, 116.4, 90)      # input cap beside pin 3
at("C1", 103.6, 118.7, 90)
at("D2", 107.2, 123.0, 90)      # TVS in its own column: the SMA pads run 3 mm past the courtyard
at("D1", 103.5, 124.5, 90)
at("F1", 103.6, 130.2, 0)

# --- reader lines: one column per terminal pin (D0, D1, LED, BEEP), buffers above -------------------
at("U4", 114.6, 114.8, 0)       # pads clear of Q3's (the SOT-23 pads run 0.5 mm past its courtyard)       # D0 / D1 buffer
at("C16", 109.2, 117.3, 90)
at("U11", 121.0, 115.2, 0)      # left of C13, so the EN cap has room      # LED / BEEP buffer
at("C41", 125.7, 118.2, 90)
for cx, (q, rg, rgd, rs, z, c, rp) in zip((111.6, 117.5, 123.4, 129.3),
                                          (("Q3", "R24", "R25", "R9", "D5", "C14", "R11"),
                                           ("Q4", "R26", "R27", "R10", "D6", "C15", "R12"),
                                           ("Q1", "R6", "R13", "R20", "D24", "C42", "R22"),
                                           ("Q2", "R7", "R14", "R21", "D25", "C43", "R23"))):
    at(q, cx, 118.1, 0)                  # rows spaced by pad extents (0.25 mm between pads)
    at(rg, cx - 1.2, 121.1, 90)
    at(rgd, cx + 1.2, 121.1, 90)
    at(z, cx, 123.35, 0)
    at(rs, cx, 124.95, 0)
    at(c, cx - 1.2, 127.25, 90)
    at(rp, cx + 1.2, 127.25, 90)
at("D15", 111.65, 130.3, 0)     # D0/D1 surge, between pins 3-4 (upright: pads 1-2 stacked at the right)
at("D16", 118.65, 130.3, 0)     # LED/BEEP, between pins 5-6
at("D19", 125.65, 130.3, 0)     # A/B, between pins 7-8

# --- RS-485 (bottom right) --------------------------------------------------------------------------
at("U9", 134.5, 131.9, 180)     # A/B pads toward the terminal
at("R65", 134.0, 127.0, 0)
at("R75", 137.2, 127.0, 0)
at("C37", 140.2, 127.0, 0)
at("R66", 138.5, 128.6, 0)
at("R67", 138.5, 130.2, 0)
at("R68", 133.6, 137.3, 0)
at("JP2", 131.0, 140.0, 0, "B")   # hand-bridged: on the back, under the terminal

# --- terminal, holes ---------------------------------------------------------------------------------
at("J3", 115.15, TERM_Y, 0)
at("H1", 103.5, 103.5)
at("H2", 138.5, 140.5)

PLACE = P
