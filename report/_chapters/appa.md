
---

# Appendix A — Bill of Materials and Costing

Prices are indicative Hong Kong retail/mail-order in HK$ and exclude shipping, the bench supply, and the
host computer. The cost target is N1: **≤ HK$500**.

## A.1 Milestone 1 — the probe

| # | Item | Spec | Qty | Unit HK$ | Ext HK$ | Note |
|---|---|---|---|---|---|---|
| 1 | ESP32 development board | ESP32-WROOM-32 / DevKitC, 240 MHz, 4 MB flash | 1 | 45 | 45 | Edge node |
| 2 | I2S MEMS microphone module | ICS-43434 or INMP441 breakout | 1 | 25 | 25 | **Primary sensor** |
| 3 | Accelerometer module | MPU6050 / GY-521 | 1 | 15 | 15 | Supervisory channel only |
| 4 | Push–pull solenoid | LSD-1040B, DC 12 V, ~23 W, intermittent duty | 1 | 55 | 55 | Striker |
| 5 | Logic-level N-MOSFET | IRLZ44N (or equivalent, R_DS(on) specified at 4.5 V) | 1 | 6 | 6 | Coil driver |
| 6 | Flyback diode | 1N5822 Schottky, ≥3 A | 1 | 2 | 2 | **Mandatory** |
| 7 | Bulk capacitor | 470 µF, ≥25 V electrolytic | 1 | 3 | 3 | Rail reservoir |
| 8 | Resistors | 220 Ω gate, 10 kΩ pulldown | 2 | 1 | 2 | Gate network |
| 9 | Baseplate | 6 mm cast acrylic, 120 × 80 mm | 1 | 20 | 20 | Machined |
| 10 | Contact feet | Hardened steel hemispheres, 3 mm protrusion, 60 mm circle | 3 | 8 | 24 | Defines contact geometry |
| 11 | Compliant washers | Silicone, for solenoid mount | 4 | 1 | 4 | Reduces reaction impulse |
| 12 | Microphone gasket | 1 mm silicone sheet | 1 | 5 | 5 | Seals the cavity |
| 13 | Striking cap | Interchangeable, POM and steel set | 2 | 5 | 10 | Sets contact time (§5.6, C.3a) |
| 14 | 12 V regulated supply | 12 V 2 A adapter (bench) | 1 | 35 | 35 | Not for field use |
| 15 | Connectors, wire, screws, heat-shrink | — | — | 25 | 25 | Sundries |
| | **Subtotal, electronics and mechanics** | | | | **HK$276** | |

## A.2 Reference and validation materials (not part of the instrument cost)

| # | Item | Spec | Qty | Ext HK$ | Note |
|---|---|---|---|---|---|
| 16 | Bonded reference panel | Render on concrete, fully bonded | 1 | 60 | Calibration baseline |
| 17 | Graded debond panels | Render with compliant interlayer at 10 / 20 / 30 cm | 3 | 180 | Validation set |
| 18 | Fully debonded panel | Render on released substrate | 1 | 60 | Ground truth |
| 19 | Interlayer shim stock | Foam and sand sheets, thicknessed | — | 40 | Defect fabrication |
| 20 | Steel block, lapped face | ≥100 mm thick | 1 | 120 | Probe self-check (C.2, C.3c) |
| 21 | Piezo film sensor | For contact-time measurement | 1 | 35 | Bench characterisation |
| | **Subtotal, validation** | | | **HK$495** | Separate from N1 |

## A.3 Milestone 2 — the gateway (specified, not built)

| # | Item | Spec | Qty | Ext HK$ | Note |
|---|---|---|---|---|---|
| 22 | Single-board computer | Raspberry Pi 4/5, 2 GB | 1 | 450 | ESP-NOW concentrator + local broker |
| 23 | microSD | 32 GB, high-endurance | 1 | 60 | Store-and-forward |
| 24 | Enclosure and PSU | IP-rated case, 5 V 3 A | 1 | 150 | Field gateway |
| | **Subtotal, gateway** | | | **HK$660** | Completes MILO *b*'s gateway requirement |

## A.4 Costing observation

The instrument is **HK$276**, against the comparison set in §2.2 — HK$10 k–100 k for a commercial
impact-echo unit, HK$30 k–300 k for thermography, HK$100 k+ for LDV. That is the comparison that
justifies the modality choice: the project is not competing on sensitivity, where it loses to every
alternative, but on **cost and deployability**, where it wins by two orders of magnitude. The
validation set (HK$495) costs more than the instrument, which is itself worth noting: the reference
panels are the expensive part, and any deployment plan should budget for them rather than treating
calibration as free.
