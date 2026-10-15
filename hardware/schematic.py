# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""Readable schematic PDF generated from netlist.py: one page per circuit block (netlistsvg, analog skin).

The board is built from code, so there is no hand-drawn schematic. This draws each block of
netlist.py: resistors/capacitors/inductors/diodes as symbols, ICs/transistors/connectors as labelled
boxes with their pin names (from the JLCPCB/EasyEDA symbols in lib/wb.kicad_sym), supply nets as
power flags, and nets shared with other blocks as named ports.

    python3 schematic.py        # -> fab/wiegand-bridge-schematic.pdf
Needs: netlistsvg 1.0.2 in ~/.local/share/netlistsvg, rsvg-convert, pdfunite.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NSV = os.path.expanduser("~/.local/share/netlistsvg/node_modules/netlistsvg")
WORK = os.path.join(HERE, "fab", "schematic")
POWER = {"GND", "+3V3", "+5V", "+5V_BUCK", "VSYS", "+VIN", "+VIN_F", "+VIN_RAW", "VBUS", "BAT+", "BAT-",
         "+12V_RDR", "BOOST_OUT", "RDR_GND"}

# --- 1. parts per block, by instrumenting netlist.py's part() ------------------------------------
src = open(os.path.join(HERE, "netlist.py")).read()
lines = src.split("\n")
block_at = []
cur = "Header"
for ln in lines:
    m = re.match(r"# --- (.*?) -{3,}", ln)
    if m:
        cur = m.group(1).strip()
    block_at.append(cur)
records = []


def recording_part(ref, fp, value, lcsc, pads):
    f = sys._getframe(1)
    while f and not (f.f_code.co_filename == "netlist.py" and f.f_code.co_name == "<module>"):
        f = f.f_back
    line = f.f_lineno if f else 0
    records.append((block_at[line - 1] if line else "?", ref, fp, value, lcsc, pads))


# run netlist.py once, line numbers intact, with part() replaced by the recorder
ns = {"__name__": "netlist_for_schematic", "part": recording_part}
exec(compile(src.replace("\ndef part(", "\ndef _unused_part("), "netlist.py", "exec"), ns)

# --- 2. pin names from the EasyEDA symbols -------------------------------------------------------
sym = open(os.path.join(HERE, "lib", "wb.kicad_sym")).read()
pin_names = {}
for m in re.finditer(r'\n  \(symbol "([^"]+)"(.*?)(?=\n  \(symbol "|\Z)', sym, re.S):
    lc = re.search(r'\(property\s+"LCSC Part"\s+"([^"]*)"', m.group(2))
    if lc:
        pin_names[lc.group(1)] = {n: nm for nm, n in re.findall(r'\(name "([^"]*)".*?\(number "([^"]*)"', m.group(2), re.S)}

# --- 3. one netlistsvg module per block -----------------------------------------------------------
net_blocks = {}
for blk, ref, fp, value, lcsc, pads in records:
    for n in pads.values():
        net_blocks.setdefault(n, set()).add(blk)


def two_pin_type(ref, fp, value, lcsc):
    if fp.startswith(("r0603", "r1206")):
        return "r_v", ("A", "B")
    if fp.startswith("c0"):
        return "c_v", ("A", "B")
    if fp.startswith("c1206"):
        return "c_v", ("A", "B")
    if fp.startswith("ind"):
        return "l_v", ("A", "B")
    return None, None


def diode(ref, fp, value, lcsc, pads):
    names = pin_names.get(lcsc, {})
    kind = "d_led_v" if fp.startswith("led") else ("d_sk_v" if value.startswith("SS") else "d_v")
    conn = {}
    for num, net in pads.items():
        nm = names.get(num, "K" if num == "1" else "A")
        conn["-" if nm in ("K", "-") else "+"] = net
    return kind, conn


os.makedirs(WORK, exist_ok=True)
pages = []
order = []
for blk, *_ in records:
    if blk not in order:
        order.append(blk)
for bi, blk in enumerate(order):
    nid = [10]
    ids = {}

    def net_id(name):
        if name not in ids:
            nid[0] += 1
            ids[name] = nid[0]
        return ids[name]
    cells, ports = {}, {}

    def power_flag(net):
        nid[0] += 1
        cells[f"{net}#{nid[0]}"] = {"type": "gnd" if net == "GND" else "vcc", "port_directions": {"A": "input"},
                                    "connections": {"A": [nid[0]]}, "attributes": {"name": net}}
        return nid[0]

    def bit(net):
        if net in POWER:
            return power_flag(net)
        if len(net_blocks[net]) > 1 and net not in ports:
            ports[net] = {"direction": "input", "bits": [net_id(net)]}
        return net_id(net)
    for b2, ref, fp, value, lcsc, pads in records:
        if b2 != blk:
            continue
        t, pins = two_pin_type(ref, fp, value, lcsc)
        if t and len(pads) == 2:
            cells[ref] = {"type": t, "port_directions": {pins[0]: "input", pins[1]: "output"},
                          "connections": {pins[0]: [bit(pads["1"])], pins[1]: [bit(pads["2"])]},
                          "attributes": {"ref": ref, "value": value}}
            continue
        if fp.startswith(("sma", "sod", "led")) and len(pads) == 2:
            kind, conn = diode(ref, fp, value, lcsc, pads)
            cells[ref] = {"type": kind, "port_directions": {"+": "input", "-": "output"},
                          "connections": {k: [bit(v)] for k, v in conn.items()},
                          "attributes": {"ref": ref, "value": value}}
            continue
        names = pin_names.get(lcsc, {})
        conn, dirs = {}, {}
        items = sorted(pads.items(), key=lambda kv: (len(kv[0]), kv[0]))
        for k, (num, net) in enumerate(items):
            label = f"{names.get(num, num)}.{num}" if names.get(num) and names.get(num) != num else num
            while label in conn:
                label += "'"
            conn[label] = [bit(net)]
            dirs[label] = "input" if k < (len(items) + 1) // 2 else "output"
        if conn:
            cells[ref] = {"type": f"{ref} {value}", "port_directions": dirs, "connections": conn,
                          "attributes": {"ref": ref, "value": value}}
    mod = {"modules": {re.sub(r"[^A-Za-z0-9]+", "_", blk): {"ports": ports, "cells": cells}}}
    jp = os.path.join(WORK, f"{bi:02d}.json")
    sp = os.path.join(WORK, f"{bi:02d}.svg")
    json.dump(mod, open(jp, "w"), indent=1)
    r = subprocess.run(["node", os.path.join(NSV, "bin", "netlistsvg.js"), jp, "-o", sp, "--skin",
                        os.path.join(NSV, "lib", "analog.svg")], capture_output=True, text=True)
    if r.returncode:
        print("netlistsvg failed on", blk, r.stderr[-300:])
        continue
    pdf = os.path.join(WORK, f"{bi:02d}.pdf")
    subprocess.run(["rsvg-convert", "-f", "pdf", "-b", "white", "-o", pdf, sp], check=True)
    pages.append((blk, pdf))
    print(f"{bi:02d} {blk}: {len(cells)} cells, {len(ports)} ports")

# --- 4. cover page listing the blocks, then concatenate ------------------------------------------
cover = os.path.join(WORK, "cover.svg")
rows = "".join(f'<text x="40" y="{150 + 26 * i}" font-size="16" font-family="sans-serif">{i + 1}. '
               f'{b.replace("&", "&amp;")}</text>' for i, (b, _) in enumerate(pages))
open(cover, "w").write(f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="{220 + 26 * len(pages)}">'
                       f'<rect width="100%" height="100%" fill="white"/>'
                       f'<text x="40" y="60" font-size="28" font-family="sans-serif" font-weight="bold">'
                       f'Wiegand reader bridge — revision 10 schematic</text>'
                       f'<text x="40" y="95" font-size="14" font-family="sans-serif">Generated from netlist.py '
                       f'(netlistsvg). Supply nets are flags; nets shared between blocks are named ports. '
                       f'IC pins are shown as name.number.</text>{rows}</svg>')
subprocess.run(["rsvg-convert", "-f", "pdf", "-o", cover.replace(".svg", ".pdf"), cover], check=True)
out = os.path.join(HERE, "fab", "wiegand-bridge-schematic.pdf")
subprocess.run(["pdfunite", cover.replace(".svg", ".pdf")] + [p for _, p in pages] + [out], check=True)
print("wrote", out, len(pages) + 1, "pages")
