# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""JLCPCB outputs from the routed board: gerbers + drill (zipped), BOM and CPL in JLCPCB's columns.

Run with the system python3 after route.py. Writes into fab/.
The aux (drill/place) origin is set to the board's bottom-left corner so gerbers and CPL share
one frame with Y up, which is what JLCPCB's placement matcher expects.
"""
import csv
import os
import shutil
import subprocess
import sys
import zipfile
import time

# Every output timestamp in UTC: KiCad stamps Gerbers, drill files and PDFs with the local offset,
# and zip entries with local wall time.
os.environ["TZ"] = "UTC"
time.tzset()
from collections import defaultdict

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from netlist import FP, PARTS  # noqa: E402
from placement import BOARD  # noqa: E402

PCB = os.path.join(HERE, "wiegand-bridge.kicad_pcb")
OUT = os.path.join(HERE, "fab")
LAYERS = "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts"

# Rotation corrections for footprints whose zero differs from JLCPCB's part model. EasyEDA-sourced
# footprints (lib/wb) share JLCPCB's zero. KiCad stock ones that are not symmetric are listed here,
# and every one of them must still be checked in JLCPCB's CPL previewer before paying.
ROT_FIX = {"vson10": 0}
# KiCad's stock JST footprint has its origin on pin 1; JLCPCB places the part by its body centre
# (seen in their preview 2026-10-12: J4's housing sat 3.75 mm off its pins). Use the F.Fab body centre.
BODY_CENTRE = {"xh4"}
GENERIC = {"C474952": "KF128-5.08-2P screw terminal", "C318884": "TS-1187A tact switch"}


def run(*a):
    r = subprocess.run(a, capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stdout + r.stderr)


def main():
    board = pcbnew.LoadBoard(PCB)
    x0, y0, w, h = BOARD
    board.GetDesignSettings().SetAuxOrigin(pcbnew.VECTOR2I(pcbnew.FromMM(x0), pcbnew.FromMM(y0 + h)))
    pcbnew.SaveBoard(PCB, board)

    shutil.rmtree(OUT, ignore_errors=True)
    g = os.path.join(OUT, "gerber")
    os.makedirs(g)
    run("kicad-cli", "pcb", "export", "gerbers", "--layers", LAYERS, "--use-drill-file-origin",
        "--no-x2", "--subtract-soldermask", "-o", g + "/", PCB)
    # drill origin must match the gerbers' origin; no drill maps (they trip JLCPCB's layer detection)
    run("kicad-cli", "pcb", "export", "drill", "--format", "excellon", "--drill-origin", "plot",
        "--excellon-units", "mm", "--excellon-separate-th", "-o", g + "/", PCB)
    zpath = os.path.join(OUT, "wiegand-bridge-gerbers.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(g)):
            z.write(os.path.join(g, f), f)

    # BOM: one line per LCSC part
    fpname = {k: v[1] for k, v in FP.items()}
    rows = defaultdict(list)
    first = {}
    for ref, fpkey, value, lcsc, pads in PARTS:
        if lcsc:
            # one line per part number; parts reused under different labels get a generic comment
            first.setdefault(lcsc, (GENERIC.get(lcsc, value), fpname[fpkey]))
            rows[(*first[lcsc], lcsc)].append(ref)
    with open(os.path.join(OUT, "wiegand-bridge-bom.csv"), "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (value, fpn, lcsc), refs in sorted(rows.items(), key=lambda r: r[1][0]):
            wr.writerow([value, ",".join(sorted(refs, key=lambda r: (r.rstrip("0123456789ABC"), len(r), r))), fpn, lcsc])

    # CPL from the board itself, in the aux-origin frame (Y up)
    key = {ref: fpkey for ref, fpkey, *_ in PARTS}
    lc = {ref: lcsc for ref, _, _, lcsc, _ in PARTS}
    ox, oy = x0, y0 + h
    with open(os.path.join(OUT, "wiegand-bridge-cpl.csv"), "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for fp in sorted(board.GetFootprints(), key=lambda m: m.GetReference()):
            ref = fp.GetReference()
            if not lc.get(ref):
                continue
            p = fp.GetPosition()
            px, py = pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)
            if key[ref] in BODY_CENTRE:
                bb = [g.GetBoundingBox() for g in fp.GraphicalItems() if g.GetLayer() == pcbnew.F_Fab]
                px = pcbnew.ToMM(min(b.GetLeft() for b in bb) + max(b.GetRight() for b in bb)) / 2
                py = pcbnew.ToMM(min(b.GetTop() for b in bb) + max(b.GetBottom() for b in bb)) / 2
            x = px - ox
            y = oy - py
            rot = (fp.GetOrientationDegrees() + ROT_FIX.get(key[ref], 0)) % 360
            wr.writerow([ref, f"{x:.3f}mm", f"{y:.3f}mm", "Top" if fp.GetLayer() == pcbnew.F_Cu else "Bottom",
                         f"{rot:.0f}"])
    # assembly drawing (references on the outline) and 3D views, for fault-finding and review
    run("kicad-cli", "pcb", "export", "pdf", "--layers", "F.Fab,F.Silkscreen,Edge.Cuts", "--mode-single",
        "--include-border-title", "-o", os.path.join(OUT, "wiegand-bridge-assembly.pdf"), PCB)
    for side in ("top", "bottom"):
        run("kicad-cli", "pcb", "render", "--side", side, "--width", "1600", "--height", "1600",
            "--quality", "high", "--zoom", "0.9", "-o", os.path.join(OUT, f"render-{side}.png"), PCB)
    run("kicad-cli", "pcb", "render", "--side", "top", "--width", "1400", "--height", "1400", "--quality",
        "high", "--zoom", "0.85", "--perspective", "--rotate", "330,0,0",
        "-o", os.path.join(OUT, "render-perspective.png"), PCB)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
