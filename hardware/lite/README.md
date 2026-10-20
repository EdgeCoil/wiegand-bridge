# Wiegand bridge LITE — board files

The small board for `docs/lite.md` (design, reasoning, what was dropped from the
full board and why). A sibling of `../` (the full board): same code-generated flow, its own
`netlist.py` and `placement.py`, and the pipeline scripts **copied and trimmed** rather than shared —
every script in the full board's tree hard-codes its board name and part references, and the live
rev 11 tree was not worth refactoring for this.

| File | What it is |
|---|---|
| `netlist.py` | **Source of truth**: every part, its JLCPCB part number and which net each pad joins |
| `placement.py` | Where each part sits (board 42 × 44 mm) |
| `build_pcb.py` | Makes `wiegand-bridge-lite.kicad_pcb`, unrouted, from the two files above |
| `route.py` | Thermal vias under the module, the USB-C VBUS pad-pair hand route, GND fan-out, Freerouting, ground pours |
| `padgap.py` | Pre-route: pads of different nets closer than 0.25 mm (new for this board) |
| `stitch.py`, `via_fix.py`, `gndcheck.py`, `dfm_post.py`, `audit.py` | Post-route, as the full board; `audit.py` has no screen/battery sections |
| `schematic.py`, `fab.py`, `finish_net.py`, `widen.py`, `plane_connect.py` | As the full board, names changed |
| `lib/`, `art/` | **Symlinks** into `../` (the full board) — one footprint library (the new parts were fetched into it) and one mark |

Differences from the full board's scripts, so a diff is not a surprise: 2 mounting holes; the
MINI-1's nine centre GND pads take the thermal vias (no exposed pads anywhere else, so `dfm_post`
has no paste windows); `route.py` pre-routes only the USB-C VBUS pair; `fab.py` has no rotation or body-centre
fixes (every footprint is EasyEDA-sourced except the 0603/0805 passives, the solder jumper and the
holes).

## Rebuild

```bash
python3 build_pcb.py                 # system python3: KiCad 9's pcbnew module
python3 audit.py --silk              # labels vs pads/outlines/bodies/edge: iterate before routing
python3 padgap.py 0.25               # pads of different nets closer than 0.25 mm: MUST be 0 before routing
ROUTE_WORK=/tmp/wbl python3 route.py 60             # 30 passes was not enough here
python3 stitch.py && python3 stitch.py --islands
python3 via_fix.py --apply && python3 via_fix.py   # the second run must report 0 vias inside pad openings
python3 gndcheck.py                  # run from this directory
python3 dfm_post.py                  # copper round D1/D3
python3 audit.py
python3 fab.py                       # NOTE: clears fab/, deleting the two PDFs below -- regenerate them
python3 schematic.py
kicad-cli pcb export pdf --layers F.Mask,F.Silkscreen,F.Courtyard,Edge.Cuts --mode-single \
    --black-and-white --ibt -o fab/wiegand-bridge-lite-1to1.pdf wiegand-bridge-lite.kicad_pcb
kicad-cli pcb drc wiegand-bridge-lite.kicad_pcb
```

**Space parts by pad extents, not courtyards.** KiCad's 0603 courtyard is 3.0 × 1.5 mm (generous)
while the EasyEDA footprints' courtyards stop short of their pad ends (the SMA, SOT-23 and TSOT pads
run up to 0.9 mm past them), so a courtyard check passed three placements whose pads overlapped and
whose routes failed on exactly those pads. `padgap.py` is the check; the 10 remaining
`courtyards_overlap` DRC warnings between cell passives are accepted (pads ≥ 0.25 mm apart).
`route.py` also pre-routes the USB-C's VBUS pad pair, which Freerouting never joins.

## Ordering at JLCPCB

Upload `fab/wiegand-bridge-lite-gerbers.zip`, choose PCB Assembly (top side), then upload the BOM
and CPL. **Check every polarised part's rotation in the CPL previewer** — the three LEDs, the four
diodes (D2 is on a reversed-pin-order SMA footprint, pad 2 = cathode), the ICs, the module, the
USB-C. The terminal J3 is through-hole: either add JLCPCB's THT assembly or leave it off the BOM
and solder it by hand. The mating plug (KF2EDGK-3.5-8P) is not on the BOM; buy it separately.
