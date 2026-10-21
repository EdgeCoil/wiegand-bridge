# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""Route wiegand-bridge-lite.kicad_pcb: thermal vias, Freerouting, ground pours, fill.

Run after build_pcb.py, with the system python3 (KiCad 9 pcbnew). Needs Java 25 for Freerouting 2.4.1.
"""
import os
import subprocess
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "wiegand-bridge-lite.kicad_pcb")
WORK = os.environ.get("ROUTE_WORK", "/tmp")
os.makedirs(WORK, exist_ok=True)
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
            ps = sorted({(p.GetPosition().x, p.GetPosition().y) for p in fp.Pads()
                         if p.GetNumber() == "GND" and p.GetSize().x > mm(1.0)})   # MINI-1: nine 1.2 mm centre pads
            xs = sorted({p[0] for p in ps})
            ys = sorted({p[1] for p in ps})
            for i in range(2):
                for j in range(2):
                    via(board, (xs[i] + xs[i + 1]) // 2, (ys[j] + ys[j + 1]) // 2, gnd)
            for p in fp.Pads():            # the centre pads (and their vias) join the pours solidly
                if p.GetNetname() == "GND" and p.GetNumber() == "GND":
                    p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
        if ref in ():                       # no other exposed pads on the lite board
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


def preroute_usb(board):
    """The USB-C's two VBUS pads (A4B9, B4A9) sit 4.8 mm apart on the pad row with D+/D-/CC between
    them; Freerouting never joins them (rev 10 had the same hand route). J1 is rotated 90 with its
    mouth at the right edge, so the pads run along y at one x: a stub inboard (-x) from each pad,
    a via, and a B.Cu track between the vias."""
    j1 = {p.GetNumber(): p.GetPosition() for p in board.FindFootprintByReference("J1").Pads()}
    vbus = board.FindNet("VBUS")
    pts = []
    for num in ("A4B9", "B4A9"):
        px, py = pcbnew.ToMM(j1[num].x), pcbnew.ToMM(j1[num].y)
        track(board, [(px, py), (px - 1.12, py)], "VBUS", 0.4)
        via(board, mm(px - 1.12), mm(py), vbus)
        pts.append((px - 1.12, py))
    track(board, pts, "VBUS", 0.5, pcbnew.B_Cu)


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
                        clash = True           # 0.5 mm copper-to-edge + via radius
                    for cx_, cy_ in ((bx0 + 3, by0 + 3), (bx0 + bw - 3, by0 + 3), (bx0 + 3, by0 + bh - 3), (bx0 + bw - 3, by0 + bh - 3)):
                        if abs(x - cx_) < 3 and abs(y - cy_) < 3 and (x - cx_) * (cx_ - bx0 - bw / 2) > 0 \
                                and (y - cy_) * (cy_ - by0 - bh / 2) > 0 and math.hypot(x - cx_, y - cy_) > 3 - 0.9:
                            clash = True       # the 3 mm rounded corners (lite: a via landed outside the arc)
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
        board.Remove(z)
    if not finish:
        for t in list(board.GetTracks()):
            board.Remove(t)
        thermal_vias(board)
        preroute_usb(board)
    if board.GetCopperLayerCount() >= 4:
        if not finish:
            fanout_gnd(board)
        gnd_plane(board)
    dsn = os.path.join(WORK, "wb.dsn")
    ses = os.path.join(WORK, "wb.ses")
    assert pcbnew.ExportSpecctraDSN(board, dsn)
    # outer_only(dsn): not on the lite board -- its HiCur nets carry 0.5 A, fine on the 0.5 oz inners
    if os.path.exists(ses):
        os.remove(ses)
    r = subprocess.run([JAVA, "-Djava.awt.headless=true", "-jar", FR, "--gui.enabled=false",
                        "-de", dsn, "-do", ses, "-mp", passes],
                       capture_output=True, text=True, timeout=int(os.environ.get("ROUTE_TIMEOUT", "5400")))
    open(os.path.join(WORK, "freerouting.log"), "w").write(r.stdout + r.stderr)
    assert os.path.exists(ses), r.stdout[-2000:] + r.stderr[-2000:]
    assert pcbnew.ImportSpecctraSES(board, ses)
    for z in list(board.Zones()):          # zones() below rebuilds every plane and pour
        board.Remove(z)
    for v in board.GetTracks():   # Freerouting occasionally emits a degenerate via
        if v.GetClass() == "PCB_VIA" and v.GetWidth(pcbnew.F_Cu) < mm(0.6):
            v.SetWidth(mm(0.6))
    zones(board)
    pcbnew.SaveBoard(PCB, board)
    print("routed; tracks:", len(board.GetTracks()))


if __name__ == "__main__":
    main()
