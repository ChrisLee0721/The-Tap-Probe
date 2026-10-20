# EEE4483 Mini-project — submission package

**Deliverable:** `EEE4483_MiniProject_Report.md` — the assembled report. Edit the chapter
sources, then run `bash build_report.sh` to regenerate it. Do not edit the assembled file
directly; it is overwritten on every build.

## What is here

| Path | What it is |
|---|---|
| `EEE4483_MiniProject_Report.md` | **The report.** Assembled from the sources below. |
| `build_report.sh` | Assembles the chapter sources into the report. Run after any edit. |
| `00_main_report.md` | Title, abstract, TOC, Chapters 1–4. Part of the report. |
| `_chapters/ch5.md` … `appf.md` | The remaining chapters and appendices. Part of the report. |
| `03_wsss_standards.md` | Appendix B, standalone (also assembled into the report). Keep for submission as a separate artefact if the lecturer wants one. |
| `06_analyze_tap.py` | The offline analysis script. Produces every table and figure in Chapter 8. |
| `results/` | Output of `06_analyze_tap.py`: `results.md`, `features_analysed.csv`, `run_log.txt`, `figures/`. |
| `05_firmware/` | ESP-IDF v5.x firmware and build files. Appendix D. |
| `_repro/ch5_model_check.py` | The script that computed Chapter 5's Tables 5.3–5.6 and 5.9. Re-run it if a material parameter changes. |
| `_repro/` | Computation scripts for the report's numbers. Not part of the submission. |

`_scratch/` is transient and not part of the submission.

## Read this before you submit

1. **The report is honest about its own state, on purpose.** The abstract, §8.0, §9.1 and Appendix F.3
   all say plainly that nothing was built and nothing was measured. **Do not delete those statements.**
   An examiner who finds a disclosed limitation credits the disclosure; an examiner who finds a
   concealed one discounts everything else. See Appendix F.4.
2. **Fill in the author fields.** The YAML front matter of `00_main_report.md` has
   `[STUDENT NAME] — [STUDENT ID]` placeholders.
3. **Resolve the `[TO VERIFY]` items.** Appendix B.1 and the References carry them. Two matter most:
   the official WSSS document (ask the lecturer — the report uses a labelled proxy because no public
   IoT standard could be found), and the NDE literature citations for §2.2.
4. **Chapter 8 is `SYNTHETIC`.** Everything in it comes from a model, not a wall. §8.0 says so in the
   text and the stamp is on every table and figure. It becomes real by running
   `python 06_analyze_tap.py --input <your data> --outdir results`.
5. **The single highest-value thing you can still do** is in Appendix F.3's gap table: build the probe
   and record one tap reaching the dashboard. "We built it and it produced this" is worth more than any
   amount of additional argument.

## Building the report

```bash
bash build_report.sh          # writes EEE4483_MiniProject_Report.md
```

Then, for a Word submission: paste the assembled file into Word and apply Heading 1/2 styles to the
`#`/`##` lines, and the table of contents field will regenerate. Figures are PNG at 300 dpi in
`results/figures/`; Appendix E says which figure supports which claim.
