# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""List GND copper fragments not connected to the In1 plane (own connectivity: KiCad's ratsnest isn't
reachable from Python). Prints each orphan component's layer, bbox, area and any pads it holds."""
import pcbnew

T = pcbnew.ToMM
nodes, parent = [], {}


def analyse(b):
    """Returns (main_items, orphan_report): GND tracks/vias/pads connected to the main In1 plane."""
    global parent
    parent = {}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x


    def union(a, c):
        parent[find(a)] = find(c)


    frags = []
    for z in b.Zones():
        if z.GetNetname() != "GND":
            continue
        L = z.GetLayer()
        fill = z.GetFilledPolysList(L)
        for k in range(fill.OutlineCount()):
            key = ("frag", L, len(frags))
            frags.append((key, L, fill.Outline(k)))
            parent[key] = key
    items = []
    for t in b.GetTracks():
        if t.GetNetname() != "GND":
            continue
        key = ("trk", t.m_Uuid.AsString())
        parent[key] = key
        items.append((key, t))
    pads = []
    for f in b.GetFootprints():
        for p in f.Pads():
            if p.GetNetname() == "GND":
                key = ("pad", f.GetReference() + "." + p.GetNumber())
                parent[key] = key
                pads.append((key, p))


    def layers_of(obj):
        if obj.GetClass() == "PCB_VIA" or (hasattr(obj, "GetDrillSize") and obj.GetDrillSize().x > 0):
            return None                       # all layers
        return {obj.GetLayer()} if obj.GetClass() != "PAD" else {L for L in (pcbnew.F_Cu, pcbnew.B_Cu) if obj.IsOnLayer(L)}


    for key, L, poly in frags:
        for k2, t in items:
            if t.GetClass() == "PCB_VIA":
                if poly.PointInside(t.GetPosition()):
                    union(key, k2)
            elif t.GetLayer() == L and (poly.PointInside(t.GetStart()) or poly.PointInside(t.GetEnd())):
                union(key, k2)
        for k2, p in pads:
            ls = layers_of(p)
            if (ls is None or L in ls) and poly.PointInside(p.GetPosition()):
                union(key, k2)
    for k1, t in items:                       # track/via/pad endpoint contacts
        pts = [t.GetPosition()] if t.GetClass() == "PCB_VIA" else [t.GetStart(), t.GetEnd()]
        for k2, p in pads:
            if any(p.HitTest(q) for q in pts):
                union(k1, k2)
        for k2, u in items:
            if k1 < k2:
                qs = [u.GetPosition()] if u.GetClass() == "PCB_VIA" else [u.GetStart(), u.GetEnd()]
                if any((a - c).EuclideanNorm() < 1000 for a in pts for c in qs):
                    union(k1, k2)
    main = max((f for f in frags if f[1] == pcbnew.In1_Cu), key=lambda f: abs(f[2].Area()))[0]
    root = find(main)
    orph = {}
    for key, L, poly in frags:
        if find(key) != root:
            orph.setdefault(find(key), []).append((L, poly))
    for r, fl in orph.items():
        for L, poly in fl:
            bb = poly.BBox()
            held = [k[1] for k, p in pads if find(k) == r]
            print(f"{b.GetLayerName(L)} orphan {abs(poly.Area()) / 1e12:.2f} mm2 at ({T(bb.GetLeft()):.1f},{T(bb.GetTop()):.1f})-({T(bb.GetRight()):.1f},{T(bb.GetBottom()):.1f}) pads {held}")
    print("orphan components:", len(orph))
    return [t for k, t in items if find(k) == root], [p for k, p in pads if find(k) == root]


if __name__ == "__main__":
    analyse(pcbnew.LoadBoard("wiegand-bridge-lite.kicad_pcb"))
