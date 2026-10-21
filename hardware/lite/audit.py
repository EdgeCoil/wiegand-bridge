# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""Mechanical and current-capacity audit of the routed board -- the checks KiCad DRC does not make.

1. Body clashes: every pair of footprints whose body outlines (F.Fab, else courtyard, else silkscreen)
   come within 0.3 mm, so a malformed courtyard (K1's) cannot hide a clash.
2. Narrowest track on every net that carries real current, against the width it needs.
3. Parts inside an M3 screw-head keep-out (4.0 mm radius from each hole centre).
4. (the full board's OLED-cover check; no screen here)
5. Tracks within 3 mm of the ESP32 antenna's board edge (the copper-free strip under the antenna
   itself is a rule area, checked by verify.py section 11).
6. Silkscreen legibility (the rev 10 full boards' labels were "blocked or overcrowded"): every silk
   text against other texts, pads (the mask opening clips it), other parts' silk outlines, fitted
   parts' bodies (hidden once assembled) and the board edge. KiCad's DRC checks none of the last
   three, and its silk_overlap is flooded by connector outlines.

    python3 audit.py            # all sections (on the routed board)
    python3 audit.py --silk     # section 6 only; works on the unrouted board straight from build_pcb.py
"""
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from netlist import PARTS  # noqa: E402

ToMM = pcbnew.ToMM
board = pcbnew.LoadBoard(os.path.join(HERE, "wiegand-bridge-lite.kicad_pcb"))
fitted = {ref for ref, _, _, lcsc, _ in PARTS if lcsc}

# nominal heights (mm) of the tall or bulky parts; everything else is <= ~2.5 mm
TALL = {"J3": 8.5, "L1": 4.0, "U1": 2.4, "SW1": 4.3, "SW2": 4.3, "J1": 3.3, "F1": 2.5}


def _bb(item):
    bb = item.GetBoundingBox()
    return (ToMM(bb.GetLeft()), ToMM(bb.GetTop()), ToMM(bb.GetRight()), ToMM(bb.GetBottom()))


def _union(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def body(fp):
    """Bounding box of the body: fab outline if present, else courtyard, else silkscreen.
    Solder jumpers (JP) and test pads are judged by their pads (their graphics are not a body).
    Boxes are combined as plain numbers: BOX2I.Merge on SWIG temporaries corrupted the heap."""
    if fp.GetReference().startswith("JP"):
        return _union([_bb(p) for p in fp.Pads()])
    for layer in (pcbnew.F_Fab, pcbnew.F_CrtYd, pcbnew.F_SilkS):
        boxes = [_bb(g) for g in fp.GraphicalItems() if g.GetLayer() == layer and g.GetClass() == "PCB_SHAPE"]
        if boxes:
            u = _union(boxes)
            if u[2] > u[0] and u[3] > u[1]:
                return u
    bb = fp.GetBoundingBox(False)
    return (ToMM(bb.GetLeft()), ToMM(bb.GetTop()), ToMM(bb.GetRight()), ToMM(bb.GetBottom()))


def gap(a, b):
    dx = max(a[0] - b[2], b[0] - a[2], 0)
    dy = max(a[1] - b[3], b[1] - a[3], 0)
    overlap = (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3])
    return -1.0 if overlap else (dx ** 2 + dy ** 2) ** 0.5


fps = [f for f in board.GetFootprints() if not f.GetReference().startswith(("H", "TP"))]
bodies = {f.GetReference(): body(f) for f in fps}
oled = (0, 0, 0, 0)                  # no screen on the lite board
STATUS_LEDS = ()
STATUS_LABELS = ()


def silk_audit():
    """Section 6. Returns the number of problems."""
    print("\n== 6. silkscreen text: clear of texts (0.25), pads (0.2), outlines (0.15), fitted bodies, edge (0.5)")
    F, B = pcbnew.F_SilkS, pcbnew.B_SilkS
    cu = {F: pcbnew.F_Cu, B: pcbnew.B_Cu}
    texts = [(t.GetText(), t.GetLayer(), _bb(t)) for t in board.GetDrawings()
             if t.GetClass() == "PCB_TEXT" and t.GetLayer() in (F, B)]
    outlines = {F: [], B: []}           # (ref, box) per silk primitive; rectangles split into edges
    for f in board.GetFootprints():
        for g in f.GraphicalItems():
            if g.GetClass() != "PCB_SHAPE" or g.GetLayer() not in (F, B):
                continue
            if g.GetShape() in (pcbnew.SHAPE_T_RECT, pcbnew.SHAPE_T_POLY):
                c = [(ToMM(p.x), ToMM(p.y)) for p in g.GetCorners()]
                for a, b in zip(c, c[1:] + c[:1]):
                    outlines[g.GetLayer()].append((f.GetReference(), (min(a[0], b[0]), min(a[1], b[1]),
                                                                       max(a[0], b[0]), max(a[1], b[1]))))
            else:
                outlines[g.GetLayer()].append((f.GetReference(), _bb(g)))
    x0, y0, x1, y1 = _bb(next(d for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts))
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.Edge_Cuts:
            e = _bb(d)
            x0, y0, x1, y1 = min(x0, e[0]), min(y0, e[1]), max(x1, e[2]), max(y1, e[3])
    probs = 0
    for i, (s, L, bx) in enumerate(texts):
        out = set()
        for j, (s2, L2, b2) in enumerate(texts):
            if j != i and L2 == L and gap(bx, b2) < 0.25:
                out.add(f"text '{s2}'")
        for f in board.GetFootprints():
            ref = f.GetReference()
            for p in f.Pads():
                if p.IsOnLayer(cu[L]) and gap(bx, _bb(p)) < 0.2:
                    out.add(f"pad {ref}.{p.GetNumber()}")
            if ref in fitted and f.GetLayer() == cu[L] and not ref.startswith(("JP", "TP")) \
                    and gap(bx, bodies.get(ref, body(f))) < 0:
                out.add(f"under {ref}")
        for ref, ob in outlines[L]:
            if gap(bx, ob) < 0.15:
                out.add(f"outline {ref}")
        if bx[0] < x0 + 0.5 or bx[1] < y0 + 0.5 or bx[2] > x1 - 0.5 or bx[3] > y1 - 0.5:
            out.add("board edge")
        if s in STATUS_LABELS and L == F and gap(bx, oled) < 0:
            out.add("under the OLED")
        if out:
            probs += 1
            print(f"   {'F' if L == F else 'B'} {chr(39) + s + chr(39):26s} {', '.join(sorted(out))}")
    for ref in STATUS_LEDS:
        if ref in bodies and gap(bodies[ref], oled) < 0:
            probs += 1
            print(f"   {ref}: status LED under a plugged-in OLED {tuple(round(v, 1) for v in oled)}")
    print(f"   {probs} problems in {len(texts)} texts")
    return probs


if "--silk" in sys.argv:
    sys.exit(1 if silk_audit() else 0)

print("== 1. body clashes (gap < 0.3 mm; 'overlap' = bodies intersect)")
n = 0
refs = sorted(bodies)
for i, a in enumerate(refs):
    for b in refs[i + 1:]:
        g = gap(bodies[a], bodies[b])
        if g < 0.3 and (a in TALL or b in TALL):
            n += 1
            print(f"   {a:4s} / {b:4s}  {'OVERLAP' if g < 0 else f'{g:.2f} mm'}"
                  f"   ({'fitted' if a in fitted else 'not fitted'} / {'fitted' if b in fitted else 'not fitted'})")
print(f"   {n} near or overlapping pairs involving tall parts")

print("\n== 2. narrowest track per current-carrying net")
NEED = {  # amps worst case -> width needed at 1 oz, ~10 C rise, outer layer (IPC-2221 approx)
    "+VIN_RAW": 0.5, "+VIN_F": 0.5, "+VIN": 0.5, "U2_SW": 0.8, "VBUS": 0.6, "+3V3": 0.6}


def width_for(amps):            # IPC-2221 external, 10 C rise, 35 um copper
    area_mil2 = (amps / (0.048 * 10 ** 0.44)) ** (1 / 0.725)
    return area_mil2 / 1.378 * 0.0254   # mils wide -> mm


widths = {}
for t in board.GetTracks():
    if t.GetClass() == "PCB_VIA":
        continue
    w = ToMM(t.GetWidth())
    widths.setdefault(t.GetNetname(), []).append((w, ToMM(t.GetLength())))
for net, amps in NEED.items():
    tr = widths.get(net, [])
    if not tr:
        print(f"   {net:10s} no tracks (pour/pads only)")
        continue
    wmin = min(w for w, _ in tr)
    narrow = sum(L for w, L in tr if w < width_for(amps))
    flag = "OK" if wmin >= width_for(amps) else f"NARROW: {narrow:.1f} mm below {width_for(amps):.2f}"
    print(f"   {net:10s} {amps:4.1f} A  min {wmin:.2f} mm  needs {width_for(amps):.2f} mm  {flag}")

print("\n== 3. M3 screw-head keep-out (4.0 mm radius)")
holes = [f for f in board.GetFootprints() if f.GetReference().startswith("H")]
for h in holes:
    hc = (ToMM(h.GetPosition().x), ToMM(h.GetPosition().y))
    for ref, bx in bodies.items():
        cx = min(max(hc[0], bx[0]), bx[2])
        cy = min(max(hc[1], bx[1]), bx[3])
        d = ((cx - hc[0]) ** 2 + (cy - hc[1]) ** 2) ** 0.5
        if d < 4.0:
            print(f"   {h.GetReference()} @ {hc}: {ref} body {d:.1f} mm from centre")

print("\n== 4. (no screen on the lite board)")

print("\n== 5. copper within 3 mm of the ESP32 antenna's board edge")
u1 = board.FindFootprintByReference("U1")
ux = ToMM(u1.GetPosition().x)
ant = (ux - 7.75 - 3.0, 100.0, ux + 7.75 + 3.0, 103.0)   # MINI-1 is 15.5 wide
hits = set()
zone = pcbnew.BOX2I(pcbnew.VECTOR2I(pcbnew.FromMM(ant[0]), pcbnew.FromMM(ant[1])),
                    pcbnew.VECTOR2L(pcbnew.FromMM(ant[2] - ant[0]), pcbnew.FromMM(ant[3] - ant[1])))
for t in board.GetTracks():          # the track itself, not its bounding box (rev 11: a diagonal's box
    if t.HitTest(zone, False, 0):    # reached into the zone while the track passed 1.4 mm outside it)
        hits.add(t.GetNetname())
print(f"   tracks in {ant}: {sorted(hits) or 'none'}  (the strip under the antenna is a keep-out: verify.py 11)")

silk_audit()
