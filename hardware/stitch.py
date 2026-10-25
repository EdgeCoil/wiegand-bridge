# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""Ground stitching for the 4-layer board: tie every GND pad and pour island to the In1 plane.

1. A GND via beside each GND SMD pad on F.Cu (short stub), unless one is already within 1.5 mm.
2. A grid of GND vias (every 4 mm) wherever a via fits clear of everything on F, In2 and B.
Then refill zones. Uses finish_net's obstacle grid. KiCad DRC is the check afterwards.

    python3 stitch.py
"""
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import finish_net as F  # noqa: E402

mm, ToMM = pcbnew.FromMM, pcbnew.ToMM
VIA_D, VIA_DRILL = 0.6, 0.3
board = pcbnew.LoadBoard(F.PCB)
gnd = board.FindNet("GND")
grids = F.obstacles(board, "GND")            # GND copper is not an obstacle to a GND via ...
for fp in board.GetFootprints():             # ... but every drilled hole is (hole-to-hole spacing)
    for p in fp.Pads():
        if p.GetDrillSize().x > 0:
            for g in grids.values():
                F.mark_disk(g, ToMM(p.GetPosition().x), ToMM(p.GetPosition().y),
                            ToMM(p.GetDrillSize().x) / 2 + 0.3 + VIA_DRILL / 2)
for t in board.GetTracks():
    if t.GetClass() == "PCB_VIA":
        for g in grids.values():
            F.mark_disk(g, ToMM(t.GetPosition().x), ToMM(t.GetPosition().y), VIA_D + F.CLR)
sig = [g for L, g in grids.items() if L != pcbnew.In1_Cu]
# GND SMD pads are not obstacles in `grids` (same net), but a via inside one leaves an open hole in a
# solder joint (DFM review 2026-10-11): keep via centres 0.45 mm outside every pad's mask opening.
# Through-hole pads too (rev 11): hole spacing alone let --islands drop vias into J6/J19 GND pads.
padmask = bytearray(F.NX * F.NY)
for fp in board.GetFootprints():
    for p in fp.Pads():
        F.mark_box(padmask, p.GetBoundingBox(), 0.45 - 0.2)
sig.append(padmask)
# obstacles are inflated by clearance + half a 0.25 mm track (+ half a grid step); a 0.6 mm via needs
# 0.175 mm more than a track's centreline, so 2 grid cells of free space around the centre is enough.
rv = 2


def fits(i, j):
    return all(F.free(g, i, j, rv) for g in sig)


def add_via(x, y):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    v.SetWidth(mm(VIA_D))
    v.SetDrill(mm(VIA_DRILL))
    v.SetNet(gnd)
    board.Add(v)
    i, j = F.cell(x, y)
    for g in grids.values():                 # later vias keep clear of this one
        F.mark_disk(g, x, y, VIA_D / 2 + F.CLR + 0.05)


def main_pass():
    existing = [(ToMM(t.GetPosition().x), ToMM(t.GetPosition().y)) for t in board.GetTracks()
                if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"]
    pad_vias = 0
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() != "GND" or p.GetDrillSize().x > 0 or not p.IsOnLayer(pcbnew.F_Cu):
                continue
            px, py = ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)
            if any(math.hypot(px - x, py - y) < 1.5 for x, y in existing):
                continue
            done = False
            for rad in [r * 0.1 for r in range(7, 26)]:
                for k in range(24):
                    a = 2 * math.pi * k / 24
                    x, y = px + rad * math.cos(a), py + rad * math.sin(a)
                    i, j = F.cell(x, y)
                    if 0 < i < F.NX - 1 and 0 < j < F.NY - 1 and fits(i, j) and F.line_free(grids[pcbnew.F_Cu], (px, py), (x, y)):
                        t = pcbnew.PCB_TRACK(board)
                        t.SetStart(p.GetPosition())
                        t.SetEnd(pcbnew.VECTOR2I(mm(x), mm(y)))
                        t.SetWidth(mm(0.3))
                        t.SetLayer(pcbnew.F_Cu)
                        t.SetNet(gnd)
                        board.Add(t)
                        add_via(x, y)
                        existing.append((x, y))
                        pad_vias += 1
                        done = True
                        break
                if done:
                    break

    grid_vias = 0
    x0, y0, w, h = F.X0, F.Y0, F.W, F.H
    y = y0 + 3.0
    while y < y0 + h - 2.0:
        x = x0 + 3.0
        while x < x0 + w - 2.0:
            i, j = F.cell(x, y)
            if fits(i, j) and not any(math.hypot(x - a, y - b) < 2.5 for a, b in existing):
                add_via(x, y)
                existing.append((x, y))
                grid_vias += 1
            x += 4.0
        y += 4.0
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(F.PCB, board)
    print(f"pad vias {pad_vias}, stitching vias {grid_vias}")



def islands():
    """Give every filled GND island on F, In2 and B at least one via down to the In1 plane."""
    global board, grids
    added = 0
    vias = [(ToMM(t.GetPosition().x), ToMM(t.GetPosition().y)) for t in board.GetTracks()
            if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"]
    vias += [(ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)) for f in board.GetFootprints() for p in f.Pads()
             if p.GetNetname() == "GND" and p.GetDrillSize().x > 0]
    for z in board.Zones():
        if z.GetNetname() != "GND" or z.GetLayer() == pcbnew.In1_Cu:
            continue
        fill = z.GetFilledPolysList(z.GetLayer())
        for k in range(fill.OutlineCount()):
            poly = fill.Outline(k)
            if any(poly.PointInside(pcbnew.VECTOR2I(mm(x), mm(y))) for x, y in vias):
                continue
            bb = poly.BBox()
            placed = False
            yy = ToMM(bb.GetTop()) + 0.4
            while yy < ToMM(bb.GetBottom()) and not placed:
                xx = ToMM(bb.GetLeft()) + 0.4
                while xx < ToMM(bb.GetRight()) and not placed:
                    i, j = F.cell(xx, yy)
                    if poly.PointInside(pcbnew.VECTOR2I(mm(xx), mm(yy))) and fits(i, j):
                        add_via(xx, yy)
                        vias.append((xx, yy))
                        added += 1
                        placed = True
                    xx += 0.1
                yy += 0.1
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(F.PCB, board)
    print(f"island vias {added}")


if "--islands" in sys.argv:
    islands()
else:
    main_pass()
