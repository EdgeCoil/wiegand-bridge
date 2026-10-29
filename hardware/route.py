# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Route wiegand-bridge.kicad_pcb: thermal vias, Freerouting, ground pours, fill.

Run after build_pcb.py, with the system python3 (KiCad 9 pcbnew). Needs Java 25 for Freerouting 2.4.1.
"""
import os
import subprocess
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "wiegand-bridge.kicad_pcb")
WORK = os.environ.get("ROUTE_WORK", "/tmp")
JAVA = "/usr/lib/jvm/java-25-openjdk-amd64/bin/java"
FR = os.path.expanduser("~/.local/share/freerouting/freerouting-2.4.1.jar")
mm = pcbnew.FromMM


def via(board, x, y, net, d=0.6, drill=0.3):
    v = pcbnew.PCB_VIA(board)
    v.SetLocked(True)
    v.SetPosition(pcbnew.VECTOR2I(x, y))
    v.SetWidth(mm(d))
    v.SetDrill(mm(drill))
    v.SetNet(net)
    board.Add(v)


def thermal_vias(board):
    gnd = board.FindNet("GND")
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref == "U1":
            # ESP32 EP is 9 pads on a 1.4 mm grid; put vias where four pads meet.
            ps = sorted({(p.GetPosition().x, p.GetPosition().y) for p in fp.Pads() if p.GetNumber() == "41"})
            xs = sorted({p[0] for p in ps})
            ys = sorted({p[1] for p in ps})
            for i in range(2):
                for j in range(2):
                    via(board, (xs[i] + xs[i + 1]) // 2, (ys[j] + ys[j + 1]) // 2, gnd)
        elif ref == "U2":
            # the footprint's own 4 vias sit at +-0.5 mm; two more at the pad's ends (thermal review)
            ep = [p for p in fp.Pads() if p.GetNumber() == "9" and p.GetSize().x > mm(1)][0]
            c = ep.GetPosition()
            for dx in (-1.05, 1.05):
                via(board, int(c.x + mm(dx)), c.y, gnd)
        elif ref == "U13":
            # reader eFuse: two vias in the exposed pad (a short holds up to 3.5 W until thermal shutdown)
            ep = [p for p in fp.Pads() if p.GetNumber() == "11"][0].GetPosition()
            for dy in (-0.5, 0.5):
                via(board, ep.x, int(ep.y + mm(dy)), gnd)
        if ref in ("U1", "U2", "U3", "U5", "U13"):   # exposed pads (and their vias) join the pours solidly
            for p in fp.Pads():
                if p.GetNetname() == "GND" and p.GetNumber() in ("41", "9", "11"):
                    p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
        if ref in ("U3", "U5"):
            ep = [p for p in fp.Pads() if p.GetNumber() in ("11", "9") and p.GetSize().x > mm(1)]
            for p in ep:
                c = p.GetPosition()
                sx, sy = p.GetSize().x, p.GetSize().y
                if fp.GetOrientationDegrees() % 180:
                    sx, sy = sy, sx
                nx = 2 if sx > mm(2.0) else 1     # U3 (1.65 mm): one column, so paste fits beside it
                ny = 3 if sy > mm(2.2) else 2
                for i in range(nx):
                    for j in range(ny):
                        ox = (i - (nx - 1) / 2) * sx / nx
                        oy = (j - (ny - 1) / 2) * sy / ny
                        via(board, int(c.x + ox), int(c.y + oy), gnd)


def track(board, pts, net, w, layer=pcbnew.F_Cu):
    n = board.FindNet(net)
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(mm(x1), mm(y1)))
        t.SetEnd(pcbnew.VECTOR2I(mm(x2), mm(y2)))
        t.SetWidth(mm(w))
        t.SetLayer(layer)
        t.SetNet(n)
        t.SetLocked(True)
        board.Add(t)


def preroute(board):
    """Hand routes where the autorouter cannot cope: U3's 0.5 mm pitch and the USB-C VBUS pair."""
    u3 = board.FindFootprintByReference("U3").GetPosition()
    ox, oy = pcbnew.ToMM(u3.x), pcbnew.ToMM(u3.y)

    def P(dx, dy):
        return (ox + dx, oy + dy)
    # pins 3, 7, 9 (GND) into the exposed pad
    track(board, [P(-1.4, 0.0), P(-0.6, 0.0)], "GND", 0.2)
    track(board, [P(1.4, 0.5), P(0.6, 0.5)], "GND", 0.2)
    track(board, [P(1.4, -0.5), P(0.6, -0.5)], "GND", 0.2)
    # VSYS: pins 6 and 8 round the outside of pin 7, then under the IC to pin 5 and C8
    track(board, [P(1.4, 1.0), P(2.15, 1.0), P(2.15, 0.0), P(1.4, 0.0)], "VSYS", 0.25)
    track(board, [P(2.15, 1.0), P(2.15, 2.6), P(-1.95, 2.6)], "VSYS", 0.3)
    track(board, [P(-1.4, 1.0), P(-1.95, 1.0), P(-1.95, 2.6), P(-2.15, 3.6)], "VSYS", 0.3)
    # L1 / L2 to the inductor at the left; VOUT up to C9
    track(board, [P(-1.4, 0.5), P(-2.5, 0.5), P(-3.1, 1.1)], "U3_L1", 0.3)
    track(board, [P(-1.4, -0.5), P(-2.5, -0.5), P(-3.1, -1.1)], "U3_L2", 0.3)
    track(board, [P(-1.4, -1.0), P(-1.95, -1.0), P(-1.95, -3.0), P(-2.15, -3.6)], "+3V3", 0.3)
    # USB-C VBUS: A4B9 and B4A9 joined on the bottom layer
    j1 = {p.GetNumber(): p.GetPosition() for p in board.FindFootprintByReference("J1").Pads()}
    a, b = j1["A4B9"], j1["B4A9"]
    ax, ay, bx, by = (pcbnew.ToMM(v) for v in (a.x, a.y, b.x, b.y))
    vbus = board.FindNet("VBUS")
    # straight out along the pad axis: a diagonal stub runs into the neighbouring GND pad.
    # Vias 2.4 mm out (rev 10) so CC2 can drop to the bottom layer inside them.
    track(board, [(ax, ay), (ax + 2.4, ay)], "VBUS", 0.4)
    track(board, [(bx, by), (bx + 2.4, by)], "VBUS", 0.4)
    via(board, mm(ax + 2.4), mm(ay), vbus)
    via(board, mm(bx + 2.4), mm(by), vbus)
    track(board, [(ax + 2.4, ay), (bx + 2.4, by)], "VBUS", 0.5, pcbnew.B_Cu)
    # CC2 (B5) is boxed in by the D+/D- exits and the VBUS stub: via beside the pad, down on the
    # bottom layer, up again beside R2 (placed below the connector for this).
    c = j1["B5"]
    cx, cy = pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)
    r2 = {p.GetNumber(): p.GetPosition() for p in board.FindFootprintByReference("R2").Pads()}
    rx, ry = pcbnew.ToMM(r2["1"].x), pcbnew.ToMM(r2["1"].y)
    cc2 = board.FindNet("CC2")
    v1 = (cx + 1.25, cy - 0.1)
    v2 = (v1[0], ry - 1.3)
    track(board, [(cx, cy), v1], "CC2", 0.2)
    via(board, mm(v1[0]), mm(v1[1]), cc2)
    track(board, [v1, v2], "CC2", 0.25, pcbnew.B_Cu)
    via(board, mm(v2[0]), mm(v2[1]), cc2)
    track(board, [v2, (rx, ry)], "CC2", 0.25)
    preroute_kelvin(board)
    preroute_rdr_sw(board)


def preroute_rdr_sw(board):
    """U13 (TPS26625) escapes at its 0.5 mm pitch, where Freerouting cannot neck a wide class down.
    OUT (pin 10, top of the right-hand column) leaves to the right 0.3 mm wide until it is clear of FLT's
    escape, then runs 0.6 mm to a lane at F1.1's x and straight down to F1 (0.3 mm carries the 0.26 A
    limit; audit NEED is 0.12 mm). FLT (pin 9) goes right under that neck and down to a via inside the
    pocket, below DVDT's exit, so pins 7 and 8 keep their way down the pocket. IN (pin 1, BOOST_SNS)
    leaves upward 0.3 mm, then 0.6 mm to C41, with a 0.25 mm tap left and down into R51 (UVLO divider,
    microamps). GND pins 3, 5 and 6 join the exposed pad under the body.
    rev 12 (eFuse): the first version ran OUT at 0.6 mm from the pin, 0.05 mm from pin 9, and checked
    only the lane; every laid segment is now checked against every other-net pad."""
    u13 = {p.GetNumber(): p for p in board.FindFootprintByReference("U13").Pads()}
    f1 = {p.GetNumber(): p for p in board.FindFootprintByReference("F1").Pads()}
    c41 = {p.GetNumber(): p for p in board.FindFootprintByReference("C41").Pads()}
    r51 = {p.GetNumber(): p for p in board.FindFootprintByReference("R51").Pads()}
    T = pcbnew.ToMM

    def c(p):
        return T(p.GetPosition().x), T(p.GetPosition().y)
    before = {t.m_Uuid.AsString() for t in board.GetTracks()}
    (px, py), (fx, fy) = c(u13["10"]), c(f1["1"])
    lane = fx
    (gx, gy) = c(u13["9"])
    pin_right = T(u13["9"].GetBoundingBox().GetRight())
    turn = pin_right + 1.1                     # FLT's turn, right of DVDT's exit and its way down
    vx, vy = turn + 0.35, gy + 0.6             # FLT via: 0.5 mm under the 0.6 mm OUT run
    neck = turn + 0.6                          # 0.6 mm OUT starts 0.6 mm (centres) past FLT's turn
    track(board, [(px, py), (neck, py)], "RDR_SW", 0.3)
    track(board, [(neck, py), (lane, py), (fx, fy)], "RDR_SW", 0.6)
    track(board, [(gx, gy), (turn, gy), (vx, vy)], "RDR_FLT", 0.2)
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(mm(vx), mm(vy)))
    v.SetWidth(mm(0.6))
    v.SetDrill(mm(0.3))
    v.SetNet(board.FindNet("RDR_FLT"))
    v.SetLocked(True)
    board.Add(v)
    (ix, iy), (cx, cy), (rx, ry) = c(u13["1"]), c(c41["1"]), c(r51["1"])
    assert ry < iy - 0.5, "R51 must stand with its BOOST_SNS end (pin 1) up, above U13 pin 2's way out"
    track(board, [(ix, iy), (ix, iy - 0.6)], "BOOST_SNS", 0.3)
    track(board, [(ix, iy - 0.6), (cx, cy)], "BOOST_SNS", 0.6)
    track(board, [(ix, iy - 0.6), (rx, ry)], "BOOST_SNS", 0.25)
    # UVLO: pin 2 straight left into R51's lower pad, on to R96's
    r96 = {p.GetNumber(): p for p in board.FindFootprintByReference("R96").Pads()}
    (ux, uy), (ax, ay), (bx, by) = c(u13["2"]), c(r51["2"]), c(r96["1"])
    track(board, [(ux, uy), (ax + 0.6, uy), (ax, ay), (bx, by)], "U13_UVLO", 0.2)
    # dV/dt and ILIM share the pocket right of pins 7-8 (0.9 mm to C42's GND pad: room for one track
    # past C42, not two). ILIM (pin 7) turns down next to the pins and back left under the body to R95;
    # dV/dt (pin 8) turns down outside it and into C42's top before C42's GND pad.
    c42 = {p.GetNumber(): p for p in board.FindFootprintByReference("C42").Pads()}
    r95 = {p.GetNumber(): p for p in board.FindFootprintByReference("R95").Pads()}
    (dx, dy), (lx, ly) = c(u13["8"]), c(u13["7"])
    (c1x, c1y), (r1x, r1y) = c(c42["1"]), c(r95["1"])
    ep_bottom = T(u13["11"].GetBoundingBox().GetBottom())
    under = ep_bottom + 0.32                   # ILIM's run under the body, 0.22 mm below the exposed pad
    top42 = T(c42["1"].GetBoundingBox().GetTop())
    xi, xd = pin_right + 0.3, pin_right + 0.7
    track(board, [(lx, ly), (xi, ly), (xi, under), (r1x + 0.2, under), (r1x, r1y)], "U13_ILIM", 0.2)
    track(board, [(dx, dy), (xd, dy), (xd, top42 - 0.25), (c1x, top42 - 0.25), (c1x, c1y)], "U13_DVDT", 0.2)
    ex = T(u13["11"].GetPosition().x)
    for n in ("3", "5", "6"):
        g = u13[n].GetPosition()
        track(board, [(T(g.x), T(g.y)), (ex, T(g.y))], "GND", 0.25)
    # every laid item keeps 0.2 mm from every other-net pad on its layer (polygon test, not GetClearance)
    pads = [q for f in board.GetFootprints() for q in f.Pads()]
    laid = [t for t in board.GetTracks() if t.m_Uuid.AsString() not in before]
    for t in laid:
        grown = pcbnew.SHAPE_POLY_SET()
        t.TransformShapeToPolygon(grown, pcbnew.F_Cu, mm(0.205), 16, pcbnew.ERROR_INSIDE)   # DRC arcs read 0.2 as 0.197
        for o in laid:                         # and from each other
            if o.GetNetname() == t.GetNetname():
                continue
            own = pcbnew.SHAPE_POLY_SET()
            o.TransformShapeToPolygon(own, pcbnew.F_Cu, 0, 16, pcbnew.ERROR_INSIDE)
            own.BooleanIntersection(grown)
            assert own.Area() == 0, ("U13 preroute tracks too close", t.GetNetname(), o.GetNetname())
        for q in pads:
            if q.GetNetname() == t.GetNetname() or not q.IsOnLayer(pcbnew.F_Cu):
                continue
            hit = pcbnew.SHAPE_POLY_SET(grown)
            hit.BooleanIntersection(q.GetEffectivePolygon(pcbnew.F_Cu, pcbnew.ERROR_INSIDE))
            assert hit.Area() == 0, ("U13 preroute too close", t.GetNetname(),
                                     q.GetParentFootprint().GetReference(), q.GetNumber())


def preroute_kelvin(board):
    """rev 12: U12's sense lines, laid here because Freerouting will not enter R59's sense pads (they sit
    inside the other net's land: net tie). Each starts on its tab outside the land, leaves sideways (+x), then turns into its pin
    from the left end of U12's pin row. IN- (pin 9) enters between pins 10 and 8 at 0.15 mm, so pins
    6-8 stay reachable from inside the row (under the body)."""
    r59 = {p.GetNumber(): p for p in board.FindFootprintByReference("R59").Pads()}
    u12 = {p.GetNumber(): p for p in board.FindFootprintByReference("U12").Pads()}
    T = pcbnew.ToMM

    def c(p):
        return T(p.GetPosition().x), T(p.GetPosition().y)
    land_edge = T(r59["1"].GetBoundingBox().GetRight())
    pin_left = min(T(u12[n].GetBoundingBox().GetLeft()) for n in ("6", "7", "8", "9", "10"))
    assert pin_left - land_edge > 0.8, ("U12 too close to R59 for the sense routes", pin_left, land_edge)
    xn = pin_left - 0.28           # IN- vertical: 0.205 mm from pins 6-8 at 0.15 mm width
    xp = xn + 0.1                  # IN+ vertical, below IN-'s end
    # start on the part of each sense tab that stands out of its land, 0.2 mm + half a track clear of it
    s3x, s3y = land_edge + 0.2 + 0.075 + 0.05, c(r59["3"])[1]
    s4x, s4y = land_edge + 0.2 + 0.075 + 0.05, c(r59["4"])[1]
    for n, x in (("3", s3x), ("4", s4x)):
        assert T(r59[n].GetBoundingBox().GetRight()) > x + 0.02, ("sense tab too short", n)
    (p10x, p10y), (p9x, p9y) = c(u12["10"]), c(u12["9"])
    track(board, [(s3x, s3y), (xp, s3y), (xp, p10y), (p10x, p10y)], "ISNS_P", 0.15)
    track(board, [(s4x, s4y), (xn, s4y), (xn, p9y), (p9x, p9y)], "ISNS_N", 0.15)


def fanout_gnd(board):
    """Before routing: a short stub and a via into the In1 plane beside every GND SMD pad on F.Cu
    (unless a GND via or through-hole GND pad is already within 1.2 mm). Without this the router
    walls some GND pads in with other nets and they end up orphaned (rev 10, U8 pin 21 / RN1)."""
    import math
    gnd = board.FindNet("GND")
    taken = [(pcbnew.ToMM(t.GetPosition().x), pcbnew.ToMM(t.GetPosition().y)) for t in board.GetTracks()
             if t.GetClass() == "PCB_VIA"]
    holes = [(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y), p) for f in board.GetFootprints()
             for p in f.Pads()]
    n = 0
    for f in board.GetFootprints():
        for p in f.Pads():
            if p.GetNetname() != "GND" or p.GetDrillSize().x > 0 or not p.IsOnLayer(pcbnew.F_Cu):
                continue
            px, py = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
            if any(math.hypot(px - x, py - y) < 1.2 for x, y in taken):
                continue
            own = p.GetBoundingBox()
            own.Inflate(mm(0.3 + 0.15))          # via ring 0.1 mm clear of the pad's mask opening
            ext = max(pcbnew.ToMM(own.GetWidth()), pcbnew.ToMM(own.GetHeight())) / 2 - 0.45
            ok = None
            for rad in [ext + d for d in (0.45, 0.6, 0.8, 1.0, 1.3, 1.7)]:
                ok = None
                for k in range(16):
                    a = 2 * math.pi * k / 16
                    x, y = px + rad * math.cos(a), py + rad * math.sin(a)
                    pt = pcbnew.VECTOR2I(mm(x), mm(y))
                    clash = own.Contains(pt)   # rev 10 put vias 0.9 mm from the CENTRE: inside big pads
                    from placement import BOARD
                    bx0, by0, bw, bh = BOARD
                    if not (bx0 + 0.9 < x < bx0 + bw - 0.9 and by0 + 0.9 < y < by0 + bh - 0.9):
                        clash = True           # 0.5 mm copper-to-edge + via radius (U1 pads 1/40 sit at the edge)
                    pid = p.m_Uuid.AsString()    # SWIG proxies differ: compare pads by UUID, not identity
                    for hx, hy, q in holes:      # keep the via off every other pad (any net) by 0.45 mm
                        if q.m_Uuid.AsString() == pid:
                            continue
                        bb = q.GetBoundingBox()
                        bb.Inflate(mm(0.3 + 0.2))
                        if bb.Contains(pt):
                            clash = True
                            break
                    if not clash:                # the stub must not cross another pad either
                        for k2 in range(1, 10):
                            sp = pcbnew.VECTOR2I(mm(px + (x - px) * k2 / 10), mm(py + (y - py) * k2 / 10))
                            for hx, hy, q in holes:
                                if q.m_Uuid.AsString() == pid or not q.IsOnLayer(pcbnew.F_Cu):
                                    continue
                                bb = q.GetBoundingBox()
                                bb.Inflate(mm(0.2 + 0.15))
                                if bb.Contains(sp):
                                    clash = True
                                    break
                            if clash:
                                break
                    if not clash:                # the stub must not cross a pre-routed track (rev 10: U3 VSYS)
                        for t in board.GetTracks():
                            if t.GetNetname() == "GND" or t.GetClass() == "PCB_VIA" or t.GetLayer() != pcbnew.F_Cu:
                                continue
                            ax, ay = pcbnew.ToMM(t.GetStart().x), pcbnew.ToMM(t.GetStart().y)
                            bx, by = pcbnew.ToMM(t.GetEnd().x), pcbnew.ToMM(t.GetEnd().y)
                            for k2 in range(11):
                                sx, sy = px + (x - px) * k2 / 10, py + (y - py) * k2 / 10
                                L2 = (bx - ax) ** 2 + (by - ay) ** 2
                                u = 0 if L2 == 0 else max(0, min(1, ((sx - ax) * (bx - ax) + (sy - ay) * (by - ay)) / L2))
                                if math.hypot(sx - ax - u * (bx - ax), sy - ay - u * (by - ay)) < pcbnew.ToMM(t.GetWidth()) / 2 + 0.15 + 0.2:
                                    clash = True
                                    break
                            if clash:
                                break
                    if not clash:                # nor sit on an existing (pre-routed) track
                        for t in board.GetTracks():
                            if t.GetNetname() == "GND":
                                continue
                            if t.GetClass() == "PCB_VIA":
                                q = t.GetPosition()
                                d = math.hypot(x - pcbnew.ToMM(q.x), y - pcbnew.ToMM(q.y)) - 0.3 - 0.3
                            else:
                                ax, ay = pcbnew.ToMM(t.GetStart().x), pcbnew.ToMM(t.GetStart().y)
                                bx, by = pcbnew.ToMM(t.GetEnd().x), pcbnew.ToMM(t.GetEnd().y)
                                L2 = (bx - ax) ** 2 + (by - ay) ** 2
                                u = 0 if L2 == 0 else max(0, min(1, ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / L2))
                                d = math.hypot(x - ax - u * (bx - ax), y - ay - u * (by - ay)) - 0.3 - pcbnew.ToMM(t.GetWidth()) / 2
                            if d < 0.25:
                                clash = True
                                break
                    if not clash and not any(math.hypot(x - tx, y - ty) < 1.0 for tx, ty in taken):
                        ok = (x, y)
                        break
                if ok:
                    break
            if not ok:
                continue
            track(board, [(px, py), ok], "GND", 0.3)
            via(board, mm(ok[0]), mm(ok[1]), gnd)
            taken.append(ok)
            n += 1
    print("GND fan-out vias:", n)


def gnd_plane(board):
    """In1 = solid GND plane, present before export so the router treats GND as a plane net."""
    from placement import BOARD
    x0, y0, w, h = BOARD
    z = pcbnew.ZONE(board)
    z.SetLayer(pcbnew.In1_Cu)
    z.SetNet(board.FindNet("GND"))
    z.SetLocalClearance(mm(0.25))   # 0.3 cut every web between 2.54 mm header pads (layout review S8)
    z.SetMinThickness(mm(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    ol = z.Outline()
    ol.NewOutline()
    for px, py in ((x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)):
        ol.Append(mm(px), mm(py))
    board.Add(z)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def zones(board):
    gnd = board.FindNet("GND")
    from placement import BOARD
    x0, y0, w, h = BOARD
    for layer in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):   # In1 = solid ground plane
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(gnd)
        z.SetLocalClearance(mm(0.25))
        z.SetMinThickness(mm(0.25))
        z.SetThermalReliefGap(mm(0.4))
        z.SetThermalReliefSpokeWidth(mm(0.5))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        ol = z.Outline()
        ol.NewOutline()
        for px, py in ((x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)):
            ol.Append(mm(px), mm(py))
        board.Add(z)
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())


def outer_only(dsn):
    """Restrict the HiCur and Relay classes to F.Cu/B.Cu: Freerouting honours (circuit (use_layer ...))."""
    import re
    s = open(dsn).read()
    n = 0
    for cls in ("HiCur", "Relay"):
        m = re.search(r"\(class \"?" + cls + r"\"?\b", s)
        if not m:
            continue
        i = s.index("(circuit", m.end())
        s = s[:i + len("(circuit")] + "\n        (use_layer F.Cu B.Cu)" + s[i + len("(circuit"):]
        n += 1
    open(dsn, "w").write(s)
    print("outer-only classes:", n)


def main():
    passes = sys.argv[1] if len(sys.argv) > 1 else "60"
    finish = "--finish" in sys.argv      # keep the existing routing; only complete what is left
    board = pcbnew.LoadBoard(PCB)
    for z in list(board.Zones()):
        if not z.GetIsRuleArea():        # keep rule areas (the antenna keep-out): Freerouting honours them
            board.Remove(z)
    if not finish:
        for t in list(board.GetTracks()):
            board.Remove(t)
        thermal_vias(board)
        preroute(board)
    if board.GetCopperLayerCount() >= 4:
        if not finish:
            fanout_gnd(board)
        gnd_plane(board)
    dsn = os.path.join(WORK, "wb.dsn")
    ses = os.path.join(WORK, "wb.ses")
    assert pcbnew.ExportSpecctraDSN(board, dsn)
    outer_only(dsn)
    if os.path.exists(ses):
        os.remove(ses)
    r = subprocess.run([JAVA, "-Djava.awt.headless=true", "-jar", FR, "--gui.enabled=false",
                        "-de", dsn, "-do", ses, "-mp", passes],
                       capture_output=True, text=True, timeout=int(os.environ.get("ROUTE_TIMEOUT", "5400")))
    open(os.path.join(WORK, "freerouting.log"), "w").write(r.stdout + r.stderr)
    assert os.path.exists(ses), r.stdout[-2000:] + r.stderr[-2000:]
    assert pcbnew.ImportSpecctraSES(board, ses)
    for z in list(board.Zones()):          # zones() below rebuilds every plane and pour
        if not z.GetIsRuleArea():
            board.Remove(z)
    for v in board.GetTracks():   # Freerouting occasionally emits a degenerate via
        if v.GetClass() == "PCB_VIA" and v.GetWidth(pcbnew.F_Cu) < mm(0.6):
            v.SetWidth(mm(0.6))
    zones(board)
    pcbnew.SaveBoard(PCB, board)
    print("routed; tracks:", len(board.GetTracks()))
    # Freerouting can stop with connections left open and still write a SES; count them, so an
    # incomplete attempt is never mistaken for a result (rev 2's first attempt left +VIN and USB_DN).
    import json
    rpt = os.path.join(WORK, "route-drc.json")
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "-o", rpt, PCB], capture_output=True)
    n = len(json.load(open(rpt)).get("unconnected_items", []))
    print("unconnected after routing:", n)
    if n:
        sys.exit(2)


if __name__ == "__main__":
    main()
