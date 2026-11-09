
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
