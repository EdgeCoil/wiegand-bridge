# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""Frozen routing (added 2026-10-27): Freerouting gives a different layout on every run, so once a
routed board has been reviewed its copper is recorded and every later build replays it. A fix is
then a small, reviewable edit to routing.json, not a new layout to review from scratch.

    python3 freeze.py save      # after the full post-route pipeline: record every track and via
    python3 freeze.py replay    # after build_pcb.py: lay the recorded copper back, rebuild the pours

Then run dfm_post.py and the checks as after routing. route.py is still how a board is routed
afresh (when placement changes); freeze.py save after it, and the next review covers all copper.
"""
import json
import os
import subprocess
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import route  # noqa: E402

JSON = os.path.join(HERE, "routing.json")


def save():
    board = pcbnew.LoadBoard(route.PCB)
    items = []
    for t in board.GetTracks():
        lk = t.IsLocked()
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            items.append({"net": t.GetNetname(), "via": [p.x, p.y], "d": t.GetWidth(pcbnew.F_Cu),
                          "drill": t.GetDrillValue(), "locked": lk})
        else:
            a, b = t.GetStart(), t.GetEnd()
            items.append({"net": t.GetNetname(), "layer": board.GetLayerName(t.GetLayer()),
                          "start": [a.x, a.y], "end": [b.x, b.y], "w": t.GetWidth(), "locked": lk})
    items.sort(key=lambda i: (i["net"], "via" in i, json.dumps(i, sort_keys=True)))
    with open(JSON, "w") as f:
        f.write("[\n" + ",\n".join(json.dumps(i, sort_keys=True) for i in items) + "\n]\n")
    print(f"froze {len(items)} tracks and vias in {os.path.basename(JSON)}")


def replay():
    board = pcbnew.LoadBoard(route.PCB)
    if len(board.GetTracks()):
        sys.exit("board already has copper: run build_pcb.py first")
    real_via = route.via
    route.via = lambda *a, **k: None       # thermal_vias for its pad zone connections only;
    route.thermal_vias(board)              # its vias are in routing.json
    route.via = real_via
    for i in json.load(open(JSON)):
        net = board.FindNet(i["net"])
        if net is None:
            sys.exit(f"routing.json names net {i['net']!r}, which the netlist no longer has")
        if "via" in i:
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(*i["via"]))
            v.SetWidth(i["d"])
            v.SetDrill(i["drill"])
            v.SetNet(net)
            v.SetLocked(i["locked"])
            board.Add(v)
        else:
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(*i["start"]))
            t.SetEnd(pcbnew.VECTOR2I(*i["end"]))
            t.SetWidth(i["w"])
            t.SetLayer(board.GetLayerID(i["layer"]))
            t.SetNet(net)
            t.SetLocked(i["locked"])
            board.Add(t)
    route.zones(board)
    pcbnew.SaveBoard(route.PCB, board)
    print(f"replayed {len(board.GetTracks())} tracks and vias from {os.path.basename(JSON)}")
    rpt = os.path.join(route.WORK, "replay-drc.json")
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "-o", rpt, route.PCB], capture_output=True)
    n = len(json.load(open(rpt)).get("unconnected_items", []))
    print("unconnected after replay:", n, "(dfm_post.py adds the diode pours next)")


if __name__ == "__main__":
    {"save": save, "replay": replay}[sys.argv[1]]()
