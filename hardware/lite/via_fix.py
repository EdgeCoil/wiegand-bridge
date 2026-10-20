# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""Move GND vias that sit inside a pad's solder-mask opening (DFM review 2026-10-11).

route.fanout_gnd placed vias 0.9 mm from a pad's CENTRE, which on big pads (SMA diodes, 1206 caps,
U2 pin 7, USB-C GND) is still inside the pad: solder wicks down the open hole. Exposed-pad thermal
vias (U1.41, U2.9, U3.11, U5.9) are deliberate and left alone. Each offending via and its stub are
removed and replaced by a via whose ring clears the pad's opening (+0.1 mm), with a 0.3 mm stub from
the pad centre, both checked against finish_net's obstacle grid (all layers for the via, the pad's
layer for the stub). KiCad DRC is the check afterwards.

    python3 via_fix.py           # report only
    python3 via_fix.py --apply
    python3 via_fix.py --pads R70.2,JP4.2     # just add a via for these GND pads
"""
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.argv.append("--tight")
import finish_net as F  # noqa: E402

mm, ToMM = pcbnew.FromMM, pcbnew.ToMM
EP = {("U1", "GND")}          # the MINI-1's nine centre pads share the number "GND"
VR = 0.3            # via radius
MASK = 0.05         # mask expansion


def box(p, inflate=0.0):
    bb = p.GetBoundingBox()
    return (ToMM(bb.GetLeft()) - inflate, ToMM(bb.GetTop()) - inflate,
            ToMM(bb.GetRight()) + inflate, ToMM(bb.GetBottom()) + inflate)


def dist_box(x, y, b):
    dx = max(b[0] - x, 0, x - b[2])
    dy = max(b[1] - y, 0, y - b[3])
    return math.hypot(dx, dy)


def offenders(board):
    pads = [(f.GetReference(), p) for f in board.GetFootprints() for p in f.Pads()
            if p.IsOnLayer(pcbnew.F_Cu) or p.IsOnLayer(pcbnew.B_Cu)]
    out = []
    for v in board.GetTracks():
        if v.GetClass() != "PCB_VIA" or v.GetNetname() != "GND":
            continue
        x, y = ToMM(v.GetPosition().x), ToMM(v.GetPosition().y)
        for ref, p in pads:
            if (ref, p.GetNumber()) in EP or p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                continue
            if p.GetDrillSize().x > 0 and p.GetNetname() == "GND" and dist_box(x, y, box(p)) == 0:
                continue                      # a via inside a GND through-hole pad is harmless
            if dist_box(x, y, box(p)) < VR + MASK:
                out.append((v, ref, p))
                break
    return out


def main(apply):
    board = pcbnew.LoadBoard(F.PCB)
    bad = offenders(board)
    for v, ref, p in bad:
        print(f"  via {ToMM(v.GetPosition().x):.2f},{ToMM(v.GetPosition().y):.2f} in {ref}.{p.GetNumber()} ({p.GetNetname()})")
    print(len(bad), "vias inside pad openings")
    if not apply or not bad:
        return
    targets = [(ref, p.GetNumber(), (ToMM(v.GetPosition().x), ToMM(v.GetPosition().y))) for v, ref, p in bad]
    # remove the vias and any GND stub ending on them, then reload (SWIG lists go stale after Remove)
    vpos = {(round(x, 3), round(y, 3)) for _, _, (x, y) in targets}
    kill = []
    for t in board.GetTracks():
        if t.GetNetname() != "GND":
            continue
        if t.GetClass() == "PCB_VIA":
            if (round(ToMM(t.GetPosition().x), 3), round(ToMM(t.GetPosition().y), 3)) in vpos:
                kill.append(t)
        else:
            for e in (t.GetStart(), t.GetEnd()):
                if (round(ToMM(e.x), 3), round(ToMM(e.y), 3)) in vpos and ToMM(t.GetLength()) < 2.5:
                    kill.append(t)
                    break
    for t in kill:
        board.Remove(t)
    pcbnew.SaveBoard(F.PCB, board)
    place([(ref, num) for ref, num, _ in targets])


def place(targets, reach=2.0):
    """Give each GND pad (ref, number) a via whose ring clears every mask opening, plus a stub."""
    board = pcbnew.LoadBoard(F.PCB)
    grids = F.obstacles(board, "GND")
    allpads = [(f.GetReference(), q) for f in board.GetFootprints() for q in f.Pads()]
    for _, q in allpads:                       # GND pads are obstacles to the via ring too (mask)
        for g in grids.values():
            if q.GetDrillSize().x > 0:
                F.mark_disk(g, ToMM(q.GetPosition().x), ToMM(q.GetPosition().y), ToMM(q.GetDrillSize().x) / 2 + 0.3)
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            for g in grids.values():
                F.mark_disk(g, ToMM(t.GetPosition().x), ToMM(t.GetPosition().y), 0.6 + 0.1)
    sig = [g for L, g in grids.items() if L != pcbnew.In1_Cu]
    moved = 0
    for ref, num in targets:
        fp = board.FindFootprintByReference(ref)
        p = [q for q in fp.Pads() if q.GetNumber() == num and q.GetNetname() == "GND"][0]
        layer = pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
        px, py = ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)
        pb = box(p)
        best = None
        for r in [x / 10 for x in range(0, int(reach * 10))]:
            for k in range(24):
                a = 2 * math.pi * k / 24
                # walk out from the pad centre until the via ring clears the opening by r
                for s in [x / 20 for x in range(4, 80)]:
                    x, y = px + s * math.cos(a), py + s * math.sin(a)
                    if dist_box(x, y, pb) >= VR + MASK + 0.1 + r:
                        break
                if any(dist_box(x, y, box(q)) < VR + MASK + 0.1 for _, q in allpads
                       if q.m_Uuid.AsString() != p.m_Uuid.AsString()):
                    continue
                i, j = F.cell(x, y)
                if not all(F.free(g, i, j, 2) for g in sig):      # obstacles already carry clearance + 0.125
                    continue
                # stub from the pad edge to the via, on the pad's layer, 0.15 mm half-width
                ex = min(max(x, pb[0]), pb[2])
                ey = min(max(y, pb[1]), pb[3])
                ok = True
                L = math.hypot(x - ex, y - ey)
                for kk in range(int(L / 0.05) + 1):
                    tx, ty = ex + (x - ex) * kk / max(1, int(L / 0.05)), ey + (y - ey) * kk / max(1, int(L / 0.05))
                    ci, cj = F.cell(tx, ty)
                    if not F.free(grids[layer], ci, cj, 1):
                        ok = False
                        break
                    if any(dist_box(tx, ty, box(q)) < 0.15 + 0.2 for _, q in allpads
                           if q.IsOnLayer(layer) and q.GetNetname() != "GND"):
                        ok = False
                        break
                if ok:
                    best = (x, y)
                    break
            if best:
                break
        if not best:
            print(f"  {ref}.{num}: no spot found -- via removed, pad relies on the pour")
            continue
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(p.GetPosition())
        t.SetEnd(pcbnew.VECTOR2I(mm(best[0]), mm(best[1])))
        t.SetWidth(mm(0.3))
        t.SetLayer(layer)
        t.SetNet(board.FindNet("GND"))
        board.Add(t)
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(mm(best[0]), mm(best[1])))
        v.SetWidth(mm(0.6))
        v.SetDrill(mm(0.3))
        v.SetNet(board.FindNet("GND"))
        board.Add(v)
        for g in grids.values():
            F.mark_disk(g, best[0], best[1], 0.6 + 0.1)
        moved += 1
        print(f"  {ref}.{num}: via -> {best[0]:.2f},{best[1]:.2f}")
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(F.PCB, board)
    print("moved", moved, "of", len(targets))


if __name__ == "__main__":
    if "--pads" in sys.argv:       # e.g. --pads R70.2,JP4.2 : add a via only (pad lost its via)
        place([tuple(a.split(".")) for a in sys.argv[sys.argv.index("--pads") + 1].split(",")], reach=3.5)
    else:
        main("--apply" in sys.argv)
