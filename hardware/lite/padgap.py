# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""Pads of different nets closer than CLR on the unrouted board (EasyEDA courtyards stop short of the
pad ends, so a courtyard check misses these -- the first lite route failed on exactly these, 2026-10-21).

    python3 padgap.py [clearance mm, default 0.2]
"""
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
CLR = float(sys.argv[1]) if len(sys.argv) > 1 else 0.2
T = pcbnew.ToMM
board = pcbnew.LoadBoard(os.path.join(HERE, "wiegand-bridge-lite.kicad_pcb"))
pads = []
for f in board.GetFootprints():
    for p in f.Pads():
        bb = p.GetBoundingBox()
        pads.append((f.GetReference(), p.GetNumber(), p.GetNetname(), f.GetLayer(), p.GetDrillSize().x > 0,
                     (T(bb.GetLeft()), T(bb.GetTop()), T(bb.GetRight()), T(bb.GetBottom()))))
n = 0
for i, a in enumerate(pads):
    for b in pads[i + 1:]:
        if a[0] == b[0] or a[2] == b[2] or (a[3] != b[3] and not a[4] and not b[4]):
            continue
        A, B = a[5], b[5]
        dx = max(A[0] - B[2], B[0] - A[2], 0)
        dy = max(A[1] - B[3], B[1] - A[3], 0)
        d = (dx * dx + dy * dy) ** 0.5
        if d < CLR:
            n += 1
            print(f"  {a[0]}.{a[1]} [{a[2]}] -- {b[0]}.{b[1]} [{b[2]}]: {d:.2f} mm  (need {CLR})")
print(n, "pad pairs under", CLR, "mm")
