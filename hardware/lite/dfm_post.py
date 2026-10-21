# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""Post-route DFM/thermal fixes (reviews of 2026-10-11). Run after routing and stitching, before fab.py.

1. Paste windows round exposed-pad vias (the full board's U2/U3/U5). The lite board has no exposed
   pad -- the MINI-1's centre GND pads carry their own paste -- so EP is empty and this is a no-op.
2. Copper pours on F.Cu round the power diodes' pads (D1, D3): their datasheet ratings assume
   ~25 mm2 of copper, the bare pads have ~4.

    python3 dfm_post.py
"""
import os

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "wiegand-bridge-lite.kicad_pcb")
mm, ToMM = pcbnew.FromMM, pcbnew.ToMM
EP = {}                                             # no exposed pads on the lite board
DIODE_POUR = {"D1": 2.0, "D3": 2.0}     # extra copper around each non-GND pad, mm


def circle_poly(x, y, r, n=24):
    import math
    ps = pcbnew.SHAPE_POLY_SET()
    ps.NewOutline()
    for k in range(n):
        a = 2 * math.pi * k / n
        ps.Append(int(x + r * math.cos(a)), int(y + r * math.sin(a)))
    return ps


def paste(board):
    vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    for ref, num in EP.items():
        fp = board.FindFootprintByReference(ref)
        ep = [p for p in fp.Pads() if p.GetNumber() == num and p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
              and p.GetSize().x > mm(1)][0]
        holes = []                          # collect first: fp.Pads() is unusable after fp.Remove()
        for v in vias:
            if ep.HitTest(v.GetPosition(), mm(0.3)):
                holes.append(v.GetPosition())
        for p in fp.Pads():                # the footprint's own through-hole thermal vias (U2)
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and p.GetNumber() == num:
                holes.append(pcbnew.VECTOR2I(p.GetPosition().x, p.GetPosition().y))
        apertures = [p for p in fp.Pads() if not p.GetLayerSet().Contains(pcbnew.F_Cu)
                     and p.GetLayerSet().Contains(pcbnew.F_Paste)]
        old = [g for g in fp.GraphicalItems() if g.GetLayer() == pcbnew.F_Paste]
        pad_area = ToMM(ep.GetSize().x) * ToMM(ep.GetSize().y)
        poly = pcbnew.SHAPE_POLY_SET()
        ep.TransformShapeToPolygon(poly, pcbnew.F_Cu, mm(-0.05), mm(0.005), pcbnew.ERROR_INSIDE)
        ls = ep.GetLayerSet()
        ls.RemoveLayer(pcbnew.F_Paste)
        ep.SetLayerSet(ls)
        for p in apertures:                 # the stock footprint's paste-only apertures (U3)
            fp.Remove(p)
        for g in old:                       # a previous run's polygon
            fp.Remove(g)
        for h in holes:
            poly.BooleanSubtract(circle_poly(h.x, h.y, mm(0.3 + 0.15)))
        poly.Fracture()
        area = poly.Area() / 1e12
        s = pcbnew.PCB_SHAPE(fp)
        s.SetShape(pcbnew.SHAPE_T_POLY)
        s.SetPolyShape(poly)
        s.SetFilled(True)
        s.SetWidth(0)
        s.SetLayer(pcbnew.F_Paste)
        fp.Add(s)
        print(f"{ref}.{num}: {len(holes)} vias, paste {area:.2f} of {pad_area:.2f} mm2 ({100 * area / pad_area:.0f}%)")


def pours(board):
    for ref, extra in DIODE_POUR.items():
        fp = board.FindFootprintByReference(ref)
        for p in fp.Pads():
            if p.GetNetname() == "GND":
                continue
            bb = p.GetBoundingBox()
            bb.Inflate(mm(extra))
            z = pcbnew.ZONE(board)
            z.SetLayer(pcbnew.F_Cu)
            z.SetNet(p.GetNet())
            z.SetAssignedPriority(5)          # above the GND pour
            z.SetLocalClearance(mm(0.25))
            z.SetMinThickness(mm(0.25))
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
            z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
            z.SetZoneName(f"pour_{ref}_{p.GetNumber()}")
            ol = z.Outline()
            ol.NewOutline()
            for x, y in ((bb.GetLeft(), bb.GetTop()), (bb.GetRight(), bb.GetTop()),
                         (bb.GetRight(), bb.GetBottom()), (bb.GetLeft(), bb.GetBottom())):
                ol.Append(x, y)
            board.Add(z)
            print(f"pour {ref}.{p.GetNumber()} {p.GetNetname()}")


def main():
    # two processes: a second LoadBoard in a process whose footprints had children removed returns a
    # bare SwigPyObject (KiCad 9.0.2 SWIG), so the pours run in a fresh interpreter
    import subprocess
    import sys
    if "--pours" not in sys.argv:
        board = pcbnew.LoadBoard(PCB)
        paste(board)
        pcbnew.SaveBoard(PCB, board)
        subprocess.run([sys.executable, __file__, "--pours"], check=True)
        return
    board = pcbnew.LoadBoard(PCB)
    for z in list(board.Zones()):          # idempotent: drop pours from a previous run
        if z.GetZoneName().startswith("pour_"):
            board.Remove(z)
    pours(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(PCB, board)


if __name__ == "__main__":
    main()
