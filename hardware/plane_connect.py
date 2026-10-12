"""Connect an orphaned GND pad to the In1 ground plane: route from the pad to the nearest spot where a
via fits AND lands inside the main In1 plane fill, then drop the via there.

    python3 plane_connect.py U8 21 RN1 5 U1 40
"""
import heapq
import math
import sys

import pcbnew

import finish_net as F

mm, ToMM = pcbnew.FromMM, pcbnew.ToMM
args = sys.argv[1:]
board = pcbnew.LoadBoard(F.PCB)
gnd = board.FindNet("GND")
main_plane = None
for z in board.Zones():
    if z.GetNetname() == "GND" and z.GetLayer() == pcbnew.In1_Cu:
        fill = z.GetFilledPolysList(pcbnew.In1_Cu)
        main_plane = max((fill.Outline(k) for k in range(fill.OutlineCount())), key=lambda p: abs(p.Area()))
grids = F.obstacles(board, "GND")
for fp in board.GetFootprints():             # no via on top of any drilled hole
    for p in fp.Pads():
        if p.GetDrillSize().x > 0:
            for g in grids.values():
                F.mark_disk(g, ToMM(p.GetPosition().x), ToMM(p.GetPosition().y), ToMM(p.GetDrillSize().x) / 2 + 0.45)
for t in board.GetTracks():
    if t.GetClass() == "PCB_VIA":
        for g in grids.values():
            F.mark_disk(g, ToMM(t.GetPosition().x), ToMM(t.GetPosition().y), 0.8)
sig = [grids[L] for L in grids if L != pcbnew.In1_Cu]
FCU = grids[pcbnew.F_Cu]


import contextlib, io
import gndcheck
with contextlib.redirect_stdout(io.StringIO()):
    main_tracks, main_pads = gndcheck.analyse(board)
TARGET = set()                      # cells on F.Cu copper already tied to the plane
for t in main_tracks:
    if t.GetClass() == "PCB_VIA" or t.GetLayer() == pcbnew.F_Cu:
        pts = [t.GetPosition()] if t.GetClass() == "PCB_VIA" else [t.GetStart(), t.GetEnd()]
        if len(pts) == 2:
            n = max(1, int(ToMM((pts[0] - pts[1]).EuclideanNorm()) / F.RES))
            pts = [pcbnew.VECTOR2I(pts[0].x + (pts[1].x - pts[0].x) * k // n, pts[0].y + (pts[1].y - pts[0].y) * k // n) for k in range(n + 1)]
        for q in pts:
            TARGET.add(F.cell(ToMM(q.x), ToMM(q.y)))
for p in main_pads:
    if p.IsOnLayer(pcbnew.F_Cu):
        TARGET.add(F.cell(ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)))


def via_ok(i, j):
    x, y = F.X0 + i * F.RES, F.Y0 + j * F.RES
    return all(F.free(g, i, j, 2) for g in sig) and main_plane.PointInside(pcbnew.VECTOR2I(mm(x), mm(y)))


for ref, num in zip(args[::2], args[1::2]):
    pad = [p for p in board.FindFootprintByReference(ref).Pads() if p.GetNumber() == num][0]
    s = F.cell(ToMM(pad.GetPosition().x), ToMM(pad.GetPosition().y))
    q, came, seen = [(0.0, s)], {s: None}, {s}
    end = None
    while q:
        c, cur = heapq.heappop(q)
        if cur != s and (cur in TARGET or via_ok(*cur)):
            end = cur
            break
        for dx, dy, w in ((1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1), (1, 1, 1.41), (1, -1, 1.41), (-1, 1, 1.41), (-1, -1, 1.41)):
            n = (cur[0] + dx, cur[1] + dy)
            if n in seen or not (0 <= n[0] < F.NX and 0 <= n[1] < F.NY) or FCU[n[1] * F.NX + n[0]]:
                continue
            seen.add(n)
            came[n] = cur
            heapq.heappush(q, (c + w, n))
    if not end:
        print(ref, num, "no route to the plane")
        continue
    path = []
    cur = end
    while cur:
        path.append(cur)
        cur = came[cur]
    pts = [(F.X0 + i * F.RES, F.Y0 + j * F.RES) for i, j in F.simplify(path[::-1])]
    for a, b in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
        t.SetEnd(pcbnew.VECTOR2I(mm(b[0]), mm(b[1])))
        t.SetWidth(mm(F.TW))
        t.SetLayer(pcbnew.F_Cu)
        t.SetNet(gnd)
        board.Add(t)
    if end in TARGET:                   # landed on connected copper: no via needed
        print(ref, num, f"-> connected copper, {sum(math.dist(a, b) for a, b in zip(pts, pts[1:])):.1f} mm")
        continue
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(mm(pts[-1][0]), mm(pts[-1][1])))
    v.SetWidth(mm(0.6))
    v.SetDrill(mm(0.3))
    v.SetNet(gnd)
    board.Add(v)
    for g in grids.values():
        F.mark_disk(g, pts[-1][0], pts[-1][1], 0.8)
    print(ref, num, f"-> plane via, {sum(math.dist(a, b) for a, b in zip(pts, pts[1:])):.1f} mm")
pcbnew.ZONE_FILLER(board).Fill(board.Zones())
pcbnew.SaveBoard(F.PCB, board)
