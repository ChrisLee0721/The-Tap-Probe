
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
