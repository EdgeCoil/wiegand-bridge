"""Hand-finish one unrouted connection on the bottom layer with a grid A* search.

Freerouting left IO7 (U1 pad 7 -> R7 pad 1) unrouted on revision 10: the top layer on the left of the
board is congested. This drops a via beside each pad (short top-layer stub), searches a 0.1 mm grid on
B.Cu that keeps the 0.2 mm clearance to every existing track/pad/via/hole, lays the path, refills the
ground zones and saves. KiCad DRC is the check afterwards.

    python3 finish_net.py U1 7 R7 1            # replaces any existing copper on the net
    python3 finish_net.py TP3 1 R7 1 --keep    # branches off the net's existing copper
"""
import heapq
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from placement import BOARD  # noqa: E402

PCB = os.path.join(HERE, "wiegand-bridge.kicad_pcb")
RES = 0.1                    # grid, mm
TW = float(sys.argv[sys.argv.index("--width") + 1]) if "--width" in sys.argv else 0.25   # track width
CLR = 0.2                    # clearance
VIA_D, VIA_DRILL = 0.6, 0.3
mm = pcbnew.FromMM
ToMM = pcbnew.ToMM
X0, Y0, W, H = BOARD
NX, NY = int(W / RES) + 1, int(H / RES) + 1


def cell(x, y):
    return int(round((x - X0) / RES)), int(round((y - Y0) / RES))


def mark_disk(g, x, y, r):
    cx, cy = cell(x, y)
    n = int(math.ceil(r / RES))
    for j in range(max(0, cy - n), min(NY, cy + n + 1)):
        for i in range(max(0, cx - n), min(NX, cx + n + 1)):
            if (i - cx) ** 2 + (j - cy) ** 2 <= (r / RES) ** 2:
                g[j * NX + i] = 1


def mark_seg(g, x1, y1, x2, y2, r):
    L = math.hypot(x2 - x1, y2 - y1)
    steps = max(1, int(L / (RES / 2)))
    for k in range(steps + 1):
        t = k / steps
        mark_disk(g, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, r)


def mark_box(g, bb, inflate):
    l, r = ToMM(bb.GetLeft()) - inflate, ToMM(bb.GetRight()) + inflate
    t, b = ToMM(bb.GetTop()) - inflate, ToMM(bb.GetBottom()) + inflate
    i0, j0 = cell(l, t)
    i1, j1 = cell(r, b)
    for j in range(max(0, j0), min(NY, j1 + 1)):
        for i in range(max(0, i0), min(NX, i1 + 1)):
            g[j * NX + i] = 1


def obstacles(board, net):
    keep = CLR + TW / 2 + (0 if "--tight" in sys.argv else RES / 2)   # half-grid rounding margin; DRC is the real check
    layers = [pcbnew.F_Cu, pcbnew.B_Cu] + ([pcbnew.In1_Cu, pcbnew.In2_Cu] if board.GetCopperLayerCount() >= 4 else [])
    grids = {L: bytearray(NX * NY) for L in layers}
    for g in grids.values():                       # board edge keep-out
        for j in range(NY):
            for i in range(NX):
                if i * RES < 0.6 or j * RES < 0.6 or (NX - 1 - i) * RES < 0.6 or (NY - 1 - j) * RES < 0.6:
                    g[j * NX + i] = 1
    for t in board.GetTracks():
        if t.GetNetname() == net:
            continue
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            for g in grids.values():
                mark_disk(g, ToMM(p.x), ToMM(p.y), ToMM(t.GetWidth(pcbnew.F_Cu)) / 2 + keep)
        elif t.GetLayer() in grids:
            s, e = t.GetStart(), t.GetEnd()
            mark_seg(grids[t.GetLayer()], ToMM(s.x), ToMM(s.y), ToMM(e.x), ToMM(e.y), ToMM(t.GetWidth()) / 2 + keep)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == net:
                continue
            for layer, g in grids.items():
                if p.IsOnLayer(layer) or p.GetDrillSize().x > 0:
                    mark_box(g, p.GetBoundingBox(), keep)
    return grids


def free(g, i, j, r_cells=0):
    for jj in range(j - r_cells, j + r_cells + 1):
        for ii in range(i - r_cells, i + r_cells + 1):
            if not (0 <= ii < NX and 0 <= jj < NY) or g[jj * NX + ii]:
                return False
    return True


def line_free(g, a, b):
    (x1, y1), (x2, y2) = a, b
    L = math.hypot(x2 - x1, y2 - y1)
    steps = max(1, int(L / (RES / 2)))
    for k in range(steps + 1):
        t = k / steps
        i, j = cell(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
        if g[j * NX + i]:
            return False
    return True


def via_spot(grids, pad):
    """A via cell near the pad, clear on both layers, reachable by a straight top-layer stub."""
    px, py = ToMM(pad.GetPosition().x), ToMM(pad.GetPosition().y)
    rv = int(math.ceil((VIA_D / 2 - TW / 2) / RES))
    best = None
    for rad in [x * 0.1 for x in range(8, 60)]:
        for k in range(36):
            a = 2 * math.pi * k / 36
            x, y = px + rad * math.cos(a), py + rad * math.sin(a)
            i, j = cell(x, y)
            if free(grids[pcbnew.F_Cu], i, j, rv) and free(grids[pcbnew.B_Cu], i, j, rv) and \
                    line_free(grids[pcbnew.F_Cu], (px, py), (x, y)):
                best = (i, j)
                break
        if best:
            return best
    raise SystemExit(f"no via spot near {pad.GetParentFootprint().GetReference()} {pad.GetNumber()}")


def astar(grids, s, targets, rv, extra_starts=()):
    """A* over (i, j, layer): 8-connected moves within a layer; a via (cost 25) where both layers are
    clear for the via's radius. Returns [(i, j, layer)]."""
    F, B = grids[pcbnew.F_Cu], grids[pcbnew.B_Cu]
    G = (F, B) + ((grids[pcbnew.In2_Cu],) if pcbnew.In2_Cu in grids else ())   # In1 is the GND plane

    t = next(iter(targets))

    def h(a):
        return math.hypot(a[0] - t[0], a[1] - t[1])
    openq, came, cost = [], {}, {}
    for st in (s,) + tuple(extra_starts):
        openq.append((h(st), 0.0, st))
        came[st] = None
        cost[st] = 0.0
    heapq.heapify(openq)
    nb = [(1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1), (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
    while openq:
        _, c, cur = heapq.heappop(openq)
        if cur in targets:
            path = []
            while cur:
                path.append(cur)
                cur = came[cur]
            return path[::-1]
        if c > cost[cur]:
            continue
        i, j, L = cur
        g = G[L]
        prev = came[cur]
        for dx, dy, w in nb:
            n = (i + dx, j + dy, L)
            if not (0 <= n[0] < NX and 0 <= n[1] < NY) or g[n[1] * NX + n[0]]:
                continue
            turn = prev is not None and prev[2] == L and (i - prev[0], j - prev[1]) != (dx, dy)
            nc = c + w + (0.4 if turn else 0) + (0.3 if L == 0 else 0)   # mild preference for the bottom
            if nc < cost.get(n, 1e18):
                cost[n] = nc
                came[n] = cur
                heapq.heappush(openq, (nc + h(n), nc, n))
        if all(free(g, i, j, rv) for g in grids.values()):   # a via passes through every layer
            for L2 in range(len(G)):
                if L2 == L:
                    continue
                n = (i, j, L2)
                nc = c + 25
                if nc < cost.get(n, 1e18):
                    cost[n] = nc
                    came[n] = cur
                    heapq.heappush(openq, (nc + h(n), nc, n))
    return None


def simplify(path):
    out = [path[0]]
    for a, b in zip(path[1:], path[2:]):
        d1 = (a[0] - out[-1][0], a[1] - out[-1][1])
        d2 = (b[0] - a[0], b[1] - a[1])
        if d1[0] * d2[1] - d1[1] * d2[0] != 0:
            out.append(a)
    out.append(path[-1])
    return out


def main():
    ref_a, pad_a, ref_b, pad_b = sys.argv[1:5]
    board = pcbnew.LoadBoard(PCB)
    pa = [p for p in board.FindFootprintByReference(ref_a).Pads() if p.GetNumber() == pad_a][0]
    pb = [p for p in board.FindFootprintByReference(ref_b).Pads() if p.GetNumber() == pad_b][0]
    net = pa.GetNetname()
    assert net == pb.GetNetname(), (net, pb.GetNetname())
    old = [] if "--keep" in sys.argv else [t for t in board.GetTracks() if t.GetNetname() == net]
    if old:                              # start clean: drop any earlier attempt on this net
        for t in old:
            board.Remove(t)
        pcbnew.SaveBoard(PCB, board)     # SWIG's track list is unusable after Remove(); reload
        board = pcbnew.LoadBoard(PCB)
        pa = [p for p in board.FindFootprintByReference(ref_a).Pads() if p.GetNumber() == pad_a][0]
        pb = [p for p in board.FindFootprintByReference(ref_b).Pads() if p.GetNumber() == pad_b][0]
    grids = obstacles(board, net)
    rv = int(math.ceil((VIA_D / 2 - TW / 2) / RES))
    def lay(p):                          # 0 = top, 1 = bottom (bottom-only SMD pads, e.g. test pads)
        return 1 if (p.IsOnLayer(pcbnew.B_Cu) and not p.IsOnLayer(pcbnew.F_Cu)) else 0
    sa = cell(ToMM(pa.GetPosition().x), ToMM(pa.GetPosition().y)) + (lay(pa),)
    sb = cell(ToMM(pb.GetPosition().x), ToMM(pb.GetPosition().y)) + (lay(pb),)
    starts = []                          # existing copper of this net: the new route may branch off it
    if "--keep" in sys.argv:
        for t in board.GetTracks():
            if t.GetNetname() != net or t.GetClass() == "PCB_VIA":
                continue
            L = 0 if t.GetLayer() == pcbnew.F_Cu else 1
            x1, y1, x2, y2 = (ToMM(v) for v in (t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y))
            n = max(1, int(math.hypot(x2 - x1, y2 - y1) / RES))
            for k in range(n + 1):
                starts.append(cell(x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n) + (L,))
    # through-hole pads already join both layers: start/finish on either, never add a via in a pad
    def tht(p):
        return p.GetDrillSize().x > 0
    if tht(pa):
        starts.append(sa[:2] + (1 - sa[2],))
    targets = {sb} | ({sb[:2] + (1 - sb[2],)} if tht(pb) else set())
    path = astar(grids, sa, targets, rv, starts)
    if not path:
        raise SystemExit("no path")
    ni = board.FindNet(net)
    layers = (pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu)

    def P(c):
        return (X0 + c[0] * RES, Y0 + c[1] * RES)
    runs, cur = [], [path[0]]
    for a in path[1:]:
        if a[2] != cur[-1][2]:
            runs.append(cur)
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(pcbnew.VECTOR2I(mm(P(a)[0]), mm(P(a)[1])))
            via.SetWidth(mm(VIA_D))
            via.SetDrill(mm(VIA_DRILL))
            via.SetNet(ni)
            board.Add(via)
            cur = [a]
        else:
            cur.append(a)
    runs.append(cur)
    total = 0.0
    for run in runs:
        if len(run) < 2:
            continue
        pts = [P(c) for c in simplify([(c[0], c[1]) for c in run])]
        for a, b in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
            t.SetEnd(pcbnew.VECTOR2I(mm(b[0]), mm(b[1])))
            t.SetWidth(mm(TW))
            t.SetLayer(layers[run[0][2]])
            t.SetNet(ni)
            board.Add(t)
            total += math.dist(a, b)
    print(f"{net}: {len(runs) - 1} vias, {total:.1f} mm")
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(PCB, board)


if __name__ == "__main__":
    main()
