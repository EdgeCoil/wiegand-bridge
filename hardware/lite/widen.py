# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""Widen power tracks in place after routing, keeping only widenings that pass KiCad DRC.

Revision 10's input nets (+VIN_RAW, +VIN_F, +VIN) were routed at 0.25 mm because build_pcb's
power-netclass list still named revision 9's nets. audit.py flagged them. This sets each narrow
track on the listed nets to the target width, runs DRC, reverts any track involved in a clearance
or short violation, and repeats until clean.

    python3 widen.py
"""
import json
import os
import subprocess
import tempfile

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "wiegand-bridge-lite.kicad_pcb")
TARGET = {n: float(os.environ.get("WIDEN_TO", "0.5")) for n in ("+VIN_RAW", "+VIN_F", "+VIN", "U2_SW", "+3V3", "VBUS")}
mm = pcbnew.FromMM


def drc_offenders():
    out = os.path.join(tempfile.gettempdir(), "widen_drc.json")
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "-o", out, PCB], capture_output=True)
    d = json.load(open(out))
    bad = set()
    for v in d["violations"]:
        if v["type"] not in ("clearance", "shorting_items", "solder_mask_bridge", "copper_edge_clearance",
                             "hole_clearance", "track_width"):
            continue
        for it in v["items"]:
            if it["description"].startswith("Track"):
                bad.add((round(it["pos"]["x"], 2), round(it["pos"]["y"], 2), it["description"].split("]")[0]))
    return bad


def main():
    board = pcbnew.LoadBoard(PCB)
    orig = {}
    for t in board.GetTracks():
        n = t.GetNetname()
        if t.GetClass() != "PCB_VIA" and n in TARGET and pcbnew.ToMM(t.GetWidth()) < TARGET[n] - 1e-3:
            orig[t.m_Uuid.AsString()] = t.GetWidth()
            t.SetWidth(mm(TARGET[n]))
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(PCB, board)
    print("widened", len(orig), "tracks")
    for rnd in range(8):
        bad = drc_offenders()
        if not bad:
            break
        board = pcbnew.LoadBoard(PCB)
        reverted = 0
        for t in board.GetTracks():
            u = t.m_Uuid.AsString()
            if u not in orig:
                continue
            bb = t.GetBoundingBox()
            for x, y, desc in bad:
                if t.GetNetname() in desc and bb.Contains(pcbnew.VECTOR2I(mm(x), mm(y))):
                    t.SetWidth(orig.pop(u))
                    reverted += 1
                    break
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        pcbnew.SaveBoard(PCB, board)
        print(f"round {rnd}: {len(bad)} violations, reverted {reverted}")
        if not reverted:
            break
    print("kept widened:", len(orig))


if __name__ == "__main__":
    main()
