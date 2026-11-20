# Probe ⇄ Dashboard wire protocol (v2)

Authoritative contract between the ESP32-S3 firmware (`05_firmware/main`) and the
analysis backend (`05_firmware/tools/mqtt_demo`).  Both sides must match this file.

Transport   MQTT 3.1.1 via the local broker.
Broker      tcp://192.168.3.12:1883   (device)     ws://192.168.3.12:8080/mqtt (browser)
Base topic  probe

dev id      probe-01  (from `PROBE_DEFAULT_DEV_ID`, editable on the device menu)

---

## 1. `probe/<dev>/waveform`  — raw tap waveform  (QoS 0, not retained)

Published once per detected tap.  The device triggers on |a| over a threshold and
captures `n` consecutive sample frames of the 3-axis accelerometer.

```json
{
  "dev":   "probe-01",
  "pt":    "P2",          // measurement point id, P0..P5 (see section 7)
  "seq":   42,            // monotonic per boot; a gap means a dropped packet
  "tap":   17,            // monotonic tap counter per boot
  "fs":    2567,          // MEASURED sample rate in Hz -- never assume it
  "n":     512,           // number of sample FRAMES in d
  "scale": 8192.0,        // LSB per g  (int16 value = round(g * scale))
  "pre":   48,            // frames captured BEFORE the trigger (pre-trigger)
  "trig":  1234,          // trigger magnitude, LSB (peak |a| at the trigger frame)
  "pkg":   0.42,          // OPTIONAL peak |a| at the trigger, in g (section 7.5)
  "sp":    false,         // OPTIONAL true == synthesised waveform, not a measurement (7.8)
  "d":     "<base64>"
}
```

`d` is base64 of a **little-endian int16** array of length `3*n`, interleaved
`x0,y0,z0, x1,y1,z1, ...`.  Unit is g via `scale`.

Total length for n=512: 3072 raw bytes -> 4096 base64 chars; the whole message is
about 4.2 kB.  The device's esp-mqtt transmit buffer is therefore 8192 bytes, not
the 1 kB default, and the broker must not cap a publish below ~6 kB.

**`fs` is measured on the device, not declared.**  The LSM6DS3's own FIFO does
not fill on this module (FIFO_CTRL5 reads back correctly but DIFF_FIFO stays 0),
so the firmware falls back to polling OUTX_L_XL and computes the achieved rate
from `esp_timer`.  On the bench that is 2.4-2.7 kHz against a 6.66 kHz ODR.  A
consumer must read `fs` from every message rather than caching one value.

---

## 2. `probe/<dev>/measurement`  — 2 s summary  (QoS 1, not retained)

Unchanged from v1.  Kept because it is cheap, proves liveness, and carries RSSI.

```json
{"dev":"probe-01","pt":"P2","n":230,"t1":[-0.002,0.001,0.002],
 "rms1":0.0014,"pk1":0.0034,"rssi":-28}
```

`t1` = mean offset vector in g over the last window, `rms1`/`pk1` in g.
`t2`/`rms2`/`pk2` appear ONLY when a second sensor is actually fitted.

---

## 3. `probe/<dev>/status`  (QoS 1, retained)

`online` on connect, `offline` as the last will.

---

## 4. `probe/<dev>/event`  (QoS 1, not retained)  — optional device notices

```json
{"dev":"probe-01","ev":"tap","n":17}      // informational
{"dev":"probe-01","ev":"menu","page":"MQTT"}
```

---

## 5. `probe/<dev>/cmd`  — backend -> device  (QoS 1)

The device subscribes to this on connect.  Unknown commands are logged and ignored.
Every command is acknowledged on `probe/<dev>/event` as
`{"dev":"...","ev":"ack","cmd":"<name>","ok":true}`.

| payload | effect |
|---|---|
| `{"cmd":"publish","on":true}` | enable/disable the periodic measurement publish |
| `{"cmd":"stream","on":true}` | enable/disable tap-waveform capture |
| `{"cmd":"led","on":true}` | heartbeat LED (optional; no-op if not fitted) |
| `{"cmd":"reboot"}` | restart the device |
| `{"cmd":"zero"}` | re-zero the accelerometer baseline |
| `{"cmd":"devid","v":"probe-02"}` | change device id (persisted in NVS) |

---

## 6. Analysis contract

The backend holds the offline analysis template `06_analyze_tap.py` (repo root)
and MUST call its `extract_features_from_waveform(t_s, amp, fs_hz)` — not a
re-implementation — so the live numbers are produced by the same code that
produced Chapter 8.

**Band re-parameterisation (mandatory, documented).**  The template's spectral
band is hard-coded to 300..15000 Hz with a 1 kHz low/high crossover because it
was written for a 44.1 kHz I2S microphone.  The LSM6DS3 cannot sample that high,
so the backend passes a reduced band to the same function.  That band is
**fixed**, not derived from `fs`:

    band       = [band_lo_hz, band_hi_hz]     defaults 30 .. 1000 Hz
    crossover  = crossover_hz                 default  300 Hz
    guard      = band_hi <= 0.45 * fs         (per message, Nyquist)

Defaults are adjustable at run time through `POST /api/config`.

Why fixed rather than `0.45*fs` / `0.45*fs/3`: `fs` is measured on the device
and varies between 2500 and 2650 Hz as the Wi-Fi stack preempts the poll loop.
A derived band therefore moved between taps (upper edge 1124-1194 Hz), so two
taps were analysed on slightly different frequency axes and the repeatability
statistics were comparing incommensurable numbers.  A fixed band makes every tap
comparable.  The Nyquist guard stays, so a slow poll interval narrows the band
instead of aliasing into it; when it does, the result is flagged
`band_clamped: true`.

The crossover is a **placeholder until real bonded/debonded samples exist.**  It
started life as `band_hi/3`, a ratio inherited from the microphone design
(15000/1000) with no physical meaning at accelerometer rates.  300 Hz is chosen
so that both sub-bands contain measurable energy inside a 1000 Hz band; it must
be re-derived from a real survey, not assumed.

Because the band differs from the report's 300..15000 Hz, `band_ratio_lh` is on
a different scale: it can exceed 1 (measured ~1.0-1.35 at the bench rate) and
must never be compared with the report's 0.78-or-0.19 cluster values.  The
backend's threshold range is [0, 2] for that reason.

**Per-tap absolute indication.**  The shipped rule from the template is a
one-feature threshold on `band_ratio_lh` oriented so that a LOWER ratio means
debonded:

    verdict = "DEBOND"  if band_ratio_lh <= TH_BAND_RATIO  else "BONDED"

`TH_BAND_RATIO` default 0.45 (between the bonded cluster ~0.78-0.82 and the
debonded cluster ~0.03-0.19 in `results/features_analysed.csv`); it is a
config value of the backend, exposed on the dashboard, never hard-coded in the
HTML.  This rule is a **reference-only single-tap indication**.  The measurement
result the dashboard reports is the differential grade of section 7, which is
relative to a bonded reference region; the two are not the same judgement and
must not be conflated.

---

## 7. Differential grading (backend, relative measurement)

Chapter 7 §7.7.1: the instrument is a **two-surface differential measurement**.
A bonded reference region is established in the same session on the same
facade, and every other point is compared against it.  Because the quantity
being compared is relative, the instrument cannot report an absolute debond
size; it can only rank points against their own baseline.

### 7.1 `pt` — measurement point id

Both `waveform` (§1) and `measurement` (§2) carry

```json
"pt": "P2"
```

`P0`..`P5` come from the device menu (TAP DATA -> POINT ID; six points).  The
backend groups taps by **(`dev`, `pt`)**; a message without a usable `pt` is
bucketed as `P?` and can never establish the reference.  One survey is one
probe; the device component of the key is what keeps the simulator's points
(`dev: "sim-01"`, `sp: true`) from merging into the real probe's buckets.

### 7.2 Reference region

`POST /api/reference` with `{"point": "P2"}` stores that point's median
`band_ratio_lh` (`r_ref`) and median `f_peak_hz` (`f_ref`).
`{"point": "auto"}` picks the point with the highest median `band_ratio_lh`
among the points that already have at least three valid taps — the operator is
saying "this region is bonded".  A reference is a session object: changing
facade, probe or session requires a new one.  While there is no reference **no
point may be graded**: every point is `NODATA` with
`reason: "NO_REFERENCE"`.  There is deliberately no absolute fallback.

**The reference is the origin, not a candidate.**  Its row always reports
`rho = 1.0` (definition value), `grade = "G0"`, `confidence = null`,
`is_reference: true` and `rank: 0`.  The point's median can drift after
`r_ref` was frozen at set time; that is reported separately, never as a grade
of the reference against itself:

    ref_drift      = current_median_band_ratio / r_ref
    ref_drift_pct  = (ref_drift - 1) * 100

A large drift says the session itself was unstable — useful information, shown
on the dashboard as "基准漂移 −16%".

**One point is not a ranking.**  `comparable` means one real, non-reference
point with `n_valid >= 3`; `/api/points` returns the count as
`n_comparable` and every point carries `comparable: true/false`.  When
`n_comparable == 0` there is nothing to rank: `most_likely_debonded` is
`null` and `verdict` says so explicitly, naming the reference point, its tap
count and the next point to measure.  Non-comparable points keep their computed
`grade` in the JSON but the dashboard shows "待对比" and no confidence: a
single measured point cannot be better or worse than anything.

### 7.3 Grading modes: relative rank (default) vs fixed threshold

`grade_mode` is a backend config (`POST /api/config {"grade_mode": "rank"|"threshold"}`,
invalid value -> 400, default `"rank"`).

    rho = median(band_ratio_lh of the point) / r_ref      (1.0 = same as reference)
    d_f = median(f_peak_hz of the point)  / f_ref

`rho` is lower for the more suspicious point.  A point needs **at least three
valid taps**; fewer gives `NODATA` with `reason: "TOO_FEW_TAPS"`.

**rank mode (default) — the grade is relative to the other points in this
session, not to a constant.**  With n = `n_comparable` (real, non-reference
points with >= 3 valid taps) and the points sorted by `rho` ascending,
rank k = 1..n (k = 1 is the most suspicious):

    q = (k - 1) / (n - 1)
    q <= 1/3          -> G2
    1/3 < q <= 2/3    -> G1
    q > 2/3           -> G0

so n=5 gives G2,G2,G1,G0,G0; n=3 gives G2,G1,G0; n=2 gives G2,G0.  This is the
"with two points one is always the more suspicious one; with three, averaged
out, one is still the most suspicious" rule.  T1/T2 are **not** used in rank
mode (they are still returned and settable for threshold mode; the dashboard
disables those inputs and says so).  The reference point is rank 0 / G0 and is
never part of the ranking.

**rank mode with n == 1 — significance against the reference.**  One point
cannot be ranked, so the backend falls back to the rho bootstrap interval:
95% CI upper bound < 1.0 -> G2 (significantly below the reference),
95% CI lower bound > 1.0 -> G0 (significantly above), otherwise G1 with
`reason: "CI straddles reference"`.  There is deliberately no hard-coded 0.8.

**threshold mode (`grade_mode="threshold"`)** keeps the old absolute-on-rho
rule for when the thresholds have actually been calibrated on real panels;
both thresholds are **PLACEHOLDER** values until then (appendix C.4):

    rho >= T1          -> G0   (bonded, indistinguishable from the reference)
    T2 <= rho < T1     -> G1   (transition / partial)
    rho <  T2          -> G2   (most likely debonded)

Defaults `T1 = 0.80`, `T2 = 0.50`; settable with
`POST /api/config {"grade_t1": .., "grade_t2": ..}`
(T1 in [0.30, 1.20], T2 in [0.05, T1-0.05]).

### 7.4 Second condition: does `f_peak` move with `band_ratio`?

The report's grade rule is a two-condition box on
`(band_ratio_lh, f_peak_hz)`, so a grade is only accepted when the two features
agree.  The **direction** of the f_peak shift is deliberately NOT asserted at
this stage: the report's 328 -> 468 Hz rise was measured in the microphone's
300..15000 Hz band, while this chain is an accelerometer with a fixed
30..1000 Hz signal band whose live f_peak sits at 210..280 Hz.  The direction is
therefore uncalibrated here (it may not even match the report), so the default
check is direction-agnostic.

`d_f = median(f_peak_hz of the point) / f_ref`; two config values:

    fpeak_mode  "either" (default) | "up" | "down"
    fpeak_tol   0.15   (range 0.02 .. 0.60)

A point graded G1/G2 is **consistent** when

    either : abs(d_f - 1) >= fpeak_tol     the peak frequency moved at all
    up     : d_f >= 1 + fpeak_tol          it moved up
    down   : d_f <= 1 - fpeak_tol          it moved down

Otherwise it is **inconsistent**: the grade is capped at G1,
`inconsistent: true` is returned and the confidence is multiplied by 0.5.
The cap can only lower a grade, never raise one.  `POST /api/config` accepts
`{"fpeak_mode": "up"|"down"|"either", "fpeak_tol": 0.15}`; the values in force
are returned in `/api/config` and echoed as
`grade_rule.fpeak_mode / grade_rule.fpeak_tol` by `/api/points`.  Pin
"up"/"down" only when real bonded/debonded samples have established the
direction; until then "either" is the honest setting.

**Rank mode ignores this cap** — its grade is relative, so a fixed consistency
threshold cannot decide it; `d_f` is still returned for inspection.  If the
reference peak sits at the bottom of the signal band
(`f_ref <= band_lo * 1.2`) the second condition has no resolving power at all:
`/api/points` sets `fpeak_resolution_limited: true` and emits the note
"基准峰 f_ref=… 贴在信号带下沿（band_lo 的 1.2 倍以内）：第二条件（f_peak
一致性）本场无分辨力，判据实际上只剩 rho。"  That situation matters because a
reference that close to the band floor makes every `d_f` ≈ 1.

### 7.5 Measurement-quality gate and `contact_ok`

`contact_ok` per tap has three sources, in priority order:

1. **firmware flag** — if the waveform payload carries a boolean
   `"contact_ok"`, it is used verbatim (`contact_source: "firmware"`).
2. **firmware `pkg`** — if the payload carries `"pkg"` (peak acceleration at
   the trigger in g), the report A.6.5 acceptance window is applied:
   `0.05 <= pkg <= 8.0` -> acceptable, outside -> not
   (`contact_source: "firmware"`).
3. **backend heuristic** — only when neither is present: `peak_au >= 0.05 g`
   and `crest_factor >= 3` (`contact_source: "heuristic"`).  This one is a
   guess and the point table says so.

`/api/points` returns `contact_source` per point ("firmware" | "heuristic" |
"missing"; "heuristic" wins if any usable tap of the point had to be guessed).
Per point, `contact_ok_share < 0.5` or `band_clamped_share > 0.3` (Nyquist
guard active, §6) downgrades the grade one step (G2 -> G1 -> G0, G0 stays),
sets `poor_contact: true` and multiplies the confidence by 0.6.

### 7.6 Confidence, rank stability and separation

Two kinds of resampling, both with the fixed seed 20261120 (identical taps give
identical numbers).

**threshold mode** resamples each point's own `band_ratio_lh` values 2000
times, takes the median of every resample and forms `rho*`:

    grade_confidence = fraction of rho* in the same band as the grade
    p_debond         = fraction of rho* < T1     (p_debond_meaning: prob_rho_below_t1)
    rho_ci           = 5th / 95th percentile of rho*

**rank mode (n >= 2) is a JOINT bootstrap**: 1000 draws; in every draw EACH
point's taps are resampled, the medians recomputed, the whole set re-sorted and
re-graded with the rules of 7.3.  Resampling one point in isolation cannot say
whether a *rank* is stable, so the rank is what gets resampled:

    grade_confidence = fraction of draws where the point lands in the same grade
    rank_confidence  = fraction of draws where its rank is exactly the final rank
    p_debond         = fraction of draws where the point is in the most
                       suspicious third (G2); p_debond_meaning: relative_top_third
    rho_ci           = 5th / 95th percentile of its rho* (joint draws)

The dashboard renames that column to "相对可疑度" in rank mode; the field name
`p_debond` is kept so existing consumers do not break.

**rank mode with n == 1** reports the CI against the reference;
`grade_confidence` is the probability `rho*` is on the same side as the final
grade (null when the CI straddles), `rank_confidence` is null and
`p_debond_meaning = "prob_rho_below_reference"`.

`confidence = grade_confidence x quality factor(s)`.

**A ranking always exists, including on a fully bonded wall, so it needs its
own reliability metric.**  `/api/points` returns

    p_order_significant = fraction of joint-bootstrap draws in which the WHOLE
                          final order is preserved
    spread              = rho(rank 1) / median(rho of the other points)

and the dashboard prints them ("排序置信度 96% ／ 分离度 3.0×").  The verdict
only claims a suspicious point when `p_order_significant >= 0.9`; otherwise it
states that the differences are not beyond noise and asks for a re-measure.

**Relative ranking always produces a rank, including when every point is
acceptable; the rank is only meaningful when `p_order_significant` is high, and
it measures relative suspicion, not an absolute probability of debonding.**

### 7.7 Ranking and API

Points are ranked by `rho` ascending (rank 1 = most likely debonded).  The
reference point has `rank: 0` and `is_reference: true`; NODATA points have no
rank.  `most_likely_debonded` names rank 1 and `verdict` is a one-line readable
conclusion.

    GET  /api/points     reference, points[], grade_rule{t1,t2,fpeak_mode,fpeak_tol},
                         grade_mode, verdict, notes, n_simulated_points,
                         n_real_points, n_comparable, has_simulated,
                         p_order_significant, spread, p_debond_meaning,
                         fpeak_resolution_limited,
                         current_point, current_point_dev, current_point_ms,
                         current_point_source, ts
    GET  /api/point      {"current_point", "current_point_dev",
                          "current_point_ms", "current_point_source"}
    POST /api/point      {"point": "P3"} | {"point": 3} | {"delta": 1}
    POST /api/reference  {"point": "P2"} | {"point": "auto"} | {"point": "clear"}
    POST /api/reset      clears taps / points / reference / stats / counters
                         (instrument configuration is kept), returns cleared{}
    POST /api/config     {"grade_mode": "rank"|"threshold",
                          "grade_t1": 0.80, "grade_t2": 0.50,
                          "fpeak_mode": "either", "fpeak_tol": 0.15, ...}
    WS   /api/stream     message type "points", pushed after every tap;
                         "reset" is pushed when a session is cleared

Every point carries `simulated: true/false`, `comparable: true/false`,
`dev`, `rank`, and (reference only) `ref_drift` / `ref_drift_pct`; simulated
points have `rank: null` and never enter `most_likely_debonded` or `verdict`.

### 7.9 Switching the measurement point from the web page

The operator should not have to hunt through the device menu mid-survey.  The
backend can move the device to a point over MQTT:

    POST /api/point   {"point": "P3"}    or {"point": 3}    or {"delta": 1}

- point strings are strictly `^P[0-5]$` (integers 0..5 are accepted);
  anything else is 400.  `delta` moves relative to the current point and is
  400 if the result leaves P0..P5.
- target device: the `dev` of the most recent **real** tap (`sp != true`); an
  explicit `{"dev": ...}` overrides it.  If no real device has been seen the
  call returns **409** `"no real device seen yet"`.
- the backend publishes `{"cmd":"point","v":<0..5>}` (QoS 1) on
  `probe/<dev>/cmd` and returns `{"ok": true, "dev": ..., "point": "P3",
  "cmd_mid": <mqtt mid>}`.  A disconnected MQTT link gives 503.
- the firmware acknowledges with `probe/<dev>/event`:
  `{"dev":"...","ev":"ack","cmd":"point","ok":true,"pt":"P3"}` and broadcasts a
  WebSocket message `{"type":"point_ack","current_point":"P3",...}`.
- `current_point` (and `current_point_dev` / `current_point_ms` /
  `current_point_source`) is the device's point-ack when it is the newer of the
  two sources, otherwise the `pt` of the latest real tap.  This second source
  matters because the operator may switch points on the device menu, which
  produces no ack.  The dashboard shows it as "当前测点 P3" with P0..P5 buttons
  (the active one highlighted) and updates on the `point_ack` push.


### 7.8 Simulated traffic and session reset

**Simulated data must be unmistakable.**  A synthesised waveform carries
`"sp": true` and should come from its own device id (`sim-01`) so it cannot be
mistaken for a measurement of the wall.  The backend:

- marks a point `simulated: true` if **any** of its taps has `sp: true`, and
  counts how many did (`n_simulated` on the point);
- gives simulated points `rank: null` and excludes them from
  `most_likely_debonded` and from the `verdict` sentence — they are shown in
  the table only so the operator can see a simulator is feeding the system;
- returns `n_simulated_points`, `n_real_points` and `has_simulated`, and adds
  a note naming the simulated points; the dashboard shows a red banner and
  marks those rows;
- refuses to establish a reference from simulated taps: `POST /api/reference`
  with `"auto"` on a simulation-only session returns 400, and an explicit
  point that only has `sp: true` taps is rejected the same way.

**Session reset.**  `POST /api/reset` starts a new measurement session.  It
clears the tap history, the point table (derived from the taps), the reference,
the error log and the session counters.  Instrument configuration (signal band,
thresholds, `fpeak_mode` / `fpeak_tol`, window) is intentionally kept.  It
returns

```json
{"ok": true, "cleared": {"taps": 40, "reference": "P0", "reference_dev": "probe-01",
                         "errors": 0, "counters": true}, "data": {"points": [], ...}}
```

Why this is mandatory rather than a convenience: rho is relative to a
reference, so after changing facade, probe or reference the old taps are stale
and comparing new rho against them would be a cross-session comparison.  The
dashboard exposes it as a red “清空本次测量” button with a confirmation prompt.
After a reset the panel is back to “尚未建立基准点”.
