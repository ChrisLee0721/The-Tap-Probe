
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
