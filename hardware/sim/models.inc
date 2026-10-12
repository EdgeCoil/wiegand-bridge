* Generic models -- close enough to the datasheet figures for logic-level questions, not for loss.
.model DZ5V1 D(Is=1e-12 Rs=8 N=1.5 BV=5.1 IBV=5m)          ; MMSZ5231B / 1N5231B
.model SS34  D(Is=5e-6 Rs=0.03 N=1.1 BV=40 IBV=0.5m Cjo=200p) ; Schottky, ~0.4 V at 1 A
.model N7002 NMOS(Level=1 Vto=2.1 Kp=0.25 Lambda=0.01)    ; 2N7002, Vth 1-2.5 V
.model P3401 PMOS(Level=1 Vto=-0.9 Kp=6 Lambda=0.01)      ; AO3401A, Vth -0.5..-1.3 V
* revision 10
* SM712 channel: asymmetric TVS, ~13.3 V breakdown positive, ~7.5 V negative (to GND)
.subckt SM712CH line gnd
* two back-to-back junctions: off between about -7.5 V and +13.3 V
D1 mid line DSM712P
D2 mid gnd DSM712N
.ends
.model DSM712P D(Is=1e-12 N=1 BV=13.3 IBV=1m Rs=0.5)
.model DSM712N D(Is=1e-12 N=1 BV=7.5 IBV=1m Rs=0.5)
* LMV321 as a behavioural rail-to-rail op-amp on 3.3 V (gain 1e5, output clamped 0.01..3.29 V)
.subckt OPA inp inn out vcc gnd
B1 out gnd V = max(0.01, min(3.29, 1e5*(V(inp)-V(inn))))
.ends
