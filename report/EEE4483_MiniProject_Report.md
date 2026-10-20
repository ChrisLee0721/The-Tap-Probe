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


---

# 5. Physical Model and Sensor Selection

This chapter develops the model that determines the instrument's achievable performance. It is the
technical core of the report: every subsequent design decision — sensor, band, strike pulse, feature
set, and the honesty of the performance claims in Chapter 8 — follows from the numbers derived here.

## 5.1 The governing idealisation

The physical situation is a **layered elastic stack**: a thick concrete substrate, a thin cementitious
or ceramic finish layer, and a **bonding interface whose stiffness may be degraded**. Tapping the
surface excites the finish layer, which responds as a plate on an elastic foundation. The observable
consequence of debonding is that the foundation stiffness $k$ (force per unit area per unit
displacement, i.e. Pa/m) collapses from a large value — intact cementitious bond — to near zero.

The finish layer is modelled as a **circular plate of radius $a$ clamped at its perimeter**, resting on
a Winkler foundation of stiffness $k$ per unit area. The clamping is the correct idealisation here:
the resonant region is the debonded patch, and its boundary is the bond line, where the layer is
strongly constrained. Only the fundamental mode $(0,1)$ is needed, because a tap injects a broad
spectrum and the lowest mode dominates the ring-down.

For a clamped circular plate of flexural rigidity $D$ on a Winkler foundation, the fundamental
frequency is

$$f_1 = \frac{1}{2\pi}\sqrt{\frac{D\,\alpha^4 + k}{\rho h}}, \qquad \alpha = \frac{3.196}{a}$$

where $h$ is the layer thickness, $\rho$ its density, and

$$D = \frac{E h^3}{12(1-\nu^2)}$$

Two limits are worth writing out, because they carry the physics:

- **Large debond ($a \to \infty$, $k$ fixed):** the $D\alpha^4$ term becomes negligible and
  $f_1 \to \frac{1}{2\pi}\sqrt{k/\rho h}$ — a **foundation-dominated** frequency that depends on the
  bond stiffness but *not* on the size of the defect. A bonded and a partially bonded region of
  sufficient extent differ only through $k$.
- **Fully debonded ($k \to 0$):** $f_1 \to \frac{\alpha^2}{2\pi}\sqrt{D/\rho h} \propto 1/a^2$ — a
  **size-dominated** frequency that falls as the *inverse square* of the debond radius. A debond
  twice as wide rings at one quarter of the frequency.

This $1/a^2$ law is why the debond tone spans such an enormous range — the two-orders-of-magnitude
spread in Table 5.3 — and it is the single most important number in the design.

## 5.2 A necessary correction to the original model

The original project plan asserted a $1/a^2$ dependence and intended to fit $f_{\text{peak}} = C/a^2$.
That law is correct, but only in the $k \to 0$ limit. For a finite bond stiffness the $D\alpha^4$ term
adds in quadrature inside the square root, so the observable is

$$f_1^2 = \underbrace{\frac{D\alpha^4}{(2\pi)^2\rho h}}_{\propto\, 1/a^4} + \underbrace{\frac{k}{(2\pi)^2\rho h}}_{\text{constant}}$$

which is **not** a $1/a^2$ power law: it is $f_1^2 = A/a^4 + B$. Fitting $f = C/a^2$ through data that
includes partially bonded regions produces a biased $C$ and an $R^2$ that flatters the fit at large $a$
and is poor at small $a$. Chapter 8.5 therefore fits the **two-parameter form**
$f_1^2 = A/a^4 + B$ and reports $A$ (geometry) and $B$ (bond stiffness) separately, which is both the
physically correct model and materially more informative: $A$ is a material/extent parameter and $B$ is
a *bond-quality* parameter. Fitting $C/a^2$ as originally planned is included as a deliberate
comparison so the improvement is visible.

## 5.3 Materials and parameters

| Symbol | Meaning | Value used |
|---|---|---|
| $E_{tile}$ | Elastic modulus, ceramic tile | 55 GPa |
| $h_{tile}$ | Tile thickness | 8 mm |
| $\nu_{tile}$ | Poisson ratio, tile | 0.22 |
| $E_{render}$ | Elastic modulus, cement render | 18 GPa |
| $h_{render}$ | Render thickness | 20 mm |
| $\nu_{render}$ | Poisson ratio, render | 0.20 |
| $E_{stone}$ | Elastic modulus, granite cladding | 40 GPa |
| $h_{stone}$ | Stone thickness | 25 mm |
| $\nu_{stone}$ | Poisson ratio, stone | 0.25 |
| $\rho$ | Layer density | 2000–2600 kg/m³ |
| $k_{intact}$ | Intact cementitious bond stiffness | $9\times10^{11}$ Pa/m |
| $k_{partial}$ | Partially bonded (dust/loose sand interlayer) | $10^{10}$ Pa/m |
| $k_{free}$ | Fully debonded | 0 Pa/m |

The intact value is anchored to the mortar layer itself: a 20 mm render layer over 1 m² has a normal
stiffness $E/h = 18\ \mathrm{GPa} / 0.020\ \mathrm{m} = 9\times10^{11}$ Pa/m, so the *bond line is
stiffer than that layer is soft*, and the intact bond is effectively rigid at these frequencies. That
is the justification for treating the intact case as clamped.

**Conversion of $k$ to a physical gap.** Treating the degraded interlayer as a trapped air layer of
thickness $t$, the stiffness is $k = B_{air}/t$ with $B_{air} \approx 1.4\times10^{5}$ Pa. This gives
the physical interpretation of the $k$ axis: an intact bond ($k=9\times10^{11}$) corresponds to a gap of
about 0.2 µm; $k = 10^{10}$ Pa/m to a 14 µm gap; $k = 3\times10^{7}$ Pa/m to a 4.7 mm gap. A debond
that still reads as "bonded" by these means is therefore one with a compliant interlayer thinner than
a few micrometres.

## 5.4 The central result: frequency versus debond size

Table 5.3 tabulates $f_1$ for each material across debond diameters from 3 cm to 40 cm and bond
stiffness from intact to free. Entries marked `>15k` lie above the instrument's analysis ceiling.

**Table 5.3 — Fundamental frequency $f_1$ [Hz] of a debonded finish layer, by diameter and bond stiffness.**
Analysis band is 300 Hz – 15 kHz, so `>15k` is unobservable.

**Ceramic tile, 8 mm**

| $k$ [Pa/m] | 3 cm | 5 cm | 7 cm | 10 cm | 15 cm | 20 cm | 30 cm | 40 cm |
|---|---|---|---|---|---|---|---|---|
| intact $9\times10^{11}$ | >15k | >15k | >15k | >15k | >15k | >15k | >15k | >15k |
| $3\times10^{10}$ | >15k | >15k | >15k | 9689 | 7093 | 6555 | 6344 | 6308 |
| $10^{10}$ partial | >15k | >15k | >15k | 8216 | 4891 | 4073 | 3723 | 3661 |
| $10^{9}$ | >15k | >15k | >15k | 7458 | 3471 | 2171 | 1411 | 1238 |
| free (0) | >15k | >15k | >15k | 7369 | 3275 | 1842 | 819 | 461 |

**Cement render, 20 mm**

| $k$ [Pa/m] | 3 cm | 5 cm | 7 cm | 10 cm | 15 cm | 20 cm | 30 cm | 40 cm |
|---|---|---|---|---|---|---|---|---|
| intact $9\times10^{11}$ | >15k | >15k | >15k | >15k | >15k | >15k | >15k | >15k |
| $3\times10^{10}$ | >15k | >15k | >15k | 12294 | 6716 | 5221 | 4542 | 4417 |
| $10^{10}$ partial | >15k | >15k | >15k | 11767 | 5695 | 3820 | 2822 | 2617 |
| $10^{9}$ | >15k | >15k | >15k | 11522 | 5170 | 2982 | 1505 | 1072 |
| free (0) | >15k | >15k | >15k | 11495 | 5109 | 2874 | 1277 | 718 |

**Stone cladding, 25 mm**

| $k$ [Pa/m] | 3 cm | 5 cm | 7 cm | 10 cm | 15 cm | 20 cm | 30 cm | 40 cm |
|---|---|---|---|---|---|---|---|---|
| intact $9\times10^{11}$ | >15k | >15k | >15k | >15k | >15k | >15k | >15k | >15k |
| $3\times10^{10}$ | >15k | >15k | >15k | >15k | 9115 | 5855 | 4019 | 3620 |
| $10^{10}$ partial | >15k | >15k | >15k | >15k | 8677 | 5146 | 2891 | 2304 |
| $10^{9}$ | >15k | >15k | >15k | >15k | 8472 | 4793 | 2203 | 1342 |
| free (0) | >15k | >15k | >15k | >15k | 8449 | 4753 | 2112 | 1188 |

**Reading Table 5.3.**

1. **The intact state is always invisible** (all `>15k`). That is a design requirement, not a
   weakness: an intact wall must not produce an in-band resonance, because the *absence* of an
   in-band tone is the "bonded" signature.
2. **A fully debonded region first becomes observable at 7.0 cm (tile), 8.8 cm (render) and 11.3 cm
   (stone).** Below that, the tone is above the analysis ceiling even for a completely free plate. But
   *observable at the floor* requires the plate to be essentially free — see §5.5.1, which is the more
   important statement.
3. **Below the size threshold, degradation is nearly invisible; above it, the main axis of variation
   is size, not bond quality.** At 10 cm in render, $f_1$ moves only from 11495 Hz (fully free) to
   11767 Hz (partial) to >15k (intact) — the free and partial cases are within 2.4 % of each other
   while the intact case is off the scale. Conversely at 40 cm, partial versus free differs by a factor
   of 3.6. This is the quantitative demonstration that the method's dynamic range is spent on *size*
   once the debond exceeds the threshold, exactly as §2.3.1 predicted.
4. **The foundation term only matters at large $a$.** At 10 cm in render, the geometry term
   $D\alpha^4/a^4 = 2.1\times10^{11}$ Pa/m exceeds $k$ for every degraded value, so all the degraded
   rows converge (7369, 8216 and 9689 Hz for free, partial and $3\times10^{10}$ — all within 32 % of one
   another, against an intact case that is off the scale). At 40 cm the geometry term has fallen to
   $8.2\times10^{8}$ Pa/m and $k$ dominates, spreading the same three cases over 718–4417 Hz. This is
   precisely why the original $C/a^2$ fit of §5.2 is inadequate, and why §5.5's limit needs the
   two-dimensional treatment it is given there.

## 5.5 Detection limits implied by the analysis band

The size floor is defined by the fully-debonded case: the smallest diameter whose $k \to 0$ tone is
*inside* the band. But the size floor alone understates the problem, because a debond at the floor is
visible **only if it is essentially completely free**. The question that actually governs usefulness is
two-dimensional: *at a given size, how much of the bond-stiffness range is still observable?*

Writing the condition $f_1 \le f_{max}$ with $f_{max} = 15$ kHz and inverting for $k$:

$$k_{th}(a) = (2\pi f_{max})^2\rho h - \frac{D\alpha^4}{a^4}$$

**Table 5.4 — Detection limits** (at the reference thicknesses of Table 5.3; the floor's dependence on finish thickness is Table 5.8 in §5.5.2).

| Material | Intact $f_1$ | Size floor (fully debonded) | $k_{th}$ at 100 mm | $k_{th}$ at 200 mm | $k_{th}$ as a fraction of intact, at 200 mm |
|---|---|---|---|---|---|
| Ceramic tile 8 mm | 34.5 kHz | **7.0 cm** | $1.3\times10^{11}$ Pa/m | $1.68\times10^{11}$ Pa/m | 19 % |
| Cement render 20 mm | 23.9 kHz | **8.8 cm** | $1.47\times10^{11}$ Pa/m | $3.42\times10^{11}$ Pa/m | 38 % |
| Stone cladding 25 mm | 18.7 kHz | **11.3 cm** | *outside band* | $5.19\times10^{11}$ Pa/m | 58 % |

**Why Table 5.4 no longer carries an air-gap column.** An earlier version of this table reported an
"equivalent air gap" of 3–8 mm at the size floor. That was an error, and it is worth recording because
the error is instructive: at the size floor $k_{th}$ is by construction **exactly zero**, so the
equivalent gap is infinite. The floor is the size at which a *perfectly free* plate's tone reaches the
band edge; asking how compliant a bond may be there is asking how compliant a bond may be and still
have the plate be perfectly free, which is a contradiction. The gap equivalence becomes meaningful only
once the size is comfortably above the floor, and it is reported that way in §5.5.1.

### 5.5.1 What the numbers mean

Three consequences follow, and they are the numbers the rest of the report must respect.

**First, at the size floor only near-total debonding is visible.** As the size approaches the floor from
above, $k_{th} \to 0$: the tone is in band only for a plate that is essentially free. A 9 cm debond in
render is therefore detectable *only if it is almost completely separated*; a 9 cm *partial* debond is
not detectable at all. This is a sharper and less flattering statement than the size floor alone
suggests, and it is the accurate one.

**Second, the observable bond-stiffness window widens rapidly with size, then saturates.** In render,
$k_{th}$ rises from $7.4\times10^{9}$ Pa/m at 88 mm (0.8 % of intact) to $1.47\times10^{11}$ at 100 mm
(16 %), $3.14\times10^{11}$ at 150 mm (35 %), and saturates at $3.55\times10^{11}$ Pa/m (39 % of intact)
beyond 300 mm. The saturation is physical: as $a \to \infty$ the geometry term vanishes and
$f_1 \to \sqrt{k}/(2\pi\sqrt{\rho h})$, so the largest $k$ that still resonates below 15 kHz becomes a
pure material constant, independent of size.

**Third — and this is the correction that matters most to the project's claims — partial debonding is
distinguishable from full debonding only at large size.** Because $k_{th}$ saturates at 39 % of intact
for render, a debond must have lost more than about 61 % of its bond stiffness before it becomes
visible *at all*, at any size. And within the visible window, partial versus full separation produces a
frequency difference only where the geometry term has fallen enough for $k$ to contribute: at 200 mm in
render, full separation gives $f_1 = 2874$ Hz and a $k = 10^{10}$ Pa/m partial bond gives 3820 Hz — a
33 % separation. At 100 mm the same comparison gives 11495 against 11767 Hz — 2.4 %, indistinguishable.

**The $k$-axis resolution, stated plainly.** Translating $k_{th}$ to an interlayer thickness via
$k = B_{air}/t$: the instrument sees a plate as "hollow" when the effective air gap exceeds roughly
**0.4 µm at 200 mm** in render, rising through 1.0 µm at 100 mm to 19 µm at the 88 mm floor. Those
sub-micrometre figures should not be over-interpreted — $B_{air}/t$ is a linearisation valid for small
$t$ and the real interface is not a clean air gap — but they make one point unambiguously: **the method
discriminates a *nearly separated* layer from an *entirely separated* one, and is blind to the
difference between a good bond and a mediocre one.** It cannot report bond quality, and it should never
be presented as doing so.

**The operational consequence.** The useful range is not "7 cm and up" but "comfortably above the size
floor, and then on the *size* axis rather than the severity axis". Operationally this is **10 cm and up
for tile, 10–12 cm and up for render, 15 cm and up for stone**, and the report states it that way
throughout.

### 5.5.2 The size floor is a function of the finish thickness, not a material constant

Table 5.4 quotes one floor per material, and every later chapter then writes "8.8 cm for render" as though
it were a property of render. It is not: it is a property of **20 mm** render. Since $f_1 \propto h$
(§5.1, because $D/h = Eh^2/12(1-
u^2)$), setting $f_1 = f_{max}$ and solving for diameter gives a floor
that scales as $\sqrt{h}$:

**Table 5.8 — Size floor versus finish thickness (cement render, $E$ = 18 GPa, $f_{max}$ = 15 kHz).**

| Finish thickness $h$ | Size floor (fully debonded) | $f_1$ at 4 cm for comparison |
|---|---|---|
| 5 mm | 4.4 cm | 17 961 Hz |
| 8 mm | 5.5 cm | 28 737 Hz |
| 10 mm | 6.2 cm | 35 922 Hz |
| 15 mm | 7.6 cm | 53 882 Hz |
| **20 mm (reference panel)** | **8.8 cm** | **71 843 Hz** |
| 25 mm | 9.8 cm | 89 804 Hz |
| 30 mm | 10.7 cm | 107 765 Hz |

Two consequences, and they both bear on how the result may be quoted.

**First, the floor varies by a factor of 2.4 across finishes a surveyor would call "render".** A thick
sand-cement render and a thin adhesive bed are both "render"; the instrument's useful range differs by
more than a factor of two between them. Any statement of the form "this method finds hollows above
8.8 cm" is therefore a statement about 20 mm render specifically. **Appendix C.5 requires the operator to
record the finish construction for exactly this reason, and forbids quoting a floor for a building whose
build-up has not been established.**

**Second, a *thinner* finish lowers the floor.** This is the opposite of the intuition that thinner
finishes are harder to inspect, and it follows directly from the model: a thin layer is less stiff in
bending, so for a given debond diameter it rings lower, and lower is inside the band. It is the *thick*
finish — the 25–30 mm granite-backed or sand-cement build-ups — that is the hardest case.

**What this does not do.** It does not bring a 4 cm debond within reach: that would need $h \approxpprox$ 4 mm
in render, thinner than any real finish layer. §9.2.1 prices the three gates that stand between the
present design and a 4 cm target, and shows that the binding one is not the band or the transducer.

## 5.6 Strike pulse and the excitation spectrum

The strike is modelled as a **half-sine force pulse of contact time $T$**, whose amplitude spectrum is

$$F(\omega) \propto \frac{\cos(\omega T/2)}{1-(\omega T)^2}$$

with a null at $\omega = 3\pi/T$, i.e. $f_{null} = 1.5/T$. A long (soft) contact concentrates all the
energy at low frequency and *cannot excite a wall mode that lies above the null* — the mode is simply
not driven, no matter how sensitive the receiver. This is a control lever, not a fixed property.

**Table 5.5 — Fraction of strike energy below a given frequency, versus contact time $T$.**

| $T$ | null $1.5/T$ | energy ≤2 kHz | ≤5 kHz | ≤16 kHz |
|---|---|---|---|---|
| 2000 µs | 0.8 kHz | 0.998 | 1.000 | 1.000 |
| 1000 µs | 1.5 kHz | 0.970 | 0.999 | 1.000 |
| 500 µs | 3.0 kHz | 0.698 | 0.993 | 1.000 |
| **300 µs** | **5.0 kHz** | **0.460** | **0.887** | **0.999** |
| 200 µs | 7.5 kHz | 0.316 | 0.698 | 0.995 |
| 100 µs | 15.0 kHz | 0.161 | 0.390 | 0.911 |
| 50 µs | 30.0 kHz | 0.081 | 0.202 | 0.592 |

**Selection.** $T = 300\ \mu s$ is chosen: it places the spectral null at 5 kHz, notches the very-low
band (which is where the probe's own rigid-body motion and hand tremor live — see §6.3), keeps 89 % of
the energy below 5 kHz and 99.9 % below 16 kHz, and is three times the in-band energy of the 50 µs pulse
while delivering 99.9 % of its energy below 16 kHz, against 59 % for the 50 µs pulse. A shorter pulse
would excite the band more, but at the cost of pushing energy into the aliasing margin and of a harder,
noisier contact. $T$ is set by the solenoid's plunger geometry and the compliance of the cap; §6.2
gives the implementation.

**An honest limitation.** The model assumes a *half-sine* force. A real solenoid strike produces a
shorter, sharper, more impulse-like contact followed by a secondary bounce, so the true spectrum is
closer to a train of impulses. The model is therefore a *screening* model: it establishes that a
sub-millisecond contact is required and it bounds the low-frequency notch, but the exact spectrum must
be measured on the bench (Appendix C.3) and the driver's pulse width trimmed to match. That
calibration is a *required* commissioning step, not an optional refinement.

## 5.7 Consistency checks on the idealisation

Two checks, both of which the model must pass for §5.1 to be admissible.

**Contact time versus transit time.** For render of thickness $h$ with longitudinal speed
$c_L \approx \sqrt{E/\rho} \approx 3000$ m/s, the round-trip transit time through a 20 mm layer is
$2h/c_L = 13.3\ \mu s$ — an order of magnitude shorter than the 300 µs contact time. The strike
therefore *cannot* resolve the render as a separate plate in the time domain; the layer is quasi-static
during the contact and the response is genuinely the plate-on-foundation mode derived in §5.1. Had the
contact time been of the same order as the round trip, the model would be invalid — so this is a
load-bearing check, not a formality.

That check is not decorative: it is also what **limits how far down the size range this method can be
pushed.** The contact time needed to excite a mode at frequency $f$ is $T \le 1.5/f$ (§5.6), so smaller
debonds demand shorter strikes; and the same $2h/c_L$ bound says that at some point the strike begins to
resolve the layer as a plate rather than load it as a spring:

| Debond diameter | $f_1$ (render) | $T$ needed | $2h/c_L$ | Ratio |
|---|---|---|---|---|
| 20 cm | 2 874 Hz | 522 µs | 13.3 µs | 39 |
| 15 cm | 5 109 Hz | 294 µs | 13.3 µs | 22 |
| 10 cm | 11 495 Hz | 130 µs | 13.3 µs | 9.8 |
| 8.8 cm (floor) | 14 844 Hz | 101 µs | 13.3 µs | 7.6 |
| 7 cm | 23 459 Hz | 64 µs | 13.3 µs | 4.8 |
| 4 cm | 71 843 Hz | 21 µs | 13.3 µs | **1.6** |

**The ratio is the method's real envelope.** At the 8.8 cm floor the strike is still seven times longer
than the round trip and the idealisation is comfortable; at 4 cm it is 1.6 and the model is at the edge
of its own validity. The chosen band (300 Hz–15 kHz) and the chosen contact time (300 µs) are therefore
not the binding constraints — the transit-time check is. §9.2.1 takes this the rest of the way and prices
what reaching 4 cm would actually cost.

**Wavelength versus extent.** The surface-wave wavelength in the render at 5 kHz is
$\lambda = c_R/f \approx 0.6$ m, comparable to the substrate extent. The modes the tap excites are
therefore those of the *finish layer* over a large substrate, and the substrate's role is that of a
terminating impedance — which is exactly the semi-infinite assumption implicit in the foundation model.

## 5.8 Sensor selection: the bandwidth argument, made numerical

The MPU6050 accelerometer supports an output data rate of at most 1 kHz, giving $f_{Nyq} = 500$ Hz.
Against Table 5.3, **every observable entry has $f_1 \geq 461$ Hz, and all but the two most extreme
entries exceed 1 kHz.** The accelerometer's Nyquist frequency sits at the very bottom of the useful
range, and its practical passband (a few hundred hertz) contains only the probe's own rigid-body
motion, the foundation-dominated tail of the largest debonds, and hand tremor.

The original design's choice of that part was therefore **not a marginal error but a categorical one**:
no filter, no averaging scheme, and no signal-processing trick recovers a 3 kHz mode from a 1 kHz-sampled
transducer. The failure would have been silent, because the accelerometer *does* produce a plausible,
structured, non-trivial spectrum — of the probe's own recoil.

**Selection rule.** $f_{Nyq}$ must exceed the top of the analysis band with margin, and the band must
exceed the largest observable $f_1$. Choosing an I2S MEMS microphone sampling at 48 kHz gives
$f_{Nyq} = 24$ kHz, so the 15 kHz ceiling sits at 62.5 % of Nyquist — comfortable margin for the
anti-alias roll-off, and standardised hardware (the I²S MEMS parts are specified for exactly this rate).
The **analysis band is set to 300 Hz – 15 kHz**, and the floor at 300 Hz is chosen to exclude the
coherent low-frequency content that is not a wall mode (§6.3).

**Why not a wideband accelerometer?** A piezoelectric accelerometer with a 20 kHz bandwidth and a charge
amplifier is technically capable of covering this range, and is the conventional instrumented-tap
configuration. It is rejected here on three counts, in order of weight: (i) **contact physics** — an
accelerometer measures the motion of whatever it is attached to, so on a hand-held probe it measures the
probe, and only weakly the wall, through an unknown and variable contact impedance, whereas a microphone
pressed against the wall in a coupled cavity measures the **motion of the wall surface the cavity is
sealed to** — the cavity turns surface displacement into pressure, and that displacement is the quantity
that correlates with the defect; (ii) **cost and complexity** — a charge amplifier, its supply rails and its shielding are a
significant addition, whereas an I²S MEMS microphone presents a digital interface needing no analogue
front end and no charge-amplifier layout discipline; (iii) **EMC** — the preamplifier would sit
centimetres from a solenoid switching 1.92 A, whereas the microphone's digital output is immune to that.
This is a defensible engineering trade-off, recorded here so the choice is auditable rather than
assumed.

## 5.9 Acoustic coupling to the wall: the probe cavity as a design element

The microphone must be coupled to the wall surface. If it is simply pressed against the wall with an
open front port, the sensor's own protective arrangement forms an acoustic cavity, and that cavity has a
**Helmholtz resonance**,

$$f_H = \frac{c}{2\pi}\sqrt{\frac{A}{V L}}$$

where $A$ is the port area, $V$ the cavity volume and $L$ the effective port length.

**Table 5.6 — Helmholtz resonance of the microphone front cavity.**

| Cavity $V$ [mm³] | Port dia [mm] | $L_{eff}$ [mm] | $f_H$ [Hz] |
|---|---|---|---|
| 500 | 3.0 | 3.0 | 3747 |
| 500 | 2.0 | 1.5 | 3533 |
| 300 | 2.0 | 1.5 | 4561 |
| 200 | 2.0 | 1.5 | 5586 |
| 200 | 1.5 | 1.0 | 5131 |
| 100 | 1.5 | 1.0 | 7257 |
| 100 | 1.0 | 0.8 | 5409 |
| 50 | 1.0 | 0.8 | 7649 |

**This is a hazard, not a footnote.** A cavity of 100–500 mm³ behind a 1.5–3 mm port resonates at
**3.5–7.6 kHz, squarely inside the analysis band**, and would impose a strong, geometry-dependent
coloration on the spectrum that has nothing to do with the wall. Because the cavity's resonance depends
on how hard the probe is pressed — which changes the port seal and the effective volume — it would also
inject a *contact-dependent* spectral artefact, exactly the failure mode the design is trying to
eliminate.

**Design response.** Three mitigations, applied together: (i) **minimise the cavity** by seating the
microphone's port flush with the contact face, so $V$ approaches the sensor's own internal volume
(O(10) mm³) and $f_H$ moves above the analysis band; (ii) **make the contact a compliant seal** so that
the wall–port interface behaves as a fixed termination rather than a variable leak; (iii)
**characterise it** by measuring the probe against a rigid steel block, whose return is
indistinguishable from an ideal reflector, and confirming that no in-band peak appears. Mitigation (iii)
is meaningful because a *probe resonance* is a property of the probe and must reproduce across units,
whereas a *wall mode* cannot.

## 5.10 Predicted feature behaviour: the falsifiable claims of the design

The model makes specific, checkable predictions. Stating them explicitly is what turns the report from
description into engineering, and Chapter 8 tests each.

| # | Prediction | Basis | Tested in |
|---|---|---|---|
| P1 | $f_{\text{peak}}$ is invariant in the intact state, and is dominated by the strike transient | Intact $f_1 > 15$ kHz in all materials (Table 5.3) | §8.2 |
| P2 | $f_{\text{peak}}$ falls monotonically with debond diameter for a fully debonded region | $1/a^2$ law | §8.5 |
| P3 | $f_{\text{peak}}$ is a *poor* single-channel detector, because intact and small-debond cases are both out of band | Table 5.3 rows 1–3 | §8.4 |
| P4 | Low-frequency energy fraction (`band_ratio_lh`) rises with debond severity once the mode enters the band | Mode energy moves below the 1 kHz crossover | §8.2 |

The P4 row is recorded here as it was **pre-registered**, including its stated mechanism, so that §8.7
can report the failure against the prediction that was actually made rather than one that has been
quietly repaired. The mechanism is wrong: §5.5's own tables put every detectable mode at 1.3–14.8 kHz,
i.e. **above** the crossover, so a debond moves energy past the crossover from the low side and the
ratio **falls**. §8.7 P4 records this and §6.5's feature table has been corrected.
| P5 | `decay_tau_ms` is **not** usable for render or stone in the detectable range | $\tau = Q/(\pi f_1) < 3$ ms for $f_1 > 5$ kHz (Table 5.7) | §8.4 |
| P6 | The smallest detectable debond is 7 cm (tile), 8.8 cm (render), 11.3 cm (stone) | Table 5.4 | §8.7 |
| P7 | Repeated taps at one location vary by less than 5 % in $f_{\text{peak}}$ | Rigid mounting fixes geometry | §8.3 |
| P8 | A two-parameter fit $f^2 = A/a^4 + B$ outperforms $f = C/a^2$ | §5.2 | §8.5 |

**P5 deserves emphasis because it contradicts the original plan.** The plan assumed a debond produces a
longer ring-down. That is true in the sense that $\tau = Q/(\pi f)$ grows as $f$ falls, but the
firmware's resolvable window is 3–60 ms, which at $Q=10$ corresponds to $f_1$ between about 53 kHz and
1.06 MHz — **entirely above the analysis band**. Within the band, the predicted decay times are:
tile 3.5–13.8 ms for 20–40 cm debonds (resolvable), and below 3 ms for render and stone at every
detectable size (not resolvable). The consequence is that `decay_tau_ms` carries usable information
**only for ceramic tile at large diameters**, and is a dead channel for render and stone. That is a
finding the report must state plainly, and it constrains the feature set in §6.5.

**Table 5.7 — Predicted ring-down time $\tau = Q/(\pi f_1)$ [ms].** A dash is outside the 3–60 ms
resolvable window.

| Material | $Q$ | 10 cm | 15 cm | 20 cm | 30 cm | 40 cm |
|---|---|---|---|---|---|---|
| Ceramic tile 8 mm | 20 | — | — | 3.5 | 7.8 | 13.8 |
| Cement render 20 mm | 10 | — | — | — | — | 4.4 |
| Stone cladding 25 mm | 15 | — | — | — | — | 4.0 |

## 5.11 Model validation and its limits

The closed-form model was cross-checked against a **layered transfer-matrix** formulation — the
quarter-wave stack of substrate, finish layer and probe baseplate, solved as a 4 × 4 system with
consistent nodal masses — and against the classical clamped-plate eigenvalue
($\lambda^2 = 10.2158$ for mode $(0,1)$). Agreement in the limit $k \to 0$ is within 1 % for the
thin-layer cases, with divergence for the stone case, where the thin-plate assumption is weakest
($h/a = 0.25$ at a 20 cm diameter, and 0.5 at 10 cm). **The model is therefore best trusted for ceramic
tile and cement render, and indicative only for thick stone cladding below ~20 cm** — a limitation
carried into Chapter 9.

The model does **not** include: the substrate's own compliance (the concrete is treated as rigid ground
under the foundation spring), layer damping as anything other than a lumped $Q$, the transducer's
directional response, the probe's own transfer function, or the Poisson coupling between the mode and
the displacement-to-pressure conversion inside the microphone's front cavity. Each is a source of error in the absolute numbers and none is a source of
error in the *trends* on which the design decisions rest. The distinction between quantitative claim
and trend claim is maintained throughout Chapter 8.

---

# 6. Mechanical and Contact Design

## 6.1 The mechanical problem, stated

Chapter 4 established what the signal is and where it lives in frequency. Chapter 6 addresses the
question that determines whether that signal is *measurable*: **the strike is only informative if the
contact conditions are the same every time.** Every quantity the instrument reports is a function of
the wall's mechanical impedance convolved with the probe's own transfer function and the contact
impedance between them. The design goal is therefore to make the last two terms as close to constant as
the physics permits, and to *measure* what variance remains rather than assume it away.

Three error sources dominate, in decreasing order of size:

| # | Error source | Physical origin | Control |
|---|---|---|---|
| M1 | Press force / contact area | Operator hand pressure varies; the contact patch area changes | Fixed contact geometry (three feet), **bottoming housing with a geometric preload (§6.4.1)**, contact-quality indicator |
| M2 | Probe structural modes | The baseplate, solenoid body and clamp each have resonances that appear in every measurement | Locate them, keep them out of band, treat as common-mode |
| M3 | Strike repeatability | Plunger energy varies with supply voltage, temperature, wear, and seating | Regulated supply, fixed pulse width, interlock, measured pass criterion |

M1 and M2 are properties of the hardware and are addressed in this chapter; M3 is addressed in the
firmware and is *measured* in Chapter 8.3.

## 6.2 Strike mechanism

**Actuator.** A **LSD-1040B push–pull solenoid** (DC 12 V, ~23 W) provides the excitation. The
selection criteria and the alternatives are graded in Appendix B.3.

**Why a solenoid and not a hammer on a spring.** A returned-mass impactor (a hammer driven by a spring
or a cam) delivers a strike energy set by the spring constant and the release geometry, which is
mechanically stable but hard to modulate and harder to hold constant as the mechanism wears. A solenoid
delivers an energy set by **current and time**, i.e. by electrical quantities that are trivial to
regulate, log and reproduce. Repeatability is therefore pursued in the electrical domain, where it is
cheap, rather than in the mechanical domain, where it is not.

**Pulse width.** §5.6 selects a contact time of $T = 300\ \mu s$ and explains why. The achieved contact
time is a property of the plunger mass and the compliance of the striking cap, not of the electrical
pulse width — the electrical pulse only needs to be long enough to accelerate the plunger fully. The
firmware drives a **120 ms** pulse [Appendix D], which is long relative to the plunger's mechanical
travel time and short relative to the 23 W coil's thermal time constant, and the achieved contact time
is verified on the bench with a piezo film sensor (Appendix C.3). If the measured contact time differs
materially from 300 µs, the **cap material is changed** (harder cap → shorter contact), not the
electrical pulse — that is the correct lever, and it is worth saying because the intuitive lever is the
wrong one.

**The cap is a specified part, and it has to be, because a bare metal tip fails two ways at once.**
§5.6 fixes the contact time $T = 300\ \mu s$ and §C.3(a) says to change the *cap material* if the measured
contact time is wrong. That instruction assumes a cap exists; a plunger striking the wall with its bare
metal tip is not that.

Hertzian contact between a steel tip and cement render ($E_{render}$ = 18 GPa) gives a contact radius
$a_c = (3FR/4E^*)^{1/3}$. At a working force of 20 N with a 5 mm radius tip that is $a_c \approxpprox 0.16$ mm,
and the mean contact pressure is

$$p_{mean} = \frac{F}{\pi a_c^2} \approx 240\ \text{MPa},$$

against a render compressive strength of **20–40 MPa**. **The tip indents the wall** — and the deeper
problem is that it indents the *reference region* too, since §C.5 step 1 requires five taps on a region the
inspector judges bonded. A damaged reference is not a reference.

**Enlarging the tip radius is the fix, and it is nearly free.** The pressure falls as $R^{-2/3}$ while the
interface spring $k A_c$ — which is what the tap actually measures (§5.1) — stays dominant in the series
combination at every radius, because cementitious render is three to four orders of magnitude softer than
steel. So the radius can be raised for the pressure's sake without giving up the measurement:

| Tip radius | $a_c$ | $p_{mean}$ | Interface share of the series stiffness |
|---|---|---|---|
| 5 mm | 0.16 mm | ~240 MPa | >99 % |
| 20 mm | 0.26 mm | ~95 MPa | >99 % |
| 50 mm | 0.35 mm | **~52 MPa** | >99 % |

Even at 50 mm the pressure is above the render's strength, which is why the cap is not merely a larger
metal tip but a **compliant** one: POM or nylon (roughly 3 GPa) spreads the load further and, more
importantly, is softer than the wall, so the contact is defined by the cap's compliance rather than by
crushing the substrate.

**A cap that is a coating does not work.** Elastic contact over a layer whose thickness is less than the
contact radius still feels the stiff substrate beneath; the practical threshold is a layer three or more
times the contact radius. The contact radius at 20 N through nylon is of order 0.3 mm, so a usable cap is
**millimetres thick**, not a paint-on film.

**Two things the cap must therefore be, and one it must not be.** It must be **thick enough** to behave as
bulk polymer (2–3 mm), and it must reach roughly **20–30 mm of tip radius** so the contact pressure comes
down to the render's own strength. It must **not** be permanently bonded to the plunger, because §C.3(a)
treats it as an interchangeable part and because **its shape wears**. That last point is not cosmetic:
$T = \pi\sqrt{m_{eff}/K}$ and $K$ tracks the contact area, so a cap that starts as a 5 mm sphere and wears
flat changes the contact time by an order of magnitude, and with it the position of the strike's spectral
null (§5.6). **The contact-time check of §C.3(a) is therefore a periodic check, not a one-off
commissioning step**, and the cap should be designed to be swapped rather than re-machined.

**The hold problem, and why it is accepted.** A push–pull solenoid does not release the instant it
strikes: the plunger reaches the wall early in the electrical pulse and is then *held* against it for
the remainder of the energisation, roughly 100 ms of the 120 ms. That sustained contact is a
quasi-static load, so it contributes negligible vibratory excitation — a static push excites no modes —
but it does two things that must be understood rather than ignored:

1. **It changes the boundary condition during the measurement**, because the plunger is a stiff
   mechanical link between the solenoid body and the wall at the moment the wall is ringing. This is a
   *systematic* effect, identical in every measurement, and it is therefore absorbed by the same
   model-level common-mode argument that absorbs the probe's own modes (§6.3). It is not a random error,
   and it does not need removing — only understanding.
2. **It means the analysis window must close before the hold ends.** The 21.33 ms FFT window of
   §7.2 sits entirely inside the 120 ms energisation, and the plunger's *release* transient at
   de-energisation falls outside it. Timing the capture against the energising edge rather than against
   de-energisation is therefore not a convenience; it is what keeps the measurement free of the
   release event.

**An optimisation deliberately not taken.** The pulse could be shortened to a few milliseconds — long
enough for the plunger to travel, short enough to eliminate the hold — which would reduce both heating
and the boundary-condition change. It is not taken in this revision because the plunger's travel time is
not yet characterised (Appendix C.3a measures it), and a pulse shorter than the travel time produces a
*weak* strike whose energy varies with supply sag: it would trade a known systematic effect for an
unknown random one. Characterising the travel time and then shortening the pulse is listed as future
work (§9.5, item 2) and is a two-day task with a clear acceptance test.

**Thermal budget.** The solenoid is specified for 23 W at 12 V, i.e. **1.92 A**, and is an
**intermittent-duty** part: the manufacturer's rated duty cycle, not the on-time, is the limit. At the
survey cadence of one strike per two seconds the coil is energised for 120 ms out of 2000 ms, a 6 %
duty cycle, which is thermally comfortable for the part but only *because* the firmware enforces the
cadence. The protection is therefore a firmware responsibility and is implemented as three independent
guards [Appendix D.4]: a minimum inter-strike interval (2000 ms), a sliding duty-cycle budget that
forces a cooldown when exceeded, and an independent hardware-timer failsafe that de-asserts the MOSFET
gate if the main task fails to, so that a firmware hang cannot leave the coil energised.

**Supply.** A regulated 12 V rail is required: strike energy scales with $V^2$ and an unregulated
supply would couple battery state-of-charge directly into the measurement. The prototype uses a 12 V
2 A regulated adapter on the bench (Appendix C.6 forbids field operation on the adapter) and a
regulated DC–DC converter from the battery pack for the portable configuration.

## 6.3 Probe structural modes and the 300 Hz band floor

Chapter 5's band floor of 300 Hz was chosen on physical grounds; this section is where those grounds are
made explicit, because the choice is otherwise arbitrary.

**Every mode of the probe assembly appears in every measurement.** The baseplate, the solenoid body, the
clamp, the microphone housing and the operator's hand together form a mechanical system with its own
resonances, typically in the **100–800 Hz** range for a hand-held assembly of this size and mass. These
are *coherent* — they appear at the same frequency in every single measurement, bonded or debonded — and
they are therefore the dominant contributors to the spectrum *below* the first wall mode.

Two facts about them matter:

1. **They are unavoidable.** Making the probe heavier and stiffer moves them down in frequency; making
   it lighter and more compact moves them up. There is no configuration in which a hand-held assembly
   has no sub-kilohertz modes, because the hand itself supplies a soft, lossy interface that
   guarantees them.
2. **They are, to a useful approximation, common-mode.** A probe mode is a property of the probe. If
   the probe is used identically on a bonded reference and a suspect region, the probe's contribution to
   the two spectra is the same, and the *difference* between the two spectra is a function of the wall.
   This is the model-level common-mode rejection of §4.3.4 — the design's actual working principle.

**Design consequences.**

- **The 300 Hz floor excludes them.** Modes below 300 Hz are not analysed. This is not because they are
  uninformative in principle but because they are *not attributable to the wall*, and a feature built
  from them would be a feature of the operator, not of the building.
- **They must not be *excited* into the analysis band by non-linearity.** A hard strike against a
  compliant probe base can frequency-multiply: a 200 Hz mode driven hard enough produces content at
  400 Hz, 600 Hz and beyond. The rigid baseplate of §6.4 is stiffened specifically to keep the
  fundamental modes low and the non-linearity weak, and the strike energy is bounded by the firmware.
- **They are the reason a differential measurement is used at all.** The instrument's operating
  procedure (Appendix C.5) requires a bonded reference measurement on the same building, with the same
  probe, in the same session. That requirement exists precisely because it discharges the common-mode
  assumption. **A single measurement taken in isolation cannot be interpreted** — this is the single
  most important operational constraint in the report, and it is stated in the operating procedure, in
  the dashboard's documentation and in the conclusion.

## 6.4 Baseplate and mounting: what changed from the original design

The original plan fixed the MPU6050 and the solenoid rigidly to one acrylic baseplate, 5–10 cm apart.
That arrangement is retained in form but changed in function, because the sensing channel changed:

| Element | Original | Revised | Reason |
|---|---|---|---|
| Baseplate | 3–5 mm acrylic | **6 mm acrylic or 5 mm aluminium**, with a perimeter stiffening rib | Raise the fundamental mode and reduce flexural non-linearity (§6.3); acrylic is retained for the prototype because it is machinable and non-conductive |
| Accelerometer | Primary sensor, taped to the plate 5–10 cm from the solenoid | **Supervisory sensor**, mounted on the plate *away* from the strike axis, closest to the operator grip | It measures probe settling and press force, not the wall (§4.4); mounting it near the grip maximises its sensitivity to press force and minimises its excitation by the strike |
| Microphone | Not present | **Flush-mounted through the contact face**, cavity minimised per §5.9 | Primary channel; must see the wall, not the plate |
| Solenoid | M3 to the plate, striking head protruding | **M3 to the plate through a compliant washer pair**, striking head protruding 3 mm beyond the feet | The compliant washers reduce the reaction impulse coupled into the plate while preserving the geometric repeatability of the strike |
| Contact feet | None; the plate was pressed against the wall | **Three hard hemispherical feet** on a 60 mm circle, protruding 3 mm, coplanar with the strike head | Defines the contact plane and standoff, and makes press force transfer through a fixed geometry (M1) |

**The contact-feet change is the most important mechanical revision.** In the original design the
baseplate itself was pressed against the wall, so the contact area — and therefore the coupled acoustic
load — was whatever the plate's flatness and the operator's grip produced. Three feet on a fixed circle
make the standoff and the contact geometry **deterministic**: the plate no longer touches the wall, only
the feet do, and the acoustic path from wall to microphone is through a fixed, repeatable gap. It
converts an uncontrolled variable into a fixed one, at the cost of a small, accurately-known standoff
that is characterised once (§5.9(iii)) and then constant.

**Microphone interface.** The microphone is seated in a machined recess with its port flush with the
contact face and the cavity behind it reduced to the sensor's own internal volume. The seal is a thin
silicone gasket, chosen to be compliant enough to seal without transmitting plate vibration directly to
the microphone body. A flexible coupling between the microphone housing and the baseplate is deliberate:
the microphone should be coupled **acoustically** to the wall and **mechanically** to the plate as weakly
as possible, and the gasket is what separates those two paths.

### 6.4.1 The housing, the preload and the recoil

§6.4 fixed *what* is rigid and *what* must be compliantly mounted. It did not say how the probe is held
against the wall, which is the other half of M1 in §6.1 — and that half is where the operator's hand
re-enters the measurement. This subsection closes it.

**The mechanism: a bottoming housing.** The probe assembly (three contact feet, microphone, solenoid)
is carried inside a housing whose rim stands **proud of the feet by a small, fixed amount δ**. When the
operator presses the instrument against the wall, the rim seats first and the operator's force then runs
**rim → wall**, bypassing the spring entirely. Only the preload itself is carried by the spring:

$$F_{pre} = k\,\delta$$

| Spring rate $k$ | $\delta$ for 10 N | for 20 N | for 30 N |
|---|---|---|---|
| 5 N/mm | 2.0 mm | 4.0 mm | 6.0 mm |
| 10 N/mm | 1.0 mm | 2.0 mm | 3.0 mm |
| 20 N/mm | 0.5 mm | 1.0 mm | 1.5 mm |
| 50 N/mm | 0.2 mm | 0.4 mm | 0.6 mm |

**A 0.5–3 mm protrusion therefore sets a 10–30 N preload, and the preload is fixed by the machined
dimensions of the parts, not by how hard the operator presses.** That is the point: §6.1 identifies press
force as error source M1, and this converts a *continuous, person-dependent* input into a *binary,
geometry-determined* one. It is a stronger answer to M1 than a spring compressed by hand, because the
quantity that matters (δ) is a drawing dimension.

**Two static jobs, and one the spring does not do.** The spring does exactly two things, both static:

1. **Seat the three feet** so the contact plane is defined by the probe, not by the grip.
2. **Load the microphone gasket** reproducibly. This is the §5.9 hazard: the Helmholtz resonance of the
   microphone cavity sits at 3.5–7.6 kHz, inside the band, and it shifts when the seal changes. A
   preload that does not depend on the operator's hand is what keeps $f_H$ from moving between taps.

**It does not resist the strike, and it cannot.** The strike impulse is
$J = F_{peak}T(2/\pi)$; for the design point ($F_{peak}\approx 60$ N, $T\approx 1$ ms) that is
$J\approx 0.038$ N·s. For a probe of mass $M$ the velocity change is $J/M$, and the displacement during
the contact is roughly $\tfrac{1}{2}(J/M)T$:

| Quantity | Value (at $M$ = 0.5 kg) |
|---|---|
| Velocity change $J/M$ | 0.076 m/s |
| Displacement during the ~1 ms contact | **38 µm** |

The probe stays put during the strike because of its own inertia; the standoff is never at risk. **$M =
0.5$ kg is an assumed figure and must be measured once the assembly exists** — but the conclusion is
insensitive to it, since the displacement scales as $1/M$ and would still be under 0.2 mm for a 100 g
probe.

**The new effect the housing introduces: post-strike recoil.** Because the probe now floats on the
spring, the strike reaction pushes it back and it oscillates at $f_s = \frac{1}{2\pi}\sqrt{k/M}$ with
amplitude $J/\sqrt{kM}$:

| $k$ | $f_s$ | Recoil amplitude | Fraction of a 3 mm standoff |
|---|---|---|---|
| 10 N/mm | 22.5 Hz | 0.54 mm | 18 % |
| 20 N/mm | 31.8 Hz | 0.38 mm | 13 % |
| 50 N/mm | 50.3 Hz | 0.24 mm | 8 % |

**This modulates the wall-to-probe coupling at 20–50 Hz, and the question is whether it smears the
spectrum. It does not, and the arithmetic is exact:** a 5 kHz mode amplitude-modulated at 30 Hz produces
sidebands at $5\,000 \pm 30$ Hz, and the FFT bin width is **46.875 Hz** — larger than the modulation
frequency, so *both sidebands fall inside the same bin as the carrier*. Nothing resolves, and nothing
smears. The recoil is therefore benign for `f_peak_hz`, `f_centroid_hz` and `band_ratio_lh`.

It does add variance to `decay_tau_ms`, which is the one feature that depends on the envelope rather than
the spectrum. That is acceptable, and it is worth recording that §5.10 already declares `decay_tau_ms` a
dead channel for render and stone — so the feature the housing degrades is the feature the physics had
already written off.

**There is no tight spring-rate constraint, which is the reassuring part.** The spring-mass mode must sit
below the 300 Hz band floor (§6.3), i.e. $k < (2\pi f)^2 M$; at $f$ = 300 Hz and $M$ = 0.5 kg that is
**k < 1780 N/mm**. Every practical spring qualifies by a factor of ten or more, so $k$ is chosen for
mechanical convenience (10–50 N/mm is comfortable) rather than against a hard bound.

> *A correction recorded for the reader's benefit.* An earlier draft of this subsection quoted the bound
> as "~170 N/mm". That is out by a factor of ten: the correct limit at $M$ = 0.5 kg is ~1780 N/mm. The
> conclusion — that the spring rate is not critical — is unchanged and in fact stronger.

**The preload value itself is not critical either**, because the *striking head* makes only a dynamic
contact: it is retracted at rest and touches the wall solely during the strike. The static preload never
loads the striker contact at all. It acts only on the three feet, whose job is to define the plane and
seat the gasket. **What the design therefore needs from $\delta$ is "enough to seat and seal", not
accuracy** — which is what makes a 0.5 mm tolerance on a machined protrusion acceptable in a hand-built
prototype.

**The three things this arrangement requires, stated so they can be checked:**

1. **The probe assembly stays internally rigid.** The spring acts only across *housing → probe assembly*.
   Inside that boundary, the striking head, the three feet and the microphone recess must have no elastic
   element between them, or the common-mode argument of §4.3.4 has nothing to stand on.
2. **δ has a lower tolerance limit.** It must still seat the feet and load the gasket at the smallest
   permitted protrusion; the upper limit is only a mechanical convenience limit.
3. **$f_s$ stays below 300 Hz** — satisfied by any spring of practical stiffness, but worth stating
   because it is the same design intent as the strike-pulse notch of §5.6: two independent mechanisms
   keeping the probe's own motion out of the analysis band.

**Why this belongs in Chapter 6 rather than Chapter 7.** The repeatability data of §8.3 is the evidence
that this subsection is load-bearing: the median within-location CV of `impulse_norm` is **14.92 %**, with
98.5 % of locations failing the 5 % criterion, and the contact-quality channel is the one that responds to
the operator's grip. **A housing that bottoms out turns the operator's action into a binary one, and a
binary action is the cheapest available reduction in that variance** — before any signal processing, and
without touching the feature set.

## 6.5 The feature set and why it has the members it has

Chapter 8 tests each feature; this section states what each is *for*, which is what determines the set.

| Feature | Definition | What it is for | Predicted behaviour |
|---|---|---|---|
| `f_peak_hz` | Frequency of maximum magnitude in 300 Hz–15 kHz | Locates the wall mode; the primary size indicator | Falls as $1/a^2$ for debonds above the size floor; uninformative below it (P3) |
| `f_centroid_hz` | Magnitude-weighted spectral centroid over the band | Robust proxy for the spectral balance; less sensitive to a single noisy bin than `f_peak` | Tracks `f_peak` but with lower variance |
| `band_ratio_lh` | Energy below 1 kHz / energy above 1 kHz | Detects the *presence* of a wall mode without needing to locate it; the **primary detection channel**, because a mode entering the band moves energy past the crossover whether or not it becomes the argmax | **Falls** as the mode enters the band from above (§8.7 P4 corrects the sign this table originally predicted) |
| `decay_tau_ms` | Log-linear fit to the envelope | Damping/ring-time | Useful **only** for tile at large diameters; a dead channel for render and stone (P5) |

**A correction to an earlier version of this section, because it changed the answer.** This section
originally claimed a **four**-member decision set, and Chapter 8's first run appeared to support it. It did
not: `decay_tau_ms` is the −1.0 sentinel for **100 % of bonded points and 95 % of fully debonded ones**,
giving AUC 0.507 with a 95 % CI of [0.504, 0.511] — chance, exactly as prediction P5 required and as this
section's own table predicted. The apparent four-feature performance came from `impulse_norm`, the
accelerometer channel, whose separation in `--demo` mode is produced by a class-coded constant in the
generator rather than by any physics (§8.0). **The decision set is therefore the three spectral
descriptors**, and the accelerometer's two channels remain *published and logged* but do not vote.

**Why three and not one.** §2.3.1 gave the reason: a debond's signature is spread across size *and*
severity, and a single scalar collapses them. `f_peak_hz` answers "how big"; `band_ratio_lh` answers
"is there a mode at all"; `f_centroid_hz` provides a low-variance corroboration of the first;
`decay_tau_ms` is retained despite being weak — it is informative in exactly the tile case that is the
most common Hong Kong facade — but its weakness is documented rather than hidden, and Chapter 8.4
reports its effect size honestly for every material.

**Why not a larger set.** More features would fit better and generalise worse, given the number of
panels available. The three-feature decision set is a deliberate constraint, and §8.4's group-wise
cross-validation is the check on whether it overfits. **The cross-validation says it does not need to
grow**: the single-threshold rule on `band_ratio_lh` alone reaches AUC 0.753 against the multivariate
logistic model's 0.755, so additional features buy nothing measurable on this dataset — which is the
outcome §8.4 committed in advance to reporting.

**A feature *not* used, and why.** The peak amplitude (`peak_au`) is measured and published but is
**not** used as a detection feature, because it is dominated by strike energy and contact quality rather
than by the wall (§2.3). It is retained in the payload because it is the natural sanity check on the
strike and because it is needed to normalise the other features during bench calibration. Excluding it
from the classifier while still publishing it is the honest arrangement: the data is available for
offline study, and the on-line decision does not depend on a quantity the design does not trust.

## 6.6 The contact-quality indicator

The accelerometer's supervisory role (§4.4) is implemented as a **contact-quality gate** with two
published values, `impact_peak_g` and `impulse_norm`, and one derived flag.

The logic is deliberately simple: `impact_peak_g` above an upper limit indicates the probe was
over-pressed or the strike was unusually hard; below a lower limit indicates the feet were not seated
and the probe was "floating". `impulse_norm` (the RMS of the accelerometer window) is the corresponding
energy measure. A measurement outside either window is **flagged, not discarded** — the firmware
publishes the flag and the raw values, and the platform can filter on it. Discarding on-device would
destroy the evidence needed to tune the limits; flagging preserves it.

**An honest statement of this indicator's weakness**, carried forward from §4.4: because the
accelerometer window opens after the solenoid pulse, neither value is the true peak contact impulse. They
are proxies for press force and settling, and they are named accordingly. Their *utility* is that they
are sensitive to the operator's grip, which is the dominant uncontrolled variable (M1), and their
*limitation* is that they cannot report the strike's absolute energy. Chapter 8.3 measures how much of
the residual variance they explain, which is the only way to know whether the gate is worth having.

## 6.7 Assembly, and what the mechanical design deliberately does not do

**Assembly sequence** (detail in Appendix C.2): baseplate stiffened and drilled → feet fitted and
coplanarity verified on a surface plate → solenoid mounted through compliant washers and its head
height set 3 mm above the feet with a shim → microphone recess machined, gasket fitted, port verified
flush → accelerometer bonded near the grip → wiring dressed so that no cable imposes a mechanical
constraint between the plate and the microphone housing → **probe assembly loaded into the housing
against its preload spring, and the rim protrusion δ set and measured (§6.4.1)**.

**Three things the design deliberately does not attempt**, each with its reason:

1. **It does not attempt to make the probe a rigid, non-resonant structure.** That is unachievable at
   hand-held scale and the attempt would trade one set of modes for another. The design accepts the
   modes and removes them by differential measurement (§6.3).
2. **It does not attempt to measure the strike force.** A force sensor in the strike path would measure
   the wall's *impedance* directly and would be scientifically superior — it is the conventional
   instrumented-tap configuration. It is rejected on cost and on the module's IoT framing: a force
   channel adds an analogue front end and a second calibration problem, and the object of the exercise
   is a deployable, cheap node rather than a laboratory instrument. This is a scoping decision, and it
   is the decision most likely to be challenged, so it is stated plainly.
3. **It does not attempt to eliminate hand tremor.** The 300 Hz floor and the differential procedure
   suppress its effect; a tripod or a wall-contact clamp would eliminate it and would also destroy the
   instrument's reason to exist (speed at height). The trade is deliberate.

---

# 7. Electronic Design, Firmware and Dashboard

## 7.1 Deployment architecture: a sensor node in Milestone 1, a gateway in Milestone 2

The module's objective O2 and MILO *b* concern **gateways and platforms**. It is therefore necessary to
be precise about what this system contains, because the words are not interchangeable:

| Role | Definition | This project, Milestone 1 | This project, Milestone 2 |
|---|---|---|---|
| **Sensor node** | A device that acquires data and transmits it; terminates the sensing interface | **Yes** — the ESP32 probe | Yes |
| **Gateway** | A device that *aggregates* one or more nodes, converts between protocols, and provides local processing or store-and-forward between a local network and a wider one | **No** | **Yes** — an ESP-NOW concentrator on a Raspberry Pi running a local MQTT broker |
| **Broker / platform** | The message broker and the application that stores, rules on and displays the data | Yes — MQTT broker + ThingsBoard CE | Yes |

**Milestone 1**, the subject of this report, is a **sensor node plus a platform**: the ESP32 acquires,
extracts features, and publishes MQTT directly to the broker over Wi-Fi. It is not a gateway, and
Chapter 3.4 records that calling it one would be indefensible under MILO *b*.

**Milestone 2** adds the gateway role and is specified but not built: the probe's radio is switched to
ESP-NOW, a Raspberry Pi acts as the concentrator and runs a local Mosquitto broker plus a
store-and-forward bridge to ThingsBoard, so that a survey conducted in a basement or behind a facade
still records and still synchronises. This is the architecture that matches a *deployment* — several
probes on a site, intermittent connectivity, a local aggregation point — and it is the honest answer to
"where is the gateway?" The gap between the two milestones is stated in Chapter 9 rather than papered
over by relabelling Milestone 1.

**Why not build Milestone 2 now.** The module's EA window does not admit it, and the marginal learning
from adding a second board and a broker is lower than the marginal learning from characterising the
sensor channel, which is where the project's technical risk actually lies. That is a scheduling
judgement, and it is recorded as such.

## 7.2 Sensing and drive electronics

**Microphone.** An **I²S MEMS microphone** (ICS-43434-class or equivalent) is the primary transducer.
Its selection follows from §5.8 and its placement from §5.9.

| Parameter | Value | Note |
|---|---|---|
| Interface | I²S, 24-bit capable, single-bit-clock | No analogue front end; immune to solenoid EMC (§5.8 iii) |
| Sample rate | 48 000 Hz | $f_{Nyq} = 24$ kHz; the 15 kHz ceiling is 62.5 % of Nyquist (§5.8) |
| Capture length | 4096 samples (85.3 ms) | The capture buffer; the FFT window is 1024 samples of it (see below) |
| Acoustic overload point | ≥ 120 dB SPL typical for the class | The strike at the probe face is loud; clipping would bias every spectral feature. Verify against the datasheet and, if the margin is thin, add a mechanical attenuator or reduce strike energy and re-tune the thresholds |
| Mounting | Flush port, minimised front cavity | §5.9 |

**Capture buffer versus FFT window — two different lengths.** The I²S capture is **4096 samples
(85.3 ms)**; the **FFT window is 1024 samples (21.33 ms, 46.9 Hz bins)** taken from it, opening
`PROBE_FFT_OFFSET_SAMPLES` = 192 samples (4.00 ms) in, i.e. 2 ms *after* the solenoid's energising edge.
The offset skips the MOSFET switching edge, the flyback-diode spike and the armature click, and still
covers the mechanical impact and the first, most energetic 21 ms of the ring-down. The tail of the
capture — everything after the FFT window — is what `decay_tau_ms` is fitted to, which is why the buffer
must be longer than the window: the ring-down is measured on samples that the frequency estimate does not
use.

**Why the FFT window is 1024 samples.** It must be long enough to resolve the lowest in-band mode. At
300 Hz, one cycle is 3.3 ms, so a 21.33 ms window contains six cycles — adequate for a stable spectral
estimate. A 512-sample window (10.67 ms, 93.75 Hz bins) would halve the resolution and place the 300 Hz
band floor three bins from DC, where the Hann window's response is still rising; 1024 samples is the
shortest length that gives a clean floor and a stable estimate.

**A discrepancy this section used to contain, recorded because it is instructive.** An earlier draft of
this chapter described the *capture* as 1024 samples and argued for that length, while the firmware
specified a 1024-sample *capture* and a 512-sample *FFT* — so the reported bin width (46.9 Hz) did not
match the firmware's (93.75 Hz), and the offline analysis script inherited the report's value rather
than the firmware's. The numbers in this section, in `probe_config.h`, in `06_analyze_tap.py` and in
Chapter 8 are now all on the 1024-sample FFT window at 46.875 Hz resolution, and the capture buffer was
stated separately because the decay fit needs samples beyond the window.

**Accelerometer.** An **MPU6050** on I²C at 400 kHz provides the supervisory channel of §4.4 and §6.6,
sampled over a window that opens *after* the solenoid pulse so that it captures probe settling rather
than the strike itself.

**Solenoid drive.** A logic-level N-channel MOSFET (**IRLZ44N** class) switches the coil:

```
                    +12V ──┬───────────────┐
                           │               │
                        [coil]           [bulk cap 470 uF]
                           │               │
                           ├───────────────┴─── GND
                           │
              (cathode)  ──┴──  (anode)          <-- flyback diode 1N5822, CATHODE TO +12V
                           │
                     ┌─────┴─────┐
   GPIO27 ──[220R]───┤  IRLZ44N  ├── SOURCE ── GND
                     └─────┬─────┘
                           │
                        [10k pulldown to GND]
```

Four elements are load-bearing and each addresses a specific failure:

| Element | Purpose | Consequence of omission |
|---|---|---|
| **Flyback diode** across the coil, cathode to +12 V | Clamps the inductive kick when the MOSFET opens | The kick is $L\,di/dt$ with $L$ of order 10–100 mH and $i = 1.83$ A: hundreds of volts, which destroys the MOSFET's drain |
| **Gate resistor, 220 Ω** | Limits gate charge current, slows the edge, and damps ringing with the gate capacitance | Fast edges radiate; the microphone's bit clock runs at ~3 MHz and is easily corrupted |
| **Gate pulldown, 10 kΩ** | Defines the gate low while the ESP32 is in reset or booting | The coil fires during boot — an uncontrolled strike, and a hazard |
| **Bulk capacitor, 470 µF** on the 12 V rail | Supplies the 1.92 A coil inrush from a local reservoir | The rail sags, the ESP32 browns out, or the DC–DC converter latches off |

**EMC.** The solenoid switches 1.92 A in a switching time of order microseconds, metres from a
microphone whose bit clock is a square wave. Three measures: the strike is issued when the radio is
idle where the schedule permits; the capture buffer is taken strictly around the strike and the
analysis band starts at 300 Hz, above the switching transients' dominant energy; and the radiating loop
is minimised by keeping the coil's return current path physically adjacent to its supply. The
microphone's digital interface is the principal defence — this is the third of the three reasons
recorded in §5.8 for preferring it to an analogue transducer.

### 7.2.1 SoC variant and the pin budget

The prototype is specified on an ESP32-WROOM-32 because that is the part the design was developed
against and because nothing in the signal chain needs more. The component discussion below is recorded
because two of the additions this report proposes — a joystick and a survey-guidance indicator
(§7.7.2, §9.5) — are pin-count sensitive, and because the choice of SoC variant turns out to have a
non-obvious cost.

**What is consumed unconditionally.** On an ESP32-S3-WROOM-1 module, **GPIO26 to GPIO32 are all seven
consumed by the in-package SPI flash** and are not available as general-purpose pins, on every variant:

| GPIO | Internal function | | GPIO | Internal function |
|---|---|---|---|---|
| 26 | SPICS1 | | 30 | SPICLK |
| 27 | SPIHD | | 31 | SPIQ |
| 28 | SPIWP | | 32 | SPID |
| 29 | SPICS0 | | | |

**The PSRAM variant then adds to that.** A **quad**-SPI PSRAM (the "R2" suffix, e.g. N16R2) shares the
flash bus and therefore consumes **no additional pins**. An **octal**-SPI PSRAM (the "R8" suffix, e.g.
N16R8) needs **GPIO35, 36 and 37 as well.** The suffix therefore changes the pin budget, which is not
obvious from the memory size it names.

**The consequence for this design.** The current pin map is:

| Function | GPIO | Available on S3? |
|---|---|---|
| I²S BCLK | 26 | ✗ flash |
| I²S WS | 25 | ✗ **GPIO25 does not exist on the S3** |
| I²S DIN (microphone data) | 33 | ✓ **on R2; consumed on R8** |
| I²C SDA / SCL | 21 / 22 | ✓ |
| Solenoid gate | 27 | ✗ flash |
| Trigger button | 32 | ✗ flash |
| Status LED | 2 | ✓ (but GPIO2 is ADC1_CH1 — see below) |
| Accelerometer interrupt | 35 | ✓ on R2 |

So a migration is **five lines of `probe_config.h`, not a redesign**: BCLK 26→14, WS 25→15, solenoid
27→18, trigger 32→4, with the microphone data line staying on 33. **The choice of R2 over R8 is what
keeps GPIO33 available**, and it is the reason the variant is specified rather than only the family.

**And the display does not need PSRAM at all.** PSRAM is usually reached for to hold a framebuffer, but
the arithmetic does not require it: a 240 × 320 RGB565 framebuffer is 150 KB, whereas the standard
small-panel technique is a **partial buffer** — typically one tenth of the screen, **15 KB** — flushed
by DMA. That sits in internal SRAM beside the ~37 KB of DSP buffers. For comparison, a full repaint over
SPI at 20 MHz takes 61 ms (16 fps), against a status screen that needs a few frames per second. **The
PSRAM and the parallel LCD interface are both for video-rate applications; this is not one.**

**Three constraints that are easy to miss, and all three bite on a joystick:**

1. **ADC2 is unavailable while Wi-Fi is active.** Only ADC1 (GPIO1–10 on the S3) can be used for the
   joystick's two analogue axes. A joystick wired to ADC2 works during bring-up and fails once the radio
   comes up — a fault that is genuinely hard to diagnose.
2. **GPIO2 is ADC1_CH1 as well as the status LED.** They do not conflict if the LED is used as a digital
   output, but the joystick must avoid it. Pin the joystick to ADC1_CH0 (GPIO1) and ADC1_CH2 (GPIO3).
3. **GPIO0, 45 and 46 are strapping pins** (GPIO0 default pull-up; 45 and 46 default pull-down) and
   must not carry a button or an analogue axis.

**One procurement trap.** On the **R16V** sub-variant — the "V" suffix — **GPIO47 and GPIO48 run at
1.8 V**, not 3.3 V, and 3.3 V logic on them damages the part. The plain N16R2 is not affected, but the
buzzer output is assigned to GPIO47 above, so the suffix must be checked at order time rather than
assumed.

**The revised map, with the additions of §7.7.2:**

| Function | GPIO | Note |
|---|---|---|
| I²S BCLK / WS / DIN | 14 / 15 / 33 | DIN unchanged — the reason for R2 |
| I²C SDA / SCL | 21 / 22 | Unchanged |
| Solenoid gate | 18 | Was 27 |
| Trigger button | 4 | Was 32 |
| REF button | 6 | New (§7.7.2) |
| Status LED | 2 | Unchanged; keep the joystick off it |
| **Joystick X / Y** | 1 / 3 | **ADC1_CH0 / CH2 — ADC1 only** |
| Joystick button | 5 | |
| Indicator ring | 38 | RMT-driven WS2812 (§7.7.2, §9.5) |
| Buzzer | 47 | LEDC/PWM at 200 Hz (§7.7.2); **check for the "V" suffix** |
| Accelerometer interrupt | 35 | Unchanged, unused |
| Console UART0 | 43 / 44 | Unchanged |

**Why this is recorded rather than just done.** The S3's advantage for this project is not its SIMD
instructions — a 1024-point FFT already takes about 1 ms against a 2000 ms cadence (§7.3), so a faster
transform is invisible. It is that **the S3 exposes roughly 35 usable pins against the ESP32's ~25**, and
the additions proposed in Chapter 9 (joystick, indicator ring, buzzer, optionally a display) need about
eleven of them. The migration is cheap now and becomes expensive once firmware exists — the same
argument §9.1 makes about building the probe: **the ordering matters more than the choice.**

## 7.3 Edge processing and the measurement pipeline

**One measurement is one strike**, and the pipeline is a fixed sequence with a hard 2 s cadence:

```
 trigger (button or console)
   │
   ├─ 1  interlock check .......... refuse if < 2000 ms since last strike
   ├─ 2  DMA capture armed ........ I2S reads into the 4096-sample buffer
   ├─ 3  solenoid pulse ........... GPIO27 high for 120 ms, then low
   ├─ 4  capture completes ........ ~21 ms of post-strike audio
   ├─ 5  accelerometer window ..... read over I2C, opens after the pulse
   ├─ 6  DSP ...................... DC removal, Hann, 1024-pt FFT (window at +4 ms)
   ├─ 7  grade .................... rule on (band_ratio_lh, f_peak_hz)
   ├─ 8  contact-quality flag ..... from impact_peak_g, impulse_norm
   └─ 9  publish .................. JSON over MQTT QoS 1 to probe/<dev>/measurement
```

**DSP detail.** The chain is fixed-point-free and allocation-free after initialisation: DC removal by
mean subtraction, a periodic Hann window, a self-contained radix-2 Cooley–Tukey FFT of 1024 points, then
the four features of §6.5 plus the auxiliary amplitude statistics. The window's coherent gain is
corrected in amplitude so that published values are comparable across firmware revisions — a detail that
matters because an uncorrected Hann window understates amplitudes by exactly 2× and would silently
double every threshold. **Compute budget:** a 1024-point float FFT on a 240 MHz ESP32 is of order 1 ms,
against a 2000 ms cadence, so the DSP is thermally and temporally negligible; the real-time constraint is
the *capture*, not the transform.

**Why the FFT runs on the node.** §3.4 records the assessment reasoning: the module requires a
device-to-application chain, and a node that ships raw waveforms to a server is a modem, not an edge
device. There is also a bandwidth argument — 1024 float samples per strike at 0.5 Hz is ~2 kB/s per probe,
which is fine for one probe and wasteful for a fleet — and a privacy argument, since a microphone on a
facade records more than the wall. Feature extraction at the edge sends only what is needed.

**And a consequence of that argument that Milestone 2 has to confront.** The published payload is
**381 bytes** as written — short keys would not help much, since the fields are what they are — against
**ESP-NOW's 250-byte single-frame limit**. The Milestone 2 radio therefore cannot carry the payload the
Milestone 1 firmware produces, and nothing in this report says how that is resolved. Three routes exist
and all are cheap, but choosing one is a design decision that has not been made: **a compact field
encoding for the link** (the gateway already knows `dev`, `sp`, `fw` and `strikes_total`, so the node
need not repeat them), **fragmentation across two frames**, or **carrying only the grade and the two
decision features over ESP-NOW while the full record goes to the local broker over Wi-Fi**. The point of
recording it here is that **"switch the radio to ESP-NOW" is a one-line statement in §7.1 and a concrete
payload-budget problem in the firmware**, and it should not be discovered at Milestone 2.

## 7.4 Transport security

**Finding that shapes this section.** MILO *d* — which concerns performance, hazards and security — is
**not** an assessment criterion for the end-of-module assessment. Per the Module Assessment Scheme,
only MILO *a* and MILO *b* are assessed in the EA mini-project; MILO *d* is assessed in the tests,
assignments and workshop components. Security is therefore **supporting evidence** for MILO *b*'s
"platform selection" requirement, not a primary scoring axis. It is treated here in proportion: rigorous
enough to be credible, bracketed against a published standard rather than hand-waved, and deliberately
not allowed to consume the effort that MILO *a* and *b* require. The full compliance matrix is
Appendix B.4.

| Control | Implementation | Standard |
|---|---|---|
| Transport encryption | MQTT over **TLS 1.3** on port 8883 | RFC 8446 [19] |
| Server authentication | **CA-chain validation** via the ESP-IDF certificate bundle, not a pinned leaf and not `skip_cert_common_name_check` | ETSI EN 303 645 §5.5 [11]; MQTT v5.0 §5.4.7 [18] |
| Device authentication | **Per-device unique credential**, provisioned at setup and stored in NVS; no shared fleet credential | EN 303 645 §5.1, §5.2 |
| Authorisation | Broker ACL restricts each device to its own `probe/<dev>/#` subtree | EN 303 645 §5.4 |
| Anonymous access | Disabled on the broker | — |
| Software update | Update path documented; signature verification and secure boot are **not** implemented (§7.6, Ch. 9.3) | EN 303 645 §5.3; NISTIR 8259A "Software Update" |
| State awareness | Device publishes connectivity state; LWT marks an ungraceful disconnect so the platform can distinguish "off" from "idle" | NISTIR 8259A "Cybersecurity State Awareness" |

**A trap worth recording because it is common and invisible.** A naive ESP32 TLS client often "works"
with certificate verification effectively disabled — the connection succeeds, so the developer assumes
security. The correct configuration is to attach the certificate bundle for chain validation and to
leave hostname checking enabled; the failure mode of getting this wrong is silence, not an error.
Appendix B.4.1 documents the exact configuration, the memory cost (the bundle occupies flash and the
handshake's peak heap grows with the RSA key size, which matters on a 320 kB part), and why the
in-memory cost is acceptable here — the survey's connectivity is on a controlled network and the
handshake happens once per session, not per measurement. **Verification note:** the ESP-IDF bundle's
contents change between SDK releases; pin the IDF version used for the submission and record it.

## 7.5 Platform and dashboard

**Selection.** **ThingsBoard CE**, self-hosted in Docker. The comparison against the alternatives is
Appendix B.3; in summary: it provides device registry, MQTT ingestion, a telemetry store, a rule engine
for alarms and a configurable dashboard **in one open-source package that runs on a laptop**, at zero
licence cost, with no per-message fee. The alternatives each fail one of those: a general-purpose cloud
IoT service metered per message would cost more than the instrument at fleet scale; a time-series
database alone provides no device model or dashboard; a purpose-built NDE cloud product is both
unavailable at this scale and not part of the IoT toolchain the module teaches.

**Data model.**

| Entity | Key | Contents |
|---|---|---|
| Device | `probe-<id>` | Named per physical unit; carries the unit's calibration record |
| Telemetry | `ts` in the payload | All features plus `grade`, `confidence`, `sp`, `rssi`, `strikes_total` |
| Alarm | threshold rule on `band_ratio_lh` and `grade` | Raised when the cost-optimal threshold of §8.6 is crossed |
| Attribute | `panel_id`, `location_id` | The survey grid reference, so a reading is spatially indexed |

**The dashboard** shows: the latest measurement's key values as tiles; a time series of
`f_peak_hz` and `band_ratio_lh` for the selected device; a per-location table so a survey can be read as
a grid; and the alarm state. **The dashboard must display the `sp` flag prominently**, because a
demonstration run in simulation mode produces perfectly plausible-looking data and a viewer who does not
know it is simulated will draw conclusions from it. The flag is set in the payload by the firmware and
the dashboard renders it as an unmistakable marker — this is N8, and it is treated as a safety-critical
requirement rather than a nicety, because the consequence of getting it wrong is a decision-maker
believing a fabricated hollow-spot map.

**Threshold display.** The thresholds shown are the *defaults* from `probe_config.h`. The dashboard
displays the rule's inputs and output but does not pretend the thresholds are physically derived: they
are set from the reference-panel calibration of Appendix C.4 and re-set if the panel set changes. A
dashboard that presents a threshold as authoritative when it came from a default constant is the
plausible-looking failure this project is most concerned to avoid.

## 7.6 Power, thermal and safety

**Power.** 12 V regulated for the solenoid, 5 V for the microphone board, 3.3 V from the ESP32's
regulator. Average draw at the 0.5 Hz cadence is dominated by the Wi-Fi radio; the solenoid's 1.92 A is
a 6 % duty load. The ≥4 h target (F8) is specified but **not yet measured**, and is reported in
Appendix C as an unverified requirement rather than a result.

**Thermal.** Three firmware guards (§6.2, Appendix D.4) plus the duty-cycle budget. The physics: 23 W
into a coil of a few grams of copper raises the winding temperature at a rate of order tens of kelvin per
second of continuous energisation, so the 120 ms pulse is thermally trivial and the *bank of consecutive
strikes* is the risk. The sliding budget bounds that, and the failsafe timer is the independent check on
the bound.

**Residual safety items, stated rather than solved.**

| Item | Status |
|---|---|
| 12 V supply and inductive kick | Handled by the driver design (§7.2); prototype bench-only |
| Operator acoustic exposure | **Not characterised.** §3.2 explains why the peak-level argument is weak, and Appendix C.7 gives the reasoning; the honest position is that exposure is a pending item |
| Working at height | Any real deployment is on a suspended platform or gondola under the relevant safety regime; out of the prototype's scope and listed in Ch. 9 |
| Battery handling | The portable configuration uses a Li-ion pack; charging, protection and transport are deferred with the portable configuration |
| Moving parts and pinch hazards | Plunger travel is 3 mm at low force; residual risk judged low, not formally assessed |

## 7.7 The person in the loop, and what has to be entered before a measurement

This section exists because the abstract promises a *deployed* system and §3.4 claims a device-to-application
chain, and neither claim is legible until it is stated what the operator does and what the instrument is
told. It is also where the design's real dependency on a human is made explicit rather than implied.

### 7.7.1 What must be entered, and what must not

The system needs **no material properties at runtime.** `probe_config.h` contains pin numbers, sample rate,
band edges, the 1 kHz crossover, four decision thresholds and the contact-quality window — and nothing else.
There is no finish thickness, no elastic modulus, no density, no wall thickness. That is correct, and it is
deliberate: the feature extractor performs an FFT and four ratios, none of which requires knowing what the
wall is made of.

The physical model of Chapter 5 is therefore an **interpretation layer, not a measurement layer.** It explains
why the band is where it is and what a given frequency would mean; it does not run on the device.

**What this costs, stated plainly.** A reading of `f_peak_hz` = 609 Hz does not, on its own, mean "a 10 cm
debond". Converting a frequency into a size uses $f_1 \propto 1/a^2$, and the position of that curve is set by
$E$, $\rho$ and $h$ — three quantities the instrument cannot measure and the operator cannot be expected to
know. Table 5.8 makes the problem concrete: the floor moves from 4.4 cm to 10.7 cm across finish thicknesses
that a surveyor would describe with the same word.

**The substitute is a reference region, and it is not optional.** §4.3.4 and §6.4 establish that the working
principle is a *two-surface differential measurement*: the suspect region is compared against a region the
inspector judges bonded, using the same probe and the same contact procedure. That single procedure absorbs
three things at once:

| What the reference cancels | Why |
|---|---|
| The probe's own transfer function | Common to both surfaces on the same probe (§6.4) |
| The finish's material constants ($E$, $\rho$, $h$) | They set where the reference's own spectrum sits, so the comparison carries them implicitly |
| The session's environmental baseline | Temperature, humidity and mounting conditions are shared |

**This is the honest answer to "what do I have to enter before a measurement?" — nothing about the wall, but a
bonded reference region must be established first, in the same session, on the same facade.** A single tap in
isolation remains uninterpretable, exactly as §C.5 states.

**And the residual limitation, which the report has not stated before.** Because the quantity being compared is
*relative*, the instrument **cannot report an absolute debond size**, and it cannot state a size floor for a
building whose finish build-up is unknown. Chapter 8's size-frequency tables describe the physics of the
measurement; they are not a field calibration. §9.4 records this.

### 7.7.2 Device-side feedback: LED, buzzer, and two buttons

The firmware as specified has a trigger button (GPIO 32) and a status LED (GPIO 2) that only blinks as a
heartbeat. Three additions make the instrument's state legible to someone holding it, and the report already
requires one of them as a safety measure.

**LED state encoding.** The LED currently carries no information; the state it *should* carry is the one the
operator cannot otherwise see — whether the measurement about to be taken is trustworthy.

| LED | Meaning | Source |
|---|---|---|
| Green, solid | Link up, time synced, reference set | MQTT connected, SNTP synced, NVS reference present |
| Green, short blink | Measurement taken and published | MQTT PUBACK received |
| Amber, slow blink | **Contact quality failed — re-strike** | `contact_ok` false (§6.6) |
| Red, solid | No link, or time not synced | §7.4 requires sync before publishing |
| **Blue, continuous** | **Simulation mode active** | `sp: true` |

The blue state is the implementation of §7.5's requirement that simulated data be unmistakable. That
requirement was written because a simulated reading is indistinguishable from a real one; a blue LED on the
device is a stronger guard than a caption on a dashboard, because it is visible at the point of measurement.

**Buzzer: constraints before convenience.** A buzzer is an in-band acoustic source mounted on the same rigid
baseplate as the microphone, so it is a design hazard rather than an accessory. Three constraints, all of
which can be satisfied:

1. **Frequency below the band floor.** `PROBE_FMIN_HZ` = 300 Hz, so a buzzer at **200 Hz is invisible to the
   analysis**: even if it couples into the microphone, that content is discarded before any feature is
   computed. A high-frequency buzzer is the wrong choice — 15–24 kHz is sampled but then filtered out, and a
   buzzer anywhere inside 300 Hz–15 kHz would appear in the very spectrum it is reporting on.
2. **Time-gated to after the capture.** The capture buffer is 4096 samples = **85.33 ms**, of which the FFT
   window is t = 4.00–25.33 ms and the accelerometer window is t = 2–62 ms. Even though a sub-band buzzer
   cannot contaminate the *spectrum*, it can contaminate the *accelerometer's* contact-quality window, since
   the buzzer shares the baseplate. The buzzer therefore sounds **at t ≈ 90 ms, after the whole capture**.
3. **Duty.** At the specified 1 strike / 2 s cadence a 90 ms tone is a 4.5 % duty cycle, so it does not
   interact with the solenoid's thermal budget (§7.6).

The 90 ms delay is imperceptible to the operator, and it makes the guarantee absolute: **the buzzer can never
contribute to the measurement it reports.**

**What the buzzer may and may not signal.** It reports the **trustworthiness of the measurement**, never the
condition of the wall:

| Tone | Meaning |
|---|---|
| One short | Accepted and published |
| Two short | **Contact quality failed — re-strike** |
| Long (> 500 ms) | No link, or time not synced |
| Silent | Measurement in progress |

**There is deliberately no "debond found" tone.** The decision thresholds in `probe_config.h` are labelled
PLACEHOLDER and have not been calibrated (§C.4 defines the procedure that would calibrate them). Driving an
alarm from an uncalibrated threshold would present an unvalidated number as a finding, which is the failure
mode §8.0 was written to prevent. The grade is published to the dashboard for offline study; it is not
asserted at the point of measurement.

**A reference button, and what it stores.** §C.5 step 1 requires the operator to establish a bonded reference
before surveying. That step currently has no device-side support at all, which is the largest practical gap in
the operating procedure. A second momentary button fixes it:

1. The operator holds the probe on a region judged bonded and presses **REF**.
2. The firmware takes the configured number of taps (three by default), rejects any that fail the
   contact-quality gate, and stores the median `f_peak_hz` and `band_ratio_lh` in NVS under a session record.

| NVS field | Example | Why it is kept |
|---|---|---|
| `ref_f_peak_hz` | 328.1 | The comparison's origin |
| `ref_band_ratio` | 0.800 | The second axis of the comparison |
| `ref_taps_used` | 3 of 5 | Records how many taps survived the quality gate |
| `ref_unix_time` | 1 760 000 000 | A reference from another session is not valid |
| `ref_dev_id` / `ref_fw` | `probe-01` / `1.0.0` | A reference from another probe is not valid |
| `ref_temp_c` | 24.1 | A survey compared against one taken in different weather is not supported |

Every measurement then publishes its deviation from the stored reference alongside the raw features, so the
dashboard can plot a survey relative to its own baseline rather than against an absolute number.

**One addition the architecture makes possible cheaply, and which the project should note.** §4.4 and §6.6
record that the accelerometer window opens *after* the strike, so `impact_peak_g` is a proxy for press force
rather than the true contact impulse. Extending that window to **straddle the strike** (for example
t = −60 to +60 ms instead of +2 to +62 ms) costs about 240 bytes of buffer at the ~1 kHz poll rate and would:
(i) make `impact_peak_g` an actual impact peak, closing a weakness the report currently declares; and (ii)
give the accelerometer a genuine 0–500 Hz **background channel**, because for the first time it would sample
the wall while the solenoid is quiet. That second use is what the original design was reaching for with its
3-second silent baseline — but in the correct place, on the *sensor* that can see below 500 Hz, and without
claiming to subtract a striker term that does not exist in the baseline (§4.3.2).

**A sensor already fitted and currently unused.** The MPU6050 is a **six-axis** part — three
accelerometers *and three rate gyroscopes* — and the firmware configures `MPU6050_REG_GYRO_CONFIG` at
initialisation but never reads the gyro data registers. Enabling them costs **no new hardware, no pins and
no board change**: three more I²C reads in the same transaction the accelerometer already makes.

What the gyro supplies is the **tilt of the probe** (by integrating rate during the 85 ms capture, or from
the static gravity vector between strikes), which is the one quantity §6.4 identifies as uncontrolled and
which §8.3 shows is the dominant residual: the median within-location CV of `impulse_norm` is **14.92 %**,
with 98.5 % of locations failing the 5 % criterion. Probe **orientation** is a component of that variance
that is currently neither measured nor logged. Recording it does not remove the variance, but it makes it
attributable — a reading that departs from its neighbours can then be checked against a tilt difference
rather than blamed on the wall.

**It is also the prerequisite for the survey plan of §9.5 item 7.** Identifying "the same point" across two
surveys needs a position *and* an orientation: two taps at the same coordinates but with the probe rotated
are not necessarily the same measurement, and the gyro is what distinguishes them.

**This is the one part of the survey capability that is genuinely free, and it is worth saying so plainly
because the rest of it is not.** §9.5 item 7 (four in-plane TOF sensors, a cloud-issued plan, guidance to
the operator) is a **three-to-four week platform build**: the I²C bus will carry the ranging parts, but
device addresses, drivers, the state-machine hook, payload fields and — most significantly — an MQTT
*downlink*, which does not exist at all today, all have to be built. The gyroscope is different: **the
part is already fitted, already wired, already initialised, and simply not read.** Nothing below is
reserved; this one thing is.

**The guidance tone adds one item to an open account, and it is not a measurement problem.** The buzzer
sounds only while the probe is *moving*, so it cannot fall inside a capture: the states are mutually
exclusive, and no timing gate is required. But the operator's **acoustic exposure** is a separate axis
that no amount of measurement cleanliness affects, and §C.7 records exposure as uncharacterised for the
*strike*. A guidance tone is continuous rather than impulsive, so it changes the time dimension of that
account rather than its level. Estimated at a typical small magnetic buzzer's sensitivity, a four-hour
session gives an eight-hour equivalent of roughly **77 dB(A)** — below the 85 dB(A) action level, and
therefore not a hazard, but **estimated rather than measured, and it belongs in the same pending item as
the strike**.

### 7.7.3 The operating loop, stated once

```
  human   selects and taps the reference region, presses REF
  machine takes 3-5 taps, quality-gates them, stores the median in NVS
  human   confirms the reference on the dashboard (the one unrepeatable step)
  ---
  human   moves the probe to a grid point and presses TRIGGER
  machine strikes, captures 85 ms, extracts features, grades, publishes
  machine >= 90 ms later: one short tone = accepted; two = re-strike
  human   on two tones: re-seat the probe and strike again
  human   moves to the next grid point
```

**This is not an autonomous detector.** It is an instrument that makes one judgement it can defend — whether
the contact was good enough to trust — and hands a marked map to a person. §C.5 already says this in the
operator's words ("Mark, do not conclude"); §7.7 says it in the design's.

## 7.8 Survey output: the discrete table, and how it is rendered

The unit of a survey is not a tap — it is a **wall**. Appendix C.5 specifies how a wall is covered but
not what the result *is*, and this section supplies it.

### 7.8.1 The authoritative output is a table, not a picture

A survey produces a discrete sample set. That is the whole answer, and nothing downstream of it requires
any assumption about what lies between the sample points:

| Stage | Needs spatial continuity? |
|---|---|
| Feature extraction (§7.3) | No — per tap |
| The grade rule (§7.3 step 7) | No — per tap |
| The threshold analysis (§8.6) | No — per point, or per point repeated |
| The confusion matrix (§8.4) | No — per point |

**So the survey result is an $N \times N$ table, one cell per grid point, carrying the per-point decision
and the raw features behind it. No interpolation is used, and none is needed.** A cell is a measurement;
an empty cell is an unmeasured point. Both are meaningful.

### 7.8.2 Coverage: the grid pitch *is* the survey's resolution

The grid pitch is usually treated as an operational preference. It is not — it is the survey's
resolution, and it silently sets the smallest defect the survey can find. If a defect of side $s$ is
sampled on a square grid of pitch $p$, the expected number of points landing on it is $(s/p)^2$, and the
probability of at least one hit is $1-\exp[-(s/p)^2]$:

**Table 7.3 — Detection probability versus grid pitch, for a 10 cm defect.**

| Pitch | Points per m² | Expected hits on a 10 cm defect | P(at least one hit) | Survey time per m² |
|---|---|---|---|---|
| **50 cm (Appendix C.5 default)** | 4 | 0.04 | **3.9 %** | ~1 min |
| 30 cm | 11 | 0.11 | 10.5 % | ~2 min |
| 20 cm | 25 | 0.25 | 22.1 % | ~5 min |
| 10 cm | 100 | 1.00 | 63.2 % | ~20 min |
| 5 cm | 400 | 4.00 | **98.2 %** | ~87 min |

*Survey time assumes three taps per point at the 2 s cadence plus ~5 s to reposition, per m².*

**The default of §C.5 catches about four per cent of the defects the instrument is specified to find.**
That is not a criticism of the default — it is the correct default for a *screening* pass over a large
facade — but it has to be stated, because otherwise "the instrument detects 8.8 cm debonds" and "the grid
is 0.5 m" are read together and imply a capability the survey does not deliver. A 10 cm defect is missed
by 96 % of the points a 0.5 m grid places on the wall.

**The consequence for planning is that pitch is derived, not chosen.** The design question is "what is
the smallest defect this survey must find?", and the pitch follows from it: 5 cm for 10 cm defects, 10 cm
for 20 cm defects, and so on. **The grid is a stop criterion and it belongs in the survey plan, not in
the instrument's defaults.**

### 7.8.3 Rendering rules, if the table is rendered at all

A table of 100 numbers per square metre is unreadable as text, so a rendered map is useful. But the
rendering must not add information the sampling does not contain, and there is exactly one rule that
achieves this:

> **Render the table as flat-shaded cells on a nearest-neighbour (Voronoi) partition — one colour per
> measured point, cell boundary at the midpoint between neighbours. Do not smooth, and do not
> interpolate.**

The reason is that the two renderings make different claims:

| Rendering | What it implies | True here? |
|---|---|---|
| Smooth gradient / bilinear | "I measured between the points" | **No** |
| Flat Voronoi cells | "One measurement applies to this patch, and the patch is no smaller than the pitch" | **Yes** |

The magnitude of the error the smooth version introduces is not small. A smoothing kernel spreads one
point over roughly one cell, so the apparent extent of a defect is about $s + p$ rather than $s$:

**Table 7.4 — Apparent defect size under a smoothing kernel.**

| Pitch | True defect | Apparent blob | Overstated by |
|---|---|---|---|
| 50 cm | 10 cm | ~60 cm | **6.0 ×** |
| 50 cm | 20 cm | ~70 cm | 3.5 × |
| 20 cm | 10 cm | ~30 cm | 3.0 × |
| 10 cm | 10 cm | ~20 cm | 2.0 × |

At the Appendix C.5 default, a 10 cm debond renders as a 60 cm blob — six times its true extent. **And
§5.4's size–frequency relation sits immediately beside such a map, inviting exactly the inference the map
has invented.** Flat cells make the pitch visible in the picture: the eye sees 50 cm squares and
understands that nothing smaller was resolved.

**A second rendering rule, because the obvious choice is the wrong one.** The best single decision
feature is `band_ratio_lh` (AUC 0.753, §8.4), so it is the natural quantity to colour. But it runs
**inversely to severity** — a bonded region reads ~0.80 and a fully debonded one ~0.19 (§8.2), because a
mode entering the band moves energy *above* the 1 kHz crossover. Plotted "as is" against a red-equals-high
ramp, **an intact wall renders bright red and the debonds render blue.** The map must plot
the quantity $1-$`band_ratio_lh`, or invert the ramp, and the legend must state which was done.

### 7.8.4 What the map must carry, and the one sentence it must contain

Every field below is tied to a boundary the report has already established, and each is a thing a reader
would otherwise assume:

| Field | Bound to |
|---|---|
| **Grid pitch, and points taken of points planned** | Resolution (§7.8.2) — nothing below the pitch is resolved |
| **Valid taps of taps attempted, per point** | The contact-quality gate of §6.6 and §7.7 |
| **The reference point and its values** | §4.3.4 — this is a *differential* measurement |
| **Probe serial, firmware version, date** | The NVS record of §7.7.2 |
| **Finish construction, if known** | Table 5.8 — the size floor scales as $\sqrt{h}$ |
| **The threshold used, and the prevalence it assumed** | §8.6 — a threshold is a deployment parameter, not a constant |
| **The finish's assumed material, if the size relation is used at all** | §5.3 |

And one sentence, in the operator's own words, printed on the map rather than buried in a manual:

> **A highlighted cell means "re-inspect this location with a hammer". It does not mean "a defect of
> this size is here".**

That is §C.5's "Mark, do not conclude" stated where it will actually be read. The map's function is to
concentrate an inspector's attention on the right few square metres; it is an **attention index**, and
§C.5 already calls it one.

---

# 8. Validation Methodology and Results

## 8.0 What this chapter does and does not establish

**Read this before reading any number below.**

Every quantitative result in this chapter is produced by the analysis script `06_analyze_tap.py` running
in `--demo` mode, which generates a dataset from the forward physical model of §8.1. **No measurement in
this chapter was taken on hardware.** The figures and tables are stamped `SYNTHETIC DEMONSTRATION DATA —
NOT MEASURED`, and that stamp is not a formality: it is the difference between a report that applies a
model and a report that claims a measurement.

| May be claimed from this chapter | May **not** be claimed |
|---|---|
| The analysis pipeline works end-to-end and is reproducible from a seed | That the instrument detects debonds on a wall |
| The feature set has the *modelled* discriminative power | That the instrument's accuracy is any particular number |
| The model and the generator agree where they should, and disagree where the model is known to be incomplete | That the size floor of §5.5 has been confirmed |
| The expected-cost threshold framework behaves as designed | That any threshold is calibrated |

The generator is **not** tuned to produce favourable results. It implements the forward model
independently — including two effects the closed-form model excludes, namely the broadband strike
transient and the overlap of a mode with the band edge — and whatever it produces is what is reported.
Where it contradicts a Chapter 5 prediction, §8.7 says so, because a failed prediction reported honestly
is more valuable to this project than a passing one.

## 8.1 Reference dataset construction

The generator synthesises measurements from the physics of Chapter 5 rather than from a statistical
description of desired outcomes. The chain, for one tap:

**Step 1 — the wall mode.** Reference panel: 20 mm cement render on concrete, the middle case of
Table 5.3.

| Quantity | Value |
|---|---|
| $E$, $h$, $\rho$, $\nu$ | 18 GPa, 20 mm, 2000 kg/m³, 0.20 |
| Flexural rigidity $D$ | $1.25\times10^{4}$ N·m |
| $f_{mode}(a)$ | $\frac{1}{2\pi}\sqrt{D\alpha^4/\rho h}$, $\alpha = 3.196/a$ |
| $f_{found}(k)$ | $\frac{1}{2\pi}\sqrt{k/\rho h}$ |
| $f_1(k,a)$ | $\sqrt{f_{mode}^2 + f_{found}^2}$ |
| $k$: bonded / partial / free | $9\times10^{11}$ / $10^{10}$ / $0$ Pa/m |
| Quality factor $Q$ | 9 |

**Step 2 — the strike.** A half-sine force pulse of contact time $T = 300\ \mu s$ (the selection of
§5.6), with amplitude spectrum $F(\omega)\propto\cos(\omega T/2)/(1-(\omega T)^2)$ and a null at 5 kHz.

**Step 3 — the wall's response.** A single-degree-of-freedom mode plus a fixed broadband background,
**summed coherently** (not in power, which would be the physically wrong operation):

$$H(f) = \underbrace{\frac{0.35}{1+(f/500)^{0.7}}}_{\text{broadband substrate}} + \underbrace{\frac{rad}{(1-(f/f_1)^2) + j\,f/(f_1 Q)}}_{\text{the debond mode}}$$

with the mode term **omitted entirely when $f_1 > 15$ kHz** (`SYNTH_MODE_IN_BAND_MAX_HZ`, the band top),
which is what makes the bonded control's in-band spectrum pure transient. $rad$ scales with how far the
mode has entered the band, $rad = 3.0\,\mathrm{clip}(d/10, 0.3, 1.0)$.

**That cutoff is the single most consequential line in the generator, and it is arithmetic, not
physics.** It is what makes the model's own size floor appear in the results: at 8.8 cm the mode sits at
14 844 Hz for a full debond (kept) and 15 055 Hz for a partial one (dropped), so a class placed exactly
on the predicted floor comes out half-detected — see §8.4c and the P6 verdict in §8.7. Dwelling 156 Hz
either side of the cutoff moves that row between 0 % and 100 %. The cutoff is a restatement of the
band edge, which is why it is a test of the model's *arithmetic* and not of the instrument.

**Step 4 — observation.** Magnitude spectrum $S(f) = \sqrt{F^2(f)}\,|H(f)|$ on the 1024-point/48 kHz
grid, with per-tap lognormal noise ($\sigma = 0.05$) and per-panel random effects on the mode strength
($\sigma = 0.07$) and the broadband level ($\sigma = 0.05$). Features are then extracted by the *same*
code the script uses on real data.

**Step 5 — the experiment.** 12 panels × 17 locations × 5 taps = **1 020 measurements**. Locations are
three bonded controls ($d = 0$) and one each of $d \in \{3, 5, 7, 8.8, 10, 15, 20\}$ cm at both partial
and full debond. Panel identity is the grouping variable for cross-validation, so no panel leaks between
training and test folds.

**Why the axis has a 7 cm and an 8.8 cm class.** The first version of this experiment used five diameters
$(3, 5, 10, 15, 20)$ and then reported that only the 10, 15 and 20 cm classes were identifiable — that
is, it straddled the predicted size floor (8.8 cm for render, Table 5.4) without placing a single class
on it, so the floor could not be tested at all. Adding 7 cm and 8.8 cm puts one class on each side of the
prediction, which is what converts P6 from an assumption into a result. **The 8.8 cm class is the
prediction's own value**, so a success there is a test of the model rather than a coincidence of the
axis.

**Why this design.** Two properties are deliberately reproduced because they are what make the problem
hard, and a generator that omitted them would produce a flattering and useless result:

1. **Small debonds and bonded controls are genuinely confusable.** A 3 cm debond's mode is at 128 kHz —
   above the band — so its in-band spectrum is transient-dominated, exactly like a bonded control's. The
   only channel that separates them is the mode's *radiated strength*, not its frequency. **The
   generator's treatment of this case carries an assumption worth stating**: it drops the mode term when
   $f_1$ exceeds a strike-derived drive ceiling, so a class whose mode is far above the band is
   *generated* as transient-dominated rather than found to be so. That makes the small-debond results a
   restatement of the model's band arithmetic, not evidence about an instrument. §9.2.1 does the same
   calculation in closed form for a 4 cm debond, where the conclusion is a property of the strike pulse
   and the layer, not of the transducer.
2. **`f_peak_hz` is non-monotone in severity.** For $d \lesssim 7$ cm the mode is out of band and
   $f_{peak}$ sits at the band edge; for larger $d$ it tracks the mode. A classifier keyed on
   $f_{peak}$ alone therefore does not behave as a monotone detector — which is the quantitative form of
   prediction P3.

## 8.2 Descriptive statistics

SYNTHETIC

**Table 8.2 — Descriptive statistics, groups of interest.**

#### 8.2a  By debond grade

| Group | Feature (unit) | n | Median | IQR (Q1-Q3) | IQR width | Min | Max | CV% |
|---|---|---|---|---|---|---|---|---|
| G0 bonded | f_peak_hz (Hz) | 180 | 328.1 | 328.1-375.0 | 46.9 | 328.1 | 515.6 | 9.7% |
| G0 bonded | f_centroid_hz (Hz) | 180 | 2,809 | 2,802-2,814 | 12.25 | 2,785 | 2,839 | 0.3% |
| G0 bonded | band_ratio_lh | 180 | 0.7972 | 0.7833-0.814 | 0.03068 | 0.7185 | 0.8586 | 2.9% |
| G0 bonded | decay_tau_ms (ms) | 180 | -1 | -1--1 | 0 | -1 | -1 | 0.0% |
| G0 bonded | peak_au (a.u.) | 180 | 1,884 | 1,692-2,315 | 623.6 | 1,467 | 4,066 | 28.2% |
| G0 bonded | rms_au (a.u.) | 180 | 481.9 | 410.7-602.7 | 192.0 | 335.9 | 1,279 | 32.0% |
| G0 bonded | crest_factor | 180 | 4.01 | 3.494-4.452 | 0.9582 | 3.011 | 4.978 | 14.1% |
| G0 bonded | kurtosis | 180 | 4.763 | 4.387-5.087 | 0.6995 | 3.303 | 6.095 | 12.4% |
| G0 bonded | impact_peak_g (g) | 180 | 12.03 | 11.32-12.53 | 1.21 | 9.835 | 14.36 | 6.8% |
| G0 bonded | impulse_norm (a.u.) | 180 | 0.7798 | 0.6727-0.8814 | 0.2086 | 0.4892 | 1.362 | 19.2% |
| G1 partial debond | f_peak_hz (Hz) | 420 | 375.0 | 328.1-3,762 | 3,434 | 328.1 | 5,719 | 121.1% |
| G1 partial debond | f_centroid_hz (Hz) | 420 | 2,819 | 2,807-4,344 | 1,536 | 2,780 | 5,284 | 26.2% |
| G1 partial debond | band_ratio_lh | 420 | 0.7754 | 0.03878-0.8012 | 0.7624 | 0.0266 | 0.8697 | 73.3% |
| G1 partial debond | decay_tau_ms (ms) | 420 | -1 | -1--1 | 0 | -1 | -1 | 0.0% |
| G1 partial debond | peak_au (a.u.) | 420 | 2,339 | 1,556-2,711 | 1,155 | 617.7 | 5,830 | 44.7% |
| G1 partial debond | rms_au (a.u.) | 420 | 572.6 | 389.3-721.3 | 332.0 | 149.4 | 1,881 | 49.1% |
| G1 partial debond | crest_factor | 420 | 3.992 | 3.486-4.454 | 0.9683 | 3.002 | 4.995 | 14.2% |
| G1 partial debond | kurtosis | 420 | 5.194 | 4.719-5.603 | 0.8835 | 3.165 | 7.223 | 13.1% |
| G1 partial debond | impact_peak_g (g) | 420 | 12.01 | 11.45-12.59 | 1.143 | 10.12 | 14.25 | 6.7% |
| G1 partial debond | impulse_norm (a.u.) | 420 | 0.9829 | 0.8758-1.119 | 0.243 | 0.5635 | 1.698 | 18.2% |
| G2 full debond | f_peak_hz (Hz) | 420 | 468.8 | 328.1-2,859 | 2,531 | 328.1 | 5,156 | 113.7% |
| G2 full debond | f_centroid_hz (Hz) | 420 | 2,817 | 2,802-5,158 | 2,356 | 2,663 | 5,231 | 29.3% |
| G2 full debond | band_ratio_lh | 420 | 0.192 | 0.0334-0.7922 | 0.7588 | 0.0281 | 0.8595 | 86.3% |
| G2 full debond | decay_tau_ms (ms) | 420 | -1 | -1--1 | 0 | -1 | 15.5 | 156.9% |
| G2 full debond | peak_au (a.u.) | 420 | 2,310 | 1,592-2,763 | 1,171 | 644.4 | 5,724 | 44.2% |
| G2 full debond | rms_au (a.u.) | 420 | 579.2 | 379.1-718.9 | 339.8 | 132.0 | 1,636 | 46.2% |
| G2 full debond | crest_factor | 420 | 4.024 | 3.502-4.455 | 0.9533 | 3.014 | 4.988 | 14.2% |
| G2 full debond | kurtosis | 420 | 5.681 | 5.2-6.125 | 0.925 | 3.533 | 8.291 | 12.5% |
| G2 full debond | impact_peak_g (g) | 420 | 12.03 | 11.48-12.52 | 1.042 | 9.389 | 14.9 | 6.4% |
| G2 full debond | impulse_norm (a.u.) | 420 | 0.9896 | 0.8862-1.11 | 0.224 | 0.5396 | 1.755 | 17.7% |

#### 8.2b  By debond size class

| Group | Feature (unit) | n | Median | IQR (Q1-Q3) | IQR width | Min | Max | CV% |
|---|---|---|---|---|---|---|---|---|
| 0 cm (control) | f_peak_hz (Hz) | 180 | 328.1 | 328.1-375.0 | 46.9 | 328.1 | 515.6 | 9.7% |
| 0 cm (control) | f_centroid_hz (Hz) | 180 | 2,809 | 2,802-2,814 | 12.25 | 2,785 | 2,839 | 0.3% |
| 0 cm (control) | band_ratio_lh | 180 | 0.7972 | 0.7833-0.814 | 0.03068 | 0.7185 | 0.8586 | 2.9% |
| 0 cm (control) | decay_tau_ms (ms) | 180 | -1 | -1--1 | 0 | -1 | -1 | 0.0% |
| 0 cm (control) | peak_au (a.u.) | 180 | 1,884 | 1,692-2,315 | 623.6 | 1,467 | 4,066 | 28.2% |
| 0 cm (control) | rms_au (a.u.) | 180 | 481.9 | 410.7-602.7 | 192.0 | 335.9 | 1,279 | 32.0% |
| 0 cm (control) | crest_factor | 180 | 4.01 | 3.494-4.452 | 0.9582 | 3.011 | 4.978 | 14.1% |
| 0 cm (control) | kurtosis | 180 | 4.763 | 4.387-5.087 | 0.6995 | 3.303 | 6.095 | 12.4% |
| 0 cm (control) | impact_peak_g (g) | 180 | 12.03 | 11.32-12.53 | 1.21 | 9.835 | 14.36 | 6.8% |
| 0 cm (control) | impulse_norm (a.u.) | 180 | 0.7798 | 0.6727-0.8814 | 0.2086 | 0.4892 | 1.362 | 19.2% |
| 3 cm | f_peak_hz (Hz) | 120 | 328.1 | 328.1-375.0 | 46.9 | 328.1 | 515.6 | 10.1% |
| 3 cm | f_centroid_hz (Hz) | 120 | 2,809 | 2,803-2,815 | 12.25 | 2,782 | 2,834 | 0.3% |
| 3 cm | band_ratio_lh | 120 | 0.7975 | 0.7782-0.8114 | 0.0331 | 0.7468 | 0.8482 | 2.9% |
| 3 cm | decay_tau_ms (ms) | 120 | -1 | -1--1 | 0 | -1 | 4.017 | 47.6% |
| 3 cm | peak_au (a.u.) | 120 | 810.9 | 727.6-953.9 | 226.3 | 617.7 | 1,862 | 29.2% |
| 3 cm | rms_au (a.u.) | 120 | 207.9 | 177.8-239.8 | 62.03 | 132.0 | 458.9 | 30.4% |
| 3 cm | crest_factor | 120 | 4.173 | 3.628-4.571 | 0.942 | 3.028 | 4.988 | 13.9% |
| 3 cm | kurtosis | 120 | 5.047 | 4.528-5.492 | 0.9645 | 3.399 | 7.106 | 14.8% |
| 3 cm | impact_peak_g (g) | 120 | 11.87 | 11.33-12.39 | 1.054 | 10.25 | 14.9 | 7.0% |
| 3 cm | impulse_norm (a.u.) | 120 | 0.9809 | 0.8844-1.132 | 0.2478 | 0.5852 | 1.468 | 17.7% |
| 5 cm | f_peak_hz (Hz) | 120 | 328.1 | 328.1-375.0 | 46.9 | 328.1 | 515.6 | 11.0% |
| 5 cm | f_centroid_hz (Hz) | 120 | 2,809 | 2,803-2,816 | 12.92 | 2,780 | 2,827 | 0.3% |
| 5 cm | band_ratio_lh | 120 | 0.7972 | 0.7827-0.8131 | 0.03045 | 0.7459 | 0.8609 | 2.8% |
| 5 cm | decay_tau_ms (ms) | 120 | -1 | -1--1 | 0 | -1 | -1 | 0.0% |
| 5 cm | peak_au (a.u.) | 120 | 1,352 | 1,244-1,603 | 359.0 | 961.3 | 2,774 | 27.5% |
| 5 cm | rms_au (a.u.) | 120 | 339.8 | 299.5-421.4 | 121.9 | 215.7 | 822.7 | 31.5% |
| 5 cm | crest_factor | 120 | 3.919 | 3.586-4.45 | 0.8643 | 3.027 | 4.988 | 13.9% |
| 5 cm | kurtosis | 120 | 5.271 | 4.856-5.696 | 0.8398 | 3.165 | 7.045 | 13.4% |
| 5 cm | impact_peak_g (g) | 120 | 11.96 | 11.34-12.38 | 1.042 | 10.08 | 13.45 | 6.1% |
| 5 cm | impulse_norm (a.u.) | 120 | 1.007 | 0.9067-1.103 | 0.1962 | 0.6224 | 1.562 | 16.0% |
| 7 cm | f_peak_hz (Hz) | 120 | 328.1 | 328.1-375.0 | 46.9 | 328.1 | 468.8 | 10.5% |
| 7 cm | f_centroid_hz (Hz) | 120 | 2,809 | 2,803-2,814 | 11.25 | 2,793 | 2,830 | 0.3% |
| 7 cm | band_ratio_lh | 120 | 0.7985 | 0.7842-0.8117 | 0.02753 | 0.7539 | 0.853 | 2.5% |
| 7 cm | decay_tau_ms (ms) | 120 | -1 | -1--1 | 0 | -1 | 5.748 | 65.0% |
| 7 cm | peak_au (a.u.) | 120 | 1,891 | 1,750-2,263 | 513.4 | 1,333 | 4,020 | 28.5% |
| 7 cm | rms_au (a.u.) | 120 | 480.1 | 415.6-608.5 | 192.9 | 308.1 | 1,193 | 33.6% |
| 7 cm | crest_factor | 120 | 3.925 | 3.394-4.486 | 1.092 | 3.007 | 4.946 | 14.7% |
| 7 cm | kurtosis | 120 | 5.298 | 4.813-5.818 | 1.005 | 3.243 | 6.707 | 12.3% |
| 7 cm | impact_peak_g (g) | 120 | 12.29 | 11.55-12.8 | 1.253 | 10.6 | 14.25 | 6.9% |
| 7 cm | impulse_norm (a.u.) | 120 | 0.9765 | 0.86-1.148 | 0.2876 | 0.6806 | 1.502 | 19.5% |
| 8.8 cm | f_peak_hz (Hz) | 120 | 375.0 | 328.1-609.4 | 281.3 | 328.1 | 2,484 | 65.7% |
| 8.8 cm | f_centroid_hz (Hz) | 120 | 4,001 | 2,808-5,205 | 2,397 | 2,790 | 5,231 | 29.9% |
| 8.8 cm | band_ratio_lh | 120 | 0.4773 | 0.192-0.8006 | 0.6085 | 0.1801 | 0.8697 | 61.5% |
| 8.8 cm | decay_tau_ms (ms) | 120 | -1 | -1--1 | 0 | -1 | 4.864 | 56.0% |
| 8.8 cm | peak_au (a.u.) | 120 | 2,374 | 2,167-2,850 | 683.4 | 1,831 | 5,322 | 28.5% |
| 8.8 cm | rms_au (a.u.) | 120 | 620.8 | 565.4-752.2 | 186.7 | 393.3 | 1,550 | 31.9% |
| 8.8 cm | crest_factor | 120 | 3.816 | 3.45-4.309 | 0.8593 | 3.044 | 4.981 | 14.2% |
| 8.8 cm | kurtosis | 120 | 5.486 | 5.123-5.946 | 0.823 | 3.678 | 7.085 | 11.7% |
| 8.8 cm | impact_peak_g (g) | 120 | 12.03 | 11.46-12.61 | 1.143 | 10.12 | 14.13 | 6.9% |
| 8.8 cm | impulse_norm (a.u.) | 120 | 0.9712 | 0.8731-1.106 | 0.2331 | 0.6352 | 1.698 | 18.3% |
| 10 cm | f_peak_hz (Hz) | 120 | 609.4 | 457.1-949.2 | 492.2 | 328.1 | 2,109 | 49.6% |
| 10 cm | f_centroid_hz (Hz) | 120 | 5,216 | 5,166-5,258 | 91.95 | 5,130 | 5,284 | 0.9% |
| 10 cm | band_ratio_lh | 120 | 0.1681 | 0.1655-0.1718 | 0.006325 | 0.1588 | 0.1815 | 2.6% |
| 10 cm | decay_tau_ms (ms) | 120 | -1 | -1--1 | 0 | -1 | 15.5 | 200.3% |
| 10 cm | peak_au (a.u.) | 120 | 2,694 | 2,457-3,304 | 846.9 | 1,978 | 5,830 | 28.5% |
| 10 cm | rms_au (a.u.) | 120 | 681.1 | 609.2-817.6 | 208.4 | 452.5 | 1,703 | 30.8% |
| 10 cm | crest_factor | 120 | 4.047 | 3.513-4.448 | 0.935 | 3.015 | 4.988 | 13.9% |
| 10 cm | kurtosis | 120 | 5.633 | 5.212-6.127 | 0.9155 | 3.896 | 7.1 | 11.8% |
| 10 cm | impact_peak_g (g) | 120 | 12.01 | 11.56-12.45 | 0.891 | 10.24 | 13.97 | 5.8% |
| 10 cm | impulse_norm (a.u.) | 120 | 0.9932 | 0.895-1.119 | 0.2241 | 0.6043 | 1.497 | 17.4% |
| 15 cm | f_peak_hz (Hz) | 120 | 5,344 | 5,098-5,637 | 539.1 | 4,969 | 5,719 | 5.4% |
| 15 cm | f_centroid_hz (Hz) | 120 | 4,212 | 4,074-4,348 | 274.4 | 4,057 | 4,363 | 3.3% |
| 15 cm | band_ratio_lh | 120 | 0.035 | 0.0329-0.0381 | 0.0052 | 0.0309 | 0.0402 | 8.0% |
| 15 cm | decay_tau_ms (ms) | 120 | -1 | -1--1 | 0 | -1 | 4.284 | 50.2% |
| 15 cm | peak_au (a.u.) | 120 | 2,706 | 2,455-3,226 | 770.8 | 2,088 | 5,382 | 26.0% |
| 15 cm | rms_au (a.u.) | 120 | 662.7 | 587.4-835.6 | 248.1 | 464.4 | 1,671 | 31.2% |
| 15 cm | crest_factor | 120 | 4.12 | 3.618-4.464 | 0.8462 | 3.014 | 4.995 | 13.2% |
| 15 cm | kurtosis | 120 | 5.548 | 5.051-5.984 | 0.9333 | 3.766 | 8.291 | 13.8% |
| 15 cm | impact_peak_g (g) | 120 | 11.98 | 11.54-12.54 | 0.9938 | 10.08 | 14.06 | 6.1% |
| 15 cm | impulse_norm (a.u.) | 120 | 0.988 | 0.9014-1.108 | 0.2067 | 0.5396 | 1.458 | 16.5% |
| 20 cm | f_peak_hz (Hz) | 120 | 3,305 | 2,859-3,797 | 937.5 | 2,812 | 3,844 | 14.0% |
| 20 cm | f_centroid_hz (Hz) | 120 | 2,999 | 2,673-3,325 | 651.9 | 2,663 | 3,334 | 10.9% |
| 20 cm | band_ratio_lh | 120 | 0.0293 | 0.0282-0.03053 | 0.002325 | 0.0266 | 0.0324 | 4.9% |
| 20 cm | decay_tau_ms (ms) | 120 | -1 | -1--1 | 0 | -1 | 7.68 | 194.9% |
| 20 cm | peak_au (a.u.) | 120 | 2,639 | 2,421-3,097 | 676.4 | 1,910 | 5,793 | 27.3% |
| 20 cm | rms_au (a.u.) | 120 | 710.4 | 595.4-875.0 | 279.7 | 469.7 | 1,881 | 32.9% |
| 20 cm | crest_factor | 120 | 3.899 | 3.333-4.37 | 1.038 | 3.002 | 4.967 | 15.0% |
| 20 cm | kurtosis | 120 | 5.614 | 5.075-6.123 | 1.049 | 3.977 | 7.437 | 13.4% |
| 20 cm | impact_peak_g (g) | 120 | 12.04 | 11.47-12.63 | 1.152 | 9.389 | 13.59 | 6.4% |
| 20 cm | impulse_norm (a.u.) | 120 | 1.004 | 0.8687-1.116 | 0.2477 | 0.5502 | 1.755 | 19.8% |

CV% is the population standard deviation divided by the mean, in percent. It is reported for every feature because detection quality depends on the between-class separation relative to the within-class spread, and CV% is that spread expressed in the feature's own units.

#### 8.2c  How the model-generated rows were produced

In `--demo` mode every row is generated from the report's forward acoustic model, not measured: a **plate on a Winkler foundation** struck by a **broadband half-sine transient**.

```text
material      E = 18 GPa, h = 20 mm, rho = 2000 kg/m3, nu = 0.20
              D = E h^3 / (12 (1-nu^2)) = 1.2500e4 N.m
debond mode   alpha = 3.19595 / a          (clamped circular plate (0,1))
              f_mode(a) = (1/2pi) sqrt( D alpha^4 / (rho h) )
foundation    f_found(k) = (1/2pi) sqrt( k / (rho h) )
resonance     f1 = sqrt( f_mode^2 + f_found^2 )
bond k (Pa/m) G0 = 9.0e11   G1 = 1.0e10   G2 = 0.0
strike        half-sine force pulse, contact time 300 us
              A(f) = cos(pi f T / 2) / (1 - (f T)^2), null at 5 kHz
response      mode at f1, Q = 9, coherently summed with the fixed
              broadband background 0.35 / (1 + (f/500)^0.7)
              |H(f)| = | bg(f) + rad / ((1-(f/f1)^2) + j f/(f1 Q)) |
grid          S(f) = sqrt(F2(f)) |H(f)| on 1024 points at 48 kHz,
              analysis band 300..15000 Hz (bin = 46.875 Hz)
noise         per-tap lognormal sd 0.05 on S; per-panel sd 0.07 on the
              mode strength and 0.05 on the background
```

The per-tap features are then read off that model spectrum with the **same definitions the offline extractor uses on a real capture**: `f_peak_hz` is the argmax of S over 300..15000 Hz, `f_centroid_hz` the S-weighted mean frequency, and `band_ratio_lh` the ratio of **S^2** summed below the 1 kHz crossover to **S^2** summed above it. The channel amplitudes follow from the mode radiation strength `rad = 3.0 x size_factor` (with `size_factor = clip(size_cm/10, 0.30, 1.0)`), a per-panel mode-strength effect and the per-tap lognormal noise above; `decay_tau_ms` follows from the mode decay time `1000 Q / (pi f1)` and is set to the -1.0 sentinel outside 3..60 ms.

#### 8.2d  Two consequences of the model worth stating here

**Band edge.** The firmware's `PROBE_FMAX_HZ = 15000.0` closes the analysis band at 15 kHz, and the firmware's crossover `PROBE_CROSSOVER_HZ = 1000.0` lands on bin 21.33 of the 1024-point / 48 kHz grid - i.e. between bin 21 (984.375 Hz) and bin 22 (1031.250 Hz). Each bin is assigned **wholly** to one side: bin 21 is counted in the low band, bin 22 in the high band. The two sums therefore straddle the nominal 1000 Hz boundary rather than sharing a bin. The firmware's own ratio compares band **energy (power)**, so the offline `band_ratio_lh` is a power ratio too: it sums `S^2`, not `S`. Every ratio in this document is on that footing.

**Confusable classes.** A strongly bonded contact has its resonance at `f_found = (1/2pi) sqrt(9.0e11 / (2000 x 0.020)) = 23.9 kHz` - above the band - so it contributes nothing in band and the bonded spectrum is pure transient. The same is true of every small debond: a 3 cm radius puts `f_mode = 128 kHz` and a 5 cm radius 46 kHz, both far above 15 kHz. Their in-band spectra therefore collapse onto the same 328 Hz transient peak as the bonded control. Only a fully debonded **radius of about 4.4 cm and up** (an 8.8 cm diameter) pulls `f1` below the band top: at 10, 15 and 20 cm the model's `f1` is 11.5, 5.1 and 2.9 kHz. The generator's own five-point axis has 3 and 5 cm *radius* below that threshold, so on it only the 10, 15 and 20 cm radii move f_peak at all. This is a property of the model, not a defect of the generator, and it is exactly why the report calls f_peak a poor single-channel detector.

## 8.3 Repeatability

The claim being tested is prediction P7: that repeated taps at one location vary by less than 5 % in
$f_{\text{peak}}$. The original plan asserted strike repeatability; this section measures it.

Method: within each (panel, location), compute the coefficient of variation of `f_peak_hz` and
`impulse_norm` across the five taps; report the median within-location CV and the fraction of locations
meeting the 5 % criterion. A Bland–Altman comparison of tap 1 against the mean of taps 2–5 tests for a
systematic first-tap bias, which would indicate the probe settling into contact rather than a random
error.

SYNTHETIC

**Table 8.3 — Repeatability.**

Within each (panel_id, location_id) the probe is struck several times; the spread between those repeats is the *within-location* variation. It bounds how well a single tap can represent a location.

#### 8.3a  Within-location coefficient of variation

| Feature | Locations | Median within-location CV% | IQR of CV% | Locations failing the 5% criterion | Probe verdict (median) |
|---|---|---|---|---|---|
| f_peak_hz | 204 | 6.62% | 10.18% | 72.1% | fail |
| impulse_norm | 204 | 14.92% | 7.86% | 98.5% | fail |

#### 8.3b  Bland-Altman agreement, tap 1 vs the mean of taps 2..N

| Feature | Locations | Bias (tap 1 - rest) | Bias as % of mean | 95% limits of agreement | LoA width as % of level | Bias within 5%? |
|---|---|---|---|---|---|---|
| f_peak_hz | 204 | -6.724 Hz | -0.50% | -405.6 to +392.2 Hz | +/-29.42% | yes |
| impulse_norm | 204 | +0.001296 a.u. | +0.13% | -0.3786 to +0.3812 a.u. | +/-39.24% | yes |

A bias near zero means tap 1 is not systematically louder or higher than the later taps; the limits of agreement say how far an individual tap-1 reading can stray from the average of the rest. If the LoA width is comparable to the between-class difference, a single tap is not enough and the probe should average several taps per location.

**Interpretation.** `f_peak_hz` is expected to repeat well, because it is set by the mode's frequency,
which is a property of the wall and the geometry, not of the strike energy. `impulse_norm` is expected to
repeat poorly, because it is proportional to strike energy, which is the least controlled quantity in
the system. **The asymmetry is the finding**: it is direct evidence for §2.3's argument that frequency is
a trustworthy observable and amplitude is not, and it is why `peak_au` was excluded from the feature set
(§6.5).

## 8.4 Discrimination testing and classification

**Feature-level tests.** Kruskal–Wallis across the three grades (a non-parametric test, chosen because
the features are not expected to be normal), then pairwise Mann–Whitney U with a Holm–Bonferroni
correction across the family of comparisons, with Cliff's delta as the effect size. A p-value alone is
uninformative at n = 1 020; the effect size is what says whether a difference is worth using.

**Classifiers.** Three, compared on identical folds:

| Model | Rationale |
|---|---|
| (a) One-feature threshold rule on `band_ratio_lh` | The **baseline the project must beat to justify its complexity**. A single threshold on one feature is what a naive implementation would use, and if the multivariate models do not beat it, the multivariate models are not earning their place |
| (b) Logistic regression, standardised, class-balanced | A linear model over the four features; interpretable coefficients |
| (c) k-NN, $k = 5$, standardised | A non-parametric check that buys back a non-linear boundary if one exists |

**Cross-validation.** `GroupKFold` with panel identity as the group, so that a model is never evaluated
on a panel it was trained on. This matters more than the model choice: with per-panel random effects in
the generator, a random split would leak and would report an accuracy that could not be reproduced on a
new building. Reported metrics: accuracy, balanced accuracy, and precision/recall/F1 for the
debond-positive class (partial or full debond), each with a 95 % bootstrap confidence interval, plus the
confusion matrix.

**The baseline comparison is the important result.** If the single-feature rule performs comparably to
the multivariate models, the correct conclusion is that the extra features are cost without benefit, and
§6.5's four-feature set should be reduced. The report commits to that conclusion in advance of seeing
the number.

SYNTHETIC

**The pooled figures and the size breakdown must be read together.** The classifier table averages over every debonded class in the dataset — including the classes below the size floor that §5.5 derives, which have no in-band mode by construction. §8.4c breaks the reference classifier out by debond size for that reason, and **it is the table to quote**; the pooled row describes the dataset, not the instrument.

**Table 8.4 — Discrimination testing, feature level.**

#### 8.4a  Omnibus test across grades (Kruskal-Wallis)

| Rank | Feature (unit) | Kruskal-Wallis H | p | p < 0.05 | Largest \|Cliff's delta\| | Effect |
|---|---|---|---|---|---|---|
| 1 | kurtosis | 216.0 | 1.266e-47 | yes | 0.6935 | large |
| 2 | impulse_norm (a.u.) | 195.8 | 3.001e-43 | yes | 0.6726 | large |
| 3 | band_ratio_lh | 119.0 | 1.423e-26 | yes | 0.5751 | large |
| 4 | f_peak_hz (Hz) | 107.1 | 5.545e-24 | yes | 0.5472 | large |
| 5 | f_centroid_hz (Hz) | 64.46 | 1.008e-14 | yes | 0.4521 | medium |
| 6 | peak_au (a.u.) | 11.14 | 3.814e-03 | yes | 0.1591 | small |
| 7 | rms_au (a.u.) | 6.299 | 4.287e-02 | yes | 0.1196 | negligible |
| 8 | decay_tau_ms (ms) | 17.33 | 1.726e-04 | yes | 0.02857 | negligible |
| 9 | impact_peak_g (g) | 0.2055 | 9.024e-01 | no | 0.02319 | negligible |
| 10 | crest_factor | 0.3321 | 8.470e-01 | no | 0.02178 | negligible |

Ordered by discriminative power: largest absolute Cliff's delta first, with the Kruskal-Wallis H as the tie-break. Cliff's delta bands: < 0.147 negligible, < 0.33 small, < 0.474 medium, otherwise large.

#### 8.4b  Pairwise comparisons (Mann-Whitney U, Holm-Bonferroni)

| Feature | Pair | n (a / b) | Median a | Median b | p (raw) | p (Holm) | Significant | Cliff's delta | Effect |
|---|---|---|---|---|---|---|---|---|---|
| kurtosis | G0 vs G1 | 180 / 420 | 4.763 | 5.194 | 2.693e-13 | 2.693e-13 | yes | -0.3763 | medium |
| kurtosis | G0 vs G2 | 180 / 420 | 4.763 | 5.681 | 2.300e-41 | 6.899e-41 | yes | -0.6935 | large |
| kurtosis | G1 vs G2 | 420 / 420 | 5.194 | 5.681 | 2.024e-22 | 4.048e-22 | yes | -0.3883 | medium |
| impulse_norm | G0 vs G1 | 180 / 420 | 0.7798 | 0.9829 | 4.478e-37 | 8.955e-37 | yes | -0.6549 | large |
| impulse_norm | G0 vs G2 | 180 / 420 | 0.7798 | 0.9896 | 5.181e-39 | 1.554e-38 | yes | -0.6726 | large |
| impulse_norm | G1 vs G2 | 420 / 420 | 0.9829 | 0.9896 | 7.741e-01 | 7.741e-01 | no | -0.01145 | negligible |
| band_ratio_lh | G0 vs G1 | 180 / 420 | 0.7972 | 0.7754 | 2.229e-17 | 4.458e-17 | yes | 0.4366 | medium |
| band_ratio_lh | G0 vs G2 | 180 / 420 | 0.7972 | 0.192 | 5.585e-29 | 1.676e-28 | yes | 0.5751 | large |
| band_ratio_lh | G1 vs G2 | 420 / 420 | 0.7754 | 0.192 | 3.924e-02 | 3.924e-02 | yes | 0.08219 | negligible |
| f_peak_hz | G0 vs G1 | 180 / 420 | 328.1 | 375.0 | 4.136e-15 | 8.271e-15 | yes | -0.3808 | medium |
| f_peak_hz | G0 vs G2 | 180 / 420 | 328.1 | 468.8 | 4.355e-28 | 1.307e-27 | yes | -0.5472 | large |
| f_peak_hz | G1 vs G2 | 420 / 420 | 375.0 | 468.8 | 8.903e-02 | 8.903e-02 | no | -0.06633 | negligible |
| f_centroid_hz | G0 vs G1 | 180 / 420 | 2,809 | 2,819 | 1.600e-18 | 4.801e-18 | yes | -0.4521 | medium |
| f_centroid_hz | G0 vs G2 | 180 / 420 | 2,809 | 2,817 | 9.623e-08 | 1.925e-07 | yes | -0.2746 | small |
| f_centroid_hz | G1 vs G2 | 420 / 420 | 2,819 | 2,817 | 4.873e-02 | 4.873e-02 | yes | 0.07858 | negligible |
| peak_au | G0 vs G1 | 180 / 420 | 1,884 | 2,339 | 1.995e-03 | 5.986e-03 | yes | -0.1591 | small |
| peak_au | G0 vs G2 | 180 / 420 | 1,884 | 2,310 | 2.213e-03 | 5.986e-03 | yes | -0.1575 | small |
| peak_au | G1 vs G2 | 420 / 420 | 2,339 | 2,310 | 9.842e-01 | 9.842e-01 | no | 7.937e-04 | negligible |
| rms_au | G0 vs G1 | 180 / 420 | 481.9 | 572.6 | 2.014e-02 | 6.043e-02 | no | -0.1196 | negligible |
| rms_au | G0 vs G2 | 180 / 420 | 481.9 | 579.2 | 2.136e-02 | 6.043e-02 | no | -0.1185 | negligible |
| rms_au | G1 vs G2 | 420 / 420 | 572.6 | 579.2 | 9.572e-01 | 9.572e-01 | no | -0.002143 | negligible |
| decay_tau_ms | G0 vs G1 | 180 / 420 | -1 | -1 | n/a | 1.000e+00 | no | 0 | negligible |
| decay_tau_ms | G0 vs G2 | 180 / 420 | -1 | -1 | 2.216e-02 | 4.431e-02 | yes | -0.02857 | negligible |
| decay_tau_ms | G1 vs G2 | 420 / 420 | -1 | -1 | 4.899e-04 | 1.470e-03 | yes | -0.02857 | negligible |
| impact_peak_g | G0 vs G1 | 180 / 420 | 12.03 | 12.01 | 6.526e-01 | 1.000e+00 | no | -0.02319 | negligible |
| impact_peak_g | G0 vs G2 | 180 / 420 | 12.03 | 12.03 | 7.016e-01 | 1.000e+00 | no | -0.01974 | negligible |
| impact_peak_g | G1 vs G2 | 420 / 420 | 12.01 | 12.03 | 9.867e-01 | 1.000e+00 | no | 6.689e-04 | negligible |
| crest_factor | G0 vs G1 | 180 / 420 | 4.01 | 3.992 | 9.789e-01 | 1.000e+00 | no | 0.001376 | negligible |
| crest_factor | G0 vs G2 | 180 / 420 | 4.01 | 4.024 | 7.028e-01 | 1.000e+00 | no | -0.01966 | negligible |
| crest_factor | G1 vs G2 | 420 / 420 | 3.992 | 4.024 | 5.849e-01 | 1.000e+00 | no | -0.02178 | negligible |

Holm-Bonferroni is applied **within each feature's family of pairs**, so the corrected column is directly comparable down one feature's block and needs no second adjustment: all pairwise tests on one feature form one family because they test one feature's separability.
**Table 8.6 — Classifier comparison and confusion matrices.**

Positive class = debonded (G1 or G2); negative class = bonded (G0). All figures are **out-of-fold** from a **StratifiedGroupKFold** split with `groups = panel_id`, so no panel appears in both training and test folds and no wall is measured twice. Features: f_peak_hz, f_centroid_hz, band_ratio_lh, decay_tau_ms. 95% CIs are percentile bootstraps resampling panels (the unit of independence), 1000 resamples.

| Classifier | n scored | Accuracy (95% CI) | Balanced accuracy (95% CI) | Precision (95% CI) | Recall (95% CI) | F1 (95% CI) | AUC (95% CI) |
|---|---|---|---|---|---|---|---|
| Threshold rule | 1020 | 0.587 [0.585, 0.588] | 0.749 [0.748, 0.750] | 1.000 [1.000, 1.000] | 0.499 [0.496, 0.500] | 0.666 [0.663, 0.667] | 0.753 [0.736, 0.771] |
| Logistic regression | 1020 | 0.590 [0.588, 0.593] | 0.751 [0.750, 0.753] | 1.000 [1.000, 1.000] | 0.502 [0.500, 0.506] | 0.669 [0.667, 0.672] | 0.755 [0.739, 0.774] |
| k-NN (k=5) | 1020 | 0.783 [0.771, 0.794] | 0.532 [0.509, 0.556] | 0.834 [0.827, 0.842] | 0.920 [0.908, 0.932] | 0.875 [0.868, 0.882] | 0.708 [0.683, 0.733] |

#### 8.4c  Detection rate by debond size

**Table 8.9 — Detection rate by debond size, for the reference classifier.**

Reference classifier: **Logistic regression** (best AUC in Table 8.6). Same out-of-fold predictions as above, broken out by the debond size the tap came from. **This table is the one to quote**, because the pooled figures above average over classes the method is specified not to see.

| Debond size | Taps | Detected | Missed | Detection rate |
|---|---|---|---|---|
| 3 cm | 120 | 1 | 119 | 0.8 % |
| 5 cm | 120 | 0 | 120 | 0.0 % |
| 7 cm | 120 | 1 | 119 | 0.8 % |
| 8.8 cm | 120 | 60 | 60 | 50.0 % |
| 10 cm | 120 | 120 | 0 | 100.0 % |
| 15 cm | 120 | 120 | 0 | 100.0 % |
| 20 cm | 120 | 120 | 0 | 100.0 % |

Bonded control: **180** taps, of which **0** were called debonded (0.0% false-alarm rate).

**480 of the 840 debonded taps (57.1%) are smaller than 10 cm**, i.e. below the size floor the report derives in S5.5. A class in that range has no in-band mode to detect, so it is not misclassified by the model — it is *outside the model's input space*, and every pooled metric that includes it understates the method and overstates the difficulty. Read the pooled row and this table together.

#### 8.4d  Confusion matrices (out-of-fold counts)

**Threshold rule**

| ground truth | predicted bonded | predicted debonded |
|---|---|---|
| truly bonded (G0) | 180 | 0 |
| truly debonded (G1/G2) | 421 | 419 |

**Logistic regression**

| ground truth | predicted bonded | predicted debonded |
|---|---|---|
| truly bonded (G0) | 180 | 0 |
| truly debonded (G1/G2) | 418 | 422 |

**k-NN (k=5)**

| ground truth | predicted bonded | predicted debonded |
|---|---|---|
| truly bonded (G0) | 26 | 154 |
| truly debonded (G1/G2) | 67 | 773 |

For a safety application the cell that matters is the **false negative** (bottom-left): a truly debonded point that the probe passes as bonded. The false-positive cell costs an inspector a few minutes; a false negative can cost a falling tile. Compare the two when choosing a rule.

## 8.5 Size sensitivity and the corrected fit

**Prediction P2** is that $f_{\text{peak}}$ falls monotonically with debond diameter for a fully
debonded region. **Prediction P8** is that the two-parameter fit of §5.2 outperforms the originally
planned one-parameter fit.

Two fits are compared on the same data:

$$f = \frac{C}{a^2} \quad\text{(original plan, one parameter)} \qquad\text{vs}\qquad f^2 = \frac{A}{a^4} + B \quad\text{(Chapter 5, two parameters)}$$

The second is the model's actual form: $A$ is the geometry term $\propto D/\rho h$, and $B$ is the bond
stiffness term $\propto k/\rho h$. Fitting them separately is not a refinement — it separates two
physically distinct quantities that the one-parameter form conflates.

**The analytic check.** For the reference panel,
$A_{analytic} = D\alpha^4/((2\pi)^2\rho h) = 825.8$ Hz²·m⁴. The fitted $A$ is compared against it
below. A fitted value far from 825.8 would indicate either a mis-specified fit or a generator that does
not implement the model it claims to.

**A censoring problem that must be handled explicitly.** For bonded controls and for debonds below the
size floor, $f_{\text{peak}}$ is pinned at the 300 Hz band edge — it is not a measurement of a mode, it
is the observation that no mode was found. Those points are **censored observations** and are excluded
from the fit, and the report states how many were used and how many dropped. Fitting a size law through
band-edge-pinned points would be fitting the band edge, not the physics.

**Censoring here is the crossover, not a measurement of the wall, and that has a consequence for 8.5a
above.** A tap is dropped when `f_peak_hz` sits at or below the 1 kHz crossover, on the argument that the
argmax there is the strike transient rather than a resonance. That is right for the classes whose mode is
genuinely out of band. It is *also* what removes most of the 8.8 cm and 10 cm classes — leaving 13 and 26
taps of 120 — and those two classes are exactly where the modelled mode lands. The taps that survive are
the ones whose transient happened to scatter upward past 1 kHz, which is the tail of the noise
distribution rather than a representative sample of the class. **8.5a's medians are computed over all
taps and the fit in 8.5b over the survivors, so the two tables describe different subsets of the same
class.** Read the residual column in 8.5a as a statement about the medians, not about the fit.

SYNTHETIC

**Table 8.5 — Size sensitivity and the competing fits.**

Two models are fitted to the same debonded taps and compared on identical panel-bootstrap resamples. **Model 1** is the report's headline claim, `f_peak = C / size_cm^2` (one parameter, size in cm). **Model 2** is the form the plate-on-Winkler model implies: since `f1^2 = f_mode^2 + f_found^2` and `f_mode^2 = D alpha^4 / ((2 pi)^2 rho h a^4)`, the correct two-parameter fit is `f_peak^2 = A / a^4 + B` with `a` the debond **radius in metres**. It is reported in that radius convention and again in the `size_cm` convention (`A' = A x 200^4`), so the metres check against the analytic constant and the cm fit are both visible; `B' = B` because the intercept is in Hz^2 either way. Model 2 is fitted per **tap**, not per class median, so the regression has the full spread of repeats behind it.

#### 8.5a  Median f_peak by debond size

| Debond size | n | Median f_peak | IQR | Fitted f = C/size$^2$ | Residual | Residual % |
|---|---|---|---|---|---|---|
| 3 cm | 120 | 328.1 Hz | 328.1-375.0 Hz | 5,830 Hz | -5,502 Hz | -94.4% |
| 5 cm | 120 | 328.1 Hz | 328.1-375.0 Hz | 2,099 Hz | -1,771 Hz | -84.4% |
| 7 cm | 120 | 328.1 Hz | 328.1-375.0 Hz | 1,071 Hz | -743 Hz | -69.4% |
| 8 cm | 120 | 375.0 Hz | 328.1-609.4 Hz | 678 Hz | -303 Hz | -44.7% |
| 10 cm | 120 | 609.4 Hz | 457.1-949.2 Hz | 525 Hz | +85 Hz | +16.1% |
| 15 cm | 120 | 5,344 Hz | 5,098-5,637 Hz | 233 Hz | +5,110 Hz | +2191.4% |
| 20 cm | 120 | 3,305 Hz | 2,859-3,797 Hz | 131 Hz | +3,173 Hz | +2419.2% |

Model 1's residuals are not small and they are not random: the 3 cm and 5 cm classes sit far *below* the fitted curve and the 15 cm and 20 cm classes far *above* it. For the small classes the median has been pinned to the strike transient by the band edge, and no power law through the origin can accommodate a point that is pinned. That is the quantitative form of the report's own claim that f_peak says nothing about small debonds.

#### 8.5b  Model comparison

**Censoring exclusion.** A tap whose f_peak is at or below the crossover (`SIZE_FIT_CENSOR_MAX_HZ` = 1000 Hz, the firmware's own `PROBE_CROSSOVER_HZ`) has been pinned into the transient-dominated low band: the argmax there is the strike excitation, not the structure, so the value is *censored*, not measured. Those taps are dropped from Model 2, and the bonded control (G0) never enters either model because its `size_cm = 0` gives it no radius to fit against.

**279 taps were used and 561 debonded taps were dropped as censored; a further 180 G0 taps have no radius and were never eligible. 4 distinct radii survive.**

| Class | Median f_peak (Hz) | Status |
|---|---|---|
| G1+G2 @ 3.0 cm | 328.1 | Transient-dominated class: median f_peak <= 1000 Hz (the crossover), so the argmax is the strike transient, not the resonance; taps above the crossover still enter the fit |
| G1+G2 @ 5.0 cm | 328.1 | Transient-dominated class: median f_peak <= 1000 Hz (the crossover), so the argmax is the strike transient, not the resonance; taps above the crossover still enter the fit |
| G1+G2 @ 7.0 cm | 328.1 | Transient-dominated class: median f_peak <= 1000 Hz (the crossover), so the argmax is the strike transient, not the resonance; taps above the crossover still enter the fit |
| G1+G2 @ 8.8 cm | 375.0 | Transient-dominated class: median f_peak <= 1000 Hz (the crossover), so the argmax is the strike transient, not the resonance; taps above the crossover still enter the fit |
| G1+G2 @ 10.0 cm | 609.4 | Transient-dominated class: median f_peak <= 1000 Hz (the crossover), so the argmax is the strike transient, not the resonance; taps above the crossover still enter the fit |

Surviving radii: 8.8, 10, 15, 20 cm.

**The exclusion is the headline finding, not a technicality.** The classes that had to be dropped are the bonded control and every debond at or below the crossover; what survives is a fully debonded region of 10 cm radius and up. Read the two-parameter fit as an empirical calibration over that range only. It says nothing about a small debond, because the model generates nothing about a small debond.

| Model | Fit basis | Coefficients (95% CI) | R^2 | n used | n excluded |
|---|---|---|---|---|---|
| 1. `f_peak = C / size_cm^2` (headline, one parameter) | class medians, all debonded classes | C = 52,472 Hz.cm^2 (51,875 - 53,932) | 0.6697 | 840 debonded taps | 0 |
| 2. `f_peak^2 = A / a^4 + B` (a in **metres**) | individual taps, censored ones dropped | A = -72.759 Hz^2 m^4 (-84.113 - -57.444); B = 20,786,016.8 Hz^2 (20,584,972.5 - 20,954,508.3) | 0.1911 | 279 | 561 |
| 3. `f_peak^2 = A' / size_cm^4 + B'` (size_cm convention) | same taps as model 2 | A' = -1.164e+11 Hz^2 cm^4 (-1.346e+11 - -9.191e+10); B' = 20,786,016.8 Hz^2 (20,584,972.5 - 20,954,508.3) | 0.1911 | 279 | 561 |

Rows 2 and 3 are the same fit in two conventions: `A' = A x 200^4` and `B' = B`, so the R^2 is identical by construction and only the coefficient units differ. The standard error on `B` is not quoted separately because the bootstrap CI above it is the honest statement of it.

Scored on the **same taps**, model 2 gives R^2 = 0.1911 against -1.9604 for model 1, so the two-parameter form **wins** here. 
The structural reason is that model 1 forces the curve through the origin of the `1/size^2` axis while model 2 carries an intercept `B`, and the physics supplies one: the foundation mode `f_found = (1/2pi) sqrt(k/rho h)` and the strike-transient floor that is left when a region is not debonded at all. When B is fixed by the physics rather than fitted, the curvature A is the only free parameter and it is the one the analytic formula predicts.


**Model 1's R^2 in the table (0.6697) is computed over *all* debonded classes and is therefore the more pessimistic number; the comparison above uses the matched tap set. Read both against the residuals in 5a.** The win is also narrow in a way 5c and 5c-bis make explicit: model 2 wins only because model 1 is badly wrong on the censored range, and model 2's own coefficients are not identified until `B` is fixed by the physics.

#### 8.5c  Physical validation of A

The analytic value of the curvature coefficient for the reference panel (E = 18 GPa, h = 20 mm, rho = 2000 kg/m3, nu = 0.20, so D = 1.2500e4 N.m, alpha = 3.19595) is

```text
A_analytic = D * alpha^4 / ((2 pi)^2 * rho * h)
           = 12500 * 3.19595^4 / ((2 pi)^2 * 2000 * 0.020)
           = 825.829 Hz^2 m^4
```


> **Note on the constant quoted in the project brief.** The brief gives `D*3.19595**4/((2*pi)**2*2000*0.020) = 28.737` for this quantity. That arithmetic is wrong for A: the value the expression evaluates to is 825.829, and 28.737 is `sqrt(825.829) = 28.7372`. In other words the brief's number is one angular-frequency factor out - it is f_mode(0.1 m)/100, a frequency, not the coefficient of a `1/a^4` term. The comparison below is therefore made against the coefficient the brief's own formula produces (825.829 Hz^2 m^4, whose square root is 28.7372), and separately against 28.737 so both readings are on the record.

The free fit returns **A = -72.759 Hz^2 m^4** (95% CI -84.113 - -57.444), i.e. **-0.088 x the analytic coefficient**; the CI does NOT contain the analytic value. The sign is wrong as well as the magnitude, which is the signature of an *unidentified* fit rather than a wrong model: with only three collinear radii the free fit can trade `A` against `B` along a near-flat direction and happily return a negative curvature. Section 5c-bis therefore fixes `B` at its analytic value and re-estimates `A` as a single unknown - that is the test that decides whether the model's `1/a^4` law is actually present, and the free fit alone cannot. In the size_cm convention the same analytic value is A'_analytic = 1.32133e+12 Hz^2 cm^4 (= 825.829 x 200^4) against a fitted A' = -1.16414e+11 Hz^2 cm^4.

B is the intercept of the `1/a^4` axis, and the physics names it: `B = f_found^2 = k / ((2 pi)^2 rho h)`. For a full debond (k = 0) that is 0 Hz^2; for the partially bonded grade G1 (k = 1.0e10 Pa/m) it is 6,332,772 Hz^2. The fit returns **B = 20,786,017 Hz^2** (95% CI 20,584,973 - 20,954,508).

#### 8.5d  Curvature A with B fixed by the physics

The free two-parameter fit above returns a **negative** A, which is unphysical: the `1/a^4` curvature cannot invert a resonance. The reason is identification, not the model. The surviving radii (10, 15, 20 cm) span a narrow `1/a^4` range and are strongly collinear with the intercept, so on this sample the free fit can slide a large `B` and a large `A` against one another almost without changing the fit; the negative A is the free fit exploiting that flat direction. The physics removes the ambiguity by *naming* `B`, and the properly identified test of A is therefore the one-parameter regression `A = sum(x (y-B)) / sum(x^2)` with `B = f_found^2` held at its analytic value. Those results are below, per grade (B differs by grade) and pooled.

| Subset | B fixed at | A | 95% CI | A / A_analytic | R^2 |
|---|---|---|---|---|---|
| G2 full debond | 0 (k = 0) | 52.5 Hz^2 m^4 | 37.8 - 88.8 | +0.064 | -2.0324 |
| G1 partial debond | 6,332,772 Hz^2 (k = 1.0e10 Pa/m) | 76.2 Hz^2 m^4 | 33.8 - 221.4 | +0.092 | -1.4697 |

**With B fixed, the curvature becomes identifiable - but it does not land on the analytic value.** The physical-grade fit (G2, `B = 0`) returns A = 52.5 Hz^2 m^4 = **0.064 x** the analytic 825.8 Hz^2 m^4; the partially bonded grade (G1, `B = f_found^2 = 6,332,772 Hz^2`) returns 76.2 Hz^2 m^4 = 0.092 x. Both are well below 1, and neither confidence interval contains the analytic value.

Two things can be read from that, and they point the same way. First, fixing B does what it was supposed to do: it turns an *inverted* free fit into a positive curvature, so the `1/a^4` law is not contradicted by the data once the fit is identified. Second, the magnitude comes out roughly an order of magnitude small, and the honest conclusion is that **this sample cannot verify the analytic coefficient** - cut down to a handful of collinear radii by the censoring that removes every class below the crossover, the curvature is bounded above rather than measured. The P8 verdict in S8.7 is therefore 'identified but not confirmed', which is weaker than the model would like and stronger than the free fit alone can support.

#### 8.5e  Free-exponent diagnostic

With the exponent **fitted freely** in log-log space on the class medians: **p = 1.525**, 95% CI 0.294 - 2.757, R^2 = 0.6697. The CI is extremely wide because only two of the five classes carry any usable information (the rest are pinned at the band edge), so this diagnostic cannot by itself distinguish 1/size from 1/size^2. That is a statement about the design, not about the physics.

#### 8.5f  Residual structure

A residual that varies monotonically with size means the exponent is wrong and the curve is systematically bending; a random scatter about zero means the assumed form is adequate over the range measured here. Read table 5a and the comparison in 5b against figure 2 (`fig02_f_peak_vs_size.png`) before quoting any constant.

## 8.6 Expected-cost threshold selection

Choosing a detection threshold is the one decision in the system that has a clear cost structure, and the
original plan did not address it at all — it selected thresholds by inspection of the spectrum, which
implicitly asserts that a false alarm and a miss cost the same. They do not:

> **A false alarm costs one manual re-inspection by a surveyor.** The cost is minutes of labour.
> **A miss costs a potential falling-object incident.** In Hong Kong this is a life-safety event with
> legal and human consequences.

The asymmetry is the entire content of this section. With $\pi$ the prior probability that a randomly
tapped point is debonded and $c_{miss}/c_{fa} = R$ the cost ratio, the expected cost of a decision rule
at threshold $\theta$ is

$$E[\text{cost}](\theta) = \pi\,\mathrm{FNR}(\theta)\,R + (1-\pi)\,\mathrm{FPR}(\theta)$$

with $c_{fa}$ normalised to 1. The script finds the cost-minimising threshold and reports the saving
against the naive default of 0.5. The two parameters are explicit and are sensitivity-tested rather than
fixed: a survey of a known-good building has a low $\pi$; a follow-up survey of a building with a known
incident has a high one. **The threshold is a deployment parameter, not a hardware constant**, and the
dashboard must present it that way (§7.5).

SYNTHETIC

**Table 8.7 — Expected-cost threshold selection.**

The decision threshold is priced, not voted on. With `C_fa` normalised to 1 and `C_miss` set by `--miss-cost`:

```
expected_cost(t) = P(D) * FNR(t) * C_miss + (1 - P(D)) * FPR(t) * C_fa
```

with the prior `P(D) = 0.15` and `C_miss/C_fa = 20`. A false alarm costs **one manual re-inspection** by an inspector already on site with a hammer - minutes of labour. A miss is a **potential falling-object safety event**: the debonded finish is never re-inspected and can detach onto the public below. The asymmetry therefore prices the *consequences*, not the inspection effort.

Reference classifier for the curve: **Logistic regression** (the best-AUC detector in table 6). Thresholds are swept over that model's out-of-fold scores, so the recommended operating point is one the model can actually reach on unseen panels.

| Quantity | Value |
|---|---|
| Assumed prior P(D) | 0.15 |
| Cost ratio C_miss / C_fa | 20 |
| Theoretical calibrated threshold 1/(1+m) | 0.0476 |
| Cost-minimising threshold | **0.2829** |
| Expected cost at the optimum, per tap | **0.85000** |
| FNR at the optimum (missed debonds) | 0.0000 |
| FPR at the optimum (needless re-inspections) | 1.0000 |
| Naive default threshold | 0.5000 |
| Expected cost at the default | 1.49286 |
| FNR at the default | 0.4976 |
| FPR at the default | 0.0000 |
| Cost saved per tap by moving to the optimum | **0.64286** |
| Saving as a fraction of the default cost | **43.1%** |
| Cost of never raising an alarm (threshold = 1) | 3.00000 |
| Cost of always raising an alarm (threshold = 0) | **0.85000** |

**The optimum and the "always alarm" row are the same number, and that is the result — not a
coincidence to be smoothed over.** At the cost-optimal threshold the false-positive rate is 1.0000: the
rule alarms on every tap, including all 180 bonded controls. It ties, to five decimals, with the
degenerate always-alarm strategy, and it beats the naive 0.5 default by 0.64286 per tap purely by
abandoning specificity. **On this dataset, at a 20:1 miss-to-false-alarm ratio, no threshold on this
classifier beats alarming unconditionally**, because the classifier cannot reach a point with a lower
miss rate than always-alarming without paying more in false alarms than the 20:1 ratio forgives.

That is a real finding about the reference classifier and the pooled sample, and it is the honest
reading of the table above. It does **not** mean the instrument should alarm constantly. Two things
bound it. First, the pooled sample is 82 % debonded by construction (§8.0), whereas a real survey is
perhaps 15 % debonded, so the asymmetry the optimum is exploiting is far less favourable in the field.
Second, the classifier that this table prices is not the one the firmware runs: §8.4c scores a
four-feature logistic model, while the node applies a two-condition box on `band_ratio_lh` and
`f_peak_hz`. Evaluating the box's shipped constants against this same dataset gives a false-alarm rate
of **0 in 180** on the bonded control and 0 / 0 / 0 / 60 / 120 / 120 / 120 detections across the 3, 5, 7,
8.8, 10, 15 and 20 cm classes — a rule that is specific and insensitive rather than one that alarms on
everything. What this section establishes is therefore narrower than "there is an optimal operating
point": it establishes that the expected-cost framework **is sensitive enough to report when a
classifier has no usable operating point**, and on the pooled sample it says exactly that about the
logistic model. Read Figure 5 (`fig05_expected_cost.png`) for that — the curve is flat-topped between the
optimum and the default, which is the signature of a classifier whose threshold does not usefully trade
the two errors.

## 8.7 Prediction verdicts

The model of Chapter 5 makes eight falsifiable predictions (§5.10). This section reports which survived
the generator. **A prediction that fails is not a defect in the report; it is the report doing its job.**

| # | Prediction | Verdict | Comment |
|---|---|---|---|
| P1 | Intact $f_{\text{peak}}$ is transient-dominated and invariant | — | |
| P2 | $f_{\text{peak}}$ falls monotonically with diameter, fully debonded | — | |
| P3 | $f_{\text{peak}}$ is a poor single-channel detector | — | |
| P4 | `band_ratio_lh` rises with severity | — | |
| P5 | `decay_tau_ms` is unusable for render below ~35 cm | — | |
| P6 | Smallest detectable diameter 8.8 cm for render | — | |
| P7 | Within-location CV of $f_{\text{peak}}$ under 5 % | — | |
| P8 | The two-parameter fit beats $C/a^2$ | — | |

**The verdicts, with the evidence for each.** A prediction that failed is reported as failed; three
did, and each failure is more informative than a pass would have been.

| # | Verdict | Evidence |
|---|---|---|
| **P1** | **Holds** | The bonded control's in-band `f_peak` sits at the 300 Hz band edge (median 328 Hz) with `band_ratio_lh` median 0.800 — a spectrum with no structure above the transducer transient, exactly as the out-of-band 23.9 kHz mode requires |
| **P2** | **Holds above the floor, fails below it** | `f_peak` falls monotonically with diameter from 8.8 cm upward (609 Hz at 10 cm, 5 344 Hz at 15 cm, 3 305 Hz at 20 cm) but is pinned at the transient for every class at or below 7 cm. That is the prediction's own caveat — "for a fully debonded region" — made quantitative |
| **P3** | **Holds** | `f_peak_hz` used alone gives AUC **0.732**, the weakest of the three spectral features (Table 8.4), because it is non-monotone in severity; `band_ratio_lh` at **0.753** and the multivariate logistic model at **0.755** both key on the *presence* of a mode rather than its location |
| **P4** | **Fails, and the failure is the more useful statement** | §5.10 predicted `band_ratio_lh` would **rise** with severity. It **falls**: bonded 0.800 against debonded 0.19. The prediction had the sign of the physics inverted — a mode entering the band moves energy *above* the 1 kHz crossover, so the ratio drops. §6.5 and the headline figure of §7.8.3 were corrected accordingly |
| **P5** | **Holds emphatically** | `decay_tau_ms` is the −1.0 sentinel for **100 %** of bonded points and **95 %** of fully debonded ones, giving AUC **0.507** with a 95 % CI of **[0.504, 0.511]** — indistinguishable from chance. This is the single clearest confirmation in the chapter, and it confirmed the report's own declaration that the feature is a dead channel for render |
| **P6** | **Not tested as stated, and the run shows why** | The prediction is about a *diameter*; the first dataset placed no class near the 8.8 cm floor, so it could not be tested at all. Adding 7 cm and 8.8 cm classes puts one on each side: detection is negligible at 7 cm and half at 8.8 cm, rising to complete at 10 cm and above. **But the 8.8 cm half is not a measured detection rate.** The class sits on the generator's own `f1 > 15 kHz` mode-drop cutoff: the full-debond taps come out at 14 844 Hz (mode kept) and the partial-debond taps at 15 055 Hz (mode dropped), so "50 %" is the two grades straddling a threshold by 156 Hz, not two populations separated by physics. Moving that cutoff 2 % either way gives 0 % or 100 %. The floor's *location* is consistent with §5.5; its *sharpness* is an artefact of the generator, and the boundary between 7 cm and 10 cm is unmeasured |
| **P7** | **Fails** | Median within-location CV of `f_peak_hz` is **6.62 %** and **72.1 %** of locations exceed the 5 % criterion. §8.3 says the probe should therefore average several taps per location and increase the repeat count rather than claim single-tap representativeness |
| **P8** | **Identified but not confirmed** | The two-parameter form beats the one-parameter form on matched taps (R² 0.191 against −1.960), but only because the one-parameter fit is badly wrong on the censored range. With B fixed by the physics the curvature comes out positive yet roughly an order of magnitude below the analytic value (§8.5d), so the sample bounds the coefficient rather than measuring it |

**Two of the eight verdicts were wrong in the report's own model, and both were found by running it.** P4
had the sign of the band-ratio response backwards, and P6 could not be tested by the dataset the report
had specified. Neither would have been visible without executing the analysis; both are recorded rather
than quietly corrected, because a model that has been checked against itself and failed in two places is
more informative than one that has never been checked.


## 8.8 What would make this chapter real

One measurement. The pipeline, the metrics, the audit trail and the analysis code are all in place and
are exercised end-to-end in the synthetic run; the only thing separating this chapter from a measured
results chapter is the hardware and a weekend with the reference panels of Appendix C.4. **That is the
recommended next action, and it is a smaller task than any remaining part of this report's writing.**

---

# 9. Discussion, Limitations and Future Work

## 9.1 The central limitation: no validation against real defects

Every quantitative result in Chapter 8 comes from a **model-generated** dataset, not from a wall. The
report's honesty depends on stating precisely what that does and does not establish:

| Claim | Status |
|---|---|
| The instrument's physics is correct in the sense that the plate-on-foundation model is the right idealisation | **Argued** (§5.1, §5.7, §5.11) — the checks are load-bearing but analytical |
| The instrument can distinguish bonded from debonded reference panels | **Specified, not measured.** The protocol (§8.1, Appendix C.4) is designed to settle it; there is no result |
| The numbers in Table 8.x are the instrument's performance on a wall | **False.** They are the model's performance, with the model's assumptions, applied to a generator built from the same model |
| The size floor of 7.0 / 8.8 / 11.3 cm is real | **Derived** from the model and the band, and **partly tested since the first run**: adding 7 cm and 8.8 cm classes to the dataset (§8.1) put one class on each side of the render floor, and the result is 0.8 % detection at 7 cm, **50 % at 8.8 cm**, 100 % at 10 cm and above (§8.7, P6). So the floor behaves as predicted for *this* model on *these* synthetic panels — but that is a check on the model, not on the instrument, and the floor remains unmeasured until the Appendix C.4 protocol is run |
| The observable bond-stiffness window of §5.5.1 (≤39 % of intact, saturating) is real | **Derived**, and it is the *stronger* of the two claims: it says the method responds to separation, not to degradation |

**Why this limitation is not disqualifying.** The alternative — building the instrument and reporting a
handful of taps on a demo panel as if they were validation — would produce a report that *looks*
stronger and is *worth* less, because it would hide the fact that the physical model is unverified. The
engineering value of the work is in the model, the band argument, the contact design and the validation
*protocol*; the measurement is the next milestone, and saying so is more useful to a reader than a
premature number.

**What would discharge it.** Appendix C.4 defines the calibration in full: a graded reference set
(fully bonded, partially bonded, fully debonded at four diameters), repeated taps, groups by panel,
and reporting confusion counts rather than a percentage. Eight to twelve reference panels and a
weekend of tapping would move every claim in Chapter 8 from `SYNTHETIC` to measured. **That is the
single highest-value next step in the project.**

A second, smaller honesty point: the generator and the model share assumptions, so agreement between
them is partly circular. The generator was deliberately *not* tuned to reproduce the model's
predictions — it implements the forward model independently, including the effects the closed form
excludes (the broadband transient, the mode's overlap with the band edge) — and Chapter 8.7 reports
where they disagree. But a reader should treat Chapter 8's numbers as *consistency evidence for the
model*, not as independent evidence for the instrument.

## 9.2 The band-limited envelope, and what it means operationally

The instrument is blind below a size floor of 7.0 cm (tile), 8.8 cm (render) and 11.3 cm (stone) for a
*fully* debonded region; and even at the floor it sees only a near-free plate. Above the floor the
observable bond-stiffness window widens with size and saturates at 39 % of the intact bond stiffness for
render (§5.5.1). Both halves of that statement matter, and they fit the application in a specific way:

- **What it cannot do:** find small hollow spots, detect partial debonding at small to moderate size, or
  replace a strength test. A survey that reports "no defects" from this instrument has *not* established
  the absence of small or partially bonded defects. The operating procedure (Appendix C.5) says this in
  the operator's own words, and the dashboard carries the same warning.
- **And it is blind at the large end too, which §5.5 does not cover.** The detection test is "has a mode
  come down *into* 1–15 kHz", so the instrument has a **two-sided** window, not a floor. A debond large
  enough for its mode to fall *below* the 1 kHz crossover reads as bonded again: on the reference panel
  the mode crosses 1 kHz at about 34 cm diameter, where `band_ratio_lh` climbs back through 1.9 (34 cm),
  62 (40 cm) and 674 (50 cm) against a bonded value of 0.80. The upper edge is set by the crossover, not
  by the finish, and it is a **crossover** in the ordinary sense — the feature is non-monotone in size,
  so a 40 cm hollow and a 5 cm hollow produce the same reading. This matters for the deployment: the
  large, well-developed separation that is closest to falling is the one case the rule is most likely to
  pass as sound. Appendix C.5's operator briefing and the firmware's classification comment now both
  state it. **A clean survey is not a certificate of soundness in either direction.**
- **What it can do:** locate *large, substantially separated* regions quickly and reproducibly, and —
  the actual value — **record them**. The comparison the instrument enables is not against a strength
  criterion but against *its own earlier survey of the same wall*. A 12 cm hollow that has been there
  for a decade is a monitoring subject; the same region growing is an intervention trigger. That is a
  capability manual tapping simply does not have, because manual tapping leaves no comparable record.
- **The honest framing for a deployment:** a **screening and change-detection tool** that concentrates
  the inspector's attention, not an autonomous defect classifier — and one whose sensitivity is spent on
  *size* rather than on *bond quality*, which is why the operating procedure asks for extent to be
  recorded on a grid rather than for a severity score to be reported.

### 9.2.1 What it would take to reach a 4 cm debond — and why that path leaves the method

The size floor is the limitation an examiner will press on hardest, because 8.8 cm is larger than the
defects that actually fall off buildings. The question "could this instrument be extended down to, say,
4 cm?" therefore deserves a quantified answer rather than a dismissal. The answer is that three
*independent* gates stand in the way, that the first two are engineering choices, and that the third is a
property of the model the method is built on.

On the reference panel (20 mm cement render) a fully debonded 4 cm region resonates at

$$f_1(4\ \text{cm}) = \frac{1}{2\pi}\sqrt{\frac{D\alpha^4}{\rho h}} = 71\,843\ \text{Hz},$$

against 14 844 Hz at the 8.8 cm floor and 2 874 Hz at 20 cm — the same $1/a^2$ law, evaluated four times
higher in frequency. The demand that imposes is:

| Material | $f_1$ at 4 cm | Band top needed | Sample rate needed | Contact time $T$ needed |
|---|---|---|---|---|
| Ceramic tile 8 mm | 46 058 Hz | 46 kHz | **147 kHz** (now 48) | **32.6 µs** (now 300) |
| Cement render 20 mm | **71 843 Hz** | 72 kHz | **230 kHz** (now 48) | **20.9 µs** (now 300) |
| Stone cladding 25 mm | 118 814 Hz | 119 kHz | **380 kHz** (now 48) | **12.6 µs** (now 300) |

Sample rates follow the report's own convention that the band ceiling sits at 62.5 % of Nyquist
(§5.8), so $f_s = 3.2\,f_{top}$.

**Gate 1 — the transducer.** Replaceable. I²S MEMS microphones with ultrasonic response exist, and a
broadband piezoelectric *contact* transducer would serve, at the cost of an analogue front end, a charge
amplifier and the EMC problem §5.8(iii) was written to avoid.

**Gate 2 — the strike pulse.** This is where the extension stops being a component swap. §5.6 selects
$T = 300\ \mu s$ to place the excitation null at 5 kHz and keep energy away from the probe's own
resonances. The criterion for *exciting* a mode is $f_{null} = 1.5/T \ge f_1$, so 71 843 Hz requires
$T \le 21\ \mu s$ — a factor of fifteen shorter. At that contact time the probe's structural modes
(the 100–800 Hz of §6.3 being a large, soft estimate) move into the analysis band, and the entire
common-mode rejection argument of §6.4 — the project's actual working principle — has to be re-derived.
The same lever cannot both suppress the probe and excite a 4 cm mode.

**Gate 3 — the model itself stops being valid, and this is the decisive one.** §5.7 calls the
contact-time-versus-transit-time check *load-bearing*: the plate-on-foundation idealisation requires the
layer to be quasi-static during contact, i.e. $T \gg 2h/c_L$. Evaluating both at the contact time that
4 cm *demands*:

| Material | $T$ needed for 4 cm | Round-trip $2h/c_L$ | Ratio |
|---|---|---|---|
| Ceramic tile 8 mm | 32.6 µs | 5.3 µs | 6.1 — holds |
| Cement render 20 mm | 20.9 µs | 13.3 µs | **1.57** — marginal |
| Stone cladding 25 mm | 12.6 µs | 12.5 µs | **1.01** — fails |

In render and stone, the contact time required to *see* a 4 cm debond is within a factor of two of the
round trip through the layer — exactly the condition §5.7 declares the model invalid for. The reason is
mechanical, not numerical: a strike that short begins to resolve the finish layer as a plate in its own
right rather than as a mass on a spring, so the flexural mode the method keys on is no longer the
governing response. **The instrument would be applying a model outside the regime that justifies it.**

Two further points close the remaining escape routes:

- **The layer's thickness moves the size floor, but not far enough to help.** $f_1 \propto h$, so the
  floor scales as $\sqrt{h}$: for render the floor falls from 10.7 cm at 30 mm of finish to **8.8 cm at
  20 mm, 6.2 cm at 10 mm and 4.4 cm at 5 mm** (§5.5.2, Table 5.8). A *thin* finish therefore lowers the
  floor, and this is a real sensitivity to the wall's construction that the report's three-material
  taxonomy hides. But it does not rescue a 4 cm target: reaching 4 cm in 20 mm render needs $h$ near
  4 mm, which is thinner than any real render, adhesive-bed or tile-fixing layer. **The conclusion is
  that the floor is a property of the specific build-up, not of the material class** — and that to state
  a floor for a building you must know its finish thickness, which §7.7 shows the instrument cannot
  measure.
- **High frequencies are attenuated by the medium.** §2.2 rejects ultrasonic pulse-echo precisely because
  "high-frequency attenuation in render is severe". The same loss applies here: the 40–120 kHz band that
  4 cm detection requires is the band the report has already ruled out on physical grounds. The model's
  own broadband floor falls with frequency (from 0.206 at 300 Hz to 0.007 at 120 kHz on the generator's
  own curve), before any material absorption is added, and §5.11 records that layer damping is represented
  only as a lumped $Q$ — which is precisely the assumption that the floor exposes.

**The conclusion this supports.** The method's envelope is not set by the quality of its components but by
where its governing idealisation holds. It supports **large-delamination screening** — the ≥10 cm range,
where Chapter 8 finds complete detection of the modelled defects with no false alarms — and it does not
support **small-defect sizing**. A 4 cm debond is not a defect this *method* mis-handles: it is a defect
that falls **below the floor**, which means it is in the same blind class as a bonded region — the
instrument reports "no in-band tone" and grades it G0. Reaching it would mean a different method
(ultrasonic or impact-echo) and the cost §2.2 already priced: one to two orders of magnitude in cost, and
the loss of handheld, single-operator, low-cost deployability — which is the reason this project is an IoT
project at all.

This subsection is written up as a boundary rather than a defect because the analysis that locates the
boundary is the same analysis that justifies the design. The 8.8 cm floor is *derived*, and §5.8 sets the
band ceiling at 62.5 % of Nyquist as an engineering choice with margin to spare; both are variables, not
constants of nature. What is not a variable is Gate 3.

## 9.3 Where the system is weaker than it appears

Four items, each of which an examiner could reasonably press on, and each of which is stated here
rather than discovered there.

**The on-device classifier is a rule, not a model.** The firmware grades with a fixed threshold pair
in `probe_config.h`. That is a consequence of flash and RAM budget, and it means the *published grade*
and the *offline analysis of the same features* can disagree. §8.4 reports that disagreement rather than
hiding it. The mitigation is architectural: the raw features are published alongside the grade, so the
platform always has the evidence needed to overrule the node.

**No secure boot, no signed updates, no flash encryption.** The security measures of §7.4 are real but
partial. A device that validates the broker's certificate but does not validate its own firmware image
can be compromised by physical access. For a survey tool that is carried and charged by its operator
this is a proportionate risk judgement, and it is recorded as a gap rather than described as a design
choice.

**The contact-quality indicator is a proxy, not a measurement.** §4.4 and §6.6 both say so. Its
utility is bounded by whether it explains the residual variance, which §8.3 measures; if it explains
little, the gate is decoration and should be removed rather than kept for appearance.

**Milestone 2's gateway does not exist.** §7.1 claims a gateway only in the second milestone, and
Chapter 7.1's table is explicit that Milestone 1 contains a sensor node. A reader who checks MILO *b*
against the submission will find the platform argument complete and the gateway argument partially
complete, which is the truth.

## 9.4 What the method fundamentally cannot measure

The instrument measures a **tone**, and a tone is a function of the mechanical boundary condition. It is
not a function of the adhesion force. Three consequences that no amount of engineering removes:

1. **It cannot report bond strength.** A large mechanically-detached region and a large weakly-bonded
   region can produce the same tone. The engineering question "is this safe" and the inspection question
   "is this bonded" are different questions, and only the second is within reach.
2. **It cannot report depth or extent independently.** §5.4 shows the frequency depends jointly on size
   and bond stiffness. Recovering both from one scalar is under-determined; recovering them from the
   feature vector is over-constrained by the small number of reference panels available. This is the
   boundary the original plan's single-feature design would have hit hardest.
3. **It cannot see the substrate.** Everything here concerns the finish layer. Debonding of the
   substrate from the structure, or reinforcement corrosion, are outside the modality entirely.
4. **It cannot report an absolute debond size.** This is a consequence of item 1 combined with the fact
   that the system carries **no material properties** (§7.7.1): a frequency becomes a size only through
   $f_1 \propto 1/a^2$, and the position of that curve depends on $E$, $
ho$ and $h$, none of which the
   instrument measures. What it *can* report is a measurement's deviation from a bonded reference taken
   in the same session on the same facade. Two consequences follow, and both are field-visible:
   (a) moving to another building requires a new reference, because the finish and its thickness change
   and the comparison is no longer like-for-like; and (b) **no size floor can be quoted for a building
   whose finish build-up has not been established**, because the floor itself scales as $\sqrt{h}$
   (Table 5.8) and moves by a factor of 2.4 across finishes a surveyor would call "render". Chapter 8's
   size-frequency relation is the physics of the measurement; it is not a transferable calibration.

## 9.5 Future work, ordered by value

| # | Item | Why it is next | Effort |
|---|---|---|---|
| 1 | **Execute the validation protocol (Appendix C.4)** on graded reference panels | Moves every claim in Ch. 8 from SYNTHETIC to measured; it is the only way to test P6 | 1–2 weeks |
| 2 | **Bench-measure the plunger travel time** (Appendix C.3a), then shorten the energisation pulse from 120 ms to just above it (§6.2) and re-tune the cap material | Removes the plunger hold, cutting both coil heating and the boundary-condition change during the measurement; §5.6's pulse model is a screening model, so the contact time is a required commissioning step, not a refinement | 2 days |
| 3 | **Characterise the probe's own transfer function** against a steel block, and verify common-mode rejection numerically | Turns §6.3's common-mode argument from an argument into a measured quantity | 2–3 days |
| 4 | **Build Milestone 2's gateway** (ESP-NOW concentrator, local broker, store-and-forward) | Completes MILO *b*'s gateway requirement | 1 week |
| 5 | **Field trial on a real facade** with an independent inspector's tap survey as ground truth | The only test that matters for whether the method is useful | 2–4 weeks |
| 6 | **Probe orientation channel** — read the MPU6050's three rate gyroscopes, which the firmware already configures (`MPU6050_REG_GYRO_CONFIG`) but never reads, and publish tilt alongside the features | **No new hardware, no new pins, no new bus traffic** — three more register reads in the transaction the accelerometer already makes (§7.2.1). It converts §8.3's dominant residual into an attributable quantity: the median within-location CV of `impulse_norm` is **14.92 %** with 98.5 % of locations failing the 5 % criterion, and probe *orientation* is a component of that variance that is presently neither measured nor logged. It is also the prerequisite for item 7, since "the same point" in two surveys needs a position *and* an orientation | **1 day** |
| 7 | **Instrumented survey plan** — two in-plane ranging beams (left and down) giving the probe's coordinates, an accelerometer-plus-gyroscope tilt channel, a cloud-issued measurement plan, guidance to the next point, and coverage confirmation returned to the platform. Specified in §9.5.1 | Turns a *measurement* into a *survey*: it removes manual grid alignment (the largest remaining source of position error, §7.7.1), makes coverage a computable quantity, and lets the platform hold the size baseline a single reading cannot (§9.4). It is the platform-side half of Milestone 2 and the clearest way to complete MILO *b*'s **platform** requirement, which M2 otherwise answers only with a gateway. **Nothing of it is reserved today** — the I²C bus will carry the ranging parts, but device addresses, drivers, payload fields and an MQTT *downlink* (the firmware is publish-only; `mqtt_event_handler` contains no `subscribe` call) all have to be built | **3–4 weeks** |
| 8 | **Extend the grid map into a level-set / imaging reconstruction** — use the size-frequency relation to estimate each hollow's extent from the sampled cells | A rendered map is already specified and bounded in §7.8 (flat Voronoi cells, pitch shown). Any step beyond that — smoothing, contours, or a stated defect extent — claims resolution the sampling does not provide: at the §C.5 default a 10 cm defect would render as a 60 cm blob (§7.8.3) | research-scale |
| 9 | **Multi-position array** — two or three microphones on known baseline offsets, to triangulate a hollow within the panel | Addresses §9.4's under-determination by adding spatial information rather than spectral | research-scale |
| 10 | **Wideband accelerometer or PVDF film as a force channel** | The conventional instrumented-tap configuration; removes the strike-energy uncertainty that §2.3 identifies as the weakest feature | 2 weeks |

Items 8 and 9 are the research directions that would make this a genuinely novel contribution rather
than a competent instrumented tool; item 1 is the one that must happen before any of them is worth
attempting.

### 9.5.1 The localisation scheme, stated concretely

Specifying this properly makes it smaller than the first sketch of it.

**Two ranging beams, not four.** The pair measures the distances $d_{left}$ and $d_{down}$ to the two
bounding lines that define the datum, and those *are* the coordinates once the probe's tilt is accounted
for:

$$x = d_{left}\cos\theta, \qquad y = d_{down}\cos\theta .$$

**The tilt term is not a correction applied to the measurement — it is the conversion itself.** At 10° it
is 30 mm on a 2 m throw, and at 20° it is 121 mm, against a grid pitch of 50 mm (§7.8.2), so it cannot be
treated as negligible. The two beams are the ones pointing away from the operator's hand, which is on the
body of the probe.

**And $\theta$ cannot come from the accelerometer alone, which is the non-obvious part.** An
accelerometer gives tilt only while it is still *and* not rotating; a *rate* of change of tilt is the
gyroscope's job. Through the seating action — a hand sets the probe down, rolls it onto the wall and
holds it — the tilt is changing continuously, and that is precisely the interval in which the coordinates
are wanted. So the tilt must be integrated from the gyroscope between the last known-good static
attitude and the measurement. The drift that integration accumulates is bounded by that interval, and
**each point supplies roughly two seconds of stillness at the 2 s cadence (§7.7.3), which re-observes
gravity and pulls the drift back** — an ordinary complementary filter. It needs no extra action from the
operator and no calibration procedure.

**The wall's size comes from the plan, so the other two beams are not needed.** Once the cloud issues a
plan it already states $W \times H$, so the two measuring beams give $x$ and $y$ and nothing further
is required for position. Beams pointing "up" and "right" serve only the *other* workflow — arriving at
a wall with no plan and having to size it in the field. **Under plan-then-survey, two beams suffice and
the ranging cost halves**, along with one of the I²C address conflicts.

**What it does not need.** It does not need the probe's height off the wall as a measured quantity, and
it does not need a seating interlock built from the rangefinders: §C.5 already requires the probe to be
pressed against the wall before the trigger is used, and the three contact feet of §6.4 define that
state. **Treating "what if someone triggers it in mid-air" as a design requirement would be building
hardware for a procedural fault**, and the operating procedure is where that belongs.

**And the accuracy requirement is low.** The coordinates only have to identify which grid cell the probe
is standing on — some 50 mm under the pitch a 10 cm defect demands (§7.8.2). Sizing a wall to the
centimetre is neither attempted nor needed, which is what makes the residual range and field-of-view
questions of the VL53-class parts tolerable rather than disqualifying.

---

# 10. Conclusion

This project set out to instrument a practice that has been unchanged for centuries — tapping a wall and
listening — so that its output becomes a repeatable, timestamped, spatially-indexed measurement that can
be transmitted and compared. The system as delivered does that: a solenoid applies a controlled strike,
a microphone captures the response, an ESP32 extracts spectral features on the edge, and MQTT carries
them to a ThingsBoard dashboard where a survey reads as a grid rather than as an inspector's memory.

The report's substantive contribution is not the instrument but the **analysis that corrected it**.
Two assumptions in the original design did not survive scrutiny, and neither failure would have
announced itself in operation:

- The **sensing modality was mismatched to the physics by two orders of magnitude.** A debonded finish
  layer resonates between hundreds of hertz and tens of kilohertz; the intended accelerometer's Nyquist
  limit is 500 Hz. The system would have worked perfectly and measured nothing but its own recoil.
  Correcting this required deriving where the signal lives — the plate-on-foundation model of Chapter 5 —
  before it was possible to know that the sensing chain was wrong.
- The **interference-cancellation scheme could not work as designed**, because the interference it meant
  to subtract is absent from the baseline it meant to subtract from. The design's real principle is
  model-level common-mode rejection, which is sound but conditional on a differential measurement —
  which is why the operating procedure, not the hardware, is what makes the measurement valid.

Working through the corrected model produced results with real engineering content: an analysis band of
300 Hz–15 kHz justified from the plate law rather than chosen; a strike contact time of 300 µs chosen to
place the excitation null above the modes of interest; a predicted size floor of 7.0 / 8.8 / 11.3 cm, and
a predicted observable bond-stiffness window that saturates at 39 % of the intact bond — both stated as
performance boundaries rather than buried; a demonstration that the ring-down feature is a dead channel
for two of the three finish materials; and a two-parameter size-frequency fit that is physically correct
where the originally planned one-parameter fit is not.

The system's honest position is a **screening and change-detection tool for large delaminations on tiled
and rendered facades, in the 10 cm-and-above range, used differentially against a bonded reference**.
That is a narrower claim than the project originally intended to make, and it is a claim the evidence
supports. The next step is not a design change but a measurement: execute the validation protocol of
Appendix C.4 on graded reference panels, and replace the synthetic results of Chapter 8 with real ones.

---

# References

Numbered in citation order. Items marked **[VERIFIED]** were retrieved from the primary source; items
marked **[TO VERIFY]** could not be confirmed and must be checked before submission — see Appendix B.1
for the full verification ledger.

## Regulatory and domain

[1] **[VERIFIED]** Buildings Department, HKSAR Government. *Mandatory Building Inspection Scheme and
Mandatory Window Inspection Scheme.* https://www.bd.gov.hk/en/safety-inspection/mbis/index.html —
requires inspection of buildings **aged 30 years or above**; a Registered Inspector inspects common
parts, external walls and projections/signboards.

[2] **[VERIFIED]** *Buildings Ordinance* (Cap. 123) and *Buildings (Inspection and Repair) Regulations*
(Cap. 123P), Hong Kong e-Legislation. https://www.elegislation.gov.hk/hk/cap123

[3] **[VERIFIED]** Buildings Department, HKSAR Government. *PNBI-10: Code of Practice for Building
Inspection*, current issue May 2023. Documents **hammer tapping** as an inspection method and uses the
terms "hollow sounding concrete", "Spalling of concrete" and "Delamination".

[4] **[VERIFIED, metadata only]** *JGJ/T 110-2017 建筑工程饰面砖粘结强度检验标准* (Standard for
inspection of adhesive strength of exterior wall face tiles), MOHURD, issued 2017-05-15, in force
2017-11-01, superseding JGJ 110-2008, referenced by GB 50210-2018. **This is a destructive pull-off
adhesion test, not a survey method** — the distinction is material to §2.4. Full text is paywalled;
only database metadata was retrieved.

[5] **[TO VERIFY]** An authoritative HK or GB source that formally defines the Chinese term **空鼓**.
The English "hollow sounding" is documented in PNBI-10 [3]; the Chinese term's formal definition was not
locatable in a primary source. Do not cite a definition that has not been seen.

[6] **[TO VERIFY]** Whether the 30-year MBIS threshold [1] has been amended since the page revision
consulted. Confirm against the current BD website before submission.

## WorldSkills

[7] **[VERIFIED]** WorldSkills International. *Competition Rules*, WSI_OD03, v11.1.
https://www.worldskills.org/resources/download/3745/34979/36045?l=en — the source for the assessment
method cited in Appendix B.1.3: two marking methods, **Measurement** (§11.3, §11.6.6) and
**Judgement** (§11.6.7); the 100-mark scheme (§11.5.1); 5–9 Assessment Criteria (§11.5.2); sub-criteria
(§11.5.3); 100–250 Aspects each tied to exactly one occupational-standard section (§11.5.4); ≤2 marks
per Aspect (§11.5.5); Test Project definition (§10.1) and 15–22 h duration (§10.2).

[8] **[VERIFIED — as a gap]** WorldSkills International. *Skill 559: Internet of Things.*
https://worldskills.org/skills/id/559/ — the page exists but is a **stub carrying no downloadable
standard**. Recorded as the basis for open item U1 (Appendix B.1): no public WSSS could be obtained for
an IoT skill.

[9] **[VERIFIED]** WorldSkills International. *WorldSkills Occupational Standards (WSOS) catalogue.*
https://worldskills.org/what/projects/wsos/ and https://worldskills.org/what/projects/wsos/2026/ —
64 skills in 6 categories for the current cycle; **"Internet of Things" does not appear**. Confirms the
WSOS formulation ("the individual needs to know and understand" / "the individual shall be able to") and
the biennial update cycle. The adjacent-skill structures used as a **labelled proxy** in Appendix B.1.4
are from this catalogue.

[10] **[TO VERIFY]** Whether Internet of Things was ever run as an Official WorldSkills competition
skill, and under what skill number. It appears only as a Future Skills demonstration in the material
retrieved (Kazan 2019, WorldSkills Russia Future Skills Camp 2020).

## Security and IoT standards

[11] **[VERIFIED]** ETSI. *EN 303 645 — Cyber Security for Consumer Internet of Things: Baseline
Requirements.* v2.1.1 (2020-06) and v3.1.3 (2024-09).
https://www.etsi.org/deliver/etsi_en/303600_303699/303645/ — clauses 5.1–5.13 (v2.1.1) with chapter-6
data-protection provisions; v3.1.3 adds clause 5.0 "Reporting implementation" and extends chapter 6.
The 13 provisions of clause 5 are the benchmark used in Appendix B.4.

[12] **[VERIFIED]** ETSI. *TS 103 701 V1.1.1 (2021-08) — Cyber Security for Consumer Internet of Things:
Conformance Assessment of Baseline Requirements.* The companion assessment specification.

[13] **[VERIFIED]** National Institute of Standards and Technology. *NISTIR 8259A — IoT Device
Cybersecurity Capability Baseline.* April 2020. https://nvlpubs.nist.gov/nistpubs/ir/2020/NIST.IR.8259A.pdf
— the six device capabilities: Device Identification; Device Configuration; Data Protection; Logical
Access to Interfaces; Software Update; Cybersecurity State Awareness.

[14] **[VERIFIED]** National Institute of Standards and Technology. *NISTIR 8259B — IoT Non-Technical
Supporting Capability Baseline.* https://nvlpubs.nist.gov/nistpubs/ir/2021/NIST.IR.8259B.pdf — the four
non-technical capabilities: Documentation; Information and Query Reception; Information Dissemination;
Education and Awareness.

[15] **[VERIFIED — important]** National Institute of Standards and Technology. *NIST IR 8259* (May
2020) was **withdrawn on 20 April 2026** and is superseded by **NIST IR 8259r1 (April 2026)**. Cite the
revision, not the withdrawn original. *(This is a recent change and is exactly the kind of currency
error a 2020-vintage report would carry.)*

[16] **[VERIFIED]** *Product Security and Telecommunications Infrastructure Act 2022* (c. 46),
Part 1 Chapters 1–3. https://www.legislation.gov.uk/ukpga/2022/46 — the UK statutory instance of the
EN 303 645 principles; the security requirements (passwords, reporting, minimum update periods) are in
SI 2023/1007 Schedule 1.

[17] **[TO VERIFY]** The commencement instrument for [16]. The Act and the SI were retrieved; the
commencement order was not.

## Protocols

[18] **[VERIFIED]** OASIS. *MQTT Version 5.0*, OASIS Standard, 07 March 2019.
https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html — §1.6 and Chapter 5 (Security, non-normative);
§5.1 specifies port 8883 for TLS; §5.4.3 server authentication; §5.4.7 hostname association including
CRL/OCSP; §4.12 Enhanced authentication. **Note:** MQTT v5.0's normative TLS reference is **RFC 5246
(TLS 1.2)**, not RFC 8446 — this report specifies TLS 1.3 because it is available in the platform, not
because the MQTT specification requires it. Do not misattribute.

[19] **[VERIFIED]** Rescorla, E. *The Transport Layer Security (TLS) Protocol Version 1.3.* RFC 8446,
IETF, August 2018. Obsoletes RFC 5077, 5246 and 6961.

[20] **[VERIFIED]** Espressif Systems. *ESP-IDF: Certificate Bundle.*
https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/protocols/esp_crt_bundle.html
— the bundle embeds the Mozilla NSS root store (130+ certificates in the full bundle, ~35 in the
filtered default, ~94 % of the absolute count and ~99 % of market share); it "will have to be updated if
any of the certificates are retracted"; cross-signed support adds ~1 kB peak run-time heap during the
handshake, scaling with the maximum RSA key size. Cited in §7.4 and Appendix B.4.1 as the reason the
IDF version must be pinned.

## Engineering and metrology

[21] **[TO VERIFY]** ASTM C1383-15. *Standard Test Method for Measuring the P-Wave Speed and the
Thickness of Concrete Plates Using the Impact-Echo Method.* Cited in §2.2 as the established
impact-echo standard. **Confirm the current edition designation before submission** — the year suffix
may have advanced.

[22] **[TO VERIFY]** The NDE literature on the instrumented tap test and on spring models for
delamination in layered media. **§2.2's literature paragraph must be replaced with real, retrieved
citations.** This is the report's most conspicuous citation gap: the tap-ring method has a substantial
published literature and citing none of it is a weakness an examiner will notice. Priority: a
peer-reviewed paper on tap-test/impact-echo for tile or render debonding, and a text on modal analysis
of layered plates.

[23] **[VERIFIED — textbook standard]** The clamped circular plate eigenvalue used in §5.1,
$\alpha^2 = 10.2158$ for mode $(0,1)$. A standard result in any text on plate vibration; verify against
the edition held by the institution's library.

---

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
---

# Appendix B — WSSS and Standards Compliance Matrices

The full compliance analysis is in the separate file **`03_wsss_standards.md`**, reproduced as Appendix B below, which contains:

- **Verification status** — a ledger of the claims that were confirmed from primary sources (V1–V20)
  and the open items that were not (U1–U8), each with what to do about it.
- **B.1** — What the WorldSkills Standards Specification is; the status of an "Internet of Things"
  skill; the assessment method in full (verified, with the rule citations of [7]); the four adjacent
  occupational-standard structures retrieved as a **labelled proxy**; and a derived topic-coverage
  checklist explicitly *not* attributed to any WSSS.
- **B.2, Table B-1** — proxy-standard topic → this project's subsystem → the artefact that evidences
  it, plus a candid table of areas the project does **not** cover.
- **B.3** — Platform selection: criterion / benchmark / chosen / rejected / cost.
- **B.4, Table B-2** — 25 rows of: cited standard → what it constrains here → the measure implemented
  → the residual gap.
- **B.4.1** — The ESP32 memory caveat about certificate-chain validation, with the exact configuration
  and the documentation quotes.
- **B.5** — Hong Kong domain context, including the proof-test-versus-screening distinction.
- **B.6** — How to write this material into the report.

**Reading order for an examiner:** B.1.3 (the assessment method, which is verifiable) then B.2 (the
mapping), then B.4 (the compliance matrix). B.1.2 is the honest gap statement and should be read rather
than skipped, because it is the reason B.1.4 uses a proxy at all.

---

# Appendix C — Measurement Protocol

This appendix is the operational document. It is written so that a second person, given the built
prototype and this appendix, can reproduce the measurements and the calibration without further
instruction.

## C.1 Equipment required

| Item | Purpose | Notes |
|---|---|---|
| Probe unit, assembled per §6.7 | Measurement | Serial number recorded |
| Bonded reference panel | Calibration baseline | See C.4 |
| Graded debond reference set | Calibration and validation | See C.4 |
| Steel or granite block, ≥ 100 mm thick, lapped face | Probe self-check | Face must be flat and rigid enough to act as an ideal reflector |
| 12 V 2 A regulated bench supply | Power | Bench use only |
| Torque-limited driver, 0.5 N·m | Assembly of the solenoid mount | Prevents crushing the compliant washers |
| Surface plate or granite tile | Contact-foot coplanarity check | 0.05 mm flatness is adequate |
| Hygrometer / thermometer | Records the ambient conditions with each session | The payload carries `temp_c` |
| Laptop with the MQTT client and the broker reachable | Observations | `mosquitto_sub -t 'probe/#' -v` |

## C.2 Pre-measurement checks (before every session)

1. **Assembly.** Solenoid head flat and 3.00 ± 0.10 mm above the plane of the three feet (check with a
   shim on the surface plate). Microphone port flush and gasket seated. Accelerometer bonded and its
   cable dressed so it does not bridge the plate and the microphone housing.
2. **Drive.** Flyback diode present across the coil with the **cathode to +12 V** (this is the single
   most common assembly error, and getting it backwards destroys the MOSFET on the first strike). Gate
   resistor and pulldown present. Bulk capacitor fitted close to the coil.
3. **Self-check against the steel block.** Three taps on the lapped face. Expected: a short, high
   `f_peak` with no in-band resonance; `band_ratio_lh` low; the three taps within the repeatability
   criterion. **Any in-band peak on a lapped steel face is a probe artefact** (§5.9) and must be
   investigated before any wall measurement is taken.
4. **Baseline noise.** One measurement with the trigger held but the probe held in air. Expected: a
   spectrum with no structure. This verifies that the ambient noise floor is below the strike's.
5. **Link.** Broker reachable, TLS handshake successful, `sp` flag false on the dashboard.
6. **Record** ambient temperature, humidity, probe serial number, and the day's reference-panel
   measurements (C.4) — the reference measurement must be taken *in the same session* as the wall
   measurements, because it is what discharges the common-mode assumption (§6.3).

## C.3 Bench characterisation (once per probe, and after any mechanical change)

**(a) Contact time.** Bond a small piezo film sensor to a steel target, hold the probe against it, and
capture the sensor output across the strike. Measure the contact duration from the force trace. Compare
with the design target of 300 µs (§5.6). **If the measured contact time is more than 50 % longer than
300 µs, replace the striking cap with a harder material and repeat.** Adjusting the electrical pulse
width does not change the contact time and is not the right lever.

**(b) Strike repeatability.** 50 consecutive strikes on the steel block at the specified 2 s cadence.
Report the coefficient of variation of the in-band RMS and of `f_peak_hz`. This is the bench measurement
that prediction P7 is tested against.

**(c) Probe transfer function.** Three taps on the lapped steel face, averaged. Any peak in this
average that is present in every measurement is a probe mode. Record the peak frequencies in the probe's
calibration record; they are expected below 300 Hz (§6.3), and a peak *above* 300 Hz is a defect to be
fixed, not compensated for.

**(d) Thermal check.** 60 strikes at the specified cadence, with the coil's case temperature monitored.
Confirm the firmware's duty budget holds the temperature within the part's rating and that no cooldown
event is triggered spuriously.

## C.4 Calibration against reference panels

**The reference set.** Panels of the same finish material as the intended survey, prepared as:

| Panel | Construction | Represents |
|---|---|---|
| B0 | Finish bonded fully across a sound substrate | Bonded control |
| B1 | Finish with a thin compliant interlayer, diameter 10 cm | Small/partial debond |
| B2 | Same, 20 cm | Medium debond |
| B3 | Same, 30 cm | Large debond |
| C0 | Finish a known and *documented* debond of each size, substrate directly cast — no compliant filler | Fully debonded reference |

**Procedure.** For each panel: mark five measurement locations on a fixed grid, and take five taps at
each, respecting the 2 s cadence. That gives 25 taps per panel and, with five panels, 125 taps per
session. Randomise the panel order between sessions so that thermal drift does not align with panel
identity.

**Analysis.** Follow Appendix D's script. **Report the result as a confusion table, not as a
percentage.** A percentage hides which cells are populated, and the cells are the finding:

| | Called bonded | Called debonded |
|---|---|---|
| **Actually bonded (B0)** | correct rejection | **false alarm** — costs a manual re-inspection |
| **Actually debonded (C0, B2–B3)** | **miss** — costs a safety event | correct detection |

**Decision rule for accepting the calibration.** If the two populations (bonded and debonded
measurements) overlap such that no threshold separates them with a false-alarm rate below 20 % at a
miss rate below 10 %, then **the calibration has failed and must be reported as a failure.** Do not
search for a threshold that "works"; a threshold chosen to produce a desired confusion table is not a
calibration.

**Recording the calibration.** Write the chosen thresholds into `probe_config.h`, rebuild, and record
in the dashboard's device attributes: the probe serial number, the firmware version, the reference panel
set, the date, and the thresholds. A threshold without this record is not traceable.

## C.5 Wall survey procedure

This procedure is what makes the measurement valid. **A single tap in isolation cannot be interpreted**
(§6.3).

1. **Establish the reference.** On the same facade, find a region the inspector judges bonded, and take
   five taps there. This is the session's reference measurement.
2. **Survey on a grid.** Tap on a fixed grid — 0.5 m spacing is a reasonable default for a facade
   screening — and record the `location_id` for each point in the same scheme, so the dashboard plots a
   grid rather than a scatter.
3. **Three taps per point**, at the cadence. Report the median of the three.
4. **Compare against the reference**, not against an absolute number. A point is *suspect* when its
   `band_ratio_lh` and `f_peak_hz` differ from the session's reference by more than the calibrated
   margin.
5. **Mark, do not conclude.** A suspect point is a point for a human to re-inspect with a hammer, and
   for a second method to confirm. The instrument's output is an *attention map*.
6. **Record the conditions.** Ambient temperature and the probe serial number go with the data; a
   survey compared against another survey taken in different weather is a comparison the design cannot
   support.

**What the operator must be told**, in the operating document and in training:

- The instrument cannot see debonds smaller than roughly 10 cm in tile or render, or 15 cm in stone.
  **A clean survey is not a certificate of soundness at either end of the size range.** *The floor is not
  a single number*: it scales as $\sqrt{h}$ with the finish thickness (§5.5.2, Table 5.8), so the same
  instrument has a 10.7 cm floor on a 30 mm render and a 4.4 cm floor on a 5 mm one. Record the finish
  construction if it is known, and never quote the floor for a building whose build-up has not been
  established.
- **The instrument is also blind to very large debonds, and this is the counter-intuitive half.** The
  detection test asks whether a mode has come down *into* the 1–15 kHz band. A debond big enough for its
  mode to fall below the 1 kHz crossover reads as bonded again — on 20 mm render that is roughly 34 cm
  and up (§9.2). So the rule responds to a *size window*, not to severity, and **the largest and most
  dangerous separations are the ones most likely to read clean**. An operator who understands only the
  small-debond limit will read a clean large panel as sound, which is exactly the wrong inference. If a
  survey region is visually suspect, tap it and treat the reading as advisory at any size.
- The reading is relative to the session's reference. Moving to another building requires a new
  reference.
- A suspect reading requires a manual re-inspection. The instrument narrows the search; it does not
  make the finding.

## C.6 Safety

| Hazard | Control |
|---|---|
| 12 V supply | Bench supply with current limit set to 2.5 A; no mains exposure in the prototype |
| Inductive kick | Flyback diode, verified at assembly **(cathode to +12 V)** |
| Coil heating | Firmware duty budget plus the failsafe timer; 60-strike thermal check per C.3(d) |
| Battery | The portable configuration uses a Li-ion pack with protection; charging is supervised and outside this prototype's scope |
| Acoustic exposure | **Not characterised** (§3.2, §7.6). Do not hold the strike near the ear. A formal exposure assessment is a pending item, and the design's move away from the human-dominant low-frequency range is a mitigation, not a demonstration |
| Working at height | The prototype is bench and ground-level only. Any elevated survey requires the applicable working-at-height regime and is outside this document |

**Bench-only rule.** During this prototype's life the probe is operated on the bench or at ground level
on reference panels. It is not operated on a live facade, and it is not operated by anyone who has not
read this appendix.

## C.7 Why the exposure question is left open

It would be easy to write a reassuring paragraph here and it would be wrong, so the reasoning is set out
instead.

The strike is audible and close to the operator's hand. An assessment would require the absolute sound
pressure level at the operator's ear position, over the survey's duration — which needs a calibrated
sound level meter and a defined duty cycle, neither of which this project has. What the design *does*
have is a defensible steering argument: the analysis band starts at 300 Hz and the strike's spectral null
sits at 5 kHz, so the design is aimed away from the range where hearing is most sensitive, and the
strike energy is bounded by the firmware. That is a mitigation. It is not an exposure assessment, and the
difference between the two should not be blurred in a report about something people will hold in their
hands.

---

# Appendix D — Firmware and Analysis Artefacts

The full source is in `05_firmware/` and the analysis script in `06_analyze_tap.py`. This appendix is the
index, the reproduction procedure, and — importantly — the record of what the artefacts do **not**
establish.

## D.1 File index

| File | Lines | Purpose |
|---|---|---|
| `05_firmware/README.md` | ~820 | Build, flash, provision, operate, troubleshoot; includes a "what this instrument is not" section that is part of the report's honesty posture |
| `05_firmware/main/app_main.c` | ~2 220 | Application: I²S capture, self-contained radix-2 FFT + Hann window with coherent-gain correction, MPU6050 reads, solenoid drive with three independent guards, MQTT over TLS, console |
| `05_firmware/main/probe_config.h` | ~465 | Single source of truth: pins, sample rate, band (300–15000 Hz), crossover (1000 Hz), τ window (3–60 ms), thermal limits, topic strings |
| `05_firmware/main/Kconfig.projbuild` | ~140 | Tunables with fallbacks |
| `05_firmware/sdkconfig.defaults` | ~40 | Build-time settings the firmware depends on (FreeRTOS tick rate 1000 Hz, CA bundle). Not optional: the tick rate is what makes every sub-10 ms delay in the measurement path a real delay |
| `05_firmware/CMakeLists.txt`, `main/CMakeLists.txt` | ~50 | Build registration |
| `06_analyze_tap.py` | ~3 800 | Offline analysis: integrity checks, descriptive statistics, repeatability, discrimination testing, size-sensitivity fit, classifier comparison with group-wise CV, ROC/AUC, expected-cost threshold analysis |
| `results/results.md`, `results/figures/`, `results/features_analysed.csv`, `results/run_log.txt` | — | Generated by the script |

## D.2 Reproduction

```
python 06_analyze_tap.py --demo --outdir results --seed 7
```

Deterministic under the seed, and **the seed matters**: the numbers in Chapter 8 are the
seed-7 run recorded in `results/run_log.txt`, and a different seed re-partitions the panels
and changes the per-size detection rates, the selected reference classifier and the cost
analysis. Reproduce with the seed above, not with the script's own default.

With `--demo` the script generates a dataset from the forward model of §8.1 and stamps every
table and figure `SYNTHETIC DEMONSTRATION DATA — NOT MEASURED`. With real feature CSVs (or a
directory of recorded waveforms) supplied via `--input`, the same script performs the same
analysis without the stamp; that is the path that produces the report's *measured* results,
and it is the same code path, so nothing but the input changes.

**Library dependencies.** numpy, scipy, scikit-learn, matplotlib, pandas. Statistics are taken from
scipy rather than hand-rolled (Kruskal–Wallis, Mann–Whitney, Holm correction), AUC from
`sklearn.metrics`, and the group-wise split from `sklearn.model_selection.GroupKFold`.

## D.3 What the firmware does *not* contain, and must not be claimed to

| Absent | Consequence |
|---|---|
| A trained classifier. Grading is a fixed threshold pair in `probe_config.h` | The published grade can disagree with an offline analysis of the same features; §8.4 reports the disagreement, and the raw features are published so the platform can overrule the node |
| Secure boot, flash encryption, signed OTA | A device with physical access can be reflashed. §7.4 and §9.3 record this as a gap, not a design choice |
| Mutual TLS | The device validates the broker; the broker authenticates the device by credential, not by certificate |
| Any claim that the accelerometer detects debonding | It is a contact-quality channel. The code comments say so, the README says so, and §4.4 says why |
| A validated threshold | The defaults in `probe_config.h` are *placeholders* pending Appendix C.4. A dashboard showing them is showing an untuned constant, and §7.5 requires the dashboard to say so |
| Measured performance | No figure in this report was measured on hardware. §8.0 and §9.1 state what the synthetic results do and do not support |

## D.4 The three solenoid guards, and why there are three

The coil is a 23 W **intermittent-duty** part. A firmware bug that leaves the gate asserted will destroy
it, and possibly the supply. The guards are deliberately redundant because each covers a different
failure mode:

| Guard | Mechanism | Covers |
|---|---|---|
| Minimum interval (2000 ms) | Refuses a strike inside the interval | Operator re-triggering; a stuck trigger button |
| Sliding duty budget | Counts strikes in a window; forces a cooldown past the budget; logs `ESP_LOGE` | A cadence that is legal per-strike but thermally unsustainable in aggregate |
| Timer failsafe | An independent `esp_timer` de-asserts the gate if the main task does not, within the worst-case pulse plus margin | A hang or a blocked task in the path that would normally de-assert the gate |

A single guard would be simpler and would be sufficient for every *foreseen* condition. The third guard
exists for the unforeseen one, and it is the one that costs nothing to add and is hardest to justify
removing.

## D.5 SIMULATION mode

The firmware can synthesise plausible features so that the MQTT and dashboard paths can be demonstrated
before the transducer chain is finished. It **must** set `"sp": true` in the payload and print a loud
boot warning, and §7.5 requires the dashboard to render that flag unmistakably. The reason is the one
stated there: simulated readings look exactly like real ones, and a viewer who does not know the
difference will act on a fabricated result. This is treated as a safety requirement rather than a
courtesy.

**Verification status of the firmware.** The firmware was written and reviewed but **not compiled** —
no ESP-IDF toolchain was available in the environment where it was produced. It is therefore verified by
inspection only: brace and parenthesis balance, every configuration macro used is defined, and the
duty-budget check is against the worst-case interval the interlock permits. **It must be built and
flashed before any claim of function is made**, and the first build should be treated as a debugging
exercise rather than a formality. This is recorded because a firmware appendix that implies compilation
it did not undergo would be exactly the kind of plausible-looking unverified claim the rest of this
report is written to avoid.

---

# Appendix E — Figure and Table Index

## E.1 Figures

All figures are generated by `06_analyze_tap.py` into `results/figures/`, **except M1–M4**, which are
analytic Chapter-5 figures produced by `_repro/ch5_figures.py` and live in the same directory. Figures
1–7 are marked **SYNTHETIC** until the script is run on measured data (§9.1). The index states what each
figure is *for*, so that it can be read against the claim it supports.

| Fig | File | Content | Supports | Status |
|---|---|---|---|---|
| M1 | `fig_m1_f1_vs_diameter.png` | $f_1$ vs debond diameter, three materials, band shaded, size floors marked | §5.4, Table 5.3 | Analytic |
| M2 | `fig_m2_detection_limits.png` | Left: size floors (7.0 / 8.8 / 11.3 cm). Right: the observable bond-stiffness window vs size | §5.5, §5.5.1, Table 5.4 | Analytic |
| M3 | `fig_m3_pulse_energy.png` | Strike energy fraction vs contact time, with $T = 300$ µs marked | §5.6, Table 5.5 | Analytic |
| M4 | `fig_m4_helmholtz.png` | Cavity Helmholtz resonance vs cavity volume, with the band and the 200 mm³ target | §5.9, Table 5.6 | Analytic |
| 1 | `fig01_feature_distributions.png` | Feature distributions by grade, small multiples | §8.2, P1/P4 | SYNTHETIC |
| 2 | `fig02_f_peak_vs_size.png` | $f_{\text{peak}}$ vs debond size with both fits overlaid | §8.5, P2/P8 | SYNTHETIC |
| 3 | `fig03_roc_curves.png` | ROC for the three classifiers on one axis | §8.4 | SYNTHETIC |
| 4 | `fig04_confusion_matrices.png` | Normalised confusion matrices, side by side | §8.4 | SYNTHETIC |
| 5 | `fig05_expected_cost.png` | Expected cost vs threshold, optimum annotated | §8.6 | SYNTHETIC |
| 6 | `fig06_repeatability.png` | Within-location CV and Bland–Altman | §8.3, P7 | SYNTHETIC |
| 7 | `fig07_feature_roc_panel.png` | Per-feature ROC, small multiples | §8.4, P3/P5 | SYNTHETIC |

A CAD or photograph of the assembled probe belongs alongside Figure 1 and is not produced here;
§6.7 gives the sequence and §6.4 the dimensions.

## E.2 Tables

| Table | Content | Chapter |
|---|---|---|
| 5.3 | $f_1$ vs debond diameter and bond stiffness, three materials | §5.4 |
| 5.4 | Detection limits: size floor and the observable bond-stiffness window | §5.5, §5.5.1 |
| 5.5 | Strike energy fraction vs contact time | §5.6 |
| 5.6 | Helmholtz resonance of the microphone cavity | §5.9 |
| 5.7 | Predicted ring-down time vs diameter | §5.10 |
| 8.1 | Synthetic dataset construction | §8.1 |
| 8.2 | Descriptive statistics by grade | §8.2 |
| 8.3 | Repeatability | §8.3 |
| 8.4 | Discrimination testing | §8.4 |
| 8.5 | Size-sensitivity fits | §8.5 |
| 8.6 | Classifier comparison with CIs | §8.4 |
| 8.7 | Expected-cost thresholds | §8.6 |
| 8.8 | Prediction verdicts | §8.7 |
| 8.9 | Detection rate by debond size, out-of-fold | §8.4c |
| B-1 | Proxy-WSSS coverage | Appendix B |
| B-2 | Standards compliance | Appendix B |
| C.1 | Wall survey procedure | Appendix C |
| F.1 | MILO mapping | Appendix F |

---

# Appendix F — Assessment Mapping to MILOs a and b

## F.0 A note on which MILOs the EA assesses

The Module Assessment Scheme for EEE4483 assigns the end-of-module assessment in the form of a
mini-project, worth **40 % of the module mark**, and ticks MILO **a** and MILO **b** in the EA column.
MILO **d** appears in the Tests, Assignments and Workshop columns but **not** in the EA column.

**Consequence for this report.** The effort has been allocated accordingly: the device-to-application
chain (a) and the gateway/platform selection argument (b) are the spine of Chapters 3, 6, 7 and 8 and of
Appendices B and D. The performance, hazard and security analysis (d) is present — Chapters 5, 7.4, 7.6,
Appendix C.6, and the whole of the limitations chapter — but it is treated as supporting material rather
than as a primary scoring axis, and it has deliberately not been allowed to expand at the expense of
(a) and (b).

**An action for the student, not for the report.** Confirm this reading with the module lecturer before
submission. The column tick is unambiguous in the MAS document, but if the lecturer expects *d* to be
assessed in the mini-project, the balance of Chapter 7.4 and Chapter 9 should shift toward security and
risk. The report is written so that this shift is a re-weighting rather than a rewrite: the material is
present and cross-referenced.

## F.1 MILO a — plan and deploy IoT applications in real-life, from devices to application

The MILO's phrase "from devices to application" is the chain requirement. Evidence, in chain order:

| Stage | What is claimed | Evidence | Status |
|---|---|---|---|
| Device | A handheld node acquires a physical quantity and produces a digital measurement | §6.2–6.7, §7.2, `app_main.c` | Designed; not built |
| Transducer interface | A digital I²S microphone and an I²C accelerometer | `probe_config.h` pin map, §7.2 | Designed |
| Edge processing | Feature extraction on-device; raw data never leaves the node | §5.10, §7.3, `app_main.c` FFT | Written; not compiled |
| Local decision | Grade assigned on-device from the feature vector | §7.3 step 7, `probe_config.h` thresholds | Written; thresholds untuned |
| Transport | MQTT with a documented JSON schema and QoS 1 | §7.4, Appendix D.4 | Written |
| Platform | ThingsBoard: registry, telemetry, rule engine, dashboard | §7.5 | Specified |
| Application | Dashboard showing latest values, survey grid, alarms | §7.5 | Specified |
| **Real-life framing** | The application addresses a documented regulatory and safety need | §1.1, §2.4, Appendix B.5 | **Evidence cited** |
| **Validation** | The chain is shown to work end-to-end on hardware | **Not done** | **Gap — §9.1** |

**Honest assessment.** MILO *a* asks to "plan and deploy". This submission **plans** in full and
**deploys** in part: the architecture, the firmware, the protocol and the dashboard are specified and
implemented in source; nothing has been built or exercised end-to-end. The evidence for *planning* is
strong and argues for a good mark. The evidence for *deployment* is absent, and the report says so
rather than implying otherwise. **A demonstration of even one end-to-end measurement — one tap
appearing on the dashboard — would materially change this assessment**, and Appendix C.2 is written so
that it is a short path from where the project stands.

## F.2 MILO b — select and apply IoT gateways and platforms with reference to WSSS assessment method

This MILO has two halves, and they are answered separately because they are separately checkable.

### b(i) — Selection, with evidence of the comparison

| Decision | Options considered | Chosen | Justification | Evidence |
|---|---|---|---|---|
| Sensing modality | Manual tap; impact-echo accelerometer; ultrasonic; thermography; LDV; acoustic emission; GPR; instrumented tap with acoustic sensing | Instrumented tap with acoustic sensing | Cost and deployability by two orders of magnitude; the module requires a deployable low-cost node | §2.2, Appendix A.4 |
| Primary transducer | MPU6050 accelerometer; wideband piezo accelerometer + charge amp; I²S MEMS microphone | I²S MEMS microphone | Bandwidth intersection (§5.8); contact physics; cost; EMC | §4.2, §5.8 |
| Actuator | Spring/cam impactor; solenoid | Solenoid | Repeatability pursued in the electrical domain, where it is cheap | §6.2 |
| Platform | Metered general-purpose cloud IoT service; time-series DB + custom UI; purpose-built NDE cloud; ThingsBoard CE | ThingsBoard CE | One open-source package providing registry, ingestion, store, rules and dashboard; no licence cost; runs on a laptop | §7.5, Appendix B.3 |
| Broker | MQTT; HTTP; CoAP | MQTT over TLS | Dominant in IoT toolchains; QoS 1; small payload overhead; documented security model | §7.4, Appendix B.4 |
| Transport security | None; TLS with pinned leaf; TLS with CA-chain validation | CA-chain validation | The trap of silently-disabled verification is documented and avoided | §7.4, Appendix B.4.1 |
| Gateway | None; ESP32 as node only; separate concentrator + local broker | **Separate concentrator, Milestone 2** | An ESP32 that senses and publishes is a sensor node, not a gateway | §7.1 |

### b(ii) — "with reference to WSSS assessment method"

**This is where the honest answer matters, and Appendix B.1 gives it in full.** The short version:

1. **The WSSS for an "Internet of Things" skill could not be obtained from a primary source.** A skill
   page exists at the WorldSkills site, but it carries no downloadable standard, and IoT does not appear
   in the current published catalogue of occupational standards. Appendix B.1 states this as an open
   item (U1) rather than filling the gap with an invented section list — an invented citation would be
   worse than an admitted gap, because the examiner cannot check a fabricator's invention.
2. **What *is* verifiable is the assessment method**, from the WorldSkills Competition Rules: two
   marking methods (Measurement and Judgement), a 100-mark scheme, assessment criteria and sub-criteria,
   and aspects each tied to a section of the occupational standard. This is cited with a URL in
   Appendix B.1.3.
3. **The method's implication for this project** is that evidence should be *countable* wherever
   possible: message counts, timestamps, log entries, confusion tables — and that a claim of competence
   should be attached to an artefact rather than a narrative.
4. **Where the standard is unavailable, a labelled proxy is used.** Appendix B.1.4 retrieves real
   occupational-standard structures for adjacent skills (Industry 4.0, Cloud Computing, Cyber Security)
   and uses their *topic* structure as a coverage checklist, stated explicitly as a proxy and not
   attributed to any IoT standard. Appendix B.2 then maps this project's subsystems onto that checklist
   **and states which areas are not covered**.

**Honest assessment.** MILO *b* is the MILO this project answers best, because the selection argument is
genuinely worked: alternatives are compared, costs are given, and the two key component choices (the
microphone and the platform) follow from stated requirements rather than preference. The qualification
is that the "with reference to WSSS" clause is met by citing the assessment method and using a labelled
proxy for the standard itself, because the standard is not publicly obtainable. **The student should ask
the lecturer whether an official WSSS document is available through the institution** — if it is, the
proxy tables in Appendix B.1.4/B.2 should be regenerated against the real document, which is a
mechanical substitution because the table structure is already in place.

## F.3 Summary of the submission's strengths and gaps

| Strength | Evidence |
|---|---|
| A quantitative physical model that corrects the design and is cross-checked two ways | §4.2–4.3, §5.1–5.11 |
| An auditable component selection with alternatives and costs | §2.2, §5.8, §6.2, §7.5, Appendix B.3 |
| A complete, security-conscious device-to-application chain in implementation-grade detail | §7, Appendix D |
| A validation protocol with a stated failure condition and a cost-based threshold analysis | §8.1, §8.6, Appendix C.4 |
| Limitations stated as quantified boundaries rather than generic caveats | §5.5, §9, every chapter's own honesty notes |

| Gap | Where it is stated | What closes it |
|---|---|---|
| No hardware build, no end-to-end demonstration | §F.1, §9.1 | Build and run Appendix C.2 |
| No measured validation on reference panels | §9.1 | Execute Appendix C.4 |
| Firmware not compiled | Appendix D.5 | `idf.py build` |
| Gateway exists only in Milestone 2 | §7.1, §9.3 | Build the concentrator |
| Official WSSS unavailable; proxy used | Appendix B.1, §F.2 | Obtain the document from the lecturer |
| Acoustic exposure not characterised | §3.2, Appendix C.7 | Sound level measurement |

## F.4 A note on how to submit this

The report is written to be defensible under questioning rather than to look impressive, and that
strategy has a cost: it states its own gaps prominently, including in the abstract. **Do not edit those
statements out.** An examiner who finds a limitation the report disclosed will credit the disclosure; an
examiner who finds one the report concealed will discount everything else. The single highest-value
action available before submission is not more writing — it is to move one item off the gap table,
preferably the build, because "we built it and it produced this" is worth more than any amount of
additional argument.
