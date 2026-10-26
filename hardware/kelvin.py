# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""Kelvin check for the reader monitor's shunt (rev 12, audit round 1).

U12's IN+ / IN- must reach R59 on copper of their own: if load current shared a sense track, that
copper's resistance would add to the shunt's (rev 12's first route had 3 mm of 0.6 mm track inside the
IN+ loop, +2.2 % gain). The board makes this structural: R59's footprint has a small sense pad inside
each land (pads 3/4, net-tied to 1/2), and the sense pins are on their own nets. This checks that the
structure is intact:
  - R59's footprint ties 1-3 and 2-4, and each sense tab overlaps its land;
  - ISNS_P / ISNS_N each join exactly two pads, U12's sense pin and R59's sense pad;
  - no track or via of a power net touches a sense pad except through its own land.

    python3 kelvin.py          # exit 1 on a violation
"""
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "wiegand-bridge.kicad_pcb")
WANT = {"ISNS_P": {("U12", "10"), ("R59", "3")}, "ISNS_N": {("U12", "9"), ("R59", "4")}}
TIE = {"3": "1", "4": "2"}


def main():
    board = pcbnew.LoadBoard(PCB)
    fails = []
    r59 = board.FindFootprintByReference("R59")
    # the SWIG binding returns an opaque vector here, so read the groups from the saved board
    import re
    txt = open(PCB).read()
    i = txt.index('(property "Reference" "R59"')
    j = txt.rindex("(footprint ", 0, i)
    k = txt.find("\n\t(footprint ", i)
    m = re.search(r'\(net_tie_pad_groups((?:\s+"[^"]*")+)\)', txt[j:k if k > 0 else len(txt)])
    groups = [g.replace(" ", "") for g in re.findall(r'"([^"]*)"', m.group(1))] if m else []
    if sorted(groups) != ["1,3", "2,4"]:
        fails.append(f"R59 net-tie groups are {groups}, want ['1,3', '2,4']")
    pads = {p.GetNumber(): p for p in r59.Pads()}
    for s, land in TIE.items():
        sb, lb = pads[s].GetBoundingBox(), pads[land].GetBoundingBox()
        if not sb.Intersects(lb):
            fails.append(f"R59 sense pad {s} does not overlap land {land}")
    for net, want in WANT.items():
        have = {(p.GetParentFootprint().GetReference(), p.GetNumber())
                for f in board.GetFootprints() for p in f.Pads() if p.GetNetname() == net}
        if have != want:
            fails.append(f"{net} joins {sorted(have)}, want {sorted(want)}")
    for t in board.GetTracks():
        if t.GetNetname() in WANT:
            continue
        for s in TIE:
            p = pads[s]
            pts = [t.GetPosition()] if t.GetClass() == "PCB_VIA" else [t.GetStart(), t.GetEnd()]
            if any(p.HitTest(q) for q in pts):
                fails.append(f"{t.GetNetname()} copper ends on R59 sense pad {s}")
    for f in fails:
        print("NOT KELVIN:", f)
    if not fails:
        print("Kelvin OK: ISNS_P = U12.10 + R59.3, ISNS_N = U12.9 + R59.4, sense tabs on their net-tied lands")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
