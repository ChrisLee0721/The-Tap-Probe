
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
