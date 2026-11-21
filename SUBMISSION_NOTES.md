# Submission notes

These are the housekeeping items that used to sit in `README.md`. The project overview is now
[README.md](README.md); this file is the checklist for handing the coursework report in.

## Read this before you submit

1. **The report is honest about its own state, on purpose.** The abstract, §8.0, §9.1 and Appendix F.3
   all say plainly that the design was not built when the report was written, and that Chapter 8's
   numbers come from a forward physical model. **Do not delete those statements.** An examiner who
   finds a disclosed limitation credits the disclosure; one who finds a concealed limitation discounts
   everything else. See Appendix F.4.

   Since then the probe *has* been built (see the top-level README), but the report text was not
   rewritten to match, and the implementation uses a different sensing channel (accelerometer at
   6.66 kHz instead of a 48 kHz microphone). If you claim the build in the report, say that too.

2. **Fill in the author fields.** The YAML front matter of `00_main_report.md` has
   `[STUDENT NAME] — [STUDENT ID]` placeholders.

3. **Resolve the `[TO VERIFY]` items.** Appendix B.1 and the References carry them. Two matter most:
   the official WSSS document (ask the lecturer — the report uses a labelled proxy because no public
   IoT standard could be found), and the NDE literature citations for §2.2.

4. **Chapter 8 is SYNTHETIC.** Everything in it comes from a model, not a wall. §8.0 says so in the
   text and the stamp is on every table and figure. It becomes real by running
   `python 06_analyze_tap.py --input <your data> --outdir results`.

5. **The single highest-value thing left** is the calibration panel in the README's limitations list:
   one bonded/debonded reference pair turns every placeholder threshold into a measured one.

## Building the report

```bash
bash build_report.sh          # writes EEE4483_MiniProject_Report.md
```

Then, for a Word submission: paste the assembled file into Word and apply Heading 1/2 styles to the
`#`/`##` lines; the table of contents field will regenerate. Figures are PNG at 300 dpi in
`results/figures/`; Appendix E says which figure supports which claim.

## What is where

| Path | What it is |
| --- | --- |
| `EEE4483_MiniProject_Report.md` | the report, assembled from the sources below |
| `build_report.sh` | assembles the chapter sources into the report |
| `00_main_report.md` | title, abstract, TOC, Chapters 1–4 |
| `_chapters/ch5.md` … `appf.md` | remaining chapters and appendices |
| `03_wsss_standards.md` | Appendix B, standalone (also assembled into the report) |
| `06_analyze_tap.py` | offline analysis script; produces every table and figure in Chapter 8 |
| `results/` | output of `06_analyze_tap.py` |
| `_repro/ch5_model_check.py` | computes Chapter 5's Tables 5.3–5.6 and 5.9 |
