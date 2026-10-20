
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
