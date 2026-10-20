# Appendix B — WSSS and Standards Compliance Matrices

**Module:** EEE4483 *Internet-of-Things Planning and Deployment* (HD in Computer and Electronic Engineering, EG114403 / EG314403 / EG524403)

**Module Intended Learning Outcome addressed:** *b* — "select and apply latest Internet-of-Things (IoT) gateways and platforms with reference to WorldSkills Standards Specification (WSSS) assessment method".

**Project:** a handheld electromagnetic tap-test probe that detects debonded ("hollow") external-wall finishes — I2S microphone + ESP32 edge DSP + MQTT over TLS + ThingsBoard.

This appendix is the evidence for MILO *b*. It does three things: it establishes what the WorldSkills standards and assessment machinery actually contain, it maps that machinery onto the subsystems this project actually built, and it sets the external technical standards the deployment would be measured against. Where a claim could not be retrieved from a primary source it is marked `[TO VERIFY]` rather than asserted. **A fabricated clause number or section title would be a worse failure than an admitted gap**, because the whole point of the appendix is that it is auditable.

---

## Verification status

Read this box first. It decides how much weight the rest of the appendix can carry.

### Verified from primary sources retrieved on 15–16 October 2026

| # | Claim | Source retrieved |
|---|---|---|
| V1 | The WorldSkills assessment method uses **two** methods, **Measurement** and **Judgement**, each with explicit industry benchmarks, and prohibits ranking of competitors for marking purposes. | WSI_OD03 Competition Rules v11.1, §11.3, §11.3.1 [1] |
| V2 | Each Marking Scheme is on a **100-mark** scale, normally has **5–9 Assessment Criteria**, breaks down into Sub Criteria and then into **Aspects**, and should have **100–200 Aspects** (minimum 100, maximum 250). **No Aspect is worth more than two marks.** | WSI_OD03, §11.5.2–§11.5.5 [1] |
| V3 | Each Aspect must relate to exactly one section of the WSOS, and Aspects are categorised as measurement or judgement. | WSI_OD03, §11.5.4 [1] |
| V4 | WSOS sections carry a percentage weighting summing to 100, with a **5 per cent tolerance** in the Marking Scheme. | WSI_OD03, §11.2.1 [1] |
| V5 | The Standards and Assessment Guide (SAG) is published at **C-1 month**; Assessment Training for Experts (MAT) is mandatory. | WSI_OD03, §11.3.2, §11.4 [1] |
| V5a | A **Test Project** "describes the work to be undertaken by Competitors to demonstrate occupational excellence", must "capture the context, purpose, processes, and outcomes of an occupation", and must be designed for **15 to 22 hours** of work over four days (C1–C4). | WSI_OD03, §10.1, §10.2 [1] |
| V6 | The WSOS uses the fixed formulations "The individual needs to know and understand:" and "The individual shall be able to:". | WSOS Industry 4.0 [7] |
| V7 | **"Internet of Things" is not in the WorldSkills Shanghai 2026 WSOS.** The 2026 catalogue contains **64 skills in 6 categories**, and IoT is not among them. | WSOS 2026 index [9] |
| V8 | `https://worldskills.org/skills/id/559/` exists and is titled "Internet of Things", but it is a **stub page**: it carries only a generic description of what an Occupational Standard is, and offers no downloadable standard, no section list and no weighting table. | WorldSkills skill page 559 [3] |
| V9 | Four WSOS structures for adjacent ICT/engineering skills were retrieved in full, including section titles and weights — these are used in B.1 and B.2 as the closest verifiable analogue. | WSOS 2452, 2455, 2461, 2694 [7]–[8] |
| V10 | ETSI EN 303 645 **clause 5.1 to 5.13** titles and the chapter-6 data-protection provisions. | ETSI EN 303 645 V2.1.1 (2020-06) [12]; V3.1.3 (2024-09) [13] |
| V11 | NISTIR 8259A's **six** device cybersecurity capabilities and NISTIR 8259B's **four** non-technical supporting capabilities, with their exact names. | NISTIR 8259A [16]; NISTIR 8259B [17] |
| V12 | **NIST IR 8259 (May 2020) was withdrawn on 20 April 2026** and superseded in its entirety by **NIST IR 8259r1, "Foundational Cybersecurity Activities for IoT Product Manufacturers" (April 2026)**. | Withdrawal notice page [15]; 8259r1 [18] |
| V13 | UK PSTI Act 2022 (c. 46) Part 1 structure, and the 2023 Regulations' Schedule 1 security requirements, Schedule 3 excepted products and Schedule 4 statement-of-compliance content. | legislation.gov.uk [19] [20] |
| V14 | MQTT Version 5.0 is an OASIS Standard dated 07 March 2019; Chapter 5 is titled "Security (non-normative)"; §5.4.1–§5.4.12 subsection titles; the port-8883 recommendation; and that its **normative TLS reference is RFC 5246 (TLS 1.2), not RFC 8446**. | MQTT v5.0 OASIS Standard [21] |
| V15 | TLS 1.3 is RFC 8446, August 2018, which obsoletes RFC 5077, 5246 and 6961. | RFC 8446 [22] |
| V16 | ESP-IDF's `esp_crt_bundle_attach` uses the Mozilla NSS root store embedded in the binary; enabling **cross-signed certificate support increases peak run-time heap use during the TLS handshake by approximately 1 KB**. | ESP-IDF docs [24] [25] |
| V17 | MBIS applies to buildings **aged 30 years or above** (except domestic buildings not exceeding 3 storeys), requiring a Registered Inspector to inspect **common parts, external walls and projections or signboards**. | Buildings Department MBIS page [27] |
| V18 | The statutory/departmental method explicitly includes **hammer-tapping**, paired with cover-meter survey and crack-width measurement as non-destructive methods; the defect list includes **"Spalling of concrete"** and **"Delamination"**. | PNBI-10, Appendix B (6 March 2017) amending Part A of s.3.4.2 [29] |
| V19 | Hammer-tapping also appears as a **proof test** under "External Elements", and "hollow sounding concrete" appears as a repair-preparation condition. | PNBI-10, Appendix VI, Table 3 [29] |
| V20 | JGJ/T 110-2017 建筑工程饰面砖粘结强度检验标准 is a MOHURD standard issued 2017-05-15, in force 2017-11-01, superseding JGJ 110-2008, referenced by GB 50210-2018. | Standard database entries [31] [32] |

### Not verified — the student must resolve these

| # | Open item | Why it is open | What to do |
|---|---|---|---|
| U1 | **The WSSS/WSOS section list and weightings for an "Internet of Things" skill.** | No such document is publicly retrievable. The skill *page* exists (V8) but the standard behind it does not. | `[TO VERIFY]` — ask the lecturer whether VTC holds a WSSS/WSOS IoT document, or whether the module intends a different skill (Industry 4.0, Cloud Computing, Cyber Security, Electronics) as the reference. |
| U2 | **Whether an "Internet of Things" skill was ever run as an Official WorldSkills competition, and under what skill number.** | IoT appears in *Future Skills* material (Kazan 2019, WorldSkills Russia Future Skills Camp 2020) and on national member sites, but no Official skill number or competition record was retrieved. | `[TO VERIFY]` — do not assert a skill number. |
| U3 | **The exact WorldSkills Shanghai 2026 WSOS document revision date** for the skills cited in B.1. | The section lists and weights were retrieved, but the "consulted upon and updated biennially" revision stamp was not read. | `[TO VERIFY]` — cite the retrieval date, as done here. |
| U4 | **Commencement date of the UK PSTI regime.** | The Act and the SI were retrieved; the commencement instrument was not. | `[TO VERIFY]` — do not state a date. |
| U5 | **Whether NISTIR 8259A and 8259B have themselves been withdrawn** following the 8259r1 replacement. | The copies retrieved on 16 October 2026 carry no withdrawal notice, but the 8259 withdrawal notice shows 8259r1 absorbed 8259, so 8259A/B status should be confirmed. | `[TO VERIFY]` — check csrc.nist.gov before citing 8259A/B as current. |
| U6 | **An authoritative HK or Mainland source defining 空鼓.** | The term could not be retrieved from any primary HK or GB/JGJ source. PNBI-10 uses the English phrase "hollow sounding concrete". | `[TO VERIFY]` — use "hollow sounding" as the cited English term and attribute 空鼓 to the regional literature without a clause reference. |
| U7 | **The full text of JGJ/T 110-2017.** | The standard is paywalled; only database metadata (number, title, dates, supersession, referencing) was retrieved. | `[TO VERIFY]` — cite only the metadata; do not quote clause numbers. |
| U8 | **Whether the thirtieth-anniversary threshold has been amended since the page revision retrieved.** | Only the current live page was read. | `[TO VERIFY]` — low risk, but state the retrieval date. |

Each row of Table B-2 (B.4) pairs a *cited* standard with this project's own implementation, so the two halves need different kinds of support. The **standard half** carries a numbered reference to the reference list below. The **project half** describes artefacts in the student's own repository (firmware, appendix, chapter) and carries no URL, because a file in the project is not an external source. Do not read a Table B-2 row as an assertion that the project complies with the standard in column 1; read the residual-gap column, which is where the honest verdict lives.

---

## B.1 What the WSSS is, and what could and could not be found

### B.1.1 The two names

The module's learning outcome says "WorldSkills Standards Specification (WSSS)". That name is the historically older one: WorldSkills' own news material from 2013 refers to "the WorldSkills Standards Specification" and to a project to define "the nature of the WorldSkills Standards Specification from which best practice in skills competition can be derived" [2]. The current name on worldskills.org is **WorldSkills Occupational Standards (WSOS)** [10]. The two are the same artefact under a renamed label, and the current WSOS landing page describes it as:

> "The WorldSkills Occupational Standards reflect the global occupations or work roles that are represented by the WorldSkills Competition... set out what a capable practitioner must know, understand, and do... are consulted upon and updated biennially with industry and business worldwide... indicate the relative importance of each section of the standards, as advised by industry and business." [10]

Three consequences follow, and they should be stated explicitly in the report because they bound what "compliance" can mean:

1. **The WSOS is an occupational standard, not a product certification.** It describes the knowledge and skill of a person performing a role. It cannot be "complied with" by choosing particular hardware. What *can* be demonstrated is that the artefacts the student produced cover the knowledge and the capability the standard describes.
2. **The WSOS is not publicly downloadable for every skill.** The landing page points to a per-event catalogue. For Shanghai 2026 the catalogue is live [9], and individual skill standards are retrievable for some skills but not for others.
3. **The term "assessment method" in MILO *b* refers to the WorldSkills assessment machinery**, which is documented in the Competition Rules and is fully public [1]. That machinery *is* retrievable, and B.1.3 below sets it out. The parts of MILO *b* that can be evidenced with hard citation are therefore the assessment method, not the section list of an IoT skill.

### B.1.2 Internet of Things as a WorldSkills skill — what was found

This is the honest position, and it should be written in the report exactly as it is here.

- **The skill page exists.** `https://worldskills.org/skills/id/559/` returns a page titled "Internet of Things". The page carries one paragraph explaining what an Occupational Standard is, and generic links ("Find out how to start competing", "Put your skills to the test"). **It does not link to a downloadable standard, and it contains no section headings, no weightings and no skill number other than the id in the URL.** Snapshots of the same page from 2021, 2022 and 2025 show the same content. [3]
- **IoT is not in the WorldSkills Shanghai 2026 WSOS.** The 2026 occupational-standards catalogue was enumerated in full: **64 skills across six categories** — Construction and Building Technology (14), Creative Arts and Fashion (7), Information and Communication Technology (8), Manufacturing and Engineering Technology (17), Social and Personal Services (10), and Transportation and Logistics (8). No skill named "Internet of Things" appears. [9]
- **IoT has a Future Skills / demonstration history.** IoT was among the skills demonstrated in the Future Skills area at WorldSkills Kazan 2019, and "Internet of Things" is explicitly listed among the skills offered in the WorldSkills Russia Future Skills Camp of 2020 [4]. Under the Competition Rules, exhibition content "shall not be regarded as having any competitive status" and cannot attract an official medal [1, §3.3].
- **National members list IoT as a skill.** WorldSkills Philippines publishes an "Internet of Things" skill page under Information and Communication Technology, describing IoT as enabling "real-time information capture and intelligent decision-making through practical IoT Modules integrated with real-world problems and situations", and credits the material to WorldSkills Singapore. This is the closest thing to a published IoT "module" list that was found — but it is national-member promotional material, **not the WSOS**, and its module names must not be presented as WSSS section titles. [11]

> **Recommended wording for the report.** "WorldSkills publishes an Internet of Things occupational-standard page (skill id 559, worldskills.org), and IoT featured as a Future Skills demonstration at WorldSkills Kazan 2019. However, no Internet of Things standard is published in the WorldSkills Shanghai 2026 occupational standards catalogue of 64 skills, and no public document setting out IoT WSOS sections or weightings could be retrieved. This appendix therefore evidences MILO *b* against (i) the WorldSkills assessment method, which is fully documented, and (ii) the WSOS section structures of the nearest published ICT and engineering skills, used explicitly as a proxy and labelled as such."
>
> Do **not** write "the WSSS IoT section 'Sensing and Actuation' has a weighting of X per cent". No such section could be verified.

### B.1.3 The WorldSkills assessment method — fully verified

The Competition Rules (WSI_OD03, version 11.1, dated 21.09.26) are public and are the authority for everything in this subsection [1].

**Two assessment methods.**

> "There are two assessment methods: measurement and judgement. **Measurement** is used to assess accuracy, precision, and other performance that can be measured objectively. It is used where ambiguity must be avoided. **Judgement** is used to assess the quality of performance about which there may be small differences of view when applying the external benchmarks." — WSI_OD03 §11.3

Both must rest on "explicit external benchmarks drawn from industry and business best practice"; the baseline for any mark is "the achievement of an acceptable industry standard" (§11.3). Ranking competitors for marking is prohibited (§11.3.1).

**Marking Scheme structure.**

| Level | Rule | Rule source |
|---|---|---|
| Total scale | 100 marks | §11.5.1 |
| Assessment Criteria | "normally between five and nine" | §11.5.2 |
| Sub Criteria | one or more per Criterion; one marking team per Sub Criterion | §11.5.3 |
| Aspects | ideally 100–200; minimum 100, maximum 250 | §11.5.4 |
| Aspect → Standard | each Aspect relates to exactly one WSOS section | §11.5.4 |
| Aspect category | each Aspect is measurement **or** judgement | §11.5.4 |
| Mark per Aspect | "No Aspect shall be worth more than two marks (equals two per cent of the total marks available)" | §11.5.5 |
| Tool | one Marking Form per Sub Criterion, generated by the Competition Information System (CIS) | §11.5.6 |
| Blind marking | maximum mark per Aspect hidden from the marking team except for measurement Aspects without calculation | §11.5.6 |

**Weightings.** WSOS sections each carry a percentage of total marks; the sum is 100; the Marking Scheme must follow the weights "to the extent practically possible" with "a variation of up to five percent... if this does not distort the weightings" (§11.2.1).

**Assessment quality apparatus.** The Standards and Assessment Guide (SAG) "detail[s] the benchmark for each assessment aspect" and is "made available in English on the website at C-1 month" (§11.3.2). Mandatory Assessment Training for Experts (MAT) "comprises both training and testing" (§11.4). Competitors are **not** given the Measurement and Judgement Marking Forms (§10.11.3). Test Projects may be circulated before the competition, in which case a 30 per cent change is applied (§10.10, §6.7).

**How a judgement Aspect is actually scored.** Measurement follows a binary or pre-determined-scale decision (§11.6.6). Judgement is scored 0–3 by each of **three** Experts on the marking team, against a fixed scale — 0: "Performance below industry standard, including a non-attempt"; 1: "Performance meets industry standard"; 2: "Performance surpasses industry standard"; 3: "Excellent or outstanding performance relative to industry expectations". Where the range of the three scores exceeds 1, the Aspect must be re-scored; the benchmarks may not be changed during assessment (§11.6.7).

**The Test Project.** "Each skill competition has a Test Project that describes the work to be undertaken by Competitors to demonstrate occupational excellence. The Test Project must capture the context, purpose, processes, and outcomes of an occupation, and in doing so support the implementation of the Marking Scheme" (§10.1). It must be sized for **15 to 22 hours** of work across four days (C1–C4) (§10.2).

**Why this matters to the project.** Four design consequences follow directly, and they are already reflected in the main report:

- A design decision must be defensible against an *external* benchmark, not against the author's preference. This is why every threshold in the firmware is traceable to a physically motivated quantity (`PROBE_FMIN_HZ`, `PROBE_CROSSOVER_HZ`) rather than tuned to a number that "looked good".
- "Measurement" evidence and "judgement" evidence are different kinds of evidence. Counts of agreement against reference panels are measurement evidence; the claim that the probe is ergonomically usable is judgement evidence. The report must not blur them. The 0–3 scale above is the reason a bare "it works well" is not evidence: "meets industry standard" and "surpasses industry standard" are distinct, benchmarked verdicts.
- Because a Marking Scheme is built from 100–250 small, single-clause Aspects, the report should be structured so that individual claims are individually checkable — hence the requirement counts in Ch. 8 and the per-requirement traceability in Ch. 3.
- A Test Project is a bounded artefact ("context, purpose, processes, and outcomes"), not an open-ended demonstration. That is the discipline the module's mini-project should mirror: state the scope, state the process, state the outcome, and declare what is outside the scope.

### B.1.4 Closest verifiable WSOS structures

Since no IoT WSOS could be retrieved, the four structures below are used as the proxy. Each was retrieved in full from the Shanghai 2026 WSOS catalogue [7]–[8]. **They are other skills' standards and must be labelled as proxies in any table derived from them.**

**Industry 4.0 (skill 2452)** — the closest single analogue: networked industrial systems, edge devices, M2M data exchange, cyber security [7].

| § | Section | Weight |
|---|---|---|
| 1 | Work organization and management | 5 % |
| 2 | Communication and interpersonal skills | 5 % |
| 3 | Design, assembly, and commissioning | 15 % |
| 4 | Software design and implementation | 20 % |
| 5 | Networking and cyber security | 20 % |
| 6 | Testing, maintenance, and fault-finding | 10 % |
| 7 | Enhancement and optimization | 15 % |
| 8 | Analysis, evaluation, and reporting | 10 % |

Selected capability statements under §4 and §5 show the IoT-relevant texture of the standard: *"Implement functions to allow for data exchange using common industrial protocols"*, *"Implement functions to allow for data exchange using M2M protocols"* (both §4); *"The scale and nature of the organization's vulnerability to breaches in information security"*, *"Document computer security and emergency measures, policies, procedures and tests"* (both §5) [7].

**Cloud Computing (skill 2455)** — platform-side analogue [6].

| § | Section | Weight |
|---|---|---|
| 1 | Work organization and management | 10 % |
| 2 | Communication and interpersonal skills | 5 % |
| 3 | Problem solving, innovation, and creativity | 20 % |
| 4 | Cybersecurity | 20 % |
| 5 | Reliability, scalability, and elasticity | 15 % |
| 6 | Performance and optimization | 10 % |
| 7 | Operational considerations | 10 % |
| 8 | Sustainability | 10 % |

**Cyber Security (skill 2461)** — used for the security-baseline discussion in B.4 and as the analogue for the secure-lifecycle sections that an IoT standard would carry [8].

| § | Section | Weight |
|---|---|---|
| 1 | Work organization and management | 5 % |
| 2 | Communication and interpersonal skills | 10 % |
| 3 | Secure systems design and creation | 10 % |
| 4 | Secure systems operation and maintenance | 15 % |
| 5 | Secure systems protection and defence | 15 % |
| 6 | Operations and Management | 20 % |
| 7 | Intelligence collection and analysis | 10 % |
| 8 | Investigation and Digital Forensics | 15 % |

**Intelligent Security Technology (skill 2694)** — the only *Construction and Building Technology* category skill with a systems-integration, sensing, edge/cloud character. Retrieved sections: Project initiation and holistic planning (5 %); Planning and design of security systems (20 %); Installation and implementation of security systems (10 %); Debugging and optimization of security systems (30 %); Application of artificial intelligence and digital technologies (10 %); Maintenance and repair (15 %), plus the two transversal sections. Its §8 statement *"Coordinate and utilise edge computing and cloud computing collaboratively"* is the closest published phrasing to this project's architecture.

**Transversal sections.** All four skills share the same first two sections — *Work organization and management* and *Communication and interpersonal skills* — which is what the WSOS landing page means by standards being "both specific to an occupational role and also transversal" [10]. Any proxy mapping should treat these two as the generic-competence rows.

### B.1.5 Topic-coverage checklist (derived, not attributed)

The module brief lists typical IoT concern areas — sensing/actuation, connectivity, data, edge/cloud, security, HMI/dashboard, project management. **No retrieved WSSS document uses this list, so it is presented here as a derived engineering checklist and must not be given WSOS section numbers.** It is nevertheless useful, because it is the vocabulary both the module and the national-member IoT material use [11].

| Concern area | Covered by this project? | Where |
|---|---|---|
| Sensing and actuation | Yes | I2S microphone (sensing); solenoid strike actuator with thermal interlock and failsafe |
| Connectivity | Yes | WiFi (WPA2-PSK only) + MQTT over TLS on 8883, QoS 1 |
| Data | Yes | Structured JSON payload with a documented schema; SNTP timestamps; NVS-backed counters |
| Edge / cloud | Partly | Edge: FFT and feature extraction and grading on-device. Cloud: ThingsBoard dashboard. **No gateway yet** — an ESP32 that senses and publishes is a sensor node, not a gateway (Milestone 2 adds a gateway role) |
| Security | Partly | TLS with CA-bundle validation, per-device MQTT credentials, LWT. **Not covered:** OTA update path, mutual TLS, encrypted NVS |
| HMI / dashboard | Yes | ThingsBoard; console CLI; payload flags for simulated rows |
| Project management | Yes | Milestones, requirement traceability, risk and limitations registers in the main report |

---

## B.2 Table B-1 — Proxy WSOS area to project subsystem to evidence

The left column uses the verified **Industry 4.0 (2452)** section structure [7] as the proxy for what an IoT standard would plausibly contain, because it is the nearest published skill. **The proxy label is load-bearing: these are not IoT WSOS sections.** Weights are shown to make the proxy visible, not to claim marks.

| § | Proxy WSOS area (skill 2452) | Wt | Subsystem in this project | Evidence artefact |
|---|---|---|---|---|
| 1 | Work organization and management | 5 % | Bench-only operating rules; strike interlock (2 s minimum interval, 15 strikes / 30 s sliding window, 120 ms independent failsafe de-energise); bill of materials and costing | Appendix A.4 (BOM, wiring); A.10 (Safety); `05_firmware/main/probe_config.h` (`PROBE_MIN_STRIKE_INTERVAL_MS`, `PROBE_DUTY_*`); Ch. 7.6 |
| 2 | Communication and interpersonal skills | 5 % | Documented JSON payload schema so a third party can consume the data without reading the firmware; operator SOP written to be followed without the author present; explicit "sentences to avoid" list | Appendix A.5.7 (schema table); A.6 (SOP); A.11 (report guidance); Ch. 9 |
| 3 | Design, assembly, and commissioning | 15 % | Full device-to-application chain: microphone → ESP32 → TLS → broker → dashboard; pinout and wiring; provisioning and first-run procedure; system architecture | Ch. 3.3 (architecture); Appendix A.2 (block diagram), A.3 (pinout), A.4 (wiring), A.5.5 (provisioning) |
| 4 | Software design and implementation | 20 % | 48 kHz I2S capture; 1024-point radix-2 FFT with Hann window and DC removal; eight acoustic features (`f_peak_hz`, `f_centroid_hz`, `band_ratio_lh`, `decay_tau_ms`, `peak_au`, `rms_au`, `crest_factor`, `kurtosis`); two-threshold G0/G1/G2 box classifier; PC-side analysis pipeline | `05_firmware/main/app_main.c`; `probe_config.h`; **Appendix D** (firmware artefacts); `06_analyze_tap.py` |
| 5 | Networking and cyber security | 20 % | `threshold.authmode = WIFI_AUTH_WPA2_PSK` (open networks refused); MQTT over TLS with `esp_crt_bundle_attach` as trust anchor; per-device device id and MQTT client id; Last Will and Testament `probe/<id>/status = "offline"`; documented plaintext-NVS limitation | `app_main.c`; Appendix A.5.5 (security note), A.5.6 (topics, LWT); **B.4 Table B-2** below |
| 6 | Testing, maintenance, and fault-finding | 10 % | Calibration against reference panels; contact-quality auxiliary channel (MPU6050) as a fault detector for bad coupling; capture-timeout and accel-unavailable event flags; troubleshooting table | Appendix A.6.5 (contact quality), A.7 (calibration), A.8 (troubleshooting); payload `event_flag`; Ch. 8 |
| 7 | Enhancement and optimization | 15 % | Tuning order that deliberately puts thresholds last; level-set treatment of debond size as future work; Milestone 2 gateway (ESP-NOW concentrator + local broker) | Appendix A.11 ("what to tune first"); Ch. 9.5; Ch. 3.4 |
| 8 | Analysis, evaluation, and reporting | 10 % | Validation methodology with explicit separation of measured from synthetic data; ROC / threshold-cost analysis; honest statement that the classifier is a fixed rule, not a model | Ch. 8 (esp. Ch. 8.0 and Ch. 8.4); `06_analyze_tap.py` outputs |

### Where the project does **not** cover an area — candid rows

These belong in the report's Limitations section, not hidden.

| Area | Status | Note for the Limitations section |
|---|---|---|
| Test Project and Marking Scheme | **Not covered** | The module's mini-project is not a WorldSkills Test Project. There is no external marking scheme, no CIS, and no independent Experts. The report should say that the assessment *method* was used as a design discipline, not that the project was assessed under it. |
| Gateway role | **Partially covered** | Milestone 1 has no gateway. Claiming one would be false. Milestone 2 adds a genuine concentrator. See main report Ch. 3.4 and D5 in the discussion. |
| Firmware update path | **Not covered** | There is no OTA update mechanism, so ETSI provision 5.3 (keep software updated) cannot be claimed — see Table B-2, row S3. |
| Mutual authentication | **Not covered** | Server authentication is performed; client authentication is by username/password over TLS. MQTT §5.4.3 notes that "basic authentication" gives the client no way to authenticate the *server* other than via TLS certificates, and that mutual authentication requires enhanced authentication (§4.12) [21]. |
| Data protection / privacy provisions | **Partially covered** | The instrument records no personal data by design (no images, no audio retained, no operator identity in the payload). That is a design mitigation, but it is not a documented assessment against the clause-6 provisions, and it should be labelled as reasoning rather than as compliance. |
| Formal EMC / electrical safety certification | **Not covered** | The solenoid driver is prototype-grade and bench-operated only. No EMC or LVD testing was performed. |
| Field validation on real defects | **Not covered** | Calibration is against two reference panels only. Quoted agreement counts apply to those panels and nowhere else. |
| Sieve / ML classification | **Not covered** | The classifier is a two-threshold box rule; the report must not describe it as a trained model. |

---

## B.3 Selecting and justifying the platform against the assessment method

MILO *b* also asks for *selection* of gateways and platforms. The defensible form of that argument, using the verified assessment vocabulary, is: name the criterion, give the benchmark it comes from, name the alternative rejected, and state the cost of the choice.

| Selection criterion | Benchmark it answers to | Chosen | Rejected | Cost accepted |
|---|---|---|---|---|
| Edge compute | WSOS 2452 §4 "data exchange using M2M protocols"; §5 networking and cyber security [7] | ESP32 with on-device 1024-point FFT | Send raw waveform to the cloud | Fixed two-threshold rule instead of a trained model (flash/RAM budget) — recorded in Ch. 9.3 |
| Transport | MQTT v5.0 §5.1 recommends TCP 8883 with TLS [21] | MQTT over TLS, `mqtts://`, port 8883 | Plain `mqtt://` on 1883 | ~1 KB extra peak handshake heap if cross-signed support is enabled [24]; no mutual TLS |
| Trust anchor | MQTT §5.4.7 — certificates "should" be associated with the connecting hostname; CRL/OCSP optional [21] | `esp_crt_bundle_attach` (Mozilla NSS roots embedded in the binary) | Pinned single CA PEM | The bundle must be updated when roots are retracted [25]; a pinned certificate or mutual TLS would be stronger for production |
| Platform | WSOS 2455 "Operational considerations" [5] | ThingsBoard | Bespoke web UI | Dashboard configuration effort; reliance on a third-party platform |
| Messaging semantics | MQTT v5.0 QoS and retained-message semantics [21] | QoS 1 for measurement; retained QoS 1 on `status` with LWT | QoS 0 (fire and forget) | Duplicate delivery is possible at QoS 1; consumers must be idempotent on `seq` |
| Network admission | ETSI 5.6 minimise exposed attack surface [12] | `WIFI_AUTH_WPA2_PSK` — open networks refused | Accept any AP | Cannot join an open test AP |
| Credential storage | ETSI 5.4 securely store sensitive security parameters [12] | NVS provisioning of SSID / MQTT URI / credentials | Hard-coded credentials in source | **NVS is not encrypted** unless flash encryption is enabled — a documented residual gap, not a claimed control |

---

## B.4 Table B-2 — cited standard to constraint to compliance measure to residual gap

| # | Standard / clause (cited) | What it constrains here | Measure actually implemented | Residual gap |
|---|---|---|---|---|
| S1 | **ETSI EN 303 645 V2.1.1, 5.1 "No universal default passwords"** — provisions 5.1-1 to 5.1-5 [12] | How the device authenticates to the broker and to the console | No default password ships; MQTT credentials are set per device at provisioning (`... <mqtt-user> <mqtt-password> <client-id>`); each device requires a unique device id and unique MQTT client id, and the README states why | There is no brute-force throttle on the console — 5.1-5 applies to devices that are "not a constrained device", and no assessment of whether this device qualifies was made. `[TO VERIFY]` |
| S2 | **ETSI 5.2 "Implement a means to manage reports of vulnerabilities"** — 5.2-1 requires a *publicly available* vulnerability disclosure policy [12]. The accompanying conformance-assessment specification is ETSI TS 103 701 [14] | Manufacturer-side process | **Not implemented.** A student prototype has no manufacturer and no disclosure channel | **Gap.** Report as a limitation. Do not claim 5.2. Note also that a *claim* of conformity would require an assessment under TS 103 701, which has not been performed for any provision. |
| S3 | **ETSI 5.3 "Keep software updated"** — 5.3-1 to 5.3-14, including publishing the support period (5.3-13) [12] | Update mechanism | **Not implemented.** There is no OTA path; updating means reflashing over USB | **Gap**, and a material one. Provision 5.3-14 covers constrained devices that cannot be updated, but it requires a *published rationale*, which this project also does not have. State plainly that 5.3 is unmet. |
| S4 | **ETSI 5.4 "Securely store sensitive security parameters"** [12] | Storage of WiFi and MQTT secrets | Secrets are stored in NVS and never in source; the README documents explicitly that NVS is **plain text** unless ESP-IDF flash encryption is enabled, and says so in the report's security discussion | **Partial.** Without flash encryption + secure boot, the parameters are recoverable from a flash dump. Report as a residual gap with the specific mitigation named. |
| S5 | **ETSI 5.5 "Communicate securely"** — 5.5-1 "shall use best practice cryptography to communicate securely" [12] | Transport security | `mqtts://` on 8883 with CA-chain validation via `esp_crt_bundle_attach`; `WIFI_AUTH_WPA2_PSK` refuses open networks | No mutual TLS and no certificate pinning. Server authentication only. |
| S6 | **ETSI 5.6 "Minimize exposed attack surfaces"** — 5.6-1 "All unused network and logical interfaces shall be disabled" [12] | Interfaces | The device exposes only the outbound MQTT client and the serial console; there is no inbound listener, no web server, no exposed debug interface on the network | Console remains available over USB for provisioning and threshold changes. Not a network surface, but it is a physical one — ETSI 5.6-3 addresses exactly this, and the project relies on the attention of the operator rather than on a technical control. |
| S7 | **ETSI 5.7 "Ensure software integrity"**; **5.8 "Ensure that personal data is secure"** [12] | Boot integrity; personal data | No secure boot; no personal data is collected (audio is not retained; the payload carries no operator identity) | **Partial.** 5.7 unmet as a technical control. 5.8 is mitigated by data minimisation rather than by a control. Say so. |
| S8 | **ETSI 5.9 "Make systems resilient to outages"** [12] | Behaviour on network loss | Last Will and Testament publishes `probe/<id>/status = "offline"` retained, so a broker or dashboard sees the failure; QoS 1 avoids silent message loss; measurement continues offline and `seq` continues | Data captured while disconnected is **not** buffered for later delivery. A gap; note it. |
| S9 | **ETSI 5.10 "Examine system telemetry data"**; **5.11 "Make it easy for users to delete user data"** [12] | Telemetry; user data | The device publishes its own diagnostic events (`event_flag`: `weak_contact`, `hard_contact`, `capture_timeout`, `accel_unavailable`, `thermal_trip`) and a status topic | No user-data deletion mechanism exists because no personal data is stored. Record as *not applicable with rationale* rather than as compliance — and note that recording a rationale is itself provision 5.0-1 in the 2024 edition [13]. |
| S10 | **ETSI 5.12 "Make installation and maintenance of devices easy"**; **5.13 "Validate input data"** — 5.13-1 requires the software to validate data input via user interfaces or APIs [12] | Provisioning UX; input handling | Provisioning is a single documented console command; the JSON payload is generated by the firmware rather than parsed, and the classifier rejects out-of-window captures and flags them | The MQTT **command** topic (`probe/<id>/cmd`) accepts input; the report should state exactly what validation is performed on it and, if none, say so. `[TO VERIFY]` at the student's end. |
| S11 | **ETSI chapter 6, "Data protection provisions for consumer IoT"** (6-1 to 6-5 in V2.1.1; expanded in V3.1.3 with 5.0 "Reporting implementation" and provisions 6-1 to 6-6) [12] [13] | Personal-data processing | Out of scope by data minimisation: the device records acoustic features and no personal data | **Not assessed.** Present as a scope statement, not a compliance claim. |
| S12 | **NISTIR 8259A, six device cybersecurity capabilities**: Device Identification; Device Configuration; Data Protection; Logical Access to Interfaces; Software Update; Cybersecurity State Awareness [16] | Device capability baseline | **Device Identification:** unique device id + unique MQTT client id, and `dev` in every payload. **Device Configuration:** console provisioning and runtime threshold changes. **Data Protection:** TLS in transit; NVS at rest is the gap. **Logical Access to Interfaces:** outbound-only MQTT; no listening service. **Software Update:** not implemented. **Cybersecurity State Awareness:** `status` topic with retained online/offline, plus the `event` topic | Two of six capabilities are weakly met (Data Protection at rest; Software Update). Present the baseline as a six-row checklist with an honest verdict per row — that is exactly the structure the module's assessment method rewards. |
| S13 | **NISTIR 8259B, four non-technical supporting capabilities**: Documentation; Information and Query Reception; Information Dissemination; Education and Awareness [17] | Manufacturer-side support processes | **Documentation** exists in strong form (Appendix A: BOM, pinout, provisioning, SOP, calibration, troubleshooting, safety, payload schema). **Information and Query Reception / Dissemination / Education and Awareness** do not exist as processes | **Gap for three of four.** An appendix set is not a support organisation. Say so. |
| S14 | **NIST IR 8259 (May 2020) withdrawn 20 April 2026; superseded by NIST IR 8259r1 (April 2026)** [15] [18] | Which edition to cite | Cite **8259r1** as current. Citing the withdrawn 8259 as current would be a citation error | The 8259r1 body was not read in full, so whether it absorbs 8259A/8259B is `[TO VERIFY]` (U5). |
| S15 | **UK PSTI Act 2022, Part 1** and the **2023 Regulations, Schedule 1** — three security requirements: Passwords; Information on how to report security issues; Information on minimum security update periods. Schedule 3 lists excepted products (Northern Ireland products, EV charge points, medical devices, smart meter products, computers); Schedule 4 sets the minimum content of a statement of compliance [19] [20] | A real-world, enforceable instance of the same class of requirement | Used in the report as the **regulatory precedent** showing that "no default password + a vulnerability-reporting route + a published support period" is now a legal minimum in a major market | The project meets only the first of the three (no default password). It has no vulnerability reporting route and no minimum security update period — because there is no OTA path (S3). The honest sentence is: "an equivalent regime is already in force in the UK, and this prototype would not satisfy two of its three requirements." |
| S16 | **MQTT Version 5.0, OASIS Standard, 07 March 2019** — §1.6 Security; Chapter 5 "Security (non-normative)"; §5.1 port 8883; §5.4.1–5.4.12; §4.12 enhanced authentication [21] | Protocol-level behaviour | QoS 1 on all three topics; retained `status` with LWT; per-subscriber credentials for the `mosquitto_sub` observer; `probe/+/...` wildcard subscriptions used only by the observer, consistent with §5.4.2's caution about broad filters such as `#` | No enhanced authentication, so no mutual authentication (§5.4.3). No CRL/OCSP checking (§5.4.7). |
| S17 | **MQTT v5.0's normative TLS reference is RFC 5246 (TLS 1.2)** — the specification cites `[RFC5246]` throughout Chapter 5 [21] [23] | Which TLS version may be claimed | The firmware hands trust-anchor validation to ESP-IDF, which negotiates TLS 1.2/1.3 with `esp_crt_bundle_attach` | **This is a citable subtlety worth a sentence in the report:** MQTT v5.0 does not normatively require TLS 1.3; its normative reference is TLS 1.2. Claiming "MQTT 5.0 requires TLS 1.3" would be wrong. |
| S18 | **RFC 8446, TLS 1.3, August 2018** — obsoletes RFC 5077, 5246 and 6961 [22] | Current TLS version | The device uses TLS with CA-chain validation; TLS 1.3 is available from ESP-IDF/mbedTLS and is preferred where the broker negotiates it | No cipher-suite policy is asserted or logged by the firmware; the report should not claim a specific negotiated version unless the log is quoted. `[TO VERIFY]` at the student's end. |
| S19 | **ESP-IDF certificate bundle documentation** — `esp_crt_bundle_attach` uses Mozilla's NSS root store embedded in the binary; full bundle is 130+ roots, filtered roughly 35; "Trusting all root certificates means the list will have to be updated if any of the certificates are retracted"; **enabling cross-signed certificate support increases peak run-time heap usage during the TLS handshake by approximately 1 KB** [24] [25] | Trust-anchor choice and its memory cost | `cfg.broker.verification.crt_bundle_attach = esp_crt_bundle_attach;` — the firmware comment records the deliberate trade-off: no rebuild needed when the CA rotates, at the cost of trusting a large root set | The device trusts every root in the bundle, so a compromise of any one of them is not detected. A pinned certificate or mutual TLS would be stronger for production — and this is already written into the firmware's own doc comment, so the report can quote it rather than reconstruct it. |
| S20 | **Buildings Ordinance (Cap 123)** and **Buildings (Inspection and Repair) Regulation (Cap 123P)** [26] | The statutory frame the inspection regime sits inside | Cited as the legal basis for the MBIS/MWIS regime | The project is a survey aid, not a statutory inspection. It produces no compliance evidence and is not an RI's prescribed inspection. State this to avoid overclaiming. |
| S21 | **MBIS** — buildings aged **30 years or above** (except domestic buildings not exceeding 3 storeys) served with statutory notices; an RI carries out the prescribed inspection of **common parts, external walls and projections or signboards** [27] | The demand case: why façade-defect screening matters at all | Cited in Ch. 1 and Ch. 2.4 as the statutory driver | The project addresses *one* defect type (debonded finish) on *one* element (external wall finish). It does not address cladding panel displacement, anchor corrosion, cracks or sealing joints, which the Code also requires to be identified. State the narrowness. |
| S22 | **PNBI-10, Code of Practice for the Mandatory Building Inspection Scheme and the Mandatory Window Inspection Scheme**, current issue May 2023 (the issue date and document numbering are from the Buildings Department's practice-note index [30]) — Appendix B (6 March 2017), amending Part A of s.3.4.2, states that structural elements "must be inspected visually and/or by other non-destructive methods such as **hammer-tapping**, cover meter survey, crack width measurement or other feasible means", and lists **"Spalling of concrete"** and **"Delamination"** among defects that must be identified [29] | The method the probe instruments | The probe is a direct instrumentation of the hammer-tap that the Code already names. This is the single strongest citation in the whole appendix: it shows the technique is the *documented* method, not an invention. | The Code names the method but specifies no instrumentation, no acceptance thresholds and no pass/fail criterion for a tapping result — so the probe cannot inherit the Code's authority. It also cannot satisfy "must be identified" because it is unvalidated on real defects. Write it as "instrumenting a documented method", never as "complying with the Code". |
| S23 | **PNBI-10, Appendix VI, Table 3** — "Minimum supervision requirements for typical stages of work": under *External Elements → Proof Test*, "(a) **Supervising hammer-tapping** (b) Conducting pull-off tests"; under *Structural Elements → Preparation*, "(a) Verifying hacking of damaged, loose, **hollow sounding** concrete, spalling and honeycomb" [29] | Terminology and the role of tapping in the workflow | The report's vocabulary ("hollow sounding") is traceable to the Code rather than invented. Tapping is a **proof** activity that follows repair, and a **preparation** check — not a primary defect-classification method | This is a genuinely awkward fact and the report should confront it: in the Code's workflow, hammer-tapping functions as a proof test after repair, whereas this project uses tapping as a pre-repair screening method. That is an extension of the documented use, not a replication of it, and it must be labelled as such. |
| S24 | **JGJ/T 110-2017 建筑工程饰面砖粘结强度检验标准** (Testing standard for adhesive strength of tapestry brick of construction engineering) — MOHURD, issued 2017-05-15, in force 2017-11-01, supersedes JGJ 110-2008, referenced by GB 50210-2018 [31] [32] | The Mainland's approach to the same defect class | Cited to make the qualitative distinction: this standard is a **destructive pull-off adhesion-strength test** — it answers "is this bond acceptable?" It answers *where* the bond is bad only by sampling | Only metadata was retrievable (U7); no clause can be quoted. The report should use JGJ/T 110-2017 to draw the "acceptable vs. locate" contrast, which is the honest justification for a screening tool — and then admit that no HK statutory acceptance criterion for a tapping result exists at all. |
| S25 | **Falling-object risk framing** | Motivation | The MBIS risk framing is established by the Code and the statutory regime [26] [27] [29]; the Minor Works Control System is the regulatory pathway for the repair works that follow a finding [28] | Specific incident statistics were **not** retrieved from a primary source and must not be quoted. `[TO VERIFY]` — obtain from BD press releases or LegCo papers if a number is wanted. |

---

## B.4.1 The ESP32 memory caveat about certificate-chain validation

This is the one place where the platform's own documentation materially changes what the project can honestly claim, so it is set out separately.

**What the firmware does.** The MQTT TLS configuration attaches the ESP-IDF certificate bundle as the trust anchor:

```c
cfg.broker.verification.crt_bundle_attach = esp_crt_bundle_attach;
```

The firmware's own doc comment records the trade-off: the trust anchor "comes from the ESP-IDF certificate bundle (esp_crt_bundle_attach) rather than a pinned PEM, so the firmware does not have to be rebuilt when the CA rotates. For a production device a pinned certificate or mutual TLS would be preferred; that trade-off is discussed in the report."

**What the bundle costs.** Per the ESP-IDF documentation [24] [25]:

- The bundle is "the complete list of root certificates from Mozilla's NSS root certificate store", with the subject name and public key of each "embedded in the ESP32 binary". The full bundle contains **more than 130 certificates**; a pre-selected filtered list reduces this to **around 35** while retaining "around 94 % absolute usage coverage and 99 % market share coverage".
- The documentation warns: "Trusting all root certificates means the list will have to be updated if any of the certificates are retracted."
- **The memory caveat:** "Enabling cross-signed certificate support increases peak run-time heap usage during the TLS handshake by approximately 1 KB. This is a transient allocation (a candidate CA certificate built during certificate verification) that is freed once the handshake completes, and the exact amount scales with the maximum supported RSA key size."

**Why this belongs in the report.** Three reasons, each of which is a *measurement-method* point rather than a security point:

1. **It is a quantified resource constraint on a real-time-adjacent device.** The handshake competes for heap with the DSP capture path. A 1 KB transient peak is small in absolute terms but it is not zero, and the report should state the number rather than describe the choice as free. The firmware already publishes `heap` in the status payload, so the claim can be supported by a log rather than by assertion.
2. **It is an example of the assessment method's "measurement" category.** A heap figure is objectively countable; "the choice was reasonable" is not. Presenting the trade-off as a number is exactly the discipline that Measurement/Aspect marking rewards [1, §11.3, §11.6.6].
3. **It shows the reverse-engineering is real.** The bundle API is documented to *avoid* embedding the certificate bundle "unless activated by the user", which is why the attach function pointer must be passed explicitly. A report that explains *why* that line of code is there — and what it costs — is demonstrating the knowledge-and-understanding layer, not just the ability layer.

**The honest residual gaps in this area**, to be repeated in Ch. 9:

| Gap | Consequence |
|---|---|
| The bundle trusts ~130 roots (or ~35 filtered); any one of them being compromised is not detected by the device | Weaker than pinning; acceptable for a lab, not for production |
| Cross-signed chain support costs ~1 KB of peak handshake heap | Quantified, not eliminated; relevant if heap is later tightened by OTA or ML work |
| The bundle must be regenerated and the firmware reflashed when roots are retracted | This is precisely the maintenance burden that OTA (unimplemented, S3) would relieve — so rows S3 and S19 compound each other |
| No revocation checking (CRL/OCSP), which MQTT §5.4.7 lists as an optional capability [21] | A revoked certificate would still be accepted by the device |
| No cipher-suite policy is set or logged | The negotiated TLS version cannot be asserted from the current firmware without quoting a log — `[TO VERIFY]` at the student's end |

---

## B.5 Hong Kong domain context

### B.5.1 The statutory chain

1. **Buildings Ordinance (Cap 123)** and the **Buildings (Inspection and Repair) Regulation (Cap 123P)** — the primary legislation and regulation [26].
2. **Mandatory Building Inspection Scheme (MBIS)** — owners of buildings **aged 30 years or above** (except domestic buildings of not more than 3 storeys), once served with a statutory notice, must appoint a **Registered Inspector** to carry out the prescribed inspection and supervise prescribed repairs of the **common parts, external walls and projections or signboards** [27].
3. **Code of Practice for MBIS and MWIS**, issued as **PNBI-10** (current issue May 2023) — the operative inspection document [29].
4. **Minor Works Control System** — the regulatory pathway for the repair works that follow an inspection finding [28].

The chain matters because it fixes the project's scope: the probe is a **screening aid in step 2**, producing a digital record of where a Registered Inspector might look. It discharges no statutory duty, and the report should say so in Ch. 1.4 and in the Limitations.

### B.5.2 The documented method and its terminology

The verified wording is worth quoting in the report, because it is the only place where an HK authority names the technique:

> "Structural elements must be inspected visually and/or by other non-destructive methods such as **hammer-tapping, cover meter survey, crack width measurement** or other feasible means, where appropriate, from ground level and other available vantage points and openings." — PNBI-10, Appendix B (2017), Part A of s.3.4.2(A) [29]

and, in the defect list of the same part: "(d) **Spalling of concrete**; (e) **Delamination**" [29].

Two terminology points:

- **"Hollow sounding"** is the Code's own term, appearing in PNBI-10 Appendix VI Table 3 ("Verifying hacking of damaged, loose, **hollow sounding** concrete, spalling and honeycomb") [29]. It is a safer citation than the Cantonese-derived term.
- **空鼓** is the term used in the regional literature for the same defect. **No HK or Mainland primary source defining 空鼓 was retrievable**, and PNBI-10 uses English throughout. The report should introduce the term as the regional usage and cite the Code for the English equivalent, not attribute 空鼓 to any standard. `[TO VERIFY]` (U6).

Also worth noting, and it belongs in the report's honesty section: in the Code's workflow, **hammer-tapping appears as a proof test on "External Elements" following repair** ("(a) Supervising hammer-tapping; (b) Conducting pull-off tests") [29]. Using tapping as a *screening* method before repair is an extension, and describing it as "the method the Code specifies" without that qualification would be a misstatement.

### B.5.3 The Mainland comparison

**JGJ/T 110-2017 建筑工程饰面砖粘结强度检验标准** is the Mainland standard for exterior-wall face-tile bond. Verified metadata: professional standard of the Ministry of Housing and Urban-Rural Development (MOHURD); issued 2017-05-15; in force 2017-11-01; supersedes JGJ 110-2008; referred to by GB 50210-2018; registered in MOHURD Announcement No. 1558 [31] [32].

The comparison is analytically useful because it is a *different kind of test*:

| | JGJ/T 110-2017 (pull-off) | This project (instrumented tap) |
|---|---|---|
| Question answered | Is the adhesion strength of this sample acceptable? | Where is the finish likely debonded? |
| Coverage | Sampled and destructive | Continuous and non-destructive |
| Output | A strength figure against a criterion | An ordinal grade (G0 / G1 / G2) plus raw features |
| Regulatory status in HK | Not the HK regime | Not a statutory method |

Because the standard text is paywalled, **only this metadata should be cited**; no clause number should be quoted (U7).

---

## B.6 How to write this in the report

Five rules, then a suggested layout.

**Rule 1 — never invent a WSSS section title or a clause number.** The single sentence that most improves this report's credibility is the one that admits the IoT WSOS could not be retrieved, names what *was* retrieved, and states the proxy explicitly. A marker who knows the standards landscape will read the admission as rigour. A fabricated "WSSS 4.2 Sensing and Actuation (15 %)" reads as a fabrication.

**Rule 2 — separate the two kinds of claim throughout.** "The standard says X" needs a reference. "This project does Y" needs a file, a figure or a test result. Do not fuse them into "the project complies with X". The `Verification status` box at the top of this appendix exists to make that separation visible at a glance.

**Rule 3 — distinguish "documented" from "compliant".** PNBI-10 documents hammer-tapping; that does not make this probe compliant with anything. ETSI 303 645 says devices *should* be securely updateable; that does not make a device without OTA compliant, it makes it non-compliant. The verb matters.

**Rule 4 — where a control is missing, name the residual gap, not the intention.** "NVS is not encrypted unless flash encryption is enabled" is a finding. "Security was considered throughout" is not.

**Rule 5 — quote counts, not percentages, for validation.** The firmware's own guidance already says this (Appendix A.11): quote the confusion counts, not a bare accuracy figure.

### Suggested layout for Ch. 2.5 and the Limitations section

**In Ch. 2.5 (WorldSkills and the standards framework), about 600–900 words:**

1. What the WSOS is, and that it is a person-competence standard, not a product certification [10].
2. What was retrievable: the assessment method in full [1], and the WSOS structures of four adjacent skills [7]–[8].
3. What was not: the IoT standard itself. State the three facts — the skill page exists as a stub [3], IoT is absent from the 2026 catalogue of 64 skills [9], IoT appears in Future Skills and national-member material [4] [11].
4. The assessment method in three sentences — Measurement vs Judgement [1, §11.3]; the 100-mark Marking Scheme with 5–9 Criteria and 100–250 Aspects [1, §11.5]; weightings and the 5 % tolerance [1, §11.2.1].
5. How the method shaped the design: external benchmarks instead of preferences; separable measurement and judgement evidence; fine-grained, individually checkable claims. Cross-refer to Ch. 3.4.
6. Point forward to this appendix for the two matrices.

**In Ch. 9 (Limitations), add one table row per item from the "candid rows" list in B.2.** The gateway row and the update-path row are the two most important; the unvalidated-on-real-defects row is the third.

**In Ch. 7.4 (security), the shortest defensible paragraph** is: TLS with CA-chain validation via ESP-IDF's certificate bundle, per-device MQTT credentials, and a Last Will message for outage visibility; benchmarked against ETSI 303 645, where the project meets the transport, attack-surface and credential-hygiene provisions and does **not** meet the update provisions (5.3) or the vulnerability-disclosure provision (5.2); the residual gaps are plaintext NVS without flash encryption, no mutual TLS, no certificate pinning, and a 1 KB peak handshake heap cost if cross-signed support is enabled [24].

**Sentences that are safe to write**

- "WorldSkills publishes an Internet of Things occupational-standard page, but no IoT occupational standard is included in the WorldSkills Shanghai 2026 catalogue of 64 skills, and no public document setting out IoT WSOS sections or weightings could be retrieved."
- "MILO *b* is evidenced against the WorldSkills assessment method, which is fully documented in the Competition Rules, and against the WSOS section structures of Industry 4.0, Cloud Computing, Cyber Security and Intelligent Security Technology, used explicitly as proxies."
- "The probe instruments a method that the Buildings Department's Code of Practice already names — hammer-tapping — as one of the non-destructive methods for inspecting structural elements."
- "TLS trust-anchor validation is delegated to the ESP-IDF certificate bundle, which trusts the Mozilla root set; a pinned certificate or mutual TLS would be preferred for production."

**Sentences to avoid**

- Any sentence naming a WSSS/IoT section title or weighting.
- Any sentence asserting a WorldSkills skill number for IoT.
- "The project complies with ETSI EN 303 645."
- "The Code of Practice requires hammer-tapping" — the Code permits it among alternatives ("such as ... or other feasible means").
- "The system detects hollow areas in external wall finishes" — it indicates a grade; it is unvalidated on real defects.
- Any assertion of a fall-from-height incident statistic without a retrieved source.

---

## References

1. WorldSkills International. *Competition Rules*, WSI_OD03, version 11.1, dated 21.09.26. Document file `WSI_OD03_competition_rules_v11.1_en.pdf`. https://www.worldskills.org/resources/download/3745/34979/36045?l=en — §3.3 (Exhibition Skills), §3.4 (Types of skills), §10 (Test Projects), §11.2 (WorldSkills Occupational Standards), §11.2.1 (Weightings), §11.3 (Assessment methods), §11.3.1 (Benchmarks), §11.3.2 (Standards and Assessment Guides), §11.4 (Assessment training), §11.5 (Marking Scheme), §11.5.1–§11.5.6.
2. WorldSkills International. *Continuing improvements being made to WorldSkills standards specifications*, 29 January 2013. https://www.worldskills.org/media/news/continuing-improvements-being-made-worldskills-standards-specifications/ — historical source for the term "WorldSkills Standards Specification".
3. WorldSkills International. *Internet of Things — Skills*. Skill page id 559. https://worldskills.org/skills/id/559/ — retrieved 16 October 2026; contains no downloadable occupational standard.
4. WorldSkills International. *Long distance communication keeps Future Skills in touch with the world* — WorldSkills Russia Future Skills Camp 2020; "Internet of Things" listed among the skills offered. https://worldskills.org/media/news/long-distance-communication-keeps-future-skills-touch-world/
5. WorldSkills International. *WorldSkills Occupational Standards — Cloud Computing*, WorldSkills Shanghai 2026, skill 2455. https://worldskills.org/what/projects/wsos/2026/events/611/skills/2455
6. WorldSkills International. *WorldSkills Occupational Standards — Cyber Security*, WorldSkills Shanghai 2026, skill 2461. https://worldskills.org/what/projects/wsos/2026/events/611/skills/2461
7. WorldSkills International. *WorldSkills Occupational Standards — Industry 4.0*, WorldSkills Shanghai 2026, skill 2452. https://worldskills.org/what/projects/wsos/2026/events/611/skills/2452
8. WorldSkills International. *WorldSkills Occupational Standards — Intelligent Security Technology*, WorldSkills Shanghai 2026, skill 2694. https://worldskills.org/what/projects/wsos/2026/events/611/skills/2694
9. WorldSkills International. *WorldSkills Occupational Standards — WorldSkills Shanghai 2026*. https://worldskills.org/what/projects/wsos/2026/ — 64 skills in six categories; "Internet of Things" absent.
10. WorldSkills International. *WorldSkills Occupational Standards* (landing page). https://worldskills.org/what/projects/wsos/ — definition, biennial update, relative importance of sections.
11. WorldSkills Philippines. *Internet of Things — Information and Communication Technology*. https://www.worldskills.ph/skills/internet-of-things/ — national-member IoT skill description, credited to WorldSkills Singapore. **National-member material; not the WSOS.**
12. ETSI. *CYBER; Cyber Security for Consumer Internet of Things: Baseline Requirements*. ETSI EN 303 645 V2.1.1 (2020-06). https://www.etsi.org/deliver/etsi_en/303600_303699/303645/02.01.01_60/en_303645v020101p.pdf
13. ETSI. *CYBER; Cyber Security for Consumer Internet of Things: Baseline Requirements*. ETSI EN 303 645 V3.1.3 (2024-09). https://www.etsi.org/deliver/etsi_en/303600_303699/303645/03.01.03_60/en_303645v030103p.pdf
14. ETSI. *CYBER; Cyber Security for Consumer Internet of Things: Conformance Assessment of Baseline Requirements*. ETSI TS 103 701 V1.1.1 (2021-08) — the assessment method that accompanies EN 303 645. https://www.etsi.org/deliver/etsi_ts/103700_103799/103701/01.01.01_60/ts_103701v010101p.pdf
15. National Institute of Standards and Technology. *Foundational Cybersecurity Activities for IoT Device Manufacturers* (NISTIR 8259, May 2020) — Withdrawn NIST Technical Series Publication, withdrawal date 20 April 2026; superseded by NIST IR 8259r1. https://csrc.nist.gov/pubs/ir/8259/final
16. Fagan, M., Megas, K. N., Scarfone, K., & Smith, M. *IoT Device Cybersecurity Capability Core Baseline*. NISTIR 8259A, May 2020. https://doi.org/10.6028/NIST.IR.8259A · PDF: https://nvlpubs.nist.gov/nistpubs/ir/2020/NIST.IR.8259A.pdf — capability names verified: Device Identification; Device Configuration; Data Protection; Logical Access to Interfaces; Software Update; Cybersecurity State Awareness.
17. Fagan, M., Megas, K. N., Scarfone, K., & Smith, M. *IoT Non-Technical Supporting Capability Core Baseline*. NISTIR 8259B, August 2021. https://doi.org/10.6028/NIST.IR.8259B · PDF: https://nvlpubs.nist.gov/nistpubs/ir/2021/NIST.IR.8259B.pdf — capability names verified: Documentation; Information and Query Reception; Information Dissemination; Education and Awareness.
18. Fagan, M., Megas, K. N., Cuthill, B., Marron, J., & Hoehn, B. *Foundational Cybersecurity Activities for IoT Product Manufacturers*. NIST IR 8259r1, April 2026. https://doi.org/10.6028/NIST.IR.8259r1 · https://csrc.nist.gov/pubs/ir/8259/r1/final
19. Parliament of the United Kingdom. *Product Security and Telecommunications Infrastructure Act 2022*, 2022 c. 46, Part 1 (Product security), Chapters 1–3. https://www.legislation.gov.uk/ukpga/2022/46/contents
20. Secretary of State. *The Product Security and Telecommunications Infrastructure (Security Requirements for Relevant Connectable Products) Regulations 2023*, SI 2023/1007. Schedule 1 (Security requirements for manufacturers), Schedule 3 (Excepted connectable products), Schedule 4 (Minimum Information Required for Statements of Compliance). https://www.legislation.gov.uk/uksi/2023/1007/contents/made
21. OASIS Message Queuing Telemetry Transport (MQTT) TC. *MQTT Version 5.0*, OASIS Standard, 07 March 2019. https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html — §1.6 (Security), Chapter 5 (Security, non-normative), §5.1 (Introduction; port 8883 recommendation), §5.4.1–§5.4.12 (Implementation notes and security profiles), §4.12 (Enhanced authentication), §5.4.7 (Detecting compromise of Clients and Servers; CRL/OCSP).
22. Rescorla, E. *The Transport Layer Security (TLS) Protocol Version 1.3*. IETF RFC 8446, August 2018. https://www.rfc-editor.org/rfc/rfc8446.txt
23. Dierks, T., & Rescorla, E. *The Transport Layer Security (TLS) Protocol Version 1.2*. IETF RFC 5246, August 2008 — cited as a normative reference by MQTT v5.0 [23]. https://www.rfc-editor.org/rfc/rfc5246.txt
24. Espressif Systems. *ESP x509 Certificate Bundle* — ESP-IDF Programming Guide. https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/protocols/esp_crt_bundle.html — `esp_crt_bundle_attach`; Mozilla NSS root store embedded in the binary; cross-signed certificate support increases peak run-time heap during the TLS handshake by approximately 1 KB.
25. Espressif Systems. *ESP-TLS* — ESP-IDF Programming Guide. https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/protocols/esp_tls.html — CA certification validation, SNI, ALPN; `crt_bundle_attach`.
26. Hong Kong Special Administrative Region. *Buildings Ordinance* (Cap 123). https://www.elegislation.gov.hk/hk/cap123 · *Buildings (Inspection and Repair) Regulation* (Cap 123P). https://www.elegislation.gov.hk/hk/cap123P
27. Buildings Department, HKSAR. *Mandatory Building Inspection Scheme*. https://www.bd.gov.hk/en/safety-inspection/mbis/index.html — buildings aged 30 years or above; Registered Inspector; prescribed inspection of common parts, external walls and projections or signboards.
28. Buildings Department, HKSAR. *Minor works*. https://www.bd.gov.hk/en/building-works/minor-works/index.html
29. Buildings Department, HKSAR. *Practice Note for Mandatory Building and Window Inspection Schemes PNBI-10: Code of Practice for the Mandatory Building Inspection Scheme and the Mandatory Window Inspection Scheme*, current issue May 2023 (first issue January 2022). PDF: https://www.bd.gov.hk/doc/en/resources/codes-and-references/practice-notes-and-circular-letters/pnbi/PNBI010.pdf · Index: https://www.bd.gov.hk/en/resources/codes-and-references/practice-notes-and-circular-letters/index_pnbi.html — Appendix B (6 March 2017), Part A of s.3.4.2(A); Appendix C (30 April 2018), s.5.3.1; Appendix D (20 July 2020); Appendix VI, Tables 1–3.
30. Buildings Department, HKSAR. *Practice Notes for Mandatory Building and Window Inspection Schemes* (PNBI index). https://www.bd.gov.hk/en/resources/codes-and-references/practice-notes-and-circular-letters/index_pnbi.html
31. Ministry of Housing and Urban-Rural Development (MOHURD), People's Republic of China. *JGJ/T 110-2017 建筑工程饰面砖粘结强度检验标准* (Testing standard for adhesive strength of tapestry brick of construction engineering), issued 2017-05-15, in force 2017-11-01; supersedes JGJ 110-2008; MOHURD Announcement No. 1558. Metadata record: https://www.chinesestandard.net/PDF.aspx/JGJT110-2017 — **standard text not retrieved; paywalled.**
32. Code of China / ChineseStandard. *JGJ/T 110-2017* reference record, including the statement that it is referred to by GB 50210-2018 *Standard for construction quality acceptance of building decoration*. https://www.codeofchina.com/standard/JGJT110-2017.html
