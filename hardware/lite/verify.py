# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""Every file-based verification of the routed board, in one run (added 2026-10-21 after the lite
board's checks had accumulated across several ad-hoc scripts):

 1. KiCad DRC: unconnected items and copper violations (clearance, shorts, edge, thermal).
 2. audit.py: body clashes, track widths, screw keep-outs, antenna box, silkscreen legibility.
 3. padgap.py: pads of different nets closer than 0.25 mm.
 4. Part spacing: the closest solder joints between neighbouring parts, and the courtyard-overlap
    pairs with their joint gaps (accepted when >= 0.25 mm).
 5. Silkscreen: text count, sizes and strokes (JLCPCB minimum 1.0 mm / 0.15 mm).
 6. Firmware <-> netlist: every GPIO in the YAML (and its packages) lands on the intended net, and
    every GPIO the netlist wires is claimed by the YAML; each reader line traces terminal pin ->
    series R -> clamp node -> buffer -> GPIO with its drive FET and surge part.
 7. Diode / LED polarity from each part's EasyEDA symbol.
 8. IC / module / connector pads with no net (the module's open pads must be exactly the planned set).
 9. BOM vs CPL designators; gerber zip contents; gerber, drill and CPL in one frame (both axes).
10. gndcheck.py: every GND pad on the plane; orphan pour islands reported.
11. The antenna keep-out rule area exists and the strip under it holds no copper on any layer.
12. JLCPCB library: every part number found, class (Basic / Preferred / Extended), stock; the
    fee-bearing set must match FEE_BEARING, so the guide's cost table stays true (network).

    python3 verify.py            # all
    python3 verify.py --offline  # skip 12
"""
import collections
import csv
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from netlist import PARTS  # noqa: E402
from placement import BOARD  # noqa: E402

T = pcbnew.ToMM
PCB = os.path.join(HERE, "wiegand-bridge-lite.kicad_pcb")
YAML = os.path.join(HERE, "..", "..", "firmware", "wiegand-bridge-lite.yaml")
FAB = os.path.join(HERE, "fab")
# Every module GPIO the netlist wires, and the net it must be on. The YAML must claim each one
# (the firmware is the only thing that sets a pin's boot-time state), and must name no other.
EXPECT_GPIO = {4: "WG_D0", 5: "WG_D1", 6: "D0_TX", 7: "D1_TX", 8: "LED_TX", 9: "BEEP_TX", 10: "LED_RX",
               11: "BEEP_RX", 21: "IO21", 47: "IO47", 38: "RS485_DE", 43: "RS485_DI", 44: "RS485_RO"}
IMPLICIT_GPIO = {19: "USB_DN", 20: "USB_DP", 0: "IO0"}       # used by the USB-JTAG console and the ROM, not named in YAML
# Module pads that are meant to be open (every other U1 pad must carry a net): IO1/IO2 (5, 6), IO3 (7),
# IO12-IO18 (16-22), IO26 (26, PSRAM), IO33-IO37 and IO48 (28-33), IO39-IO42 (35-38), IO45 (41),
# IO46 (44). Pads 42/43 are GND on the module, so they are wired.
U1_OPEN = {"5", "6", "7", "16", "17", "18", "19", "20", "21", "22", "26", "28", "29", "30", "31", "32", "33",
           "35", "36", "37", "38", "41", "44"}
# JLCPCB part numbers that pay the US$3 loading fee (Extended and not Preferred), as costed in the guide.
FEE_BEARING = {"C3013941", "C780769", "C10429", "C2765186", "C305174", "C516067", "C441177"}
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
tmp = tempfile.mkdtemp(prefix="wbl-verify-")
out = os.path.join(tmp, "drc.json")
r = subprocess.run(["kicad-cli", "pcb", "drc", "--severity-error", "--severity-warning", "--format", "json", "-o", out, PCB],
                   capture_output=True, text=True)
if r.returncode or not os.path.exists(out):
    sys.exit("kicad-cli pcb drc failed:\n" + r.stdout + r.stderr)
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
pad2io = symbol_pins(byref["U1"][3])
io2net = {}
for pad, net in byref["U1"][4].items():
    io = pad2io.get(pad, pad).replace("TXD0", "IO43").replace("RXD0", "IO44")
    if io.startswith("IO") or io == "EN":
        io2net[io] = net
ytext = open(YAML).read()
for inc in re.findall(r"!include\s+(\S+\.yaml)", ytext):        # packages, whether or not commented out
    ytext += open(os.path.join(os.path.dirname(YAML), inc)).read()
used = sorted(set(int(g) for g in re.findall(r"GPIO(\d+)", ytext)))
for g in used:
    net = io2net.get(f"IO{g}")
    ok = g in EXPECT_GPIO and net == EXPECT_GPIO[g]
    print(f"   GPIO{g:<3} {net!s:10} {'OK' if ok else 'MISMATCH'}")
    if not ok:
        fail(f"GPIO{g} is on {net!s}, expected {EXPECT_GPIO.get(g, 'nothing: the YAML names a GPIO the board does not wire')}")
unclaimed = sorted(set(EXPECT_GPIO) - set(used))
if unclaimed:
    fail(f"netlist wires GPIO{unclaimed} but the YAML never claims them (boot-time state undefined)")
wired = {int(k[2:]) for k in io2net if k.startswith("IO")}
unexpected = sorted(wired - set(EXPECT_GPIO) - set(IMPLICIT_GPIO))
if unexpected:
    fail(f"netlist wires GPIO{unexpected}, not in EXPECT_GPIO or IMPLICIT_GPIO")
print(f"   {len(used)} GPIOs named by the YAML; {len(wired)} wired by the netlist ({sorted(IMPLICIT_GPIO)} implicit)")
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
        if ref == "U1" and set(nc) != U1_OPEN:
            fail(f"U1 open pads differ from the plan: extra {sorted(set(nc) - U1_OPEN)}, missing {sorted(U1_OPEN - set(nc))}")
        if ref == "J1" and set(nc) != {"", "A8", "B8"}:        # "" = the two unnamed NPTH locating pegs
            fail(f"J1 open pads {nc}, expected only the SBU pair A8/B8 and the unnamed pegs")

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
hy = [float(v) for v in re.findall(r"Y(-?[\d.]+)", drl)]
cx = [float(r["Mid X"][:-2]) for r in cpl]
cy_ = [float(r["Mid Y"][:-2]) for r in cpl]
W, H = BOARD[2], BOARD[3]
print(f"   edge gerber x {min(xs):.2f}..{max(xs):.2f} y {min(ys):.2f}..{max(ys):.2f}; drills x {min(hx):.2f}..{max(hx):.2f} y {min(hy):.2f}..{max(hy):.2f}; "
      f"CPL x {min(cx):.2f}..{max(cx):.2f} y {min(cy_):.2f}..{max(cy_):.2f} (one frame {W} x {H}, origin bottom-left)")
if not (abs(min(xs)) < 0.01 and abs(max(xs) - W) < 0.01 and abs(min(ys)) < 0.01 and abs(max(ys) - H) < 0.01
        and 0 < min(hx) and max(hx) < W and 0 < min(hy) and max(hy) < H
        and 0 < min(cx) and max(cx) < W and -1 < min(cy_) and max(cy_) < H + 5):     # U1 and J3 overhang the edges
    fail("gerber / drill / CPL frames disagree")

# --- 10. ground plane -----------------------------------------------------------------------------
section(10, "gndcheck.py: GND pads on the plane, orphan pour islands")
r = subprocess.run([sys.executable, os.path.join(HERE, "gndcheck.py")], capture_output=True, text=True, cwd=HERE)
for ln in r.stdout.splitlines()[-6:]:
    print("  ", ln)
if r.returncode:
    fail("gndcheck: a GND pad is not on the plane")
m = re.search(r"orphan components: (\d+)", r.stdout)
orphans = int(m.group(1)) if m else -1
if orphans < 0:
    fail("gndcheck produced no summary")
held = re.findall(r"orphan .* pads \[([^\]]+)\]", r.stdout)
if held:
    fail(f"orphan pour islands hold pads: {held}")

# --- 11. antenna keep-out -------------------------------------------------------------------------
section(11, "antenna keep-out: rule area present, no copper under the antenna strip")
rules = [z for z in board.Zones() if z.GetIsRuleArea() and z.GetZoneName() == "antenna_keepout"]
if len(rules) != 1:
    fail(f"{len(rules)} antenna_keepout rule areas (want 1)")
else:
    rb = rules[0].GetBoundingBox()
    x1, x2, yb = T(rb.GetLeft()), T(rb.GetRight()), T(rb.GetBottom())
    print(f"   rule area x {x1:.1f}..{x2:.1f}, down to y {yb:.2f} (board top {BOARD[1]}), layers {len(rules[0].GetLayerSet().Seq())}")
    if len(rules[0].GetLayerSet().Seq()) != board.GetCopperLayerCount():
        fail("antenna keep-out is not on every copper layer")
    probes = [pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)) for x in (x1 + 0.5, (x1 + x2) / 2, x2 - 0.5)
              for y in (BOARD[1] + 0.2, yb - 0.1)]
    copper = []
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        for L in z.GetLayerSet().Seq():
            poly = z.GetFilledPolysList(L)
            if any(poly.Collide(p, 0) for p in probes):
                copper.append((z.GetNetname(), board.GetLayerName(L)))
    for t in board.GetTracks():
        if t.HitTest(pcbnew.BOX2I(pcbnew.VECTOR2I(rb.GetLeft(), pcbnew.FromMM(BOARD[1])), pcbnew.VECTOR2L(rb.GetWidth(), pcbnew.FromMM(yb - BOARD[1]))), False, 0):
            copper.append((t.GetNetname(), "track/via"))
    print(f"   copper in the strip: {copper or 'none'}")
    if copper:
        fail(f"copper under the antenna strip: {copper}")

# --- 12. JLCPCB library ---------------------------------------------------------------------------
if "--offline" not in sys.argv:
    section(12, "JLCPCB library: class and stock for every part number")
    codes = collections.defaultdict(list)
    for ref, fp, val, lcsc, pads in PARTS:
        if lcsc:
            codes[lcsc].append(ref)
    fee = 0
    fee_set = set()
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
        if cls == "Extended":
            fee_set.add(code)
        stock = x.get("stockCount") or 0
        flag = "" if stock >= 100 else "   <-- LOW STOCK"
        print(f"   {code:12} {','.join(rs):24} {cls:9} stock {stock:<8} {x.get('componentModelEn', '')[:30]}{flag}")
        if stock < 20:
            fail(f"{code} stock {stock}")
    print(f"   fee-bearing Extended types: {fee} {sorted(fee_set)}")
    if fee_set != FEE_BEARING:
        fail(f"fee-bearing set changed: now +{sorted(fee_set - FEE_BEARING)} -{sorted(FEE_BEARING - fee_set)}; update the guide's cost table and FEE_BEARING")

print("\n" + ("ALL CHECKS PASSED" if not fails else f"{len(fails)} FAILURE(S):\n   " + "\n   ".join(fails)))
sys.exit(1 if fails else 0)
