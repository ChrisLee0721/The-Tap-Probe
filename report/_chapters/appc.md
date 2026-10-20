
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
  **A clean survey is not a certificate of soundness.** *The floor is not a single number*: it scales as
  $\sqrt{h}$ with the finish thickness (§5.5.2, Table 5.8), so the same instrument has a 10.7 cm floor on
  a 30 mm render and a 4.4 cm floor on a 5 mm one. Record the finish construction if it is known, and
  never quote the floor for a building whose build-up has not been established.
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
