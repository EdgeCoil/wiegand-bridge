"""Mechanical and current-capacity audit of the routed board -- the checks KiCad DRC does not make.

1. Body clashes: every pair of footprints whose body outlines (F.Fab, else courtyard, else silkscreen)
   come within 0.3 mm, so a malformed courtyard (K1's) cannot hide a clash.
2. Narrowest track on every net that carries real current, against the width it needs.
3. Parts inside an M3 screw-head keep-out (4.0 mm radius from each hole centre).
4. Tall parts inside the area a plugged-in OLED covers (8.5 mm socket height).
5. Copper near the ESP32 antenna on the board edge.

    python3 audit.py
"""
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from netlist import PARTS  # noqa: E402

ToMM = pcbnew.ToMM
board = pcbnew.LoadBoard(os.path.join(HERE, "wiegand-bridge.kicad_pcb"))
fitted = {ref for ref, _, _, lcsc, _ in PARTS if lcsc}

# nominal heights (mm) of the tall or bulky parts; everything else is <= ~2.5 mm
TALL = {"K1": 15.5, "J2": 10, "J3": 10, "J9": 10, "J10": 10, "J11": 10, "J12": 10, "J13": 10,
        "J15": 10, "J16": 10, "J20": 10, "J21": 10, "J14": 11, "J4": 7, "J5": 8.5, "J6": 8.5,
        "J17": 8.5, "J19": 8.5, "J8": 8.5, "L1": 3.0, "L2": 3.0, "L3": 4.0, "U1": 3.1,
        "SW1": 4.3, "SW2": 4.3, "SW3": 4.3, "J18": 4.3, "J1": 3.3, "F2": 2.5}


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
    "+VIN_RAW": 1.05, "+VIN_F": 1.05, "+VIN": 1.05, "U2_SW": 1.2, "+5V_BUCK": 1.2, "+5V": 1.2, "VBUS": 0.9,
    "VSYS": 1.0, "BAT+": 1.0, "BAT-": 1.0, "Q6_D": 1.0, "BOOST_SW": 1.2, "BOOST_OUT": 0.35,
    "RDR_SW": 0.35, "+12V_RDR": 0.35, "RDR_GND": 0.35, "U3_L1": 1.0, "U3_L2": 1.0, "+3V3": 0.6,
    "RELAY_COM": 2.0, "RELAY_NO": 2.0, "RELAY_NC": 2.0}


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

print("\n== 4. tall parts under a plugged-in OLED (J5 socket, module ~35 x 34 mm hanging below it)")
j5 = board.FindFootprintByReference("J5").GetPosition()
ox, oy = ToMM(j5.x), ToMM(j5.y)
oled = (ox - 17.5, oy - 1.5, ox + 17.5, oy + 32.5)
for ref, bx in bodies.items():
    if ref != "J5" and gap(bx, oled) < 0 and TALL.get(ref, 2.5) >= 7.0:
        print(f"   {ref}: {TALL[ref]} mm tall inside the OLED footprint {tuple(round(v, 1) for v in oled)}"
              f" ({'fitted' if ref in fitted else 'not fitted'})")

print("\n== 5. copper within 3 mm of the ESP32 antenna's board edge")
u1 = board.FindFootprintByReference("U1")
ux = ToMM(u1.GetPosition().x)
ant = (ux - 9.0 - 3.0, 100.0, ux + 9.0 + 3.0, 103.0)
hits = set()
for t in board.GetTracks():
    bb = t.GetBoundingBox()
    b = (ToMM(bb.GetLeft()), ToMM(bb.GetTop()), ToMM(bb.GetRight()), ToMM(bb.GetBottom()))
    if gap(b, ant) < 0:
        hits.add(t.GetNetname())
print(f"   tracks in {ant}: {sorted(hits) or 'none'}  (ground pour is also present up to the edge)")
