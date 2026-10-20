# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Build wiegand-bridge.kicad_pcb from netlist.py + placement.py (unrouted).

Run with the system python3 (KiCad 9's pcbnew module). Routing is a separate step (route.py).
"""
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from netlist import FP, PARTS, STD  # noqa: E402
from placement import BOARD, PLACE, HOLES  # noqa: E402

OUT = os.path.join(HERE, "wiegand-bridge.kicad_pcb")
mm = pcbnew.FromMM

POWER = {"VBUS", "+5V", "BOOST_OUT", "RDR_SW", "+12V_RDR", "BAT+", "BAT-", "Q6_D"}
# Input and switch-node nets: 1.0 mm and OUTER layers only (JLCPCB's inner layers are 0.5 oz; layout
# and DFM reviews 2026-10-11). route.py adds (use_layer F.Cu B.Cu) to these classes in the DSN.
HICUR = {"+VIN_RAW", "+VIN_F", "+VIN", "+5V_BUCK", "U2_SW", "BOOST_SW"}
RELAY = {"RELAY_COM", "RELAY_NO", "RELAY_NC"}     # contacts: outer layers, 0.5 mm from everything
# (revision 10 renamed +12V_IN/+12V to +VIN_RAW/+VIN; this list was missed and audit.py caught it)
MID = {"+3V3", "VSYS", "U3_L1", "U3_L2", "GND"}


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


def pad_xy(board, ref, num):
    for p in board.FindFootprintByReference(ref).Pads():
        if p.GetNumber() == num:
            return pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
    raise KeyError((ref, num))


TERMINAL_LABELS = {
    "J11": ("LED", "BEEP"), "J10": ("D0", "D1"), "J3": ("+12V", "GND"), "J2": ("6-36V", "GND"),
    "J20": ("A", "B"), "J21": ("+12V", "GND"), "J15": ("NC", "NO"), "J16": ("", "COM"),
    "J9": ("IN1", "IN2"), "J12": ("GND", "IN3"), "J13": ("IN4", "GND"),
}


def logo(board, cx, cy, width, layer=pcbnew.B_SilkS, src="edgecoil-mark.geojson"):
    """The edgecoil mark from art/edgecoil-mark.geojson (potrace of brand/edgecoil/v2's one-colour
    full cut): one polygon per feature, each an outline + holes, scaled to `width` mm, centred at
    (cx, cy), mirrored on the back so it reads correctly."""
    import json
    feats = [f["geometry"]["coordinates"] for f in json.load(open(os.path.join(HERE, "art", src)))["features"]]
    xs = [p[0] for g in feats for p in g[0]]
    ys = [p[1] for g in feats for p in g[0]]
    k = width / (max(xs) - min(xs))
    mx, my = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    flip = -1 if layer == pcbnew.B_SilkS else 1

    def pt(p):                         # potrace y is up; board y is down
        return mm(cx + flip * (p[0] - mx) * k), mm(cy - (p[1] - my) * k)
    for g in feats:                    # one shape per part: a saved gr_poly keeps only its first outline
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
    """Silkscreen a wiring legend: terminal pins, connector pin orders, buttons, LEDs, title."""
    x0, y0, w, h = BOARD
    for ref, names in TERMINAL_LABELS.items():
        for num, name in zip(("1", "2"), names):
            px, py = pad_xy(board, ref, num)
            if not name:
                continue
            if ref in ("J9", "J12", "J13"):      # left edge: label just inboard of the body
                text(board, name, x0 + 11.6, py, 0.8, 90)
            elif ref in ("J15", "J16"):          # right edge: on the back -- the top gap between K1 and
                text(board, name, 180.6, py, 1.0, 0, pcbnew.B_SilkS)    # the blocks is 0.9 mm, under the relay
            else:                                # bottom edge
                text(board, name, px, y0 + h - 11.6, 0.8)
    for num, name in zip("1234", ("GND", "3V3", "SCL", "SDA")):
        px, py = pad_xy(board, "J5", num)
        text(board, name, px, py + 2.6, 0.8, 90)
    for ref, names in (("J6", ("3V3", "GND", "SCK", "MOSI", "CS", "DC", "RST", "BL/BSY")),
                       ("J17", ("3V3", "GND", "SCK", "MOSI", "MISO", "CS", "INT", "RST"))):
        for num, name in enumerate(names, 1):
            px, py = pad_xy(board, ref, str(num))
            text(board, name, px, py + 3.8, 0.8, 90)
    for ref, name, dy in (("J17", "W5500", -2.6), ("J19", "EXPANSION (see guide)", 2.9)):
        px, py = pad_xy(board, ref, "1")
        text(board, name, px + 8, py + dy, 0.8)
    for num, name in (("1", "+"), ("2", "-"), ("3", "T"), ("4", "T")):   # cell +/-, thermistor T T
        bx, by = pad_xy(board, "J4", num)
        text(board, name, bx, by + 4.0, 1.0)
        text(board, name, bx, by + 2.2, 1.0, 0, pcbnew.B_SilkS)      # same legend under each pin, back side
    bx, by = pad_xy(board, "J4", "2")                                   # clear of the pins, inside the edge
    text(board, "BATTERY: LiFePO4 3.2V ONLY", 177.5, by + 4.2, 1.0, 0, pcbnew.B_SilkS)
    text(board, "T T: 10k B3950 NTC", 177.5, by - 2.4, 1.0, 0, pcbnew.B_SilkS)
    tx, ty = pad_xy(board, "J8", "1")
    text(board, "EXT TAMPER", tx + 3.6, ty + 2.2, 0.8)
    for ref, name, dy in (("SW1", "BOOT", 3.4), ("SW2", "RESET", 3.4), ("SW3", "TAMPER", 3.4)):
        f = board.FindFootprintByReference(ref).GetPosition()
        text(board, name, pcbnew.ToMM(f.x), pcbnew.ToMM(f.y) + dy, 0.8)
    for ref, name, dx, dy in (("D7", "PWR", 4.2, 0), ("D8", "STATUS", 0, 2.0), ("D12", "CHG", 0, 1.8),
                              ("JP1", "13V2", 0, 1.8), ("J1", "USB-C", 0, 6.0), ("JP2", "TERM", 0, -2.6),
                              ("J18", "QWIIC", 0, 3.4), ("J14", "DC IN", -6.0, -4.5),
                              ("JP5", "NTC", 0, 1.8)):
        f = board.FindFootprintByReference(ref).GetPosition()
        text(board, name, pcbnew.ToMM(f.x) + dx, pcbnew.ToMM(f.y) + dy, 0.8)
    f = board.FindFootprintByReference("JP3").GetPosition()   # no room on top: label the bias jumpers underneath
    text(board, "JP3+JP4 = RS485 BIAS", pcbnew.ToMM(f.x) + 1.3, pcbnew.ToMM(f.y) - 3.6, 0.8, 0, pcbnew.B_SilkS)
    lh = logo(board, 158.0, 149.0, 28.0)
    text(board, "WIEGAND BRIDGE  v1.0", 158.0, 149.0 + lh / 2 + 2.0, 1.2, 0, pcbnew.B_SilkS)
    text(board, "rev 10b  2026-10", 158.0, 149.0 + lh / 2 + 4.0, 0.9, 0, pcbnew.B_SilkS)
    text(board, "wiegand.edgecoil.dev", 158.0, 149.0 + lh / 2 + 6.2, 1.2, 0, pcbnew.B_SilkS)


def main():
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)           # rev 10: SIG / GND plane / SIG+power / SIG
    board.SetLayerName(pcbnew.In1_Cu, "In1.Cu")
    board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)   # plane layer: the router keeps signals off it
    ds = board.GetDesignSettings()
    # JLCPCB standard 2-layer capability is 0.127/0.127 mm; keep comfortable margins.
    ds.m_MinClearance = mm(0.15)
    ds.m_TrackMinWidth = mm(0.15)
    ds.m_ViasMinSize = mm(0.5)
    ds.m_MinThroughDrill = mm(0.3)
    ds.m_CopperEdgeClearance = mm(0.5)    # V-cut rails need >= 0.4 (DFM review)
    ds.m_HoleClearance = mm(0.25)
    ns = ds.m_NetSettings
    default = ns.GetDefaultNetclass()
    default.SetClearance(mm(0.2))
    default.SetTrackWidth(mm(0.25))
    default.SetViaDiameter(mm(0.6))
    default.SetViaDrill(mm(0.3))
    for name, width, via, drill, clr in (("Power", 0.6, 0.8, 0.4, 0.2), ("Mid", 0.4, 0.6, 0.3, 0.2),
                                         ("HiCur", 1.0, 0.8, 0.4, 0.25), ("Relay", 1.0, 0.8, 0.4, 0.5)):
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
        if ref == "J14":                       # EasyEDA's DC-005 model is mirrored against the footprint and
            models = fp.Models()             # mounted with its mouth inboard: mirror it (negative scale) and
            for k in range(len(models)):     # shift it onto the outline. Render only; the pads are right.
                m = models[k]                # (Measured by rendering candidates, 2026-10-21. Assign the element
                m.m_Scale.y = -1.0           # back: editing fp.Models()[k] in place does not save.)
                m.m_Offset.x, m.m_Offset.y, m.m_Offset.z = -1.6, -1.4, 0.0
                models[k] = m
        for f in fp.GetFields():
            if not f.IsReference():
                f.SetVisible(False)
        # references go on the fab layer (assembly drawing); the silkscreen carries labels() instead
        fp.Reference().SetLayer(pcbnew.F_Fab)
        fp.Reference().SetPosition(fp.GetPosition())
        fp.Reference().SetTextSize(pcbnew.VECTOR2I(mm(0.6), mm(0.6)))
        fp.Reference().SetTextThickness(mm(0.09))
        for f in list(fp.GetFields()):          # stale numbers that came in with downloaded footprints
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
        x, y, rot, side = PLACE.get(ref, (BOARD[0] + 70, BOARD[1] + 5, 0, "F"))
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
        elif name in RELAY:
            ns.SetNetclassPatternAssignment(name, "Relay")
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
