# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""Build wiegand-bridge-lite.kicad_pcb from netlist.py + placement.py (unrouted).

Run with the system python3 (KiCad 9's pcbnew module). Routing is a separate step (route.py).
A trimmed copy of ../build_pcb.py (same stack, netclasses and outline code; its
labels() rewritten for this board's parts).
"""
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from netlist import FP, PARTS, STD  # noqa: E402
from placement import BOARD, PLACE, HOLES  # noqa: E402

OUT = os.path.join(HERE, "wiegand-bridge-lite.kicad_pcb")
mm = pcbnew.FromMM

POWER = {"VBUS"}
# Input and switch-node nets. The full board routes these at 1.0 mm on the outer layers only, for
# 2 A at 36 V; this board draws ~0.15 A at 12 V (0.5 A from USB), so 0.5 mm on any layer is plenty
# (IPC-2221: 0.5 A needs ~0.2 mm outer, ~0.4 mm inner at 0.5 oz). At 1.0 mm outer-only the first
# route left 21 connections unrouted in the left-edge input column (2026-10-21).
HICUR = {"+VIN_RAW", "+VIN_F", "+VIN", "U2_SW"}
RELAY = set()
MID = {"+3V3", "GND"}


def lib_path(lib):
    return os.path.join(HERE, "lib", "wb.pretty") if lib == "wb" else os.path.join(STD, lib + ".pretty")


def text(board, s, x, y, size=0.8, rot=0, layer=pcbnew.F_SilkS):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetLayer(layer)
    t.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    size = max(size, 1.0)                 # JLCPCB minimum legible silkscreen height (DFM review)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(max(0.15, size * 0.15)))
    t.SetTextAngleDegrees(rot)
    if layer == pcbnew.B_SilkS:
        t.SetMirrored(True)
    board.Add(t)
    return t


def text_from(board, s, x, edge, side, size=0.8, rot=90, layer=pcbnew.F_SilkS):
    """A label whose top (side="top") or bottom (side="bottom") edge sits at y = `edge`."""
    t = text(board, s, x, edge, size, rot, layer)
    bb = t.GetBoundingBox()
    dy = mm(edge) - (bb.GetTop() if side == "top" else bb.GetBottom())
    t.Move(pcbnew.VECTOR2I(0, dy))
    return t


def silk_top(board, ref):
    fp = board.FindFootprintByReference(ref)
    return min(pcbnew.ToMM(g.GetBoundingBox().GetTop()) for g in fp.GraphicalItems()
               if g.GetClass() == "PCB_SHAPE" and g.GetLayer() == pcbnew.F_SilkS)


def pad_xy(board, ref, num):
    for p in board.FindFootprintByReference(ref).Pads():
        if p.GetNumber() == num:
            return pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
    raise KeyError((ref, num))


TERMINAL = ("12V", "GND", "D0", "D1", "LED", "BEEP", "A", "B")


def logo(board, cx, cy, width, layer=pcbnew.B_SilkS, src="edgecoil-mark.geojson"):
    """The edgecoil mark (art/ is ../wiegand-bridge/art): one polygon per feature, scaled to `width`
    mm, centred at (cx, cy), mirrored on the back so it reads correctly."""
    import json
    feats = [f["geometry"]["coordinates"] for f in json.load(open(os.path.join(HERE, "art", src)))["features"]]
    xs = [p[0] for g in feats for p in g[0]]
    ys = [p[1] for g in feats for p in g[0]]
    k = width / (max(xs) - min(xs))
    mx, my = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    flip = -1 if layer == pcbnew.B_SilkS else 1

    def pt(p):                         # potrace y is up; board y is down
        return mm(cx + flip * (p[0] - mx) * k), mm(cy - (p[1] - my) * k)
    for g in feats:
        ps = pcbnew.SHAPE_POLY_SET()
        ps.NewOutline()
        for p in g[0]:
            ps.Append(*pt(p))
        for ring in g[1:]:
            ps.NewHole()
            for p in ring:
                ps.Append(*pt(p), 0, ps.HoleCount(0) - 1)
        ps.Fracture()
        sh = pcbnew.PCB_SHAPE(board)
        sh.SetShape(pcbnew.SHAPE_T_POLY)
        sh.SetPolyShape(ps)
        sh.SetFilled(True)
        sh.SetLayer(layer)
        sh.SetWidth(0)
        board.Add(sh)
    return (max(ys) - min(ys)) * k


def labels(board):
    """Silkscreen a wiring legend: terminal pins, buttons, LEDs, the termination jumper, title.
    Every label is held clear of pads, outlines, fitted parts and other text -- `audit.py --silk`."""
    x0, y0, w, h = BOARD
    top = silk_top(board, "J3")
    # "LED" and "BEEP" at 1.0 mm would touch on a 3.5 mm pitch: nudged apart
    DX = {"LED": -0.35, "BEEP": 0.35}
    for num, name in enumerate(TERMINAL, 1):      # one row above the terminal body
        px, py = pad_xy(board, "J3", str(num))
        text_from(board, name, px + DX.get(name, 0), top - 0.2, "bottom", 1.0, 0)
    f = board.FindFootprintByReference("SW1").GetPosition()
    text_from(board, "BOOT", pcbnew.ToMM(f.x), silk_top(board, "SW1") - 0.2, "bottom", 1.0, 0)
    f = board.FindFootprintByReference("SW2").GetPosition()
    text(board, "RESET", pcbnew.ToMM(f.x) - 3.0, pcbnew.ToMM(f.y) + 3.75, 1.0, 0)   # below, shifted left of U4
    for ref, name in (("D7", "PWR"), ("D8", "FAULT"), ("D23", "OK")):   # vertical, right of each LED
        f = board.FindFootprintByReference(ref).GetPosition()
        text(board, name, pcbnew.ToMM(f.x) + 3.4, pcbnew.ToMM(f.y), 1.0, 90)
    f = board.FindFootprintByReference("JP2").GetPosition()
    text(board, "TERM", pcbnew.ToMM(f.x), pcbnew.ToMM(f.y) - 2.6, 1.0, 0, pcbnew.B_SilkS)
    f = board.FindFootprintByReference("J1").GetPosition()
    text(board, "USB", pcbnew.ToMM(f.x) - 0.5, pcbnew.ToMM(f.y), 1.0, 90, pcbnew.B_SilkS)
    lh = logo(board, 120.0, 111.5, 18.0)
    text(board, "WIEGAND BRIDGE LITE", 120.0, 111.5 + lh / 2 + 2.0, 1.2, 0, pcbnew.B_SilkS)
    text(board, "rev 1  2026-10", 120.0, 111.5 + lh / 2 + 4.3, 1.0, 0, pcbnew.B_SilkS)
    text(board, "wiegand.edgecoil.dev", 120.0, 111.5 + lh / 2 + 6.6, 1.2, 0, pcbnew.B_SilkS)
    for num, name in enumerate(TERMINAL, 1):      # the legend again on the back, under each pin
        px, py = pad_xy(board, "J3", str(num))
        text(board, name, px + DX.get(name, 0), py - 2.3, 1.0, 0, pcbnew.B_SilkS)


def main():
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)           # as the full board: SIG / GND plane / SIG+power / SIG
    board.SetLayerName(pcbnew.In1_Cu, "In1.Cu")
    board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)   # plane layer: the router keeps signals off it
    ds = board.GetDesignSettings()
    ds.m_MinClearance = mm(0.15)
    ds.m_TrackMinWidth = mm(0.15)
    ds.m_ViasMinSize = mm(0.5)
    ds.m_MinThroughDrill = mm(0.3)
    ds.m_CopperEdgeClearance = mm(0.5)
    ds.m_HoleClearance = mm(0.25)
    ns = ds.m_NetSettings
    default = ns.GetDefaultNetclass()
    # Signals: 0.2 mm / 0.15 mm (JLCPCB 4-layer allows 0.09 / 0.09). The full board's 0.25 / 0.2 left
    # 23 connections unrouted here: the SOT-23 and SM712 pad gaps in the cell columns are 0.42 mm.
    default.SetClearance(mm(0.15))
    default.SetTrackWidth(mm(0.2))
    default.SetViaDiameter(mm(0.6))
    default.SetViaDrill(mm(0.3))
    for name, width, via, drill, clr in (("Power", 0.5, 0.6, 0.3, 0.2), ("Mid", 0.3, 0.6, 0.3, 0.2),
                                         ("HiCur", 0.5, 0.6, 0.3, 0.2)):
        nc = pcbnew.NETCLASS(name)
        nc.SetClearance(mm(clr))
        nc.SetTrackWidth(mm(width))
        nc.SetViaDiameter(mm(via))
        nc.SetViaDrill(mm(drill))
        ns.SetNetclass(name, nc)

    nets = {}

    def net(name):
        if name not in nets:
            ni = pcbnew.NETINFO_ITEM(board, name)
            board.Add(ni)
            nets[name] = ni
        return nets[name]

    for ref, fpkey, value, lcsc, pads in PARTS:
        lib, name = FP[fpkey]
        fp = pcbnew.FootprintLoad(lib_path(lib), name)
        assert fp is not None, (ref, lib, name)
        fp.SetReference(ref)
        fp.SetValue(value)
        for f in fp.GetFields():
            if not f.IsReference():
                f.SetVisible(False)
        fp.Reference().SetLayer(pcbnew.F_Fab)
        fp.Reference().SetPosition(fp.GetPosition())
        fp.Reference().SetTextSize(pcbnew.VECTOR2I(mm(0.6), mm(0.6)))
        fp.Reference().SetTextThickness(mm(0.09))
        for f in list(fp.GetFields()):
            if f.GetName() == "LCSC Part":
                fp.RemoveField(f.GetName())
        if lcsc:
            fp.SetField("LCSC", lcsc)
            fp.GetFieldByName("LCSC").SetVisible(False)
        else:
            fp.SetExcludedFromBOM(True)
            fp.SetExcludedFromPosFiles(True)
        padnums = {p.GetNumber() for p in fp.Pads()}
        missing = set(pads) - padnums
        assert not missing, (ref, missing, padnums)
        for p in fp.Pads():
            n = pads.get(p.GetNumber())
            if n:
                p.SetNet(net(n))
        x, y, rot, side = PLACE.get(ref, (BOARD[0] + 20, BOARD[1] + 5, 0, "F"))
        board.Add(fp)
        if side == "B":
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        fp.SetOrientationDegrees(rot)
        fp.Reference().SetPosition(fp.GetPosition())
        for g in fp.GraphicalItems():         # EasyEDA silk lines down to 0.06 mm: JLCPCB minimum is 0.15
            if g.GetClass() == "PCB_SHAPE" and g.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS) \
                    and 0 < g.GetWidth() < mm(0.15):
                g.SetWidth(mm(0.15))

    for name in nets:
        if name in HICUR:
            ns.SetNetclassPatternAssignment(name, "HiCur")
        elif name in POWER:
            ns.SetNetclassPatternAssignment(name, "Power")
        elif name in MID:
            ns.SetNetclassPatternAssignment(name, "Mid")

    # outline, rounded corners
    x0, y0, w, h = BOARD
    r = 3.0
    pts = [((x0 + r, y0), (x0 + w - r, y0)), ((x0 + w, y0 + r), (x0 + w, y0 + h - r)),
           ((x0 + w - r, y0 + h), (x0 + r, y0 + h)), ((x0, y0 + h - r), (x0, y0 + r))]
    for (a, b) in pts:
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
        s.SetEnd(pcbnew.VECTOR2I(mm(b[0]), mm(b[1])))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)
    for cx, cy, sx, sy in ((x0 + r, y0 + r, -1, -1), (x0 + w - r, y0 + r, 1, -1),
                           (x0 + w - r, y0 + h - r, 1, 1), (x0 + r, y0 + h - r, -1, 1)):
        a = pcbnew.PCB_SHAPE(board)
        a.SetShape(pcbnew.SHAPE_T_ARC)
        a.SetCenter(pcbnew.VECTOR2I(mm(cx), mm(cy)))
        a.SetStart(pcbnew.VECTOR2I(mm(cx + sx * r), mm(cy)))
        a.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(90 if sx * sy > 0 else -90, pcbnew.DEGREES_T), True)
        a.SetLayer(pcbnew.Edge_Cuts)
        a.SetWidth(mm(0.1))
        board.Add(a)

    labels(board)
    pcbnew.SaveBoard(OUT, board)
    print("saved", OUT, len(PARTS), "footprints", len(nets), "nets")


if __name__ == "__main__":
    main()
