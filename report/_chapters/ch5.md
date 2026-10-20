
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
