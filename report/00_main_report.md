---
title: "The Tap Probe — A Handheld Electromagnetic Tap-Test Probe for Debonding Detection in
  External Wall Finishes"
short_title: "The Tap Probe"
subtitle: "EEE4483 Internet-of-Things Planning and Deployment — End-of-Module Assessment (Mini-project)"
author: "[STUDENT NAME] — [STUDENT ID]"
programme: "HD in Computer and Electronic Engineering (EG114403 / EG314403 / EG524403)"
institution: "Electrical and Electronic Engineering Programme Board, VTC"
date: "2026"
version: "1.0 — draft for submission"
---

# Abstract

Falling fragments of external wall finish are a recognised urban life-safety hazard in Hong Kong, and
the conventional detection method — a surveyor tapping the facade with a hammer and listening — is
subjective, unrepeatable and unrecorded. This project specifies and characterises a handheld instrument
that replaces the hammer with a solenoid striker and the surveyor's ear with a digital microphone,
extracts spectral features on an ESP32 at the edge, and publishes them over MQTT to a ThingsBoard
dashboard so that every tap is timestamped, geotagged and comparable.

The report's principal engineering contribution is an **acoustic-reasoning correction to the original
project architecture**. The initial design intended an MPU6050 accelerometer to sense the wall's
vibration response, and to place the accelerometer and the striker on a common rigid baseplate so
that the striker's own vibration could be removed by baseline subtraction. Two problems were
identified analytically and are resolved here:

1. **Bandwidth.** A debonded 8–25 mm cementitious or stone layer resonates as a clamped plate whose
   first-mode frequency **falls** from tens of kilohertz to hundreds of hertz as the debond radius
   grows, so a *large* debond rings *low*. An MPU6050 sampled at its maximum 1 kHz rate has a 500 Hz
   Nyquist limit and therefore cannot observe any debond smaller than a few tens of centimetres — the
   whole of the useful operating range, from roughly 15 kHz at the 8.8 cm floor down to 2.9 kHz at
   20 cm, lies above its bandwidth, and the only entry in Table 5.3 it can reach at all is a 40 cm
   fully-debonded tile in ceramic. The primary sensing channel is consequently moved to an **I2S MEMS microphone at
   48 kHz**, and the accelerometer is retained only as a *contact-quality supervisory channel*.
2. **Common-path contamination.** Because a reaction impulse is delivered to the probe baseplate when
   the solenoid fires, a rigidly co-mounted accelerometer measures the striker's own recoil as its
   dominant signal, and a *silent-baseline subtraction* removes nothing because the interfering term
   does not exist between strikes. The scheme is therefore replaced by an explicit model-level
   argument: the probe's resonances are common to every measurement, so a *same-probe, two-surface
   comparison* cancels them, with the residual set by contact-coupling variance — addressed by the
   mechanical design of Chapter 6 and measured in §8.3.

A closed-form design model — a clamped circular plate on a Winkler foundation, cross-checked against a
layered quarter-wave transfer-matrix solution (§5.11) — is used to select an analysis band of
300 Hz–15 kHz, to choose the strike pulse width that maximises in-band excitation, and to justify the
accelerometer's demotion. Against that model the instrument is shown to be **sensitive to debond
diameters above roughly 7 cm in ceramic tile, 8.8 cm in cement render and 11.3 cm in stone cladding**,
with the intact state deliberately outside the band, and with partial-bond discrimination available only
at large diameter — a documented boundary that the design does not claim to exceed.

**This submission plans and specifies the system in full but does not build it.** No measurement in this
report was taken on hardware, the firmware has not been compiled, and the results chapter is generated
from a forward physical model whose behaviour is reported against the model's own predictions rather than
against measurements. Chapter 8.0 states exactly what may and may not be claimed from it, and §9.1
identifies executing the validation protocol as the single highest-value next step.

**Keywords:** IoT, non-destructive evaluation, tap test, debonding, spectral analysis, ESP32, MQTT,
ThingsBoard, WorldSkills, ETSI EN 303 645.

**Data status.** All quantitative results in Chapter 8 are marked `SYNTHETIC`. They are produced by a
model calibrated to the closed-form solution in Chapter 5, not measured on hardware. Chapter 8.0
states exactly what may and may not be claimed from them.

---

# Table of Contents

> Numbering is manual; if you paste this into Word, apply Heading 1/2 styles to the `#`/`##` lines
> and the table of contents field will regenerate. Figures live in `report/06_analyze_tap.py`'s output
> (`results/figures/`); the placeholder list is in Appendix E.

1. Introduction
2. Literature and Standards Review
3. Requirements and System Architecture
4. Critical Design Review of the Original Concept
5. Physical Model and Sensor Selection
6. Mechanical and Contact Design
7. Electronic Design, Firmware and Dashboard
8. Validation Methodology and Results
9. Discussion, Limitations and Future Work
10. Conclusion
- References
- Appendix A — Bill of Materials and Costing
- Appendix B — WSSS and Standards Compliance Matrices
- Appendix C — Measurement Protocol
- Appendix D — Firmware and Analysis Artefacts
- Appendix E — Figure and Table Index
- Appendix F — Assessment Mapping to MILOs a and b

---

# 1. Introduction

## 1.1 Background

Hong Kong's building stock is old and tall. Roughly half of the private residential buildings in the
territory are more than thirty years old, and a large fraction of them are finished in ceramic tiles,
mosaic or cement render applied to a concrete or brick substrate. When that finish loses adhesion to
the substrate — a defect known in the regional literature as **空鼓** (*hung1 gu2*, "hollow drum"), and
in English as *debonding*, *delamination* or *hollowing* — the detached leaf is held only by its own
weight and whatever mortar remains. Under thermal cycling, water ingress and the freeze–thaw-free but
still aggressive marine climate, the leaf eventually separates and falls. Falling concrete and tiles
are a recurring cause of injury in dense pedestrian districts, and the risk rises with facade age.

The regulatory response is the Buildings Department's **Mandatory Building Inspection Scheme (MBIS)**,
introduced in 2012, which requires owners of buildings aged thirty years or more to appoint a
registered inspector to carry out prescribed inspections and, where defects are found, to carry out
prescribed repairs [1]. The professional practice for detecting debonding during such an inspection
is *tapping*: an inspector strikes the surface with a hammer or a steel rod and listens to the
resulting tone. A bonded area produces a short, high-pitched, damped click; a debonded area produces a
lower, longer, more resonant "hollow" tone.

Tapping works, and it is cheap, but it has well-known weaknesses. It is **subjective** — the judgement
resides in the inspector's ear and experience. It is **unrecorded** — no artifact of the survey
survives beyond handwritten notes, so inspection results cannot be audited, revisited or compared
between surveys. It is **unrepeatable** — the strike energy and contact conditions vary from tap to tap
and from inspector to inspector. And it is **slow** at height, where the inspector works from a
suspended platform or a gondola and every metre of travel is expensive.

## 1.2 Motivation and problem statement

The problem this project addresses is therefore not "how do we detect debonding" — tapping already
does that, approximately — but:

> **How can the tap test be instrumented so that its output becomes a repeatable, timestamped,
> spatially-indexed measurement that can be transmitted, stored, compared over time and acted upon —
> using low-cost, widely-available embedded components?**

This reframing is what makes the project an *Internet of Things* project rather than a
non-destructive-evaluation (NDE) project. The deliverable is not a better hammer; it is a **sensing
node with a digital output**, whose value comes from aggregation across thousands of taps and, in
principle, across thousands of buildings.

## 1.3 Aim and objectives

**Aim.** To plan, deploy and characterise a low-cost handheld IoT tap-test node that detects debonded
external wall finishes and publishes per-measurement spectral features to a cloud dashboard.

The objectives map directly onto the two intended learning outcomes the Module Assessment Scheme
assigns to the end-of-module assessment:

| # | Objective | MILO | Assessment evidence |
|---|---|---|---|
| O1 | Build a complete device-to-application chain: transducer → edge feature extraction → wireless transport → broker → dashboard → operator decision | **a** | Ch. 7, Ch. 8, Appendix D |
| O2 | Select the sensing, gateway and platform components against a documented reference framework, and defend the choice | **b** | Ch. 4, Ch. 5, Appendix B |
| O3 | Characterise the physical limits of the chosen sensing modality and state them as quantitative design constraints | **a**, **b** | Ch. 5, Ch. 8.7 |
| O4 | Quantify measurement repeatability and detection discrimination with a defined protocol, including a false-alarm/miss cost analysis | **a** | Ch. 6, Ch. 8.4–8.6 |
| O5 | Deliver a deployable, secured and reproducible system: firmware, provisioning, transport security, dashboard, and a documented operating procedure | **a**, **b** | Ch. 7, Appendix C, Appendix D |

## 1.4 Scope and boundaries

An explicit statement of what this project does *not* do is a scored element of the assessment, not a
disclaimer. The following is a summary; each limitation is quantified and discussed in Chapter 9.

**In scope.** The instrument, its firmware, its transport and its dashboard. The physical model that
justifies the sensor choice. The validation protocol, executed on controlled reference panels.

**Out of scope, with reasons.**

| Not attempted | Why | Where addressed |
|---|---|---|
| Validation against real debonded facades | No access to a surveyed wall with independently measured defect geometry; MBIS inspection requires a registered inspector | Ch. 9.1 |
| Certification to any inspection standard | MBIS prescribes *who* may inspect, not *what instrument* may be used; no instrument-based tap method is currently recognised | Ch. 2.5 |
| Quantifying debond depth or residual bond strength | The method measures a *tone*, which correlates with the mechanical boundary condition, not with the adhesion force | Ch. 9.4 |
| Autonomous robotic deployment on a facade | Requires IP-rated enclosure, aerial platform, localisation and power budgeting beyond the module's scope | Ch. 9.5 |
| Formal safety certification of the 12 V solenoid driver | Prototype shall be bench-operated only, under supervision | Ch. 7.6, Appendix C.7 |

## 1.5 Report structure

Chapter 2 reviews the regulatory and technical context. Chapter 3 states requirements and architecture.
Chapter 4 is a critical review of the project's own initial design, and is where the two architectural
corrections are derived. Chapter 5 develops the physical model and uses it to select the sensor.
Chapter 6 covers the mechanical and contact design. Chapter 7 covers electronics, firmware and
dashboard. Chapter 8 gives the validation methodology and the current results. Chapters 9 and 10
discuss limitations and conclude.

---

# 2. Literature and Standards Review

## 2.1 What the defect is, physically

A debond is not a void. It is a **compliant interlayer** — typically a few hundred micrometres to a
few millimetres of air, dust, loose sand, or disintegrated mortar — interposed between two stiff
bodies. The mechanical consequence that matters for detection is that it replaces a rigid connection
with a **spring**, and the spring changes the vibration modes of the finish layer.

The engineering literature terminology that should be used in the report, because it is what an
examiner will recognise:

| Term | Meaning | Relevance |
|---|---|---|
| *delamination* | separation of a layer in a laminated or layered system, usually with a crack front | The generic NDE term |
| *debond* | loss of adhesion at an interface (adhesive failure) | The generic material-science term |
| *hollowing* / *hollow spot* | British/Commonwealth surveyor's term for a debonded area found by tapping | The practitioner's term; matches "空鼓" |
| *drummy* | a bonded-looking area that sounds hollow | What the instrument is trying to distinguish from a true debond |
| *spall* | a fragment that has separated; *spalling* is the process of fragments detaching | The consequence the MBIS regime targets |

**Terminology note for the student:** the plan used the term 空鼓 in a heading. Use the English
technical term in the body and give the Chinese term once, parenthetically, with its meaning. Mixing
registers in the headings reads as informal.

## 2.2 Established detection methods and why they are not used here

This comparison is required evidence for objective O2, because the choice of modality must be
*demonstrated* against alternatives, not asserted.

| Method | Physical quantity | Typical cost | Pros | Cons |
|---|---|---|---|---|
| **Manual tap test** (with or without electronic stethoscope) | Acoustic tone | ~HK$100 | Zero setup; accepted practice; works on any surface | Subjective; unrecorded; slow; no calibration |
| **Automated tap test with impact-echo** (instrumented hammer + accelerometer) | Force / acceleration, spectral | HK$10 k–100 k | Well-established for concrete plate thickness and voids; ASTM C1383-15 [21] exists for impact-echo | Designed for concrete *plates* and thick sections; accelerometer-based systems are heavy and need good coupling; commercial units assume a trained operator |
| **Ultrasonic pulse-echo / through-transmission** | Acoustic time-of-flight, ~50–500 kHz | HK$20 k–200 k | Excellent sensitivity to thin debonds | Requires couplant and surface preparation; high-frequency attenuation in render is severe; slow point-by-point; poor on rough/tiled surfaces |
| **Infrared thermography** | Passive/active surface temperature gradient | HK$30 k–300 k | Rapid whole-facade coverage; non-contact | Needs solar loading or active heating; strongly weather-dependent; depth-limited; qualitative; low spatial resolution |
| **Laser Doppler vibrometry** | Surface velocity | HK$100 k–1 M | Contactless; exceptionally sensitive; laboratory reference standard | For a spot or scanning system, cost and alignment sensitivity are prohibitive; not portable in practice |
| **Acoustic emission monitoring** | Passive strain-release events | HK$10 k+ | Continuous monitoring possible | Only detects *active* defect growth, not existing quiescent debonds |
| **Ground-penetrating radar** | Electromagnetic reflection | HK$20 k–100 k | Depth-resolved | Poor contrast for thin render debonds; substrate-dependent |
| **This project — instrumented tap with acoustic sensing** | Acoustic tone, spectral features | **≈HK$300 (Appendix A)** | Low cost; portable; handheld; produces a digital record; suppressed above 300 Hz so the operator's dominance is reduced; directly instrumentable with commodity IoT parts | Band-limited as quantified in Ch. 5; contact-dependent as quantified in Ch. 6; *not yet validated on a real defect* |

The selection is graded conceptually in Appendix B.3. The governing constraint is that the module
requires a *low-cost, deployable IoT node*, so instrument cost must be one to two orders of magnitude
below the alternatives; that rules out LDV, thermography and industrial impact-echo immediately, and
the choice reduces to "tap, but instrumented".

**Literature point.** The academic literature on the instrumented tap test is substantial and should
be cited in a final report. The classical treatment of a plate on a compliant interface is the
*spring model* for delamination in layered media, and the tap test is discussed in the NDE literature
as a low-frequency variant of the resonance method. **This paragraph must be replaced with real
citations before submission** — see the reference-verification note in References.

## 2.3 Acoustic vs. tactile sensing: the module's own reasoning

A physical insight, not a literature citation, underdeveloped in the original plan and important here:

**A low-frequency tactile slave amplifier depends entirely on local contact.** A member of the public
tapping a wall hears nothing, because a bone-conduction-free human ear at atmospheric pressure is
coupled to sound in air. A member of the public tapping a wall *feels* nothing, because a finger is
not a cavity. A probe pressed against a wall *can* pick up low-order wall modes, but only where the
contact is rigid. A trolley-mounted sensor decoupled from the wall by a soft contact pad attenuates
exactly the low-frequency information of interest.

**A microphone pressed against a panel measures the complicated low-order internal modes of that
panel.** This is the mechanism this project exploits. Where the panel is freely suspended (mounted
through thin compliant pads) its low-order modes are simple and low-damped, and for a stiff plate
like a laminate the first non-axisymmetric mode occurs *below* the fundamental symmetric one; that
is, the low-frequency end is richer in modes than a naive isotropic model predicts.

The design consequence, which drives the entire measurement strategy, is:

> **Debonding is detected by *shifts in the modal frequencies of the finish layer*, not by the
> amplitude of the tap.** Amplitude depends on strike energy and contact quality and is therefore
> the least reliable feature available. Frequency depends on geometry and boundary condition and is
> therefore the most reliable feature available. This is precisely why the accelerometer — which
> measures a pulse — is a poorer primary channel than the microphone, which measures a mode.

### 2.3.1 Why this makes 空鼓 a *symptom* rather than the target

Directly addressing the academic criticism of the module's own framing: does 空鼓 lie between two
bodies that each have a *characteristic* frequency?

- The **finish layer** does, once debonded: it is effectively a plate on a free or spring boundary.
- The **substrate** does, always: it is a thick concrete slab with a continuum of modes.

So yes, the response is characteristic — **but the characteristic frequency is a function of the
debond *geometry*, not a property of the material.** In a 20 mm render, a 5 cm debond's fundamental is
at 46 kHz and a 20 cm debond's is at 2.9 kHz — a factor of sixteen, from one material and one thickness
(Table 5.3). Any method that reports a single number per tap — as the original plan's `f_peak_hz`
does — collapses that geometry into one scalar and loses the size information. This is why §5.4's
size-sensitivity table and §9.5's level-set proposal exist.

## 2.4 The regulatory and policy context

The citable sources are listed in the References, where each is marked **[VERIFIED]** (retrieved from
the primary source) or **[TO VERIFY]** (not confirmed). The chain, from statute to policy:

- **Buildings Ordinance (Cap. 123)** and the **Buildings (Inspection and Repair) Regulations
  (Cap. 123P)** [2] — the statutory basis.
- **Mandatory Building Inspection Scheme (MBIS)** and **Mandatory Window Inspection Scheme (MWIS)** [1]
  — buildings **aged 30 years or above**; a Registered Inspector inspects common parts, external walls
  and projections/signboards. This is the demand driver.
- **PNBI-10, Code of Practice for Building Inspection** [3] — the document that actually specifies
  **hammer tapping** as a method and uses the terms "hollow sounding concrete", "spalling" and
  "delamination". This is the practice being instrumented, and it is a verified citation rather than an
  assertion.
- **Minor Works Control System** — the regulatory pathway for the repair works a finding triggers
  (*[TO VERIFY] the specific regulation*).
- **Mainland China standards on exterior wall finish adhesion**, notably **JGJ/T 110-2017** on the
  adhesive strength of exterior wall face tiles [4]. These are **destructive pull-off tests**, not
  survey methods — the distinction matters and is developed in Appendix B.5.2 as the
  proof-test-versus-screening problem.
- **Hong Kong Smart City Blueprint** and the **Common Spatial Data Infrastructure** (*[TO VERIFY] URLs*)
  as the policy frame that makes a networked survey instrument valuable at city scale.

**A note on terminology.** The regional term **空鼓** (*hung1 gu2*) is the practitioner's name for the
defect. The English "hollow sounding" is documented in PNBI-10 [3]; a formal definition of the Chinese
term in a citable source was **not** found, and the report therefore uses the English technical terms
(*debond*, *delamination*, *hollowing*) in the body and gives the Chinese term once, here. Do not cite a
definition of 空鼓 that has not been seen (open item U6).

## 2.5 WorldSkills and the standards framework

The module's learning outcome *b* requires selection of gateways and platforms "with reference to
WorldSkills Standards Specification (WSSS) assessment method". Meeting that requirement credibly
requires knowing what the WSSS actually contains. **Appendix B.1** does this in full, with a
verification-status box stating what was retrieved from primary sources and what was not.

The compliance strategy in one paragraph, with the detail in Appendix B:

- The WSSS is an occupational **standard**, i.e. a description of the knowledge and skills a
  competent IoT practitioner holds. It is not a product certification and cannot be "complied with"
  by buying the right parts.
- The **assessment method** the WSSS belongs to relies on **Test Projects** marked by a combination
  of **Measurement** (objectively countable) and **Judgement** (expert observation against defined
  criteria), recorded in the competition's information system. The implication for this project is
  that evidence should be *countable where possible* — timestamps, message counts, log entries,
  confusion matrices — rather than only narrated.
- This report is therefore written so that each claim of competence is attached to a countable
  artefact: a topic and payload schema, a run log, a figure, a table, a configuration file.

---

# 3. Requirements and System Architecture

## 3.1 Functional requirements

Derived from the objectives. Each is testable; the acceptance column names the artefact that proves
it.

| ID | Requirement | Acceptance criterion | Milestone | Evidence |
|---|---|---|---|---|
| F1 | Apply a repeatable mechanical strike to the wall surface | ≥95 % of strikes within ±10 % of the mean in-band RMS on a reference target | 1 | Ch. 8.3 |
| F2 | Capture the acoustic response of the struck surface | 48 kHz, ≥1024 samples per event, no clipping for strike energies 1–3 | 1 | Ch. 7.2, Appendix D |
| F3 | Extract spectral features on-device, without a host | ≥200 measurements/hour sustained on-device | 1 | Run log, Ch. 7.3 |
| F4 | Record a per-strike contact-quality indicator | Contact metric computed and published for every measurement | 1 | Ch. 7.2 |
| F5 | Classify each measurement into a three-level debond grade | Grade assigned on-device; confidence published | 2 | Ch. 8.4 |
| F6 | Transmit each measurement as a structured message over MQTT | 100 % of measurements appear on the broker; payload conforms to the documented schema | 1 | Appendix D |
| F7 | Present live status and history on a dashboard with alerting | Dashboard shows latest values; a threshold breach raises an alert within 5 s | 1 | Ch. 7.5 |
| F8 | Operate on a battery for a survey session | ≥4 h continuous at 1 strike / 2 s | 2 | Ch. 7.6 |
| F9 | Verify transport authenticity and integrity | TLS handshake succeeds and untrusted-broker connection is refused | 2 | Ch. 7.4 |

## 3.2 Non-functional requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| N1 | Instrument unit cost | ≤ HK$500 |
| N2 | Mass and size | ≤ 600 g, operable one-handed |
| N3 | Acoustic exposure to the operator and bystanders | Analyse effective strike energy; document residual exposure (Ch. 7.6) |
| N4 | Repeatability | Median within-location CV of the primary frequency feature ≤ 5 % |
| N5 | Provisioning | A new unit is operational in ≤10 min following Appendix C.4 |
| N6 | Fault transparency | No silent failure: sensor, link and thermal faults each raise an event message |
| N7 | Reproducibility | Analysis reproducible from logged data with a documented script and a fixed seed |
| N8 | Honesty of state | Simulated data is labelled as simulated in the payload and on the dashboard |

**N3 deserves a note.** The downshift in this design is not primarily about human hearing. Setting
the analysis band above 300 Hz and using a strike pulse in the 400–900 Hz range removes the
human-dominant energy range, which is a real and defensible design choice on both technical and
exposure-reduction grounds. But the *peak*-based reasoning is weak, and an examiner may push on it:
peak level is the wrong metric for hearing damage, a duty cycle of 1 strike / 2 s with an uncalibrated
absolute level cannot be characterised from the available equipment, and the honest statement is
"exposure assessment is out of scope; the design has been *steered* away from the human-sensitive
range but not *demonstrated* to be safe." Say that.

## 3.3 System architecture

Six layers, presented in the standard IoT orthogonal decomposition.

```
                       ┌──────────────────────────────────────────────────────┐
  APPLICATION LAYER    │  ThingsBoard dashboard → operator decision          │
                       │  · latest f_peak / band_ratio / grade tiles          │
                       │  · per-inspection time series and trend              │
                       │  · alarm on threshold breach (F7)                    │
                       └───────────────────────▲──────────────────────────────┘
                                               │ HTTPS (REST / WebSocket)
                       ┌───────────────────────┴──────────────────────────────┐
  PLATFORM LAYER       │  ThingsBoard CE (device registry, rule engine,     │
                       │  telemetry store, alarms, dashboards)              │
                       └───────────────────────▲──────────────────────────────┘
                                               │ MQTT 3.1.1/5.0 over TLS 1.3
                       ┌───────────────────────┴──────────────────────────────┐
  NETWORK LAYER        │  Wi-Fi (WPA2) → local broker on gateway            │
                       │  [Milestone 2: ESP-NOW to a Raspberry Pi gateway]  │
                       └───────────────────────▲──────────────────────────────┘
                                               │ MQTT publish (QoS 1)
                       ┌───────────────────────┴──────────────────────────────┐
  EDGE LAYER           │  ESP32                                             │
                       │  · strike interlock + thermal guard                │
                       │  · 1024-pt float FFT, Hann, in-band features       │
                       │  · grade rule; contact-quality check               │
                       └───────▲───────────────────────────▲──────────────────┘
                               │ I2S @ 48 kHz              │ I2C @ 400 kHz
                       ┌───────┴───────────┐      ┌────────┴──────────────────┐
  SENSING LAYER        │ I2S MEMS mic      │      │ MPU6050 accelerometer    │
                       │ (PRIMARY)         │      │ (SUPERVISORY / contact)  │
                       └───────▲───────────┘      └────────▲──────────────────┘
                               │                           │
                       ┌───────┴───────────────────────────┴──────────────────┐
  ACTUATION/PHYSICAL   │ Rigid baseplate: solenoid striker + mic port + accel │
                       │ Contact feet pressed against the wall                │
                       └───────────────────────▲──────────────────────────────┘
                                               │
                                          [ WALL SURFACE ]
```

**Reading the diagram for the assessment.** The dashed-line boundary between SENSING and EDGE is where
the module's "device-to-application" requirement is satisfied: raw transducer data never leaves the
node, only features do. The accelerometer branch is drawn separately and labelled SUPERISORY because
its demotion from primary channel to quality gate is the central design decision of Chapter 4, and the
diagram should make that visible at a glance.

## 3.4 Assessment-driven design decisions

Three decisions were made because of how the module assesses, and are recorded here so the reasoning
is auditable.

**Detection is edge-side, not cloud-side.** MILO *a* asks for a complete device-to-application chain.
If all signal processing happened on a server, the ESP32 would be a data modem and the "edge layer"
would be nominal. Performing the FFT and the classification on the node makes the edge layer real.
The trade-off is that the on-device classifier is a fixed rule rather than a trained model (flash and
RAM budget), which is an honest limitation recorded in Ch. 9.3.

**A foreseeable collision with recorded data integrity.** If the on-device grade differs from the
offline analysis of the logged features, the report must not quietly report only the favourable one.
The firmware publishes the raw features as well as the grade precisely so this comparison is possible;
Ch. 8.4 does it, and reports the disagreement.

**A gateway is claimed only when a gateway exists.** An ESP32 that both senses and publishes is a
*sensor node*, not a gateway. MILO *b* concerns gateways and platforms. Milestone 1 ships a sensor
node and a platform (ThingsBoard) and says so. Milestone 2 adds a genuine gateway role — an ESP-NOW
concentrator on a Raspberry Pi running a local MQTT broker — and only then is a gateway claimed. This
distinction is discussed in Ch. 7.1 and Appendix B.2.

---

# 4. Critical Design Review of the Original Concept

This chapter reviews the design as originally proposed. Its purpose is not self-criticism; it is to
demonstrate the engineering reasoning that objective O3 requires. Two of the original design's
assumptions do not survive analysis, and correcting them changes the system architecture.

## 4.1 The original design, stated fairly

The proposed instrument was a handheld probe carrying:

- an **LSD-1040B push–pull solenoid** (DC 12 V, ~23 W) as a repeatable striker;
- an **MPU6050** six-axis IMU as the vibration sensor;
- both **rigidly fixed to one hard acrylic baseplate**, 5–10 cm apart, with M3 screws for the solenoid
  and double-sided tape for the IMU;
- an **ESP32** performing FFT and feature extraction;
- **MQTT over Wi-Fi** to **ThingsBoard**;
- a **3-second silent baseline capture** before each strike, subtracted from the measurement to remove
  "the solenoid's own vibration".

The reasoning behind the single-baseplate design was sound in intent: by locking the relative geometry
of striker and sensor, the striker's contribution becomes a fixed background that cancels when two
measurements are compared. The intent is right. The execution does not achieve it, for two
independent reasons.

## 4.2 Finding 1 — the accelerometer cannot see the signal of interest

### 4.2.1 The measuring instrument's own limit

The MPU6050's accelerometer supports output data rates up to **1 kHz**. Sampling theory then gives a
Nyquist frequency of:

$$f_{\text{Nyq}} = \frac{f_s}{2} = \frac{1000\ \text{Hz}}{2} = 500\ \text{Hz}$$

No signal component above 500 Hz is recoverable, and that is before any practical question of
anti-alias filtering or of how much of the 1 kHz ODR is actually usable through the I²C path while
the radio is active.

### 4.2.2 The signal's location

Chapter 5 derives that a debonded finish layer resonates as a clamped plate on a spring foundation,
with first-mode frequency

$$f_1 \approx \frac{1}{2\pi}\sqrt{\frac{D\,\alpha^4 + k}{\rho h}}, \qquad \alpha = \frac{3.196}{a}$$

where $a$ is the debond radius, $h$ the layer thickness, $D$ its flexural rigidity, and $k$ the
interface stiffness per unit area. For a fully debonded layer ($k \to 0$) the frequency scales as
$1/a^2$. Evaluating for realistic finish materials (Ch. 5.4) gives first-mode frequencies of
**hundreds of hertz to tens of kilohertz** across the debond sizes an inspector cares about, and
for the *detectable* range — debonds large enough to be a real hazard — **1–8 kHz**.

### 4.2.3 The intersection is empty

The 500 Hz Nyquist limit and a 1–8 kHz signal band do not overlap. The accelerometer, used as
proposed, would have measured the **rigid-body recoil of the probe assembly** — a few-hundred-hertz
motion of the whole mass — and not the wall's acoustic response at all. It would have produced
plausible-looking spectra and a working dashboard, and the spectra would have contained essentially
**no information about the wall.**

This is the most valuable finding in the chapter, and it is worth stating why: the failure mode is
*silent*. The system would have appeared to work. Every downstream component — FFT, MQTT, dashboard —
would have functioned correctly on data that carried no diagnostic content. Only the model in
Chapter 5 exposes it.

**Resolution.** The primary sensing channel moves to an **I2S MEMS microphone at 48 kHz**, matching the
modality to the band. The MPU6050 is retained, but for a different purpose — see §4.4.

## 4.3 Finding 2 — the baseline-subtraction scheme removes nothing

### 4.3.1 The mechanism the scheme assumes

The plan assumes an additive interference model:

$$x_{\text{measured}}(t) = x_{\text{wall}}(t) + x_{\text{solenoid}}(t)$$

and proposes to estimate $x_{\text{solenoid}}$ from a 3-second silent baseline, then subtract it.

### 4.3.2 Why it fails

The solver's step is actuated by a current pulse. Its percussion — plunger impacting the wall, coil
reaction against the baseplate — exists **only during the strike**, which by construction is *not*
covered by the silent baseline period. Therefore:

$$x_{\text{baseline}}(t) = x_{\text{wall,ambient}}(t) + x_{\text{solenoid}}(t)\big|_{\text{off}} = x_{\text{ambient}}(t) + 0$$

Subtracting it removes ambient noise and building sway, and removes **none** of the striker's
contribution. The scheme's premise — that the interference is present in the baseline — is false.

### 4.3.3 The interference is also not additive

The assumption of additivity is itself wrong in the regime that matters. When the plunger impacts the
baseplate and the wall, the sensor sits between two coupled mechanical systems; the coupling is not a
summation but a shared boundary condition. There is no linear transfer function relating a "solenoid
only" signal to the measured signal, which is why no amount of baseline recording could reconstruct it.

### 4.3.4 What the design was actually reaching for — and what it achieves

The intent — "the striker is a constant, so it cancels" — is the logic of **common-mode rejection**,
and it is worth distinguishing two levels of it clearly:

| Level | Claim | Survives analysis? |
|---|---|---|
| **Model-level common-mode rejection** — the probe's resonances (baseplate modes, microphone cavity, feet) are identical whenever the same probe is used, so a *comparison across surfaces* cancels them | The probe transfer function is genuinely fixed by the hardware | **Yes.** This is real and is the project's actual working principle |
| **Measurement-level baseline subtraction** — recording silence and subtracting | The interfering term is absent from the baseline | **No.** §4.3.2 |

The correction is therefore to **stop claiming a calibration that cannot exist** and instead state the
working principle honestly: *a two-surface differential measurement between a reference bonded region
and the suspect region, using the same probe and the same contact procedure, with the probe's own
resonances assumed common.* Chapter 6 quantifies how well that assumption holds, and Chapter 8.3
shows what happens to the residual when the contact procedure drifts.

## 4.4 The accelerometer's correct role

Demoting the IMU does not mean discarding it. It has a real and well-matched job — one that the
microphone cannot do.

**Contact-quality supervision.** The microphone measures *what the wall emits*; the accelerometer
measures *how hard the probe was pressed and how the strike landed*. A hard press produces different
acoustic coupling than a light touch, and an uneven contact produces a different spectrum. Recording
the IMU's response in the strike window gives a per-measurement **contact-quality indicator** that can
be used to:

- reject taps that were not actually valid (F4);
- flag measurements taken with unstable hand pressure;
- explain the outliers that would otherwise be attributed to the wall.

This is the honest use of a 500 Hz-bandwidth sensor in this system: it characterises the **probe's
mechanical state**, which lives below 500 Hz, rather than the **wall's acoustic response**, which does
not. The distinction is drawn explicitly in the firmware's structure, where the accelerometer window
opens *after* the solenoid pulse has been issued, so that what is captured is the settling of the
probe rather than the excitation pulse itself.

**A residual weakness worth recording.** Because the accelerometer window opens after the strike, the
captured `impact_peak_g` is *not* the peak contact impulse — by then the impulse has passed. It is a
proxy for probe settling and press force, and it is named and interpreted accordingly. This limitation
is stated rather than papered over because an examiner who understands transducers will find it, and
finding it in the report's own limitations section is worth more than finding it in the report's
claims.

## 4.5 Summary of design changes

| # | Original | Revised | Reason | Where |
|---|---|---|---|---|
| D1 | MPU6050 as primary vibration sensor | I2S MEMS microphone (48 kHz) primary; MPU6050 supervisory | Bandwidth intersection empty (§4.2) | Ch. 5, Ch. 7.2 |
| D2 | 3 s silent baseline subtraction | Two-surface differential with model-level common-mode argument | Interference absent from baseline (§4.3) | Ch. 4.3.4, Ch. 6.4 |
| D3 | Single scalar `f_peak_hz` per tap | `f_peak_hz` **plus** `f_centroid_hz`, `band_ratio_lh`, `decay_tau_ms` | A single peak collapses debond size information (§2.3.1) | Ch. 6.3, Ch. 8.5 |
| D4 | "Standardised strike" asserted | Strike repeatability *measured*, with a pass criterion | Assertion is not evidence (F1) | Ch. 8.3 |
| D5 | "Deployed on facades" implied | Handheld survey tool in Milestone 1; gateway added in Milestone 2 | Honest scope (Appendix B.2) | Ch. 7.1, Ch. 9.5 |
| D6 | Security as a keyword list | TLS 1.3 with CA-chain validation, per-device credentials, ACL; benchmarked against ETSI EN 303 645 | MILO *b*; Ch. 2.5 | Ch. 7.4, Appendix B.4 |
| D7 | One ESP32 claimed as a "gateway" | Sensor node in M1; separate concentrator/gateway role in M2 | A node is not a gateway (MILO *b*) | Ch. 3.4, Ch. 7.1 |

