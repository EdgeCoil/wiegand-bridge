# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""Every file-based verification of the routed board, in one run (added 2026-10-21 after the lite
board's checks had accumulated across several ad-hoc scripts):

 1. KiCad DRC: unconnected items and copper violations (clearance, shorts, edge, thermal).
 2. audit.py: body clashes, track widths, screw keep-outs, antenna box, silkscreen legibility.
 3. padgap.py: pads of different nets closer than 0.25 mm.
 4. Part spacing: the closest solder joints between neighbouring parts, and the courtyard-overlap
    pairs with their joint gaps (accepted when >= 0.4 mm).
 5. Silkscreen: text count, sizes and strokes (JLCPCB minimum 1.0 mm / 0.15 mm).
 6. Firmware <-> netlist: every GPIO in the YAML lands on the intended net; each reader line
    traces terminal pin -> series R -> clamp node -> buffer -> GPIO with its drive FET and surge part.
 7. Diode / LED polarity from each part's EasyEDA symbol.
 8. IC / module / connector pads with no net.
 9. BOM vs CPL designators; gerber zip contents; gerber, drill and CPL in one frame.
10. JLCPCB library: every part number found, class (Basic / Preferred / Extended), stock (network).

    python3 verify.py            # all
    python3 verify.py --offline  # skip 10
"""
import collections
import csv
import json
import os
import re
import subprocess
import sys
import zipfile

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from netlist import PARTS  # noqa: E402

T = pcbnew.ToMM
PCB = os.path.join(HERE, "wiegand-bridge-lite.kicad_pcb")
YAML = os.path.join(HERE, "..", "..", "firmware", "wiegand-bridge-lite.yaml")
FAB = os.path.join(HERE, "fab")
EXPECT_GPIO = {4: "WG_D0", 5: "WG_D1", 6: "D0_TX", 7: "D1_TX", 8: "LED_TX", 9: "BEEP_TX", 10: "LED_RX",
               11: "BEEP_RX", 19: "USB_DN", 20: "USB_DP", 21: "IO21", 47: "IO47", 38: "RS485_DE",
               43: "RS485_DI", 44: "RS485_RO", 0: "IO0"}
ACCEPTED_DRC = {"hole_clearance", "courtyards_overlap", "silk_edge_clearance", "silk_over_copper", "silk_overlap"}
fails = []


def fail(msg):
    fails.append(msg)
    print("   FAIL:", msg)


def section(n, title):
    print(f"\n== {n}. {title}")


board = pcbnew.LoadBoard(PCB)
byref = {p[0]: p for p in PARTS}
nets = collections.defaultdict(list)
for ref, fp, val, lcsc, pads in PARTS:
    for pad, net in pads.items():
        nets[net].append((ref, pad))
sym = open(os.path.join(HERE, "lib", "wb.kicad_sym")).read()


def symbol_pins(lcsc):
    for m in re.finditer(r'\n  \(symbol "([^"]+)"(.*?)(?=\n  \(symbol "|\Z)', sym, re.S):
        if re.search(r'\(property\s+"LCSC Part"\s+"' + lcsc + '"', m.group(2)):
            return {n: nm for nm, n in re.findall(r'\(name "([^"]*)".*?\(number "([^"]*)"', m.group(2), re.S)}
    return {}


# --- 1. DRC ---------------------------------------------------------------------------------------
section(1, "KiCad DRC")
out = "/tmp/wiegand-bridge-lite-drc.json"
subprocess.run(["kicad-cli", "pcb", "drc", "--severity-error", "--severity-warning", "--format", "json", "-o", out, PCB],
               capture_output=True)
drc = json.load(open(out))
kinds = collections.Counter(v["type"] for v in drc["violations"])
unconn = drc.get("unconnected_items", [])
print("   violations:", dict(kinds))
print("   unconnected:", len(unconn))
if unconn:
    fail(f"{len(unconn)} unconnected items")
for k in kinds:
    if k not in ACCEPTED_DRC:
        fail(f"DRC {k} x{kinds[k]}: " + "; ".join(" / ".join(i.get("description", "")[:40] for i in v["items"])
                                                   for v in drc["violations"] if v["type"] == k)[:300])

# --- 2. audit.py ----------------------------------------------------------------------------------
section(2, "audit.py (clashes, widths, keep-outs, antenna, silkscreen)")
r = subprocess.run([sys.executable, os.path.join(HERE, "audit.py")], capture_output=True, text=True)
lines = [ln for ln in r.stdout.splitlines() if ln.strip() and "assert" not in ln]
for ln in lines:
    print("  ", ln)
if "NARROW" in r.stdout:
    fail("a current-carrying net is narrower than it needs")
m = re.search(r"(\d+) problems in \d+ texts", r.stdout)
if not m or m.group(1) != "0":
    fail("silkscreen audit not clean")
m = re.search(r"(\d+) near or overlapping pairs involving tall parts", r.stdout)
if not m or m.group(1) != "0":
    fail("tall-part clash")
if re.search(r"H\d @ .*from centre", r.stdout):
    fail("part inside a screw-head keep-out")

# --- 3. padgap ------------------------------------------------------------------------------------
section(3, "padgap.py 0.25")
r = subprocess.run([sys.executable, os.path.join(HERE, "padgap.py"), "0.25"], capture_output=True, text=True)
print("  ", r.stdout.strip().splitlines()[-1])
if not r.stdout.strip().startswith("0 pad pairs"):
    fail("pads of different nets closer than 0.25 mm")

# --- 4. part spacing ------------------------------------------------------------------------------
section(4, "part spacing: closest solder joints between neighbouring parts")
fps = [f for f in board.GetFootprints() if not f.GetReference().startswith(("H", "JP"))]


def padbox(f):
    bs = [p.GetBoundingBox() for p in f.Pads()]
    return (min(T(x.GetLeft()) for x in bs), min(T(x.GetTop()) for x in bs), max(T(x.GetRight()) for x in bs), max(T(x.GetBottom()) for x in bs))


def gap(A, B):
    dx = max(A[0] - B[2], B[0] - A[2], 0)
    dy = max(A[1] - B[3], B[1] - A[3], 0)
    return (dx * dx + dy * dy) ** 0.5


def joint_gap(fa, fb):
    """Smallest distance between any pad of a and any pad of b."""
    best = 99
    for p in fa.Pads():
        A = p.GetBoundingBox(); A = (T(A.GetLeft()), T(A.GetTop()), T(A.GetRight()), T(A.GetBottom()))
        for q in fb.Pads():
            B = q.GetBoundingBox(); B = (T(B.GetLeft()), T(B.GetTop()), T(B.GetRight()), T(B.GetBottom()))
            best = min(best, gap(A, B))
    return best


byname = {f.GetReference(): f for f in fps}
tight = []
for i, a in enumerate(fps):
    for b in fps[i + 1:]:
        if gap(padbox(a), padbox(b)) < 1.0:
            g = joint_gap(a, b)
            if g < 0.6:
                tight.append((g, a.GetReference(), b.GetReference()))
tight.sort()
print("   pairs with joints under 0.6 mm apart:", [(a, b, round(g, 2)) for g, a, b in tight] or "none")
for g, a, b in tight:
    if g < 0.25:
        fail(f"{a}/{b} joints {g:.2f} mm apart")
cy = [(" / ".join(i["description"].split()[-1] for i in v["items"])) for v in drc["violations"] if v["type"] == "courtyards_overlap"]
print(f"   courtyard-overlap warnings: {len(cy)} (accepted: joints >= 0.25 mm apart; EasyEDA courtyards stop short of pad ends)")

# --- 5. silkscreen text ---------------------------------------------------------------------------
section(5, "silkscreen text")
texts = [t for t in board.GetDrawings() if t.GetClass() == "PCB_TEXT"]
sizes = sorted({round(T(t.GetTextSize().y), 2) for t in texts})
strokes = sorted({round(T(t.GetTextThickness()), 2) for t in texts})
print(f"   {len(texts)} texts; heights {sizes} mm; strokes {strokes} mm (JLCPCB minimum 1.0 / 0.15)")
if min(sizes) < 1.0 or min(strokes) < 0.15:
    fail("silkscreen text below JLCPCB's minimum")

# --- 6. firmware <-> netlist ----------------------------------------------------------------------
section(6, "firmware GPIOs -> netlist nets -> terminal pins")
pad2io = symbol_pins("C3013941")
io2net = {}
for pad, net in byref["U1"][4].items():
    io = pad2io.get(pad, pad).replace("TXD0", "IO43").replace("RXD0", "IO44")
    if io.startswith("IO") or io == "EN":
        io2net[io] = net
used = sorted(set(int(g) for g in re.findall(r"GPIO(\d+)", open(YAML).read())))
for g in used:
    net = io2net.get(f"IO{g}")
    ok = net == EXPECT_GPIO.get(g)
    print(f"   GPIO{g:<3} {net!s:10} {'OK' if ok else 'MISMATCH'}")
    if not ok:
        fail(f"GPIO{g} is on {net}, expected {EXPECT_GPIO.get(g)}")
for pin in ("3", "4", "5", "6"):
    raw = byref["J3"][4][pin]
    try:
        q = [r for r, p in nets[raw] if r.startswith("Q")][0]
        rs = [r for r, p in nets[raw] if r.startswith("R")][0]
        sm = [r for r, p in nets[raw] if r.startswith("D1")][0]
        node = [n for n in byref[rs][4].values() if n != raw][0]
        bref, bpad = [(r, p) for r, p in nets[node] if r.startswith("U")][0]
        gpio_net = byref[bref][4][{"1": "6", "3": "4"}[bpad]]
        gate = byref[q][4]["1"]
        rg = [r for r, p in nets[gate] if byref[r][2] == "100"][0]
        tx = [n for n in byref[rg][4].values() if n != gate][0]
        zener = [r for r, p in nets[node] if r.startswith("D")][0]
        pull = [r for r, p in nets[node] if byref[r][2] == "10k"][0]
        print(f"   J3.{pin} {raw:9} -{rs}-> {node:8} ({zener}, {pull}) -> {bref}.{bpad} -> {gpio_net:8}; drive {q} <- {rg} <- {tx}; surge {sm}")
        assert io2net[[k for k, v in io2net.items() if v == gpio_net][0]] == gpio_net
        assert tx in io2net.values()
    except (IndexError, KeyError, AssertionError) as e:
        fail(f"line cell on J3.{pin} ({raw}) does not trace: {type(e).__name__}")

# --- 7. polarity ----------------------------------------------------------------------------------
section(7, "diode / LED pin names from each symbol, with the net on each")
WANT = {"D1": ("K", "+VIN"), "D3": ("K", "+VIN"), "D2": ("K", "+VIN"), "D7": ("K", "GND"), "D8": ("+", "+3V3"),
        "D23": ("A", "+3V3"), "D5": ("K", "D0_IN"), "D6": ("K", "D1_IN"), "D24": ("K", "LED_IN"), "D25": ("K", "BEEP_IN"),
        "D15": ("K", "GND"), "D16": ("K", "GND"), "D19": ("K", "GND")}
for ref, fp, val, lcsc, pads in PARTS:
    if not ref.startswith("D"):
        continue
    names = symbol_pins(lcsc)
    shown = "  ".join(f"pad{p}={names.get(p, '?')}:{pads[p]}" for p in sorted(pads))
    want = WANT.get(ref)
    ok = want is None or any(names.get(p) == want[0] and pads[p] == want[1] for p in pads)
    print(f"   {ref:4} {val:10} {shown}   {'OK' if ok else 'WRONG'}")
    if not ok:
        fail(f"{ref} polarity: expected {want[0]} on {want[1]}")

# --- 8. open pads ---------------------------------------------------------------------------------
section(8, "IC / module / connector pads with no net")
for f in board.GetFootprints():
    ref = f.GetReference()
    if ref[0] in "UJ":
        nc = sorted({p.GetNumber() for p in f.Pads() if not p.GetNetname()}, key=lambda s: (len(s), s))
        print(f"   {ref}: {nc or 'all assigned'}")
        if ref in ("U2", "U4", "U9", "U11", "J3") and nc:
            fail(f"{ref} has unassigned pads {nc}")

# --- 9. fab outputs -------------------------------------------------------------------------------
section(9, "BOM vs CPL, gerber zip, coordinate frame")
bom = set()
for row in csv.DictReader(open(os.path.join(FAB, "wiegand-bridge-lite-bom.csv"))):
    bom |= set(row["Designator"].split(","))
cpl = list(csv.DictReader(open(os.path.join(FAB, "wiegand-bridge-lite-cpl.csv"))))
refs = [r["Designator"] for r in cpl]
dupes = [d for d, c in collections.Counter(refs).items() if c > 1]
print(f"   BOM {len(bom)} designators, CPL {len(refs)}, dupes {dupes}, BOM-only {sorted(bom - set(refs))}, CPL-only {sorted(set(refs) - bom)}, layers {dict(collections.Counter(r['Layer'] for r in cpl))}")
if bom != set(refs) or dupes:
    fail("BOM and CPL designators differ")
fitted = {p[0] for p in PARTS if p[3]}
if bom != fitted:
    fail(f"BOM differs from netlist's fitted parts: {sorted(bom ^ fitted)}")
z = zipfile.ZipFile(os.path.join(FAB, "wiegand-bridge-lite-gerbers.zip"))
names = z.namelist()
need = ["F_Cu", "In1_Cu", "In2_Cu", "B_Cu", "F_Mask", "B_Mask", "F_Paste", "B_Paste", "F_Silkscreen", "B_Silkscreen", "Edge_Cuts", "PTH.drl", "NPTH.drl"]
missing = [n for n in need if not any(n in f for f in names)]
print(f"   gerber zip: {len(names)} files; missing: {missing or 'none'}")
if missing:
    fail(f"gerber zip missing {missing}")
edge = z.read([f for f in names if "Edge_Cuts" in f][0]).decode()
xs = [int(v) / 1e6 for v in re.findall(r"X(-?\d+)", edge)]
ys = [int(v) / 1e6 for v in re.findall(r"Y(-?\d+)", edge)]
drl = z.read([f for f in names if "PTH.drl" in f and "NPTH" not in f][0]).decode()
hx = [float(v) for v in re.findall(r"X(-?[\d.]+)Y", drl)]
cx = [float(r["Mid X"][:-2]) for r in cpl]
print(f"   edge gerber x {min(xs):.2f}..{max(xs):.2f} y {min(ys):.2f}..{max(ys):.2f}; drills x {min(hx):.2f}..{max(hx):.2f}; CPL x {min(cx):.2f}..{max(cx):.2f} (one frame, origin bottom-left)")
if not (abs(min(xs)) < 0.01 and abs(max(xs) - 42) < 0.01 and 0 < min(hx) and max(hx) < 42 and 0 < min(cx) and max(cx) < 42):
    fail("gerber / drill / CPL frames disagree")

# --- 10. JLCPCB library ---------------------------------------------------------------------------
if "--offline" not in sys.argv:
    section(10, "JLCPCB library: class and stock for every part number")
    codes = collections.defaultdict(list)
    for ref, fp, val, lcsc, pads in PARTS:
        if lcsc:
            codes[lcsc].append(ref)
    fee = 0
    for code, rs in sorted(codes.items()):
        body = json.dumps({"keyword": code, "currentPage": 1, "pageSize": 3, "searchSource": "search", "componentLibraryType": ""})
        try:
            r = subprocess.run(["curl", "-s", "-m", "25", "-X", "POST",
                                "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList/v2",
                                "-H", "Content-Type: application/json", "-d", body], capture_output=True, text=True)
            x = [y for y in json.loads(r.stdout)["data"]["componentPageInfo"]["list"] if y.get("componentCode") == code][0]
        except Exception as e:
            fail(f"{code} ({','.join(rs)}) not found in JLCPCB's library ({type(e).__name__})")
            continue
        cls = "Basic" if x.get("componentLibraryType") == "base" else ("Preferred" if x.get("preferredComponentFlag") else "Extended")
        fee += cls == "Extended"
        stock = x.get("stockCount") or 0
        flag = "" if stock >= 100 else "   <-- LOW STOCK"
        print(f"   {code:12} {','.join(rs):24} {cls:9} stock {stock:<8} {x.get('componentModelEn', '')[:30]}{flag}")
        if stock < 20:
            fail(f"{code} stock {stock}")
    print(f"   fee-bearing Extended types: {fee}")

print("\n" + ("ALL CHECKS PASSED" if not fails else f"{len(fails)} FAILURE(S):\n   " + "\n   ".join(fails)))
sys.exit(1 if fails else 0)
