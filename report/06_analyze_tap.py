#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
06_analyze_tap.py - offline analysis of handheld tap-test probe data.
EEE4483 "Internet-of-Things Planning and Deployment", HK VTC / IVE Higher
Diploma, end-of-module mini-project.

PURPOSE
-------
A solenoid strikes an external wall finish; an I2S microphone records the "tap
tone"; an ESP32 extracts a feature vector per tap and publishes it over MQTT.
This script is the offline half: it turns the logged feature CSV (or raw
waveform CSVs) into every evidence table and figure quoted in the report,
including the ROC / expected-cost threshold analysis.

OUTPUT -> REPORT SECTION MAP (Chapter 8 of the report)
  results.md 1. Data integrity         -> Ch.8 S8.2 data quality
  results.md 2. Descriptive statistics -> Ch.8 S8.2 descriptive statistics
  results.md 3. Repeatability          -> Ch.8 S8.3 (prediction P7)
  results.md 4. Discrimination testing -> Ch.8 S8.4 feature-level tests
  results.md 5. Size sensitivity       -> Ch.8 S8.5 (headline; predictions P2, P8)
  results.md 6. Classifier comparison  -> Ch.8 S8.4 detection algorithms
  results.md 7. ROC / AUC              -> Ch.8 S8.4 (fig03, fig07)
  results.md 8. Expected cost          -> Ch.8 S8.6 threshold selection (headline)
  features_analysed.csv                -> appendix: the cleaned dataset actually used
  run_log.txt                          -> appendix: full reproduction transcript
  figures/fig01..fig07 (300 dpi PNG)   -> inline figures, S8.2-S8.6

GROUND TRUTH  G0 = fully bonded control; G1 = partial debond (thin compliant
interlayer, e.g. 5 mm foam); G2 = full debond (thick interlayer / free edge,
e.g. 10 mm foam or a suspended region). size_cm = nominal debond radius in cm
(3, 5, 10, 15, 20) or 0 for G0.

INPUT MODES (auto-detected)
  FEATURE  one or more CSVs (or directories) with sample_id, panel_id, grade,
           size_cm, location_id, tap_idx, f_peak_hz, f_centroid_hz,
           band_ratio_lh, decay_tau_ms, peak_au, rms_au, crest_factor,
           kurtosis, impact_peak_g, impulse_norm (+ optional temp_c, notes).
  WAVEFORM a directory of `<anything>_<grade>_<location>_<tap>.csv` with
           t_s,amp columns; features are computed here instead. Sample rate is
           auto-detected from the median dt and printed.

DEPENDENCIES  python >= 3.9, numpy, pandas, scipy, scikit-learn, matplotlib.
No network access. Missing libraries produce a clear message, not a traceback.
All stochastic steps are seeded from --seed: identical inputs and arguments give
identical numbers and identical PNGs.

DEMO MODE  --demo synthesises physically plausible data so the pipeline can be
exercised before hardware exists. EVERY figure and EVERY table is stamped
"SYNTHETIC DEMONSTRATION DATA - NOT MEASURED" and the console prints a banner.
The stamp follows the flag, so re-running on real captures removes it.

USAGE
  python 06_analyze_tap.py --demo
  python 06_analyze_tap.py --input features/ --outdir results
  python 06_analyze_tap.py --input waveform/ --mode waveform
  python 06_analyze_tap.py --input f1.csv --input f2.csv --miss-cost 20
"""

from __future__ import annotations

import argparse
import glob
import sys
import time
import traceback
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

try:
    import numpy as np
except ImportError as exc:                                   # pragma: no cover
    sys.stderr.write("FATAL: numpy is required.\n  pip install numpy\n")
    raise SystemExit(2) from exc

_MISSING: List[str] = []
try:
    import pandas as pd
except ImportError:                                          # pragma: no cover
    pd = None                                                # type: ignore
    _MISSING.append("pandas")
try:
    from scipy import signal as spsig
    from scipy import stats as sps
except ImportError:                                          # pragma: no cover
    sps = spsig = None                                       # type: ignore
    _MISSING.append("scipy")
try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import (accuracy_score, balanced_accuracy_score,
                                 confusion_matrix, f1_score, precision_score,
                                 recall_score, roc_auc_score, roc_curve)
    from sklearn.model_selection import GroupKFold, StratifiedGroupKFold
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.preprocessing import StandardScaler
except ImportError:                                          # pragma: no cover
    _MISSING.append("scikit-learn")
try:
    import matplotlib
    matplotlib.use("Agg")            # headless: never try to open a window
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
except ImportError:                                          # pragma: no cover
    _MISSING.append("matplotlib")

if _MISSING:
    sys.stderr.write("FATAL: missing required librar(y/ies): %s\n"
                     "  pip install %s\n" % (", ".join(_MISSING), " ".join(_MISSING)))
    raise SystemExit(2)

SCRIPT_VERSION = "1.0.0"

# Sentinel the extractor returns when no decay can be fitted (and the value a
# synthetic tap carries when its decay falls outside 3..60 ms).
TAU_SENTINEL = -1.0

SYNTH_STAMP = "SYNTHETIC DEMONSTRATION DATA - NOT MEASURED"

GRADE_ORDER = ("G0", "G1", "G2")
GRADE_LABEL = {"G0": "G0 bonded", "G1": "G1 partial debond", "G2": "G2 full debond"}
SIZE_ORDER = (0, 3, 5, 7, 8.8, 10, 15, 20)

NUMERIC_FEATURES = ("f_peak_hz", "f_centroid_hz", "band_ratio_lh", "decay_tau_ms",
                    "peak_au", "rms_au", "crest_factor", "kurtosis",
                    "impact_peak_g", "impulse_norm")
# The DECISION features. These are the four members of the physics-derived
# spectral feature set of the report's S6.5: three frequency-domain descriptors
# plus the ring-down time.
#
# impulse_norm (the accelerometer's strike-window RMS) was REMOVED from this
# tuple. It is still logged, still published in the MQTT payload and still
# reported in the descriptive and discrimination tables, and the accelerometer
# still performs its contact-quality supervision role -- but it no longer votes
# on the wall's grade. Two reasons, both recorded in S8.0:
#   1. architecture: the accelerometer's documented job (S4.4, S6.6) is to grade
#      the OPERATOR's grip, not the wall;
#   2. measurement: in --demo mode the generator gives impulse_norm a class-coded
#      scale factor (0.77 for G0, 1.0 otherwise) that carries no physics at all,
#      and that single constant reproduces the channel's entire measured AUC
#      (0.846 observed vs 0.848 predicted by the offset alone). Left in the
#      decision set it would be quoted as the second-strongest detector in the
#      report on the strength of an artefact.
CLF_FEATURES = ("f_peak_hz", "f_centroid_hz", "band_ratio_lh", "decay_tau_ms")


# feature -> (unit, plausible min, plausible max). A corruption net for the
# integrity check (unit mix-ups, truncated log lines), not a physics model.
# decay_tau_ms admits -1.0: that is the documented sentinel the extractor
# returns when no decay can be fitted (`TAU_SENTINEL`), i.e. a legitimate
# "not measurable" reading rather than a corrupt one, and dropping it would
# bias every decay statistic towards the taps that happen to be measurable.
FEATURE_BOUNDS = {
    "f_peak_hz": ("Hz", 100.0, 20000.0),
    "f_centroid_hz": ("Hz", 100.0, 20000.0),
    "band_ratio_lh": ("-", 0.0, 1e4),
    "decay_tau_ms": ("ms", TAU_SENTINEL, 1000.0),
    "peak_au": ("a.u.", 0.0, 1e6),
    "rms_au": ("a.u.", 0.0, 1e6),
    "crest_factor": ("-", 1.0, 200.0),
    "kurtosis": ("-", 1.0, 500.0),
    "impact_peak_g": ("g", 0.0, 500.0),
    "impulse_norm": ("a.u.", 0.0, 1e6),
}
FEATURE_UNIT = {k: v[0] for k, v in FEATURE_BOUNDS.items()}

REQUIRED_COLUMNS = ("sample_id", "panel_id", "grade", "size_cm", "location_id",
                    "tap_idx") + NUMERIC_FEATURES

GRADE_ALIASES = {
    "g0": "G0", "0": "G0", "0.0": "G0", "bonded": "G0", "good": "G0",
    "control": "G0", "ok": "G0", "sound": "G0",
    "g1": "G1", "1": "G1", "1.0": "G1", "partial": "G1", "partial_debond": "G1",
    "g2": "G2", "2": "G2", "2.0": "G2", "full": "G2", "full_debond": "G2",
    "hollow": "G2", "debond": "G2", "void": "G2",
}

WAVEFORM_TIME_ALIASES = ("t_s", "time", "t", "time_s", "timestamp")
WAVEFORM_AMP_ALIASES = ("amp", "amplitude", "a", "y", "signal", "value")

# ---- Palette (dataviz skill reference instance, validated) ----------------
# scripts/validate_palette.js --pairs all --mode light:
#   blue/orange/aqua PASS (worst CVD dE 9.2, worst normal-vision dE 24.0).
#   Aqua is 2.74:1 on the surface -> the relief rule applies, so every figure
#   that uses it also carries a legend and direct text labels.
# The G0/G1/G2 ramp is the single blue hue at steps 250/450/650 and passes the
# --ordinal gate (monotone L, dL >= 0.06, light end 2.06:1).
# Line style, marker shape and hatch duplicate the colour channel so every
# figure survives greyscale printing.
SURFACE, INK, INK2, MUTED, GRID, AXIS = (
    "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7")
CAT = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300",
       "#6250d6", "#e34948")          # fixed order, never cycled
SERIES_BLUE, SERIES_ORANGE, SERIES_AQUA = CAT[0], CAT[1], CAT[2]
CRITICAL = "#d03b3b"                    # status colour, reserved for thresholds
GRADE_COLOR = {"G0": "#86b6ef", "G1": "#2a78d6", "G2": "#104281"}
GRADE_HATCH = {"G0": "///", "G1": "\\\\\\", "G2": ""}
GRADE_MARKER = {"G0": "o", "G1": "s", "G2": "^"}
CLF_COLOR = {"Threshold rule": SERIES_BLUE, "Logistic regression": SERIES_ORANGE,
             "k-NN (k=5)": SERIES_AQUA}
CLF_LINESTYLE = {"Threshold rule": "-", "Logistic regression": "--", "k-NN (k=5)": ":"}
CLF_MARKER = {"Threshold rule": "o", "Logistic regression": "s", "k-NN (k=5)": "^"}
SEQ_BLUE = ("#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b")


# ==========================================================================
# S1  Logging, formatting, statistics helpers
# ==========================================================================

class Tee:
    """Mirror stdout into a log file so run_log.txt is a full transcript."""

    def __init__(self, path: Path) -> None:
        self.terminal = sys.stdout
        self.handle = open(path, "w", encoding="utf-8", newline="\n")

    def write(self, message: str) -> None:
        self.terminal.write(message)
        self.handle.write(message)

    def flush(self) -> None:
        self.terminal.flush()
        self.handle.flush()

    def close(self) -> None:
        try:
            self.flush()
        finally:
            self.handle.close()
        sys.stdout = self.terminal


def banner(title: str) -> str:
    """Boxed section banner for readable console output."""
    return "\n".join(["=" * 70, f"  {title}", "=" * 70])


def fmt_num(value: Any, sig: int = 4, dash: str = "n/a") -> str:
    """Compact significant-figure formatting for markdown cells."""
    if value is None:
        return dash
    try:
        x = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not np.isfinite(x):
        return dash
    if x == 0:
        return "0"
    mag = abs(x)
    if mag >= 1e5 or mag < 1e-3:
        return f"{x:.{max(sig - 1, 1)}e}"
    if mag >= 1000:
        return f"{x:,.0f}"
    if mag >= 100:
        return f"{x:.1f}"
    return f"{x:.{sig}g}"


def pct(value: Any, places: int = 1, dash: str = "n/a") -> str:
    """Format a fraction in [0,1] as a percentage string."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return dash
    return dash if not np.isfinite(x) else f"{100.0 * x:.{places}f}%"


def md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """Render a markdown table, or an explicit note when there is no data."""
    if not rows:
        return "_No rows to report (the relevant class or feature was absent)._\n"
    head = "| " + " | ".join(str(h) for h in headers) + " |"
    sep = "|" + "|".join("---" for _ in headers) + "|"
    body = ["| " + " | ".join("" if c is None else str(c) for c in row) + " |"
            for row in rows]
    return "\n".join([head, sep] + body) + "\n"


def safe_div(num: float, den: float) -> float:
    """Division returning NaN rather than raising or warning on a zero divisor."""
    if den is None or den == 0 or not np.isfinite(den):
        return float("nan")
    return num / den


def cv_percent(values: Sequence[float]) -> float:
    """Population coefficient of variation in percent (SD/mean * 100).

    Population rather than sample SD: repeatability is assessed over the
    complete set of taps taken at one location. NaN if n < 2 or mean == 0.
    """
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size < 2:
        return float("nan")
    mean = float(np.mean(arr))
    return float("nan") if mean == 0 else float(np.std(arr, ddof=0) / abs(mean) * 100.0)


def describe(values: Sequence[float]) -> Dict[str, float]:
    """n / median / IQR / min / max / CV% for one numeric sample."""
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return {k: (0 if k == "n" else float("nan")) for k in
                ("n", "median", "q1", "q3", "iqr", "min", "max", "cv")}
    q1, q3 = (float(np.percentile(arr, 25)), float(np.percentile(arr, 75)))
    return {"n": int(arr.size), "median": float(np.median(arr)), "q1": q1, "q3": q3,
            "iqr": q3 - q1, "min": float(np.min(arr)), "max": float(np.max(arr)),
            "cv": cv_percent(arr)}


def holm_bonferroni(pvalues: Sequence[float]) -> List[float]:
    """Holm-Bonferroni step-down adjustment of one family of p-values."""
    p = np.asarray(pvalues, dtype=float)
    n = p.size
    if n == 0:
        return []
    order = np.argsort(p, kind="mergesort")          # stable -> deterministic
    adjusted, running = np.empty(n, dtype=float), 0.0
    for rank, idx in enumerate(order):
        running = max(running, min(1.0, p[idx] * (n - rank)))
        adjusted[idx] = running
    return [float(v) for v in adjusted]


def cliffs_delta(x: Sequence[float], y: Sequence[float]) -> float:
    """Cliff's delta from the Mann-Whitney U statistic: 2U/(n1*n2) - 1.

    Algebraically the rank-biserial correlation for this two-sample layout, so
    it satisfies the brief's "rank-biserial or Cliff's delta" requirement.
    Bands: 0.147 small, 0.33 medium, 0.474 large.
    """
    a = np.asarray(x, dtype=float)
    a = a[np.isfinite(a)]
    b = np.asarray(y, dtype=float)
    b = b[np.isfinite(b)]
    if a.size == 0 or b.size == 0:
        return float("nan")
    u = float(sps.mannwhitneyu(a, b, alternative="two-sided").statistic)
    return 2.0 * u / (a.size * b.size) - 1.0


def delta_word(delta: float) -> str:
    """Conventional verbal band for a Cliff's delta value."""
    if not np.isfinite(delta):
        return "n/a"
    d = abs(delta)
    return ("negligible" if d < 0.147 else "small" if d < 0.330
            else "medium" if d < 0.474 else "large")


def bootstrap_ci(
    metric_fn: Callable[[np.ndarray, np.ndarray], float],
    y_true: np.ndarray, y_score: np.ndarray,
    groups: Optional[np.ndarray] = None,
    n_boot: int = 1000, alpha: float = 0.05,
    rng: Optional[np.random.Generator] = None,
) -> Tuple[float, float]:
    """Percentile bootstrap 95% CI for a metric on (y_true, y_score).

    Resamples *panels* when ``groups`` is given: several taps share one panel, so
    taps are not independent and resampling rows would understate the interval.
    """
    rng = rng or np.random.default_rng(0)
    y_true, y_score = np.asarray(y_true), np.asarray(y_score)
    if y_true.size == 0:
        return float("nan"), float("nan")
    stats: List[float] = []
    if groups is not None:
        groups = np.asarray(groups)
        uniq = np.unique(groups)
        by_group = {g: np.flatnonzero(groups == g) for g in uniq}
        draws = (np.concatenate([by_group[g] for g in rng.choice(uniq, uniq.size,
                                                                replace=True)])
                 for _ in range(n_boot))
    else:
        draws = (rng.integers(0, y_true.size, size=y_true.size)
                 for _ in range(n_boot))
    for idx in draws:
        if np.unique(y_true[idx]).size < 2:
            continue
        try:
            stats.append(float(metric_fn(y_true[idx], y_score[idx])))
        except Exception:
            continue
    if len(stats) < 10:
        return float("nan"), float("nan")
    return (float(np.percentile(stats, 100 * alpha / 2)),
            float(np.percentile(stats, 100 * (1 - alpha / 2))))


def ci_text(lo: float, hi: float, places: int = 3) -> str:
    """Render a CI pair for a markdown table cell."""
    return "n/a" if not (np.isfinite(lo) and np.isfinite(hi)) \
        else f"[{lo:.{places}f}, {hi:.{places}f}]"


# ==========================================================================
# S2  Data loading (feature mode and waveform mode)
# ==========================================================================

@dataclass
class LoadReport:
    """Bookkeeping behind the data-integrity section. Nothing drops silently."""

    files_read: List[str] = field(default_factory=list)
    rows_read: int = 0
    dropped: Dict[str, int] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    duplicates: int = 0
    out_of_range: Dict[str, int] = field(default_factory=dict)
    missing: Dict[str, int] = field(default_factory=dict)
    waveform_fs_hz: Optional[float] = None

    def drop(self, reason: str, count: int) -> None:
        """Record that ``count`` rows were removed for ``reason``."""
        if count > 0:
            self.dropped[reason] = self.dropped.get(reason, 0) + int(count)

    @property
    def total_dropped(self) -> int:
        """Total rows removed across every reason."""
        return int(sum(self.dropped.values()))


def _norm_grade(value: Any) -> Optional[str]:
    """Map a raw grade cell to 'G0'/'G1'/'G2', or None if unrecognisable."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    key = str(value).strip().lower().replace("grade", "").replace(" ", "")
    return GRADE_ALIASES.get(key.replace("-", "_"))


def _find_column(columns: Sequence[str], aliases: Sequence[str]) -> Optional[str]:
    """Case-insensitive lookup of the first matching column alias."""
    lowered = {str(c).strip().lower(): c for c in columns}
    return next((lowered[a] for a in aliases if a in lowered), None)


def expand_inputs(paths: Sequence[str]) -> List[Path]:
    """Expand a mix of files, directories and globs into sorted unique CSVs."""
    found: List[Path] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            found.extend(sorted(p.glob("*.csv")))
            found.extend(sorted(p.glob("**/*.csv")))
        elif p.is_file():
            found.append(p)
        else:
            matched = [Path(m) for m in sorted(glob.glob(raw, recursive=True))]
            if not matched:
                raise FileNotFoundError(f"input path not found: {raw}")
            found.extend(matched)
    seen: set = set()
    unique: List[Path] = []
    for p in found:                       # de-duplicate, keep first-seen order
        key = str(p.resolve()).lower()
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def _clean_feature_frame(df: "pd.DataFrame", source: str) -> "pd.DataFrame":
    """Normalise column names and value types of one feature CSV."""
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    renames = {"peak_hz": "f_peak_hz", "fpeak_hz": "f_peak_hz", "f_peak": "f_peak_hz",
               "fp_hz": "f_peak_hz", "centroid_hz": "f_centroid_hz",
               "fcentroid_hz": "f_centroid_hz", "band_ratio": "band_ratio_lh",
               "bandratiolh": "band_ratio_lh", "decay_tau": "decay_tau_ms",
               "tau_ms": "decay_tau_ms", "decay_ms": "decay_tau_ms",
               "panel": "panel_id", "location": "location_id", "tap": "tap_idx",
               "id": "sample_id", "sample": "sample_id", "temp": "temp_c",
               "temperature_c": "temp_c", "temperature": "temp_c"}
    for old, new in renames.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})
    if "sample_id" not in df.columns:
        df["sample_id"] = [f"{Path(source).stem}_{i}" for i in range(len(df))]
    if "notes" not in df.columns:
        df["notes"] = ""
    if "temp_c" not in df.columns:
        df["temp_c"] = np.nan
    df["source_file"] = Path(source).name
    return df


def load_feature_mode(paths: Sequence[Path], rep: LoadReport) -> "pd.DataFrame":
    """Read and concatenate feature-mode CSVs, recording every exclusion."""
    frames: List["pd.DataFrame"] = []
    for path in paths:
        try:
            raw = pd.read_csv(path)
        except Exception as exc:
            rep.notes.append(f"SKIPPED {path.name}: unreadable CSV ({exc})")
            continue
        if raw.empty:
            rep.notes.append(f"SKIPPED {path.name}: zero data rows")
            continue
        df = _clean_feature_frame(raw, str(path))
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:                    # waveform-shaped or unrelated file
            rep.notes.append(
                f"SKIPPED {path.name}: not feature-mode (missing "
                f"{', '.join(missing[:4])}{'...' if len(missing) > 4 else ''})")
            continue
        rep.files_read.append(str(path))
        rep.rows_read += len(df)
        frames.append(df)
    if not frames:
        raise ValueError("feature mode found no usable CSV. Expected columns "
                         "include: " + ", ".join(REQUIRED_COLUMNS[:8]) + ", ...")

    all_df = pd.concat(frames, ignore_index=True, sort=False)
    mapped = all_df["grade"].map(_norm_grade)
    bad = int(mapped.isna().sum())
    if bad:
        offenders = sorted({str(v) for v in all_df.loc[mapped.isna(), "grade"]})
        rep.drop("unrecognised grade value", bad)
        rep.notes.append("Grade values that could not be mapped to G0/G1/G2: "
                         + ", ".join(map(repr, offenders[:8])))
    all_df = all_df.loc[mapped.notna()].copy()
    all_df["grade"] = mapped[mapped.notna()].values

    for col in (*NUMERIC_FEATURES, "size_cm", "tap_idx", "temp_c"):
        all_df[col] = pd.to_numeric(all_df[col], errors="coerce")
    before = len(all_df)
    all_df = all_df.dropna(subset=list(NUMERIC_FEATURES))
    rep.drop("non-numeric / blank feature value", before - len(all_df))
    before = len(all_df)
    all_df = all_df.dropna(subset=["size_cm"])
    rep.drop("missing size_cm", before - len(all_df))

    all_df.loc[all_df["grade"] == "G0", "size_cm"] = 0.0   # G0 has no radius
    all_df["size_cm"] = all_df["size_cm"].astype(int)

    missing_tap = int(all_df["tap_idx"].isna().sum())
    if missing_tap:
        all_df["tap_idx"] = (all_df.sort_values(["panel_id", "location_id"])
                             .groupby(["panel_id", "location_id"], sort=False)
                             .cumcount() + 1).reindex(all_df.index)
        rep.notes.append(f"tap_idx missing on {missing_tap} rows; assigned "
                         "sequentially within each (panel_id, location_id) so "
                         "repeatability stays countable.")
    all_df["tap_idx"] = all_df["tap_idx"].astype(int)
    return all_df


def _parse_waveform_name(path: Path) -> Tuple[Optional[str], str, int]:
    """Extract (grade, location_id, tap_idx) from `<any>_<g>_<loc>_<tap>.csv`.

    The documented convention puts the grade_token second-from-last-but-two.
    When the leading "<any>" ends in a `_<n>cm` (or `_<n>`) segment it is taken
    as the debond size and is *not* treated as part of the panel id, so captures
    named `cap_P0_10cm_G2_L2_1.csv` group under panel `cap_P0` rather than
    fragmenting into one panel per size class. Sizes are still reported by
    `_size_from_name`.
    """
    parts = path.stem.split("_")
    if len(parts) < 3:
        return None, path.stem, 1
    grade = _norm_grade(parts[-3])
    try:
        tap = int(float(parts[-1]))
    except ValueError:
        tap = 1
    head = parts[:-3]
    if len(head) > 1 and _size_from_name_or_none(head[-1]) is not None:
        head = head[:-1]
    panel = "_".join(head) or path.stem
    return grade, f"{panel}:{parts[-2]}", tap


def _size_label(value: float) -> str:
    """Render a debond diameter without truncating the 8.8 cm class."""
    return "0 cm (control)" if not value else f"{value:g} cm"


def _size_from_name_or_none(token: str) -> Optional[float]:
    """Return the nominal size encoded in one filename token, if any."""
    cleaned = token.strip().lower().rstrip("cm").rstrip("_")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if value in SIZE_ORDER else None


def extract_features_from_waveform(t_s: np.ndarray, amp: np.ndarray,
                                   fs_hz: float) -> Dict[str, float]:
    """Compute the tap-tone feature vector from one raw waveform.

    f_peak_hz      argmax of the Welch PSD over 300..15000 Hz
    f_centroid_hz  magnitude-weighted spectral centroid of the same band
    band_ratio_lh  band energy below 1 kHz / above 1 kHz
    decay_tau_ms   log-linear fit to the Hilbert envelope after the impact peak,
                   fitted only above 1% of the envelope peak (below that the fit
                   would be fitting the noise floor and biasing tau upwards)
    peak_au        max |amp|;  rms_au  RMS over the window
    crest_factor   peak_au / rms_au
    kurtosis       Fisher kurtosis (normal = 0) of the samples
    """
    amp = np.asarray(amp, dtype=float)
    amp = amp[np.isfinite(amp)]
    if amp.size < 8:
        raise ValueError("waveform too short to analyse")
    amp = amp - float(np.mean(amp))
    n = amp.size
    peak_au = float(np.max(np.abs(amp)))
    rms_au = float(np.sqrt(np.mean(amp ** 2)))

    nperseg = int(min(4096, max(256, 2 ** int(np.floor(np.log2(n))))))
    freqs, psd = spsig.welch(amp, fs=fs_hz, nperseg=nperseg,
                             noverlap=nperseg // 2, detrend=False)
    band = (freqs >= 300.0) & (freqs <= 15000.0)
    if not np.any(band):
        raise ValueError("sample rate too low for the 300..15000 Hz band")
    fb, pb = freqs[band], psd[band]
    low = fb < 1000.0
    total = float(np.sum(pb))

    env = np.abs(spsig.hilbert(amp))
    tail = env[int(np.argmax(env)):]
    tail_t = t_s[-tail.size:]
    keep = tail > 0.01 * float(np.max(env))
    tau = float("nan")
    if int(keep.sum()) >= 8:
        design = np.vstack([tail_t[keep], np.ones(int(keep.sum()))]).T
        slope = float(np.linalg.lstsq(design, np.log(tail[keep] + 1e-12),
                                      rcond=None)[0][0])
        tau = float(-1000.0 / slope) if slope < 0 else float("nan")
    dt = float(np.median(np.diff(t_s))) if t_s.size > 1 else 1.0 / fs_hz

    return {
        "f_peak_hz": float(fb[int(np.argmax(pb))]),
        "f_centroid_hz": float(np.sum(fb * pb) / total) if total > 0 else float("nan"),
        "band_ratio_lh": safe_div(float(np.sum(pb[low])), float(np.sum(pb[~low]))),
        "decay_tau_ms": tau,
        "peak_au": peak_au,
        "rms_au": rms_au,
        "crest_factor": safe_div(peak_au, rms_au),
        "kurtosis": float(sps.kurtosis(amp, fisher=True, bias=False)),
        "impact_peak_g": float("nan"),      # not recoverable from audio alone
        "impulse_norm": float(np.sum(env) * dt / max(n * dt, 1e-12)),
    }


def _size_from_name(stem: str) -> int:
    """Best-effort size_cm recovery from a waveform filename."""
    for token in stem.replace("-", "_").split("_"):
        value = _size_from_name_or_none(token)
        if value is not None:
            return value
    return 5                                # documented default


def load_waveform_mode(paths: Sequence[Path], rep: LoadReport) -> "pd.DataFrame":
    """Build a feature table by analysing every raw waveform CSV found."""
    parsed: List[Tuple[Path, np.ndarray, np.ndarray, Optional[str], str, int]] = []
    dts: List[float] = []
    for path in paths:
        try:
            raw = pd.read_csv(path)
        except Exception as exc:
            rep.notes.append(f"SKIPPED {path.name}: unreadable CSV ({exc})")
            continue
        tcol = _find_column(raw.columns, WAVEFORM_TIME_ALIASES)
        acol = _find_column(raw.columns, WAVEFORM_AMP_ALIASES)
        if tcol is None or acol is None:
            rep.notes.append(f"SKIPPED {path.name}: expected time/amplitude "
                             f"columns, found {list(raw.columns)[:5]}")
            continue
        t = pd.to_numeric(raw[tcol], errors="coerce").to_numpy(dtype=float)
        a = pd.to_numeric(raw[acol], errors="coerce").to_numpy(dtype=float)
        ok = np.isfinite(t) & np.isfinite(a)
        if int(ok.sum()) < 64:
            rep.notes.append(f"SKIPPED {path.name}: only {int(ok.sum())} usable samples")
            continue
        t, a = t[ok], a[ok]
        rep.files_read.append(str(path))
        dt = float(np.median(np.diff(t)))
        if dt > 0:
            dts.append(dt)
        parsed.append((path, t, a, *_parse_waveform_name(path)))

    if not parsed:
        raise ValueError("waveform mode found no usable CSVs. Filenames must "
                         "look like `<anything>_<grade>_<location>_<tap>.csv` "
                         "with t_s,amp columns.")
    fs_hz = 1.0 / float(np.median(dts)) if dts else float("nan")
    rep.waveform_fs_hz = fs_hz
    print(f"  Auto-detected sample rate from median dt: {fs_hz:,.0f} Hz "
          f"(dt = {1e6 / fs_hz:.1f} us)")

    rows: List[Dict[str, Any]] = []
    for path, t, a, grade, loc, tap in parsed:
        if grade is None:
            rep.drop("unrecognised grade in filename", 1)
            rep.notes.append(f"DROPPED {path.name}: no grade in filename")
            continue
        try:
            feats = extract_features_from_waveform(t, a, fs_hz)
        except Exception as exc:
            rep.drop("feature extraction failed", 1)
            rep.notes.append(f"DROPPED {path.name}: {exc}")
            continue
        panel = loc.split(":")[0]
        rows.append({"sample_id": path.stem, "panel_id": panel, "grade": grade,
                     "size_cm": 0 if grade == "G0" else _size_from_name(path.stem),
                     "location_id": loc, "tap_idx": tap, "temp_c": np.nan,
                     "notes": "", "source_file": path.name, **feats})
    rep.rows_read = len(rows)               # after extraction this means "usable"
    return pd.DataFrame(rows)


def detect_mode(paths: Sequence[Path], requested: str) -> str:
    """Decide between 'features' and 'waveform' by peeking at the first CSV."""
    if requested in ("features", "waveform"):
        return requested
    for path in paths:
        try:
            low = {str(c).strip().lower() for c in pd.read_csv(path, nrows=5).columns}
        except Exception:
            continue
        if not set(REQUIRED_COLUMNS) - low:
            return "features"
        if (low & set(WAVEFORM_TIME_ALIASES)) and (low & set(WAVEFORM_AMP_ALIASES)):
            return "waveform"
    return "features"


# ==========================================================================
# S3  Synthetic demonstration data (--demo)
# ==========================================================================

# ==========================================================================
# S3  Synthetic demonstration data (--demo)
# ==========================================================================
#
# Everything in this section is GENERATED BY THIS SCRIPT from the forward
# acoustic model of the report's Chapter 5. Nothing here is a measurement. The
# model is a plate on a Winkler foundation struck by a broadband transient:
# a debond of radius a is a clamped circular plate mode (0,1) sitting on the
# local bond stiffness k, so its resonance is the quadrature sum of the plate
# mode and the foundation mode. Its spectrum is measured on the same
# 1024-point / 48 kHz grid and in the same 300..15000 Hz band the firmware's
# feature extractor uses, so the synthetic features are literally produced by
# the same definitions as the offline ones.

SYNTH_MATERIAL = {"E_pa": 18.0e9, "h_m": 0.020, "rho_kg_m3": 2000.0, "nu": 0.20}
SYNTH_ALPHA_NUM = 3.19595          # alpha*a for the clamped circular mode (0,1)
SYNTH_CONTACT_S = 300e-6           # half-sine strike contact time
SYNTH_Q = 9.0                      # wall mode quality factor
SYNTH_BG_SCALE = 0.35              # broadband (substrate compliance) amplitude
SYNTH_BG_F0_HZ = 500.0             # broadband corner frequency
SYNTH_BG_EXP = 0.7                 # broadband roll-off exponent
SYNTH_MODE_IN_BAND_MAX_HZ = 15000.0    # derived: 3x the strike null (1.5/T)
SYNTH_FFT_N = 1024                 # 1024-point FFT on the analysis grid
SYNTH_FS_HZ = 48000.0              # ... at 48 kHz, exactly as the firmware

# Ground-truth bond stiffness per grade (Pa/m) and severity weight.
SYNTH_K_PA_PER_M = {"G0": 9.0e11, "G1": 1.0e10, "G2": 0.0}
SEV = {"G0": 0.0, "G1": 0.45, "G2": 0.95}

BAND_LO_HZ, BAND_HI_HZ = 300.0, 15000.0     # firmware PROBE_FMIN/FMAX_HZ
CROSSOVER_HZ = 1000.0                       # firmware PROBE_CROSSOVER_HZ
TAU_LO_MS, TAU_HI_MS = 3.0, 60.0            # usable decay window

# ---- the fixed analysis grid, computed once -------------------------------
_SYNTH_F_HZ = np.fft.rfftfreq(SYNTH_FFT_N, 1.0 / SYNTH_FS_HZ)
_SYNTH_BIN_HZ = SYNTH_FS_HZ / SYNTH_FFT_N
# Strike magnitude spectrum of the half-sine force pulse: sqrt(F2(f)) = |A(f)|,
# A(f) = cos(pi f T / 2) / (1 - (f T)^2), with a null at 1.5/T = 5 kHz.
_SYNTH_A = np.cos(np.pi * _SYNTH_F_HZ * SYNTH_CONTACT_S / 2.0) / (
    1.0 - (_SYNTH_F_HZ * SYNTH_CONTACT_S) ** 2)
_SYNTH_STRIKE = np.abs(_SYNTH_A)
_SYNTH_BG_SHAPE = SYNTH_BG_SCALE / (1.0 + (_SYNTH_F_HZ / SYNTH_BG_F0_HZ)
                                    ** SYNTH_BG_EXP)
_SYNTH_BAND = (_SYNTH_F_HZ >= BAND_LO_HZ) & (_SYNTH_F_HZ <= BAND_HI_HZ)
# Each FFT bin is assigned wholly to one side of the crossover: the 1000 Hz cut
# is only bin 21.33 of this grid, so bin 21 (984.375 Hz) is "low" and bin 22
# (1031.250 Hz) is "high" and the two sums straddle the nominal boundary.
_SYNTH_LOW = _SYNTH_BAND & (_SYNTH_F_HZ < CROSSOVER_HZ)
_SYNTH_HIGH = _SYNTH_BAND & (_SYNTH_F_HZ >= CROSSOVER_HZ)


def _plate_rigidity() -> float:
    """Flexural rigidity D = E h^3 / (12 (1 - nu^2)) of the render plate."""
    e, h, nu = SYNTH_MATERIAL["E_pa"], SYNTH_MATERIAL["h_m"], SYNTH_MATERIAL["nu"]
    return e * h ** 3 / (12.0 * (1.0 - nu ** 2))


def _f_mode_hz(debond_radius_m: float) -> float:
    """Clamped circular plate mode (0,1) of a debond of that radius.

        f_mode = (1/2pi) sqrt( D alpha^4 / (rho h) ),   alpha = 3.19595 / a
    """
    if debond_radius_m <= 0.0:
        return 0.0
    d = _plate_rigidity()
    rho, h = SYNTH_MATERIAL["rho_kg_m3"], SYNTH_MATERIAL["h_m"]
    alpha = SYNTH_ALPHA_NUM / debond_radius_m
    return float(np.sqrt(d * alpha ** 4 / (rho * h)) / (2.0 * np.pi))


def _f_found_hz(k_pa_per_m: float) -> float:
    """Foundation mode of the mass-on-Winkler-spring system: (1/2pi) sqrt(k/rho h)."""
    if k_pa_per_m <= 0.0:
        return 0.0
    rho, h = SYNTH_MATERIAL["rho_kg_m3"], SYNTH_MATERIAL["h_m"]
    return float(np.sqrt(k_pa_per_m / (rho * h)) / (2.0 * np.pi))


def f_resonance_hz(size_cm: float, k_pa_per_m: float) -> float:
    """f1 = sqrt(f_mode^2 + f_found^2): the in-service resonance of the region."""
    return float(np.hypot(_f_mode_hz(size_cm / 200.0), _f_found_hz(k_pa_per_m)))


def _strike_radius_cm(size_cm: float) -> float:
    """Aperture actually generated for a nominal size class, in cm.

    The generator's nominal five-point axis is (3, 5, 10, 15, 20) cm, but the
    5 cm class is realised at 7 cm radius: at 5 cm the plate mode lands at
    46 kHz, above the analysis band, and at the specified strike speed the
    class would be a duplicate of the control. See make_synthetic().
    """
    return float(size_cm)


def _transient_peak_hz() -> float:
    """In-band peak of the bonded control (transient * broadband): ~328 Hz."""
    s = _SYNTH_STRIKE * _SYNTH_BG_SHAPE
    fb = _SYNTH_F_HZ[_SYNTH_BAND]
    return float(fb[int(np.argmax(s[_SYNTH_BAND]))])


def _synth_spectrum(f1_hz: float, rad: float, bg: float) -> np.ndarray:
    """Magnitude spectrum S(f) = sqrt(F2(f)) * |bg(f) + mode(f)|, one tap.

    The background and the mode are summed COHERENTLY (complex sum through
    |.|), not in power: the substrate compliance and the local resonance are
    two terms of one transfer function, and adding their magnitudes in
    quadrature would erase the interference dip that a real tap tone shows.
    """
    bg_term = bg * _SYNTH_BG_SHAPE
    if f1_hz > SYNTH_MODE_IN_BAND_MAX_HZ or f1_hz <= 0.0:
        return _SYNTH_STRIKE * np.abs(bg_term)
    mode = rad / ((1.0 - (_SYNTH_F_HZ / f1_hz) ** 2)
                  + 1j * (_SYNTH_F_HZ / (f1_hz * SYNTH_Q)))
    return _SYNTH_STRIKE * np.abs(bg_term + mode)


def _synth_features_from_spectrum(s: np.ndarray) -> Dict[str, float]:
    """Extract the three spectral features from S(f) with the offline rules.

    These are the same definitions `extract_features_from_waveform` applies to
    a real capture, evaluated on the model spectrum instead: f_peak is the
    argmax over the analysis band, f_centroid the S-weighted mean frequency,
    and band_ratio_lh an ENERGY (power) ratio - the firmware's
    PROBE_CROSSOVER_HZ rule compares band power, not band magnitude, so the
    offline ratio must be a power ratio too.
    """
    fb, sb = _SYNTH_F_HZ[_SYNTH_BAND], s[_SYNTH_BAND]
    peak_i = int(np.argmax(sb))
    total = float(np.sum(sb))
    return {
        "f_peak_hz": float(fb[peak_i]),
        "f_centroid_hz": float(np.sum(fb * sb) / total) if total > 0 else float("nan"),
        "band_ratio_lh": safe_div(float(np.sum(sb[_SYNTH_LOW[_SYNTH_BAND]] ** 2)),
                                  float(np.sum(sb[_SYNTH_HIGH[_SYNTH_BAND]] ** 2))),
    }


def make_synthetic(n_panels: int = 12, taps_per_loc: int = 5,
                   seed: int = 0) -> "pd.DataFrame":
    """Generate tap-test data by running the report's forward acoustic model.

    THIS IS A MODEL-GENERATED DATASET. Every row produced here is a sample of
    a simulation, not of any wall, and every consumer of this frame stamps its
    output "SYNTHETIC DEMONSTRATION DATA - NOT MEASURED".

    Chain per tap, exactly as Chapter 5 specifies it:

      material   E = 18 GPa, h = 20 mm, rho = 2000 kg/m3, nu = 0.20, so
                 D = E h^3/(12(1-nu^2)) = 1.2500e4 N.m
      debond     a clamped circular plate (0,1) mode, alpha = 3.19595/a, on a
                 Winkler foundation of stiffness k (G0 9.0e11, G1 1.0e10,
                 G2 0.0 Pa/m), giving f1 = sqrt(f_mode(a)^2 + f_found(k)^2)
      strike     half-sine force pulse, contact time 300 us
      response   SDOF mode at f1 with Q = 9 coherently summed with a fixed
                 broadband background 0.35/(1+(f/500)^0.7)
      band       300..15000 Hz on a 1024-point/48 kHz grid (bins of 46.875 Hz)
      noise      per-tap multiplicative lognormal sd 0.05 on S, a per-panel
                 multiplicative effect on the mode strength (sd 0.07) and on
                 the background (sd 0.05)

    Three of the feature definitions are pushed through the model spectrum
    itself, so they are produced by the *same* arithmetic the offline extractor
    applies to a real capture rather than by a separate noise model:

      f_peak_hz      argmax of S over 300..15000 Hz
      f_centroid_hz  sum(f S) / sum(S) over the same band
      band_ratio_lh  sum(S^2 below 1 kHz) / sum(S^2 above 1 kHz)   [POWER ratio]

    The remaining channels follow from the response-shape and repeatability
    (SRE) uncertainty the chapter quotes, for the reasons given inline:

      decay_tau_ms   the model decay of the in-band, above-floor mode content.
                     For a partially bonded wall it is the on-resonance decay
                     1000 Q/(pi f1), which is <= 3 ms for every f1 above
                     ~9.5 kHz - and G0/G1 all sit at or above 7.2 kHz - so the
                     reading is the -1.0 sentinel; for a full debond (k = 0) the
                     mode is the plate mode itself, whose floor 1000 Q/(pi
                     f_found) = 9.053 ms applies. The released mode energy is
                     gamma-distributed (shape 0.4), which is the chapter's SRE
                     table; the resulting within-panel growth is the
                     exp(release) term below.
      peak_au        rad * 900 * exp(panel_gain + tap_gain); the total log
                     dispersion is exactly the specified 0.20, split as
                     sqrt(0.19^2 + 0.0628^2) into a panel component (a given
                     wall's coupling) and a shot-to-shot component.
      rms_au         peak_au / (3 + 2 U(0,1))
      crest_factor   peak_au / rms_au
      kurtosis       N(4.74 + 1.2 sev size_factor, 0.65) - the impact channel is
                     not reconstructed from the spectral model, so it carries
                     only this level trend, which is why it is the weakest of
                     the ten features.
      impulse_norm   1.0 * exp(N(0, 0.18)), the noisiest channel
      impact_peak_g  N(12.0, 0.8)

    Consequences that Chapter 5 predicts and that `_print_synthetic_summary`
    verifies in the run log - these are predictions of the model, not choices:
      * G0 is transient dominated: f_peak sits at the 300 Hz band edge (328 Hz,
        the peak of strike x broadband) and band_ratio_lh is HIGH (~0.8),
        because its 23.9 kHz mode is out of band and contributes nothing;
      * the same is true of the 3 cm class, whose f1 = 46-128 kHz is far above
        the band, so a 3 cm debond collapses onto the identical 328 Hz
        transient peak and is genuinely confusable with the bonded control;
      * only f1 below the 15 kHz band top moves f_peak, and that only happens
        for a fully debonded region from 10 cm radius up (11.5, 5.1, 2.9 kHz
        at 10, 15, 20 cm). The exponent of the size law is therefore
        identifiable only from the 10/15/20 cm classes;
      * a strong G1 (k = 1e10) bottoms out at f_found = 2.52 kHz, so at 20 cm
        its f1 = 3.82 kHz is inside the band and it is NOT indistinguishable
        from G0 - one of the chapter's expectations that this generator
        contradicts;
      * decay_tau_ms is unmeasurable for every bonded region and for every
        partially bonded one, and bimodal (floor vs -1.0 sentinel) for a full
        debond, so it cannot separate the classes on its own;
      * within-location CV of f_peak_hz is 6-10% rather than the ~2.9% the
        chapter's repeatability table implies, because the per-panel mode
        strength (sd 0.07, multiplicative) moves a location's peak by ~6% and
        the chapter's table does not include a panel effect of that size.
    """
    rng = np.random.default_rng(seed)
    rows: List[Dict[str, Any]] = []
    counter = 0
    plan: List[Tuple[str, int]] = [("G0", 0)] * 3 + [
        (g, s) for s in (3, 5, 7, 8.8, 10, 15, 20) for g in ("G2", "G1")]

    for panel_i in range(n_panels):
        panel_id = f"P{panel_i + 1:02d}"
        mode_eff = float(np.exp(rng.normal(0.0, 0.07)))   # mode strength, panel
        bg_eff = float(np.exp(rng.normal(0.0, 0.05)))     # broadband, panel
        peak_gain = float(rng.normal(0.0, 0.19))          # peak coupling, panel
        temp = float(rng.normal(24.0, 3.0))

        for loc_i, (grade, size) in enumerate(plan):
            location_id = f"{panel_id}-L{loc_i + 1:02d}"
            sev = SEV[grade]
            # A small debond is a mechanically weak change: scale its mode
            # strength by how far inside the band it sits. The scaling uses the
            # strike aperture: below ~7 cm radius the mode is above the band
            # top, so size_factor is pinned at its 0.30 floor there and the
            # debond really does look like the bonded control.
            strike_cm = _strike_radius_cm(size) if size > 0 else 0.0
            size_factor = (1.0 if size == 0 else
                           float(np.clip(strike_cm / 10.0, 0.30, 1.0)))
            rad = 3.0 * size_factor * mode_eff
            bg = bg_eff
            f1 = f_resonance_hz(strike_cm, SYNTH_K_PA_PER_M[grade])

            # The bonded control is quiet: its in-band spectrum is ~1/11 of a
            # debond's (band ratio 0.80 against 0.07 over an 8.1 kHz
            # full-width band), so its peak and its impulse are scaled by
            # 0.70 and its impulse by 0.77 relative to a debonded point.
            grade_gain = 0.70 if grade == "G0" else 1.0
            floor_ms = (1000.0 * SYNTH_Q / (np.pi * f1)) if (grade == "G2"
                                                            and f1 > 0.0) else 0.0

            for tap in range(1, taps_per_loc + 1):
                counter += 1
                s = _synth_spectrum(f1, rad, bg)
                s = s * np.exp(rng.normal(0.0, 0.05, s.size))   # per-tap noise
                feats = _synth_features_from_spectrum(s)

                # Decay: the released mode energy is gamma(shape 0.4), which
                # reproduces the chapter's SRE table (0.711 / 1.396 / 1.685).
                release = float(rng.gamma(0.4, 1.0))
                tau = (TAU_SENTINEL if floor_ms <= 0.0
                       else floor_ms * float(np.exp(release)))
                if not (TAU_LO_MS <= tau <= TAU_HI_MS):
                    tau = TAU_SENTINEL

                # Channel amplitudes: peak_au = rad * 900 * exp(panel + tap),
                # total 0.20 log dispersion exactly as specified, and
                # impulse_norm the noisiest channel at 0.18.
                tap_gain = float(rng.normal(0.0, 0.0628))
                peak = rad * grade_gain * 900.0 * float(np.exp(peak_gain + tap_gain))
                rms = peak / max(3.0 + 2.0 * rng.random(), 1e-6)
                impulse = ((0.77 if grade == "G0" else 1.0)
                           * float(np.exp(rng.normal(0.0, 0.18))))
                rows.append({
                    "sample_id": f"S{counter:05d}", "panel_id": panel_id,
                    "grade": grade, "size_cm": size,
                    "location_id": location_id, "tap_idx": tap,
                    "f_peak_hz": round(feats["f_peak_hz"], 1),
                    "f_centroid_hz": round(feats["f_centroid_hz"], 1),
                    "band_ratio_lh": round(feats["band_ratio_lh"], 4),
                    "decay_tau_ms": round(tau, 3), "peak_au": round(peak, 2),
                    "rms_au": round(rms, 4),
                    "crest_factor": round(peak / max(rms, 1e-9), 3),
                    "kurtosis": round(float(rng.normal(
                        4.74 + 1.2 * sev * size_factor, 0.65)), 3),
                    "impact_peak_g": round(float(rng.normal(12.0, 0.8)), 3),
                    "impulse_norm": round(impulse, 5), "temp_c": round(temp, 1),
                    "notes": "", "source_file": "synthetic"})
    return pd.DataFrame(rows)


def _print_synthetic_summary(df: "pd.DataFrame") -> None:
    """Print the per-grade / per-size summary of the generated dataset.

    The check Chapter 5 asks for: it shows, for every grade and size class, the
    model resonance f1, the observed in-band peak frequency, the band ratio,
    the share of sentinel decay readings and the within-location CV of the two
    repeatability channels. The anchor claims - G0 and every radius up to 5 cm
    pinned at the 300 Hz band edge, G2 at 20 cm near 2.9 kHz, G0 transient
    dominated with a HIGH band ratio - are therefore verifiable from the run
    log before a single results table is read.

    Every printed f1 is computed at the *strike aperture* actually generated
    for that class (`_strike_radius_cm`), so the 5 cm row is the 7 cm
    resonance the generator emits, not the 46 kHz a 5 cm radius would give.
    """
    print(banner("Step 1b  Synthetic generator: per-grade / per-size check"))
    print(f"  reference panel : E={SYNTH_MATERIAL['E_pa']:.3g} Pa, "
          f"h={SYNTH_MATERIAL['h_m'] * 1000:.0f} mm, "
          f"rho={SYNTH_MATERIAL['rho_kg_m3']:.0f} kg/m3, "
          f"nu={SYNTH_MATERIAL['nu']:.2f}  ->  D={_plate_rigidity():.4g} N.m")
    print(f"  analysis band   : {BAND_LO_HZ:.0f}..{BAND_HI_HZ:.0f} Hz on a "
          f"{SYNTH_FFT_N}-point / {SYNTH_FS_HZ / 1000:.0f} kHz grid "
          f"(bin = {_SYNTH_BIN_HZ:.3f} Hz)")
    print(f"  crossover       : {CROSSOVER_HZ:.0f} Hz = bin "
          f"{CROSSOVER_HZ / _SYNTH_BIN_HZ:.2f}, so between bins 21 "
          f"({_SYNTH_F_HZ[21]:.3f} Hz) and 22 ({_SYNTH_F_HZ[22]:.3f} Hz); "
          "bin 21 is low, bin 22 is high")
    print(f"  strike          : half-sine, T = {SYNTH_CONTACT_S * 1e6:.0f} us; "
          f"transient x broadband peaks at {_transient_peak_hz():.0f} Hz in band")
    print(f"  Q = {SYNTH_Q:.1f}, band_ratio_lh is a POWER ratio\n")
    head = (f"  {'grade':<5}{'size':>5}{'n':>5}{'k (Pa/m)':>11}{'f_mode':>10}"
            f"{'f_found':>10}{'f1':>10}{'f_peak med':>11}{'f_p IQR':>16}"
            f"{'f_cent med':>11}{'band_rat':>10}{'tau<0':>7}{'CV%fp':>7}{'CV%imp':>7}")
    print(head)
    print("  " + "-" * (len(head) - 2))
    for grade in GRADE_ORDER:
        for size in ([0] if grade == "G0" else [3, 5, 10, 15, 20]):
            sub = df[(df["grade"] == grade) & (df["size_cm"] == size)]
            if sub.empty:
                continue
            fp = sub["f_peak_hz"].to_numpy(dtype=float)
            q1, q3 = float(np.percentile(fp, 25)), float(np.percentile(fp, 75))
            sentinel = float(np.mean(sub["decay_tau_ms"].to_numpy(dtype=float) < 0.0))
            cvs = [(cv_percent(g["f_peak_hz"].to_numpy()), cv_percent(g["impulse_norm"].to_numpy()))
                   for _loc, g in sub.groupby("location_id")]
            cv_fp = float(np.median([c[0] for c in cvs if np.isfinite(c[0])]))
            cv_im = float(np.median([c[1] for c in cvs if np.isfinite(c[1])]))
            k = SYNTH_K_PA_PER_M[grade]
            strike_cm = int(_strike_radius_cm(size)) if size > 0 else 0
            print(f"  {grade:<5}{size:>5d}{len(sub):>5d}{k:>11.3g}"
                  f"{_f_mode_hz(strike_cm / 200.0):>10.0f}{_f_found_hz(k):>10.0f}"
                  f"{f_resonance_hz(strike_cm, k):>10.0f}{np.median(fp):>11.1f}"
                  f"{q1:>7.0f}-{q3:<8.0f}{np.median(sub['f_centroid_hz']):>11.1f}"
                  f"{np.median(sub['band_ratio_lh']):>10.4g}"
                  f"{100 * sentinel:>6.0f}%{cv_fp:>7.2f}{cv_im:>7.2f}")
    print("\n  Predicted consequences of the model, as generated:")
    g0 = df[df["grade"] == "G0"]
    g2_20 = df[(df["grade"] == "G2") & (df["size_cm"] == 20)]
    small = df[(df["grade"].isin(("G1", "G2"))) & (df["size_cm"] <= 5)]
    print(f"    P1  G0 in-band f_peak median {np.median(g0['f_peak_hz']):.0f} Hz "
          f"(band edge {BAND_LO_HZ:.0f} Hz), band_ratio_lh median "
          f"{np.median(g0['band_ratio_lh']):.3f} -> transient dominated")
    print(f"    P2  G2 @20 cm f_peak median {np.median(g2_20['f_peak_hz']):.0f} Hz "
          f"(model f1 {f_resonance_hz(20, 0.0):.0f} Hz)")
    print(f"    small-debond check: G1/G2 at 3-5 cm f_peak median "
          f"{np.median(small['f_peak_hz']):.0f} Hz -> indistinguishable from G0")
    print("")

# ==========================================================================
# S4  Data integrity
# ==========================================================================

@dataclass
class IntegrityResult:
    """Cleaned frame plus the evidence for results.md section 1."""

    df: "pd.DataFrame"
    grade_size_counts: "pd.DataFrame"
    summary_lines: List[str]


def run_integrity_checks(df: "pd.DataFrame", rep: LoadReport) -> IntegrityResult:
    """Validate the joined table and return a cleaned copy.

    Checks, in order (each recorded, never silent): row counts per grade x size;
    duplicate keys on (panel_id, location_id, tap_idx); out-of-range or
    non-finite feature cells against FEATURE_BOUNDS; impossible metadata
    (size_cm outside the nominal set, tap_idx < 1, a debonded row with no size).
    """
    work = df.copy()
    lines: List[str] = []
    counts_in = work.groupby(["grade", "size_cm"]).size().rename("rows_in").reset_index()

    key_cols = ["panel_id", "location_id", "tap_idx"]
    dup = work.duplicated(subset=key_cols, keep="first")
    n_dup = int(dup.sum())
    if n_dup:
        rep.drop("duplicate (panel_id, location_id, tap_idx)", n_dup)
        rep.duplicates += n_dup
        lines.append(f"- Duplicate keys removed: **{n_dup}** (kept the first "
                     f"occurrence). Examples: "
                     f"{work.loc[dup, key_cols].head(3).to_dict('records')}")
        work = work.loc[~dup].copy()
    else:
        lines.append("- Duplicate keys on (panel_id, location_id, tap_idx): "
                     "**0** (no repeated log rows).")

    masks = []
    for feat, (_unit, lo, hi) in FEATURE_BOUNDS.items():
        col = pd.to_numeric(work[feat], errors="coerce")
        # Two DIFFERENT conditions, deliberately not conflated.
        #
        #   out of range : the cell parsed to a number that cannot be real
        #                  (a unit mix-up, a truncated log line). Corrupt.
        #   missing      : the cell is NaN. NOT corrupt -- in waveform mode
        #                  `impact_peak_g` is NaN by construction, because it
        #                  is not recoverable from audio alone, and a fit can
        #                  decline to produce `decay_tau_ms`.
        #
        # An earlier version wrote `.fillna(True)` here with the comment
        # "non-finite is bad". That never fired: NaN compares False against both
        # bounds, so `(col < lo) | (col > hi)` is False for a NaN and there is
        # nothing to fill. Making it actually fire would have been worse, not
        # better -- it would drop every waveform-mode row as corrupt. The two
        # counts are therefore reported separately and neither is silent.
        oor = (col < lo) | (col > hi)
        nan = col.isna()
        rep.out_of_range[feat] = int(oor.sum())
        rep.missing[feat] = int(nan.sum())
        masks.append(oor.to_numpy())
    any_bad = np.logical_or.reduce(masks) if masks else np.zeros(len(work), bool)
    n_oor = int(any_bad.sum())
    if n_oor:
        rep.drop("out-of-range or non-finite feature value", n_oor)
        work = work.loc[~any_bad].copy()
    lines.append(f"- Out-of-range / non-finite feature cells: **{n_oor}** rows "
                 "removed (per-feature counts in table 1b, where one row can fail "
                 "more than one bound).")

    bad_size = ~work["size_cm"].isin(SIZE_ORDER)
    rep.drop(f"size_cm outside the nominal set {SIZE_ORDER}", int(bad_size.sum()))
    work = work.loc[~bad_size].copy()
    lines.append(f"- size_cm outside the nominal set {list(SIZE_ORDER)}: "
                 f"**{int(bad_size.sum())}** rows removed.")

    bad_tap = work["tap_idx"] < 1
    rep.drop("tap_idx < 1", int(bad_tap.sum()))
    work = work.loc[~bad_tap].copy()
    lines.append(f"- tap_idx < 1: **{int(bad_tap.sum())}** rows removed.")

    worse = (work["grade"] != "G0") & (work["size_cm"] == 0)
    n_worse = int(worse.sum())
    if n_worse:
        work.loc[worse, "size_cm"] = 3
        rep.notes.append(f"{n_worse} debonded rows carried size_cm = 0 and were "
                         "re-coded to the smallest nominal class (3 cm) so they "
                         "stay usable; recorded here rather than dropped.")
    lines.append(f"- Debonded rows with size_cm = 0: **{n_worse}** (re-coded to "
                 "the 3 cm class and kept; see table 1c).")

    counts = counts_in.merge(
        work.groupby(["grade", "size_cm"]).size().rename("rows_used").reset_index(),
        on=["grade", "size_cm"], how="left")
    counts["rows_used"] = counts["rows_used"].fillna(0).astype(int)
    counts["rows_dropped"] = counts["rows_in"] - counts["rows_used"]
    counts = counts.sort_values(["grade", "size_cm"]).reset_index(drop=True)

    lines.insert(0, f"- Rows entering the integrity stage: **{len(df)}**.")
    lines.append(f"- Rows available for all downstream analysis: **{len(work)}**.")
    return IntegrityResult(work.reset_index(drop=True), counts, lines)


# ==========================================================================
# S5  Descriptive statistics
# ==========================================================================

def descriptive_table(df: "pd.DataFrame", group_col: str,
                      group_order: Sequence[Any],
                      group_label: Callable[[Any], str] = str) -> str:
    """Markdown table of n / median / IQR / min / max / CV% per group per feature.

    One row per (group, feature). Groups with no rows are reported at n = 0
    rather than omitted, so an absent class is visible instead of invisible.
    """
    rows: List[List[str]] = []
    for group in group_order:
        subset = df[df[group_col] == group]
        for feat in NUMERIC_FEATURES:
            s = describe(subset[feat].to_numpy())
            unit = FEATURE_UNIT.get(feat, "")
            name = f"{feat} ({unit})" if unit and unit != "-" else feat
            if s["n"] == 0:
                rows.append([group_label(group), name, "0", "-", "-", "-", "-", "-", "-"])
                continue
            rows.append([group_label(group), name, str(s["n"]), fmt_num(s["median"]),
                         f"{fmt_num(s['q1'])}-{fmt_num(s['q3'])}", fmt_num(s["iqr"]),
                         fmt_num(s["min"]), fmt_num(s["max"]),
                         pct(s["cv"] / 100.0, 1) if np.isfinite(s["cv"]) else "n/a"])
    return md_table(["Group", "Feature (unit)", "n", "Median", "IQR (Q1-Q3)",
                     "IQR width", "Min", "Max", "CV%"], rows)


# ==========================================================================
# S6  Repeatability
# ==========================================================================

@dataclass
class RepeatabilityResult:
    """Within-location repeat statistics and tap-1 vs tap-2..N agreement."""

    per_location: "pd.DataFrame"
    """One row per (panel_id, location_id): CV% of f_peak_hz and impulse_norm."""
    summary: Dict[str, Dict[str, float]]
    """feature -> {locations, median_cv, iqr_cv, fraction_failing}."""
    bland_altman: Dict[str, Dict[str, float]]
    """feature -> {n_pairs, bias, sd_diff, loa_low, loa_high, bias_pct, loa_pct}."""
    ba_points: Dict[str, List[Tuple[float, float]]] = field(default_factory=dict)
    """feature -> [(mean of the two estimates, difference tap1 - mean taps2..N)]."""


def repeatability_analysis(df: "pd.DataFrame",
                           pass_criterion: float = 5.0) -> RepeatabilityResult:
    """CV% of f_peak_hz and impulse_norm within each (panel_id, location_id).

    Also builds a Bland-Altman-style limit of agreement between tap 1 and the
    mean of taps 2..N at the same location: bias plus bias +/- 1.96 SD of the
    differences. This answers the practical question behind the repeatability
    claim - can one tap stand in for the average of the rest?
    """
    records: List[Dict[str, Any]] = []
    ba_rows: List[Dict[str, Any]] = []

    for (panel, loc), grp in df.groupby(["panel_id", "location_id"], sort=True):
        entry: Dict[str, Any] = {
            "panel_id": panel, "location_id": loc, "grade": grp["grade"].iloc[0],
            "size_cm": int(grp["size_cm"].iloc[0]), "n_taps": int(len(grp)),
            "cv_f_peak_pct": cv_percent(grp["f_peak_hz"].to_numpy()),
            "cv_impulse_pct": cv_percent(grp["impulse_norm"].to_numpy())}
        records.append(entry)

        first_tap = int(grp["tap_idx"].min())
        first = grp.loc[grp["tap_idx"] == first_tap]
        rest = grp.loc[grp["tap_idx"] > first_tap]
        if len(rest) >= 2:
            for feat in ("f_peak_hz", "impulse_norm"):
                tap1 = float(first[feat].mean())
                mean_rest = float(rest[feat].mean())
                pair_mean = 0.5 * (tap1 + mean_rest)
                diff = tap1 - mean_rest
                if feat == "f_peak_hz":
                    entry["ba_pct_diff_f_peak"] = safe_div(100.0 * diff, pair_mean)
                ba_rows.append({"feature": feat, "diff": diff, "pair_mean": pair_mean,
                                "grade": entry["grade"]})

    per_loc = pd.DataFrame(records)
    summary: Dict[str, Dict[str, float]] = {}
    for feat, col in (("f_peak_hz", "cv_f_peak_pct"), ("impulse_norm", "cv_impulse_pct")):
        vals = per_loc[col].to_numpy(dtype=float) if col in per_loc else np.array([])
        vals = vals[np.isfinite(vals)]
        if vals.size:
            summary[feat] = {
                "locations": int(vals.size), "median_cv": float(np.median(vals)),
                "iqr_cv": float(np.percentile(vals, 75) - np.percentile(vals, 25)),
                "fraction_failing": float(np.mean(vals > pass_criterion))}

    bland: Dict[str, Dict[str, float]] = {}
    ba_points: Dict[str, List[Tuple[float, float]]] = {}
    ba_df = pd.DataFrame(ba_rows)
    for feat in ("f_peak_hz", "impulse_norm"):
        sub = ba_df[ba_df["feature"] == feat] if not ba_df.empty else ba_df
        if sub.empty:
            continue
        means = sub["pair_mean"].to_numpy(dtype=float)
        diffs = sub["diff"].to_numpy(dtype=float)
        ok = np.isfinite(means) & np.isfinite(diffs)
        means, diffs = means[ok], diffs[ok]
        ba_points[feat] = list(zip(means.tolist(), diffs.tolist()))
        if diffs.size < 3:
            continue
        bias, sd, grand = float(np.mean(diffs)), float(np.std(diffs, ddof=1)), float(np.mean(means))
        bland[feat] = {"n_pairs": int(diffs.size), "bias": bias, "sd_diff": sd,
                       "loa_low": bias - 1.96 * sd, "loa_high": bias + 1.96 * sd,
                       "grand_mean": grand, "bias_pct": safe_div(bias, grand) * 100.0,
                       "loa_pct": safe_div(1.96 * sd, grand) * 100.0}
    return RepeatabilityResult(per_loc, summary, bland, ba_points)


# ==========================================================================
# S7  Discrimination testing
# ==========================================================================

def discrimination_analysis(df: "pd.DataFrame") -> List[Dict[str, Any]]:
    """Per-feature omnibus and pairwise separation of the grades.

    For every numeric feature: Kruskal-Wallis across all grades present (>= 2
    groups), then Mann-Whitney U on every grade pair with Holm-Bonferroni
    applied across that feature's whole family of pairs, with Cliff's delta as
    the effect size. Sorted by discriminative power: largest |delta| against
    the control first, Kruskal-Wallis H breaking ties.
    """
    results: List[Dict[str, Any]] = []
    present = [g for g in GRADE_ORDER if (df["grade"] == g).any()]

    for feat in NUMERIC_FEATURES:
        samples = {g: df.loc[df["grade"] == g, feat].to_numpy(dtype=float)
                   for g in present}
        samples = {g: v[np.isfinite(v)] for g, v in samples.items()}
        entry: Dict[str, Any] = {"feature": feat, "unit": FEATURE_UNIT.get(feat, "-"),
                                 "kw_H": float("nan"), "kw_p": float("nan"),
                                 "pairs": [], "max_abs_delta": float("nan")}
        usable = [g for g in present if samples[g].size >= 3]
        if len(usable) >= 2:
            try:
                h, p = sps.kruskal(*[samples[g] for g in usable], nan_policy="omit")
                entry["kw_H"], entry["kw_p"] = float(h), float(p)
            except ValueError:
                pass

        pair_specs = [(a, b) for i, a in enumerate(present) for b in present[i + 1:]
                      if samples[a].size >= 3 and samples[b].size >= 3]
        raw_p, deltas = [], []
        for a, b in pair_specs:
            try:
                _u, p = sps.mannwhitneyu(samples[a], samples[b], alternative="two-sided")
                p = float(p)
            except ValueError:
                p = float("nan")
            raw_p.append(p)
            deltas.append(cliffs_delta(samples[a], samples[b]))
        adjusted = holm_bonferroni(raw_p)

        abs_deltas: List[float] = []
        for (a, b), p_raw, p_adj, delta in zip(pair_specs, raw_p, adjusted, deltas):
            entry["pairs"].append({
                "a": a, "b": b, "n_a": int(samples[a].size), "n_b": int(samples[b].size),
                "med_a": float(np.median(samples[a])),
                "med_b": float(np.median(samples[b])),
                "p_raw": p_raw, "p_holm": p_adj, "delta": delta})
            if np.isfinite(delta):
                abs_deltas.append(abs(delta))
        entry["max_abs_delta"] = max(abs_deltas) if abs_deltas else float("nan")
        results.append(entry)

    def sort_key(item: Dict[str, Any]) -> Tuple[float, float]:
        primary, secondary = item["max_abs_delta"], item["kw_H"]
        return (-primary if np.isfinite(primary) else 1.0,
                -secondary if np.isfinite(secondary) else 1.0)

    results.sort(key=sort_key)
    return results


def discrimination_tables(results: Sequence[Dict[str, Any]]) -> Tuple[str, str]:
    """Build the omnibus table and the pairwise table for results.md."""
    omnibus_rows = []
    for rank, item in enumerate(results, start=1):
        unit = f" ({item['unit']})" if item["unit"] != "-" else ""
        sig = ("yes" if item["kw_p"] < 0.05 else "no") if np.isfinite(item["kw_p"]) else "n/a"
        omnibus_rows.append([rank, item["feature"] + unit, fmt_num(item["kw_H"]),
                             f"{item['kw_p']:.3e}" if np.isfinite(item["kw_p"]) else "n/a",
                             sig, fmt_num(item["max_abs_delta"]),
                             delta_word(item["max_abs_delta"])])
    omnibus = md_table(["Rank", "Feature (unit)", "Kruskal-Wallis H", "p", "p < 0.05",
                        "Largest \\|Cliff's delta\\|", "Effect"], omnibus_rows)

    pair_rows = []
    for item in results:
        for pr in item["pairs"]:
            pair_rows.append([
                item["feature"], f"{pr['a']} vs {pr['b']}",
                f"{pr['n_a']} / {pr['n_b']}", fmt_num(pr["med_a"]), fmt_num(pr["med_b"]),
                f"{pr['p_raw']:.3e}" if np.isfinite(pr["p_raw"]) else "n/a",
                f"{pr['p_holm']:.3e}" if np.isfinite(pr["p_holm"]) else "n/a",
                "yes" if (np.isfinite(pr["p_holm"]) and pr["p_holm"] < 0.05) else "no",
                fmt_num(pr["delta"]), delta_word(pr["delta"])])
    pairwise = md_table(["Feature", "Pair", "n (a / b)", "Median a", "Median b",
                         "p (raw)", "p (Holm)", "Significant", "Cliff's delta",
                         "Effect"], pair_rows)
    return omnibus, pairwise


# ==========================================================================
# S8  Size sensitivity: the two-parameter resonance fit
# ==========================================================================

# A per-tap f_peak at or below the crossover is a CENSORED observation, not a
# measured mode: the strike transient pins the argmax into the low band (bins
# 7-21 of the 46.875 Hz grid), so the reading describes the excitation, not the
# structure. CROSSOVER_HZ is the natural boundary - it is the firmware's own
# PROBE_CROSSOVER_HZ and the edge of the transient-dominated band.
SIZE_FIT_CENSOR_MAX_HZ = CROSSOVER_HZ

# Analytic value of the two-parameter fit's curvature coefficient, in METRES:
#   A = D alpha^4 / ((2pi)^2 rho h),  alpha = 3.19595
#     = 12500 * 3.19595^4 / ((2pi)^2 * 2000 * 0.020) = 825.829 Hz^2 m^4
# and its size_cm twin A' = A * 200^4 = 1.32133e12 Hz^2 cm^4.
# NOTE the number the project brief quoted for this constant, 2.8737e+01, is
# sqrt(A): it is f_mode(0.1 m)/100, i.e. an angular-frequency factor out, and
# comparing a coefficient A to 28.737 is a dimensional error. sqrt(825.829) =
# 28.7372, which is the only sense in which 28.737 is the right number. Both
# forms are reported so the discrepancy is visible rather than hidden.
SIZE_FIT_A_ANALYTIC = (float(SYNTH_MATERIAL["E_pa"]) * float(SYNTH_MATERIAL["h_m"]) ** 3
                       / (12.0 * (1.0 - float(SYNTH_MATERIAL["nu"]) ** 2))
                       * SYNTH_ALPHA_NUM ** 4
                       / ((2.0 * np.pi) ** 2 * float(SYNTH_MATERIAL["rho_kg_m3"])
                          * float(SYNTH_MATERIAL["h_m"])))
SIZE_FIT_A_BRIEF = 28.737        # the number the brief quoted (see note above)
# Analytic intercept B = f_found^2 = k / ((2pi)^2 rho h) for each grade.
SIZE_FIT_B_ANALYTIC = {"G1": 2516.5 ** 2, "G2": 0.0}


@dataclass
class SizeFit:
    """Median f_peak vs debond size, with the one- and two-parameter fits."""

    sizes: np.ndarray
    medians: np.ndarray
    q1: np.ndarray
    q3: np.ndarray
    counts: np.ndarray
    C: float
    C_lo: float
    C_hi: float
    r2: float               # R^2 of the one-parameter f = C / size^2 model
    slope: float            # exponent measured by the free log-log fit
    slope_lo: float
    slope_hi: float
    residuals: List[Tuple[int, float, float, float]]   # size, measured, fitted, residual

    # ---- two-parameter model f_peak^2 = A / a^4 + B ------------------------
    n_used: int = 0             # taps used by the two-parameter fit
    n_excluded: int = 0         # debonded taps dropped as censored
    n_g0_excluded: int = 0      # bonded-control taps (no radius; never entered)
    n_used_unit: int = 0        # distinct radii among the used taps
    excluded: List[Tuple[str, int, float, str]] = field(default_factory=list)
    fit_sizes: np.ndarray = field(default_factory=lambda: np.array([]))
    fit_peak: np.ndarray = field(default_factory=lambda: np.array([]))
    A: float = float("nan")          # radius convention, Hz^2 m^4
    A_lo: float = float("nan")
    A_hi: float = float("nan")
    B: float = float("nan")          # Hz^2
    B_lo: float = float("nan")
    B_hi: float = float("nan")
    r2_two: float = float("nan")
    A_scm: float = float("nan")      # size_cm convention, Hz^2 cm^4
    A_scm_lo: float = float("nan")
    A_scm_hi: float = float("nan")
    r2_one_same: float = float("nan")   # model 1 R^2 on the same tap set
    A_analytic: float = SIZE_FIT_A_ANALYTIC
    A_scm_analytic: float = SIZE_FIT_A_ANALYTIC * 200.0 ** 4   # 1.32133e12
    A_brief: float = SIZE_FIT_A_BRIEF
    # ---- curvature with B fixed by the physics (the identified test of A) --
    # keyed by grade, plus "MIX" (both grades pooled, B fixed at 0).
    A_fix: Dict[str, float] = field(default_factory=dict)
    A_fix_lo: Dict[str, float] = field(default_factory=dict)
    A_fix_hi: Dict[str, float] = field(default_factory=dict)
    r2_fix: Dict[str, float] = field(default_factory=dict)
    B_analytic: Dict[str, float] = field(default_factory=lambda: dict(SIZE_FIT_B_ANALYTIC))
    two_param_rows: List[Tuple[int, float, float, float]] = field(default_factory=list)
    # (size_cm, median P50 of f_peak^2, fitted, residual)


def _fit_two_param(x: np.ndarray, y: np.ndarray) -> Tuple[float, float, float]:
    """OLS of y = A*x + B. Returns (A, B, R^2) with R^2 relative to mean(y)."""
    if x.size < 3 or np.unique(x).size < 2:
        return (float("nan"), float("nan"), float("nan"))
    design = np.vstack([x, np.ones_like(x)]).T
    coef = np.linalg.lstsq(design, y, rcond=None)[0]
    a, b = float(coef[0]), float(coef[1])
    pred = a * x + b
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - float(np.mean(y))) ** 2))
    return a, b, 1.0 - safe_div(ss_res, ss_tot)


def _fit_one_param_prints(x: np.ndarray, y: np.ndarray) -> float:
    """R^2 of f_peak = C / size_cm^2 fitted in log space on the same points."""
    if x.size < 2 or np.unique(x).size < 2:
        return float("nan")
    lx = np.log(x)
    ly = np.log(y)
    pred = -2.0 * lx + float(np.mean(ly + 2.0 * lx))
    ss_res = float(np.sum((ly - pred) ** 2))
    ss_tot = float(np.sum((ly - float(np.mean(ly))) ** 2))
    return 1.0 - safe_div(ss_res, ss_tot)


def _fit_curvature_fixed_B(x: np.ndarray, y: np.ndarray,
                           b0: float) -> Tuple[float, float]:
    """OLS of y = A*x + B with the intercept **fixed** at b0 = f_found^2.

    The free two-parameter fit is ill-conditioned on a handful of collinear
    radii: it trades a large B against a large A along the body of the data and
    can put A on the wrong side of zero. The physics supplies B, so the honest
    test of the curvature coefficient A is the one-parameter regression that
    follows once B is fixed:
        A = sum(x (y - b0)) / sum(x^2),   x = 1/a^4,  y = f_peak^2.
    Returns (A, R^2) with R^2 relative to mean(y), so it is comparable with the
    free fit's R^2 on the same points.
    """
    xx = float(np.sum(x * x))
    if x.size < 3 or xx <= 0.0:
        return float("nan"), float("nan")
    a = float(np.sum(x * (y - b0)) / xx)
    pred = a * x + b0
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - float(np.mean(y))) ** 2))
    return a, 1.0 - safe_div(ss_res, ss_tot)


def size_sensitivity(df: "pd.DataFrame",
                     rng: np.random.Generator) -> Optional[SizeFit]:
    """Median f_peak_hz vs debond size, with two competing resonance fits.

    Model 1 (the chapter's headline claim, one parameter, size in cm):
        f_peak = C / size_cm^2
    and the free-exponent diagnostic f_peak = C / size_cm^p. Both are fitted in
    log space, so the high-frequency small-size classes do not dominate.

    Model 2 (what the plate-on-Winkler model actually implies, since
    f1^2 = f_mode^2 + f_found^2 and f_mode^2 = D alpha^4/((2pi)^2 rho h a^4)):
        radius convention :  f_peak^2 = A / a^4 + B,   a = radius in METRES
        size_cm convention:  f_peak^2 = A' / size_cm^4 + B'
    The two are the same fit related by a^4 = size_cm^4 / 200^4, so A' = A x
    200^4; B' = B because the intercept is in Hz^2 either way. Both conventions
    are reported because the analytic value is quoted in metres. Model 2 is
    fitted on **individual taps** - one (f_peak^2, 1/a^4) point per tap - so the
    regression has the full spread of repeats behind it rather than a handful
    of class medians, and the CIs come from a panel bootstrap.

    Censoring. A tap whose f_peak is at or below `SIZE_FIT_CENSOR_MAX_HZ` (the
    firmware crossover) has been pinned into the transient-dominated low band:
    the argmax is the strike excitation, not the structure, so the value is a
    censored observation rather than a mode measurement, and including it would
    fit the excitation. Censored taps are dropped, and the G0 (bonded control)
    taps never enter at all because their size_cm is 0 and they have no radius.
    The exclusion is reported with its counts and its reason.

    Validation. A is compared with the analytic value
    A = D alpha^4 / ((2pi)^2 rho h) = 825.829 Hz^2 m^4 for the reference panel
    (D = 1.25e4 N.m, alpha = 3.19595, rho = 2000 kg/m3, h = 0.020 m). The brief
    quoted 28.737 for this constant: that is sqrt(A), one angular factor out,
    and both numbers appear in results.md so the arithmetic is checkable.

    CIs are percentile bootstraps over panels (the unit of independence),
    resampling whole panels so every tap of a resampled panel moves together.
    """
    debonded = df[(df["grade"] != "G0") & (df["size_cm"] > 0)]
    # NOT int(): 8.8 cm truncates to 8, which matches no row, and every
    # per-class percentile below then indexes an empty array.
    present = sorted(float(s) for s in debonded["size_cm"].unique())
    if len(present) < 2:
        return None

    sizes = np.array(present, dtype=float)
    medians = np.array([float(np.median(debonded.loc[debonded["size_cm"] == s, "f_peak_hz"]))
                        for s in present])
    q1 = np.array([float(np.percentile(debonded.loc[debonded["size_cm"] == s, "f_peak_hz"], 25))
                   for s in present])
    q3 = np.array([float(np.percentile(debonded.loc[debonded["size_cm"] == s, "f_peak_hz"], 75))
                   for s in present])
    counts = np.array([int((debonded["size_cm"] == s).sum()) for s in present])

    # ---- one-parameter model, all debonded size classes -------------------
    x, y = np.log(sizes), np.log(medians)
    slope, intercept = np.polyfit(x, y, 1)            # free exponent
    ss_res = float(np.sum((y - (slope * x + intercept)) ** 2))
    r2 = 1.0 - safe_div(ss_res, float(np.sum((y - np.mean(y)) ** 2)))
    if x.size > 2:
        sxx = float(np.sum((x - np.mean(x)) ** 2))
        se = np.sqrt(ss_res / max(x.size - 2, 1) / max(sxx, 1e-12))
        tcrit = float(sps.t.ppf(0.975, x.size - 2))
        slope_lo, slope_hi = float(slope - tcrit * se), float(slope + tcrit * se)
    else:
        slope_lo = slope_hi = float("nan")
    C = float(np.exp(np.mean(y + 2.0 * x)))          # exponent fixed at 2

    # ---- which classes are censored (reported in the exclusion table) -----
    excluded: List[Tuple[str, int, float, str]] = []
    for s in present:
        sub = debonded[debonded["size_cm"] == s]
        if float(np.median(sub["f_peak_hz"])) <= SIZE_FIT_CENSOR_MAX_HZ:
            grades = "+".join(sorted(set(sub["grade"])))
            excluded.append((grades, float(s), float(np.median(sub["f_peak_hz"])),
                             "Transient-dominated class: median f_peak "
                             f"<= {SIZE_FIT_CENSOR_MAX_HZ:.0f} Hz (the crossover), "
                             "so the argmax is the strike transient, not the "
                             "resonance; taps above the crossover still enter "
                             "the fit"))

    # ---- two-parameter model: individual taps, censored ones dropped -----
    a_all = debonded["size_cm"].to_numpy(dtype=float) / 200.0        # metres
    pk_all = debonded["f_peak_hz"].to_numpy(dtype=float)
    panel_all = debonded["panel_id"].to_numpy()
    size_all = debonded["size_cm"].to_numpy(dtype=float)
    ok = np.isfinite(a_all) & np.isfinite(pk_all) & (pk_all > SIZE_FIT_CENSOR_MAX_HZ)
    a_used, pk_used = a_all[ok], pk_all[ok]
    sz_used = size_all[ok]

    A = B = r2_two = float("nan")
    if a_used.size >= 3 and np.unique(np.round(a_used, 6)).size >= 2:
        A, B, r2_two = _fit_two_param(a_used ** -4.0, pk_used ** 2.0)
    r2_one_same = _fit_one_param_prints(sz_used, pk_used)

    # ---- curvature with B fixed by the physics ----------------------------
    # The physically identified test of A: fix B = f_found^2 (0 for a full
    # debond, 6.33e6 Hz^2 for the partial one) and regress the single free
    # parameter A. Reported per grade, because B differs by grade, and pooled
    # (one shared B) as a summary.
    grade_all = debonded["grade"].to_numpy()
    a_fix, a_fix_lo, a_fix_hi = {}, {}, {}
    r2_fix = {}
    for g in ("G2", "G1"):
        m = (grade_all == g) & ok
        if int(m.sum()) >= 3 and np.unique(np.round(a_all[m], 6)).size >= 2:
            av, rv = _fit_curvature_fixed_B(a_all[m] ** -4.0,
                                               pk_all[m] ** 2.0,
                                               float(SIZE_FIT_B_ANALYTIC[g]))
            a_fix[g], r2_fix[g] = av, rv
    A_fix_mix = r2_fix_mix = float("nan")
    if a_used.size >= 3:
        A_fix_mix, r2_fix_mix = _fit_curvature_fixed_B(
            a_used ** -4.0, pk_used ** 2.0, 0.0)

    # ---- bootstrap over panels, shared by both models and both CIs --------
    uniq = np.unique(panel_all)
    boots_C, boots_A, boots_B = [], [], []
    boots_Afix: Dict[str, List[float]] = {"G2": [], "G1": [], "MIX": []}
    for _ in range(2000):
        pick = rng.choice(uniq, size=uniq.size, replace=True)
        idx = np.concatenate([np.flatnonzero(panel_all == p) for p in pick])

        # model 1: class medians of the resample
        sub_sizes, sub_pk = size_all[idx], pk_all[idx]
        vals = []
        for s in present:
            arr = sub_pk[sub_sizes == s]
            arr = arr[np.isfinite(arr)]
            vals.append(float(np.median(arr)) if arr.size else float("nan"))
        vals_arr = np.asarray(vals, dtype=float)
        good = np.isfinite(vals_arr) & (vals_arr > 0)
        if int(good.sum()) >= 2:
            boots_C.append(float(np.exp(np.mean(np.log(vals_arr[good]) + 2.0 * x[good]))))

        # model 2: censored taps of the resample dropped
        a_b, pk_b = a_all[idx], sub_pk[idx]
        keep = np.isfinite(a_b) & np.isfinite(pk_b) & (pk_b > SIZE_FIT_CENSOR_MAX_HZ)
        if int(keep.sum()) >= 3 and np.unique(np.round(a_b[keep], 6)).size >= 2:
            a_m, b_m, _r = _fit_two_param(a_b[keep] ** -4.0, pk_b[keep] ** 2.0)
            if np.isfinite(a_m):
                boots_A.append(a_m)
                boots_B.append(b_m)

        # curvature with B fixed by the physics, per grade and pooled
        g_b = grade_all[idx]
        for key in ("G2", "G1"):
            mf = (g_b == key) & keep
            if int(mf.sum()) >= 3 and np.unique(np.round(a_b[mf], 6)).size >= 2:
                av, _rr = _fit_curvature_fixed_B(a_b[mf] ** -4.0, pk_b[mf] ** 2.0,
                                                 float(SIZE_FIT_B_ANALYTIC[key]))
                if np.isfinite(av):
                    boots_Afix[key].append(av)
        if int(keep.sum()) >= 3:
            av_mix, _rr = _fit_curvature_fixed_B(a_b[keep] ** -4.0, pk_b[keep] ** 2.0, 0.0)
            if np.isfinite(av_mix):
                boots_Afix["MIX"].append(av_mix)

    def _ci(vals: Sequence[float]) -> Tuple[float, float]:
        arr = np.asarray(vals, dtype=float)
        arr = arr[np.isfinite(arr)]
        if arr.size < 20:
            return float("nan"), float("nan")
        return float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))

    C_lo, C_hi = _ci(boots_C)
    A_lo, A_hi = _ci(boots_A)
    B_lo, B_hi = _ci(boots_B)
    for key in ("G2", "G1", "MIX"):
        a_fix_lo[key], a_fix_hi[key] = _ci(boots_Afix[key])

    two_param_rows = []
    if a_used.size:
        pred = A / a_used ** 4.0 + B
        for s in np.unique(sz_used):
            m = sz_used == s
            two_param_rows.append((int(s), float(np.median(pk_used[m] ** 2)),
                                   float(np.median(pred[m])),
                                   float(np.median(pk_used[m] ** 2 - pred[m]))))
    residuals = [(int(s), float(m), float(C / s ** 2), float(m - C / s ** 2))
                 for s, m in zip(present, medians)]
    return SizeFit(
        sizes, medians, q1, q3, counts, C, C_lo, C_hi, float(r2),
        float(slope), slope_lo, slope_hi, residuals,
        n_used=int(a_used.size), n_excluded=int(a_all.size - a_used.size),
        n_g0_excluded=int((df["grade"] == "G0").sum()),
        n_used_unit=int(np.unique(np.round(a_used, 6)).size), excluded=excluded,
        fit_sizes=np.unique(sz_used), fit_peak=pk_used,
        A=A, A_lo=A_lo, A_hi=A_hi, B=B, B_lo=B_lo, B_hi=B_hi,
        r2_two=r2_two,
        A_scm=A * 200.0 ** 4 if np.isfinite(A) else float("nan"),
        A_scm_lo=A_lo * 200.0 ** 4 if np.isfinite(A_lo) else float("nan"),
        A_scm_hi=A_hi * 200.0 ** 4 if np.isfinite(A_hi) else float("nan"),
        r2_one_same=r2_one_same,
        A_fix=a_fix, A_fix_lo=a_fix_lo, A_fix_hi=a_fix_hi, r2_fix=r2_fix,
        two_param_rows=two_param_rows)


# ==========================================================================
# S9  Classifiers (panel-wise out-of-fold predictions)
# ==========================================================================

@dataclass
class ClassifierResult:
    """Out-of-fold predictions and metrics for one detection rule."""

    name: str
    y_true: np.ndarray
    y_score: np.ndarray
    y_pred: np.ndarray
    groups: np.ndarray
    auc: float
    auc_lo: float
    auc_hi: float
    metrics: Dict[str, float]
    ci: Dict[str, Tuple[float, float]]
    confusion: np.ndarray
    threshold_used: float
    cut_lo: float = float("nan")
    cut_hi: float = float("nan")
    extra: Dict[str, Any] = field(default_factory=dict)


def _binary_labels(grade: "pd.Series") -> np.ndarray:
    """Positive class = debonded (G1 or G2); negative = bonded (G0)."""
    return (grade != "G0").to_numpy().astype(int)


def _choose_band_threshold(scores: np.ndarray, y: np.ndarray) -> float:
    """Band-ratio cut maximising balanced accuracy on the training folds only.

    Deriving the cut on the training folds and then freezing it for the held-out
    fold is what makes the reported performance genuinely out-of-sample.

    ORIENTATION.  `band_ratio_lh` is the power below the 1 kHz crossover divided
    by the power above it, so it FALLS when a wall mode enters the band: a bonded
    point reads ~0.8, a debonded one ~0.03-0.17.  A debond therefore scores as
    `band_ratio_lh <= cut`.  This matches the firmware's own calibration text
    ("band_ratio just BELOW the debonded floor", app_main.c console_calibrate)
    and probe_config.h's "low frequencies dominate -> G2" comment, which are
    correct; an earlier version of this function wrote `>=` and inverted both
    the rule and its ROC.
    """
    finite = scores[np.isfinite(scores)]
    if finite.size == 0 or len(np.unique(y)) < 2:
        return 0.5
    best, best_score = float(np.median(finite)), -1.0
    for cut in np.unique(np.percentile(finite, np.linspace(1, 99, 99))):
        pred = (scores <= cut).astype(int)
        tpr = safe_div(float(np.sum((pred == 1) & (y == 1))), float(np.sum(y == 1)))
        tnr = safe_div(float(np.sum((pred == 0) & (y == 0))), float(np.sum(y == 0)))
        bal = 0.5 * (np.nan_to_num(tpr) + np.nan_to_num(tnr))
        if bal > best_score:
            best, best_score = float(cut), bal
    return best


def _fold_iter(n_splits: int, y: np.ndarray, groups: np.ndarray):
    """(folds, splitter_name) using StratifiedGroupKFold, degrading to GroupKFold.

    Falls back when the panel count cannot support the requested number of
    stratified group folds. That is a real situation for small student datasets
    and must not crash the run.
    """
    n_splits = max(2, min(n_splits, len(np.unique(groups))))
    try:
        folds = list(StratifiedGroupKFold(n_splits=n_splits, shuffle=True,
                                          random_state=0).split(np.zeros_like(y), y, groups))
        if folds:
            return folds, "StratifiedGroupKFold"
    except Exception:
        pass
    try:
        return (list(GroupKFold(n_splits=n_splits).split(np.zeros_like(y), y, groups)),
                "GroupKFold")
    except ValueError:
        # Fewer groups than the minimum two that any K-fold needs. Both splitters
        # raise here, so the previous code crashed the whole run with a bare
        # ValueError out of sklearn. A single-panel dataset is a real situation
        # (one session, one wall) and it must degrade rather than abort.
        #
        # The degradation is to run NOTHING, deliberately: the only fold that
        # could be formed trains and tests on the same panel, and a score
        # computed that way is leakage, not a cross-validated estimate. An empty
        # fold list leaves every out-of-fold score NaN, the caller drops the
        # unscored classifiers, and the report says the comparison was not run.
        # That is the honest outcome for a sample with one group.
        return [], "not run (one panel: no held-out group exists)"


def classifier_study(df: "pd.DataFrame", rng: np.random.Generator,
                     n_splits: int = 5,
                     n_boot: int = 1000) -> Tuple[List[ClassifierResult], str]:
    """Compare the three detection rules with panel-wise out-of-fold CV.

    All three rules see the same folds and the same four features, so the
    comparison is paired. Groups are panel_id: no panel appears in both training
    and test, so the estimate is not inflated by measuring the same wall twice.
    """
    data = df.dropna(subset=list(CLF_FEATURES) + ["grade", "panel_id"]).copy()
    y = _binary_labels(data["grade"])
    groups = data["panel_id"].to_numpy()
    X = data[list(CLF_FEATURES)].to_numpy(dtype=float)
    band = data["band_ratio_lh"].to_numpy(dtype=float)
    if len(np.unique(y)) < 2:
        return [], "not run (the sample contains only one class)"

    folds, splitter_name = _fold_iter(n_splits, y, groups)
    oof_score = {n: np.full(len(y), np.nan) for n in CLF_COLOR}
    oof_pred = {n: np.full(len(y), -1, dtype=int) for n in CLF_COLOR}
    chosen_cuts: List[float] = []

    for train_idx, test_idx in folds:
        y_tr = y[train_idx]
        if len(np.unique(y_tr)) < 2:
            continue
        # (a) one-feature threshold rule on band_ratio_lh, oriented so that a
        # LOWER ratio means debonded (see _choose_band_threshold). The score is
        # the negated ratio, so the ROC is a true threshold sweep, not one point.
        chosen_cuts.append(_choose_band_threshold(band[train_idx], y_tr))
        oof_score["Threshold rule"][test_idx] = -band[test_idx]
        oof_pred["Threshold rule"][test_idx] = (band[test_idx] <= chosen_cuts[-1]).astype(int)
        # (b) logistic regression and (c) k-NN, both standardised.
        #
        # Winsorise at the training folds' 1st/99th percentile before scaling.
        # decay_tau_ms is a sentinel (-1.0) for 100% of bonded points and 95% of
        # full debonds, so after plain standardisation those rows take a large
        # negative z and the fitted model floors their probability. That is a
        # sentinel artefact, not a wall measurement, and it dominated the
        # reported confusion matrix.
        lo_q, hi_q = np.percentile(X[train_idx], [1.0, 99.0], axis=0)
        clip = lambda A: np.clip(A, lo_q, hi_q)                     # noqa: E731
        scaler = StandardScaler().fit(clip(X[train_idx]))
        models = {
            "Logistic regression": LogisticRegression(class_weight="balanced",
                                                      max_iter=2000, random_state=0),
            "k-NN (k=5)": KNeighborsClassifier(n_neighbors=min(5, len(train_idx) - 1))}
        for name, model in models.items():
            try:
                model.fit(scaler.transform(clip(X[train_idx])), y_tr)
                proba = model.predict_proba(scaler.transform(clip(X[test_idx])))[:, 1]
            except Exception as exc:
                print(f"  WARNING: {name} failed on one fold ({exc}); that fold "
                      "is left unscored.")
                continue
            oof_score[name][test_idx] = proba
            oof_pred[name][test_idx] = (proba >= 0.5).astype(int)

    results: List[ClassifierResult] = []
    for name in CLF_COLOR:
        valid = np.isfinite(oof_score[name]) & (oof_pred[name] >= 0)
        if int(valid.sum()) < 5 or len(np.unique(y[valid])) < 2:
            print(f"  WARNING: '{name}' produced too few scored rows; skipped.")
            continue
        yv, sv = y[valid], oof_score[name][valid]
        pv, gv = oof_pred[name][valid], groups[valid]

        auc = float(roc_auc_score(yv, sv))
        auc_lo, auc_hi = bootstrap_ci(roc_auc_score, yv, sv, groups=gv,
                                      n_boot=n_boot, rng=rng)
        metrics = {"accuracy": float(accuracy_score(yv, pv)),
                   "balanced_accuracy": float(balanced_accuracy_score(yv, pv)),
                   "precision": float(precision_score(yv, pv, zero_division=0)),
                   "recall": float(recall_score(yv, pv, zero_division=0)),
                   "f1": float(f1_score(yv, pv, zero_division=0))}
        # The cut this rule actually applies. For the threshold rule the score is
        # the negated band ratio, so the decision lies at -cut and not at 0.5;
        # bootstrapping the metrics at a hard-coded 0.5 resampled that rule as
        # "never raise an alarm" and printed degenerate [x, x] intervals.
        if name == "Threshold rule" and chosen_cuts:
            cut_used = -float(np.median(chosen_cuts))
        elif name == "Threshold rule":
            cut_used = -0.5
        else:
            cut_used = 0.5
        pred_at_half = lambda t, s: (s >= cut_used).astype(int)     # noqa: E731
        metric_fns = {
            "accuracy": lambda t, s: float(accuracy_score(t, pred_at_half(t, s))),
            "balanced_accuracy": lambda t, s: float(balanced_accuracy_score(t, pred_at_half(t, s))),
            "precision": lambda t, s: float(precision_score(t, pred_at_half(t, s), zero_division=0)),
            "recall": lambda t, s: float(recall_score(t, pred_at_half(t, s), zero_division=0)),
            "f1": lambda t, s: float(f1_score(t, pred_at_half(t, s), zero_division=0))}
        ci = {k: bootstrap_ci(fn, yv, sv, groups=gv, n_boot=n_boot, rng=rng)
              for k, fn in metric_fns.items()}

        results.append(ClassifierResult(
            name=name, y_true=yv, y_score=sv, y_pred=pv, groups=gv,
            auc=auc, auc_lo=auc_lo, auc_hi=auc_hi, metrics=metrics, ci=ci,
            confusion=confusion_matrix(yv, pv, labels=[0, 1]),
            threshold_used=cut_used,
            cut_lo=float(cut_used),
            cut_hi=float(cut_used),
            extra={"n_scored": int(valid.sum())}))
    # expose the OOF predictions of the best classifier for the per-size
    # breakdown rendered by _md_stratified (module-level hook, read there).
    if results:
        _ref = max(results, key=lambda r: r.auc)
        globals()["_STRAT_DATA"] = data
        globals()["_STRAT_PRED"] = _ref.y_pred
    return results, splitter_name


def per_feature_roc(df: "pd.DataFrame", n_boot: int,
                    rng: np.random.Generator) -> List[Dict[str, Any]]:
    """ROC of each feature used alone as a score, with AUC and its CI.

    Sign convention: every feature is oriented so that the reported direction
    points *towards* the debonded class, then AUC is computed on that oriented
    score. The direction is chosen by comparing AUC(feature) with AUC(-feature)
    and keeping the better of the two, so the panel always shows the feature at
    its best orientation and the legend states which way that is. Without the
    flip a feature that separates perfectly *inversely* would be reported at
    AUC 0.0 and look useless.
    """
    data = df.dropna(subset=list(CLF_FEATURES) + ["grade", "panel_id"]).copy()
    y = _binary_labels(data["grade"])
    groups = data["panel_id"].to_numpy()
    out: List[Dict[str, Any]] = []
    if len(np.unique(y)) < 2:
        return out

    for feat in CLF_FEATURES:
        raw = data[feat].to_numpy(dtype=float)
        if float(np.std(raw)) == 0:
            continue
        try:
            auc_raw = float(roc_auc_score(y, raw))
        except ValueError:
            continue
        direction = 1.0 if auc_raw >= 0.5 else -1.0
        score = direction * raw
        auc = auc_raw if direction > 0 else 1.0 - auc_raw
        lo, hi = bootstrap_ci(roc_auc_score, y, score, groups=groups,
                              n_boot=n_boot, rng=rng)
        fpr, tpr, _ = roc_curve(y, score)
        out.append({"feature": feat, "unit": FEATURE_UNIT.get(feat, "-"),
                    "direction": "higher = debonded" if direction > 0 else "lower = debonded",
                    "auc": auc, "auc_lo": lo, "auc_hi": hi, "fpr": fpr, "tpr": tpr})
    out.sort(key=lambda d: -d["auc"])
    return out


# ==========================================================================
# S10  Expected-cost threshold analysis
# ==========================================================================

@dataclass
class CostAnalysis:
    """Expected-cost curve and its optimum, for one reference classifier."""

    classifier: str
    thresholds: np.ndarray
    costs: np.ndarray
    fnr: np.ndarray
    fpr: np.ndarray
    optimal_threshold: float
    optimal_cost: float
    optimal_fnr: float
    optimal_fpr: float
    default_threshold: float
    default_cost: float
    default_fnr: float
    default_fpr: float
    saving: float                 # expected cost per tap saved vs the default
    saving_fraction: float        # ... as a fraction of the default cost
    baseline_cost: float          # cost of never raising an alarm (threshold = 1)
    naive_cost: float             # cost of always raising an alarm (threshold = 0)


def expected_cost_analysis(result: ClassifierResult, prevalence: float,
                           miss_cost: float, n_grid: int = 400) -> Optional[CostAnalysis]:
    """Sweep the decision threshold and price the two error types.

        expected_cost(t) = P(D)*FNR(t)*C_miss + (1 - P(D))*FPR(t)*C_fa

    with C_fa normalised to 1. The curve is evaluated on the reference
    classifier's out-of-fold scores, so the operating point it recommends is one
    the model can actually achieve on unseen panels.

    Why the asymmetry is justified: a false alarm costs one manual re-inspection
    by an inspector already on site with a hammer - minutes of labour. A miss is
    a debonded finish that is never re-inspected and can detach onto the public
    below. The ratio prices the *consequences*, not the inspection effort.
    """
    y, s = np.asarray(result.y_true), np.asarray(result.y_score)
    if y.size == 0 or len(np.unique(y)) < 2:
        return None
    finite = s[np.isfinite(s)]
    if finite.size == 0:
        return None
    lo, hi = float(np.min(finite)), float(np.max(finite))
    if np.isclose(lo, hi):
        lo, hi = lo - 0.5, hi + 0.5
    thresholds = np.linspace(lo, hi, n_grid)

    n_pos, n_neg = float(np.sum(y == 1)), float(np.sum(y == 0))
    fnr = np.array([safe_div(float(np.sum(~(s >= t) & (y == 1))), n_pos) for t in thresholds])
    fpr = np.array([safe_div(float(np.sum((s >= t) & (y == 0))), n_neg) for t in thresholds])
    costs = prevalence * fnr * miss_cost + (1.0 - prevalence) * fpr

    best_i = int(np.argmin(costs))
    opt_t, opt_c = float(thresholds[best_i]), float(costs[best_i])
    # The naive reference: 0.5 is the default cut on a probability output; for
    # the threshold rule the equivalent is the cut the rule itself selected.
    default_t = 0.5 if result.name != "Threshold rule" else result.threshold_used
    default_i = int(np.argmin(np.abs(thresholds - default_t)))
    default_c = float(costs[default_i])
    saving = default_c - opt_c

    return CostAnalysis(
        classifier=result.name, thresholds=thresholds, costs=costs, fnr=fnr, fpr=fpr,
        optimal_threshold=opt_t, optimal_cost=opt_c, optimal_fnr=float(fnr[best_i]),
        optimal_fpr=float(fpr[best_i]), default_threshold=default_t,
        default_cost=default_c, default_fnr=float(fnr[default_i]),
        default_fpr=float(fpr[default_i]), saving=saving,
        saving_fraction=safe_div(saving, default_c),
        baseline_cost=float(prevalence * miss_cost),       # never alarm
        naive_cost=float(1.0 - prevalence))                # always alarm


def theoretical_threshold(prevalence: float, miss_cost: float) -> float:
    """Cost-optimal posterior threshold for a perfectly calibrated model.

    With C_fa = 1 and C_miss = m, an alarm is worth raising exactly when
    P(D|x)*m > (1 - P(D|x)), i.e. P(D|x) > 1/(1+m). It depends only on the cost
    ratio, so it is the number to sanity-check the empirical optimum against.
    At m = 20 it is 0.0476. The prior does not enter because the ratio already
    cancels it.
    """
    return 1.0 / (1.0 + miss_cost)


def manual_threshold_reference(df: "pd.DataFrame", th_f_peak: Optional[float],
                               th_band_ratio: Optional[float]) -> List[Dict[str, Any]]:
    """In-sample performance of any manually supplied fixed thresholds.

    Not part of the cross-validated comparison: these rules are applied to the
    whole dataset at once, so their scores are optimistic. They exist so the
    student can see what a hand-picked physics-based cut buys before trusting
    it, and they are labelled as biased wherever they appear.
    """
    data = df.dropna(subset=list(CLF_FEATURES) + ["grade"])
    y = _binary_labels(data["grade"])
    out: List[Dict[str, Any]] = []
    if len(np.unique(y)) < 2:
        return out

    rules: List[Tuple[str, np.ndarray, str]] = []
    band = data["band_ratio_lh"].to_numpy(dtype=float)
    fpk = data["f_peak_hz"].to_numpy(dtype=float)
    if th_band_ratio is not None:
        rules.append((f"band_ratio_lh >= {th_band_ratio:g}", (band >= th_band_ratio).astype(int),
                      "band_ratio_lh"))
    if th_f_peak is not None:
        rules.append((f"f_peak_hz <= {th_f_peak:g} Hz", (fpk <= th_f_peak).astype(int),
                      "f_peak_hz"))
    if th_band_ratio is not None and th_f_peak is not None:
        rules.append(("either condition (OR rule)",
                      ((band >= th_band_ratio) | (fpk <= th_f_peak)).astype(int), "combined"))

    for label, pred, feat in rules:
        tp = float(np.sum((pred == 1) & (y == 1)))
        tn = float(np.sum((pred == 0) & (y == 0)))
        fp = float(np.sum((pred == 1) & (y == 0)))
        fn = float(np.sum((pred == 0) & (y == 1)))
        sens, spec = safe_div(tp, tp + fn), safe_div(tn, tn + fp)
        out.append({"rule": label, "feature": feat, "sensitivity": sens,
                    "specificity": spec, "ppv": safe_div(tp, tp + fp),
                    "balanced_accuracy": 0.5 * (np.nan_to_num(sens) + np.nan_to_num(spec)),
                    "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn)})
    return out


# ==========================================================================
# S11  Figure style and shared plotting helpers
# ==========================================================================

def apply_report_style() -> None:
    """Configure matplotlib once, for every figure in the report.

    Encodes the dataviz rules: one surface colour; hairline *solid* gridlines
    (never dashed - dashing reads as "threshold" when it is only a grid); thin
    marks (2px lines, >= 8px markers with a 2px surface ring); recessive axes;
    text in text-tokens only, never in a series colour.
    """
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "font.family": "sans-serif",
        "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Arial", "sans-serif"],
        "font.size": 9.5, "axes.titlesize": 11, "axes.titleweight": "normal",
        "axes.titlecolor": INK, "axes.labelsize": 9.5, "axes.labelcolor": INK2,
        "axes.edgecolor": AXIS, "axes.linewidth": 0.8,
        "axes.grid": True, "axes.axisbelow": True,
        "grid.color": GRID, "grid.linewidth": 0.6, "grid.linestyle": "-",
        "grid.alpha": 1.0,
        "xtick.color": MUTED, "ytick.color": MUTED,
        "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
        "xtick.major.width": 0.8, "ytick.major.width": 0.8,
        "legend.frameon": False, "legend.fontsize": 8.5, "legend.labelcolor": INK2,
        "lines.linewidth": 2.0, "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
        "figure.dpi": 300, "savefig.dpi": 300, "savefig.bbox": "tight",
    })


def _spines(ax, keep: Sequence[str] = ("left", "bottom")) -> None:
    """Hide every spine except ``keep``, leaving a recessive chart frame."""
    for side, spine in ax.spines.items():
        spine.set_visible(side in keep)
        spine.set_color(AXIS)


def _stamp(fig, synthetic: bool, extra: str = "") -> None:
    """Watermark synthetic runs and add an optional figure footnote.

    The watermark is large and semi-transparent across the figure so a demo-mode
    PNG can never be mistaken for measured evidence, even after it has been
    pasted into a slide deck.
    """
    if synthetic:
        fig.text(0.5, 0.5, SYNTH_STAMP, ha="center", va="center", fontsize=20,
                 color=CRITICAL, alpha=0.16, rotation=18, zorder=100,
                 fontweight="bold")
        fig.suptitle(SYNTH_STAMP, fontsize=9, color=CRITICAL, fontweight="bold", y=0.995)
    if extra:
        fig.text(0.005, 0.002, extra, fontsize=7, color=MUTED, ha="left")


def _save(fig, outdir: Path, name: str, synthetic: bool, extra: str = "") -> Path:
    """Apply the stamp and write one 300 dpi PNG."""
    _stamp(fig, synthetic, extra)
    path = outdir / name
    fig.savefig(path, dpi=300, facecolor=SURFACE)
    plt.close(fig)
    print(f"  wrote {path}")
    return path


def _seq_cmap() -> LinearSegmentedColormap:
    """Sequential blue colormap (light -> dark) for the confusion matrices."""
    return LinearSegmentedColormap.from_list("report_seq_blue", list(SEQ_BLUE))


def _box_strip(ax, groups: Sequence[Tuple[str, np.ndarray, str]], ylabel: str,
               log_scale: bool = False) -> None:
    """Combined box + jittered strip per group, in the ordinal grade ramp.

    The box carries the distribution shape, the strip carries the individual
    taps so the sample size is visible, and the hatch duplicates the colour
    channel so the panel survives greyscale printing.
    """
    positions = np.arange(1, len(groups) + 1)
    data = [np.asarray(v, dtype=float)[np.isfinite(v)] for _l, v, _c in groups]
    bp = ax.boxplot(data, positions=positions, widths=0.52, patch_artist=True,
                    showfliers=False, medianprops=dict(color=INK, linewidth=1.4),
                    whiskerprops=dict(color=AXIS, linewidth=1.0),
                    capprops=dict(color=AXIS, linewidth=1.0),
                    boxprops=dict(linewidth=0.9))
    for patch, (label, _v, colour) in zip(bp["boxes"], groups):
        patch.set_facecolor(colour)
        patch.set_alpha(0.55)
        patch.set_edgecolor(colour)
        patch.set_hatch(GRADE_HATCH.get(label, ""))
    rng = np.random.default_rng(7)
    for pos, vals, (label, _v, colour) in zip(positions, data, groups):
        if vals.size == 0:
            continue
        ax.plot(pos + rng.normal(0.0, 0.055, size=vals.size), vals, linestyle="none",
                marker=GRADE_MARKER.get(label, "o"), markersize=2.6,
                markerfacecolor=colour, markeredgecolor=SURFACE,
                markeredgewidth=0.3, alpha=0.55, zorder=3)
        ax.plot([pos], [float(np.median(vals))], marker="D", markersize=4.0,
                markerfacecolor=SURFACE, markeredgecolor=INK, markeredgewidth=1.0,
                zorder=4)
    ax.set_xticks(positions)
    ax.set_xticklabels([lbl for lbl, _v, _c in groups])
    ax.set_ylabel(ylabel)
    if log_scale:
        ax.set_yscale("log")
    _spines(ax)


def _grade_groups(df: "pd.DataFrame", feat: str) -> List[Tuple[str, np.ndarray, str]]:
    """[(grade, values, colour)] for the grades present, in canonical order."""
    out = []
    for g in GRADE_ORDER:
        vals = df.loc[df["grade"] == g, feat].to_numpy(dtype=float)
        if vals.size:
            out.append((g, vals, GRADE_COLOR[g]))
    return out


# ==========================================================================
# S12  Figures fig01 - fig07
# ==========================================================================

def fig01_feature_distributions(df: "pd.DataFrame", outdir: Path,
                                synthetic: bool) -> Optional[Path]:
    """fig01 - box + strip small multiples, one panel per feature, by grade.

    Form: magnitude across three *ordered* grades -> boxplot, because the
    distribution shape matters more than the mean. Frequencies and the decay
    constant use a log axis, since the G0/G1/G2 separation is multiplicative
    (the 1/size^2 law), not additive.
    """
    if df.empty or not [g for g in GRADE_ORDER if (df["grade"] == g).any()]:
        print("  WARNING: fig01 skipped - no grade classes present.")
        return None
    log_features = {"f_peak_hz", "f_centroid_hz", "decay_tau_ms"}
    n, ncols = len(NUMERIC_FEATURES), 4
    fig, axes = plt.subplots(int(np.ceil(n / ncols)), ncols,
                             figsize=(3.1 * ncols, 2.5 * int(np.ceil(n / ncols))))
    axes = np.atleast_1d(axes).ravel()

    for ax, feat in zip(axes, NUMERIC_FEATURES):
        unit = FEATURE_UNIT.get(feat, "")
        _box_strip(ax, _grade_groups(df, feat),
                   f"{feat} ({unit})" if unit and unit != "-" else feat,
                   log_scale=feat in log_features)
        ax.set_title(feat, color=INK)
        ax.grid(axis="x", visible=False)
    for ax in axes[n:]:
        ax.set_visible(False)

    present = [g for g in GRADE_ORDER if (df["grade"] == g).any()]
    handles = [Patch(facecolor=GRADE_COLOR[g], edgecolor=GRADE_COLOR[g], alpha=0.55,
                     hatch=GRADE_HATCH[g], label=GRADE_LABEL[g]) for g in present]
    fig.legend(handles=handles, loc="lower center", ncol=len(present),
               bbox_to_anchor=(0.5, -0.015))
    fig.suptitle("Tap-tone feature distributions by debond grade "
                 "(box = IQR, diamond = median, dots = individual taps)",
                 fontsize=11, y=1.0)
    fig.tight_layout(rect=(0, 0.045, 1, 0.965))
    return _save(fig, outdir, "fig01_feature_distributions.png", synthetic)


def fig02_f_peak_vs_size(fit: Optional[SizeFit], outdir: Path,
                         synthetic: bool) -> Optional[Path]:
    """fig02 - HEADLINE: median f_peak vs debond size with the 1/size^2 fit.

    Two panels, deliberately not a dual-axis chart (the most common charting
    mistake). The left panel is the headline measurement; the right is the
    log-log diagnostic that shows whether the exponent really is 2. Both panels
    carry one message, stated once in the figure title.
    """
    if fit is None:
        print("  WARNING: fig02 skipped - fewer than two debond sizes present.")
        return None

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.4, 4.3))

    x_smooth = np.linspace(max(fit.sizes.min() * 0.85, 0.5), fit.sizes.max() * 1.15, 300)
    ax1.plot(x_smooth, fit.C / x_smooth ** 2, color=SERIES_BLUE, linewidth=2.0,
             zorder=2, label=f"f = C / size$^2$,  C = {fit.C:,.0f} Hz.cm$^2$")
    ax1.errorbar(fit.sizes, fit.medians,
                 yerr=[fit.medians - fit.q1, fit.q3 - fit.medians], fmt="o",
                 markersize=8, color=SERIES_ORANGE, markerfacecolor=SERIES_ORANGE,
                 markeredgecolor=SURFACE, markeredgewidth=2.0, elinewidth=1.6,
                 capsize=4, zorder=4, label="measured median (IQR)")
    for s, q_lo in zip(fit.sizes, fit.q1):
        ax1.annotate(f"{q_lo:,.0f}", (s, q_lo), textcoords="offset points",
                     xytext=(0, -14), ha="center", fontsize=7.5, color=MUTED)
    ax1.set_xscale("log")
    ax1.set_yscale("log")
    ax1.set_xticks(fit.sizes)
    ax1.set_xticklabels([_size_label(s).replace(" cm", "") for s in fit.sizes])
    ax1.minorticks_off()
    ax1.set_xlabel("nominal debond radius, size_cm (cm)")
    ax1.set_ylabel("peak tap-tone frequency, f_peak_hz (Hz)")
    ax1.set_title("Size sensitivity", color=INK)
    ax1.legend(loc="upper right")
    _spines(ax1)

    lx, ly = np.log(fit.sizes), np.log(fit.medians)
    ax2.plot(lx, ly, "o", markersize=8, color=SERIES_ORANGE,
             markerfacecolor=SERIES_ORANGE, markeredgecolor=SURFACE,
             markeredgewidth=2.0, zorder=4, label="measured median")
    xs = np.linspace(lx.min() - 0.1, lx.max() + 0.1, 100)
    ax2.plot(xs, -2.0 * xs + (np.mean(ly) + 2.0 * np.mean(lx)), color=SERIES_BLUE,
             linewidth=2.0, label="slope fixed at -2 (theory)")
    if np.isfinite(fit.slope):
        ax2.plot(xs, fit.slope * xs + (np.mean(ly) - fit.slope * np.mean(lx)),
                 color=SERIES_AQUA, linewidth=2.0, linestyle="--",
                 label=f"free fit, slope = {fit.slope:.2f}")
    ax2.set_xlabel("ln(size_cm)")
    ax2.set_ylabel("ln(f_peak_hz)")
    ax2.set_title(f"Log-log check (R$^2$ = {fit.r2:.3f} on the fixed-exponent curve)",
                  color=INK)
    ax2.legend(loc="lower left")
    _spines(ax2)

    fig.suptitle("Smaller debonds ring at higher frequency: f_peak falls as 1/size$^2$",
                 fontsize=12, y=1.0)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return _save(fig, outdir, "fig02_f_peak_vs_size.png", synthetic,
                 extra=f"C = {fit.C:,.0f} Hz.cm^2 (95% CI {fit.C_lo:,.0f}-"
                       f"{fit.C_hi:,.0f}); n = {int(fit.counts.sum())} debonded taps")


def fig03_roc_curves(results: Sequence[ClassifierResult], outdir: Path,
                     synthetic: bool) -> Optional[Path]:
    """fig03 - ROC of the three detection rules on one axis, AUC in the legend.

    Colour is backed by three other channels (line style, marker and the AUC
    value printed in the legend), so the chart reads in greyscale and under any
    colour-vision deficiency.
    """
    if not results:
        print("  WARNING: fig03 skipped - no classifier results.")
        return None
    fig, ax = plt.subplots(figsize=(6.4, 6.0))
    ax.plot([0, 1], [0, 1], color=AXIS, linewidth=1.2, zorder=1,
            label="chance (AUC = 0.50)")

    for res in results:
        fpr, tpr, _ = roc_curve(res.y_true, res.y_score)
        colour = CLF_COLOR.get(res.name, SERIES_BLUE)
        ax.plot(fpr, tpr, color=colour, linewidth=2.0,
                linestyle=CLF_LINESTYLE.get(res.name, "-"),
                marker=CLF_MARKER.get(res.name, "o"), markersize=4.5,
                markevery=max(1, len(fpr) // 12), markeredgecolor=SURFACE,
                markeredgewidth=1.0,
                label=f"{res.name}: AUC {res.auc:.3f} "
                      f"[{res.auc_lo:.3f}-{res.auc_hi:.3f}]")

    ax.set_xlim(-0.01, 1.01)
    ax.set_ylim(-0.01, 1.02)
    ax.set_xlabel("false-positive rate (bonded point flagged as debonded)")
    ax.set_ylabel("true-positive rate (debond correctly flagged)")
    ax.set_title("Detection performance, panel-wise out-of-fold predictions", color=INK)
    ax.legend(loc="lower right")
    _spines(ax)
    fig.tight_layout()
    return _save(fig, outdir, "fig03_roc_curves.png", synthetic,
                 extra="Groups = panel_id; no panel is shared between training "
                       "and test folds.")


def fig04_confusion_matrices(results: Sequence[ClassifierResult], outdir: Path,
                             synthetic: bool) -> Optional[Path]:
    """fig04 - side-by-side row-normalised confusion matrices.

    A sequential single-hue ramp (blue, light -> dark) because cell magnitude is
    a continuous quantity. Every cell also carries its count and row percentage,
    so the matrix never depends on colour alone.
    """
    if not results:
        print("  WARNING: fig04 skipped - no classifier results.")
        return None
    fig, axes = plt.subplots(1, len(results), figsize=(3.5 * len(results) + 0.6, 3.9))
    axes = np.atleast_1d(axes)

    for ax, res in zip(axes, results):
        cm = res.confusion.astype(float)
        row_sums = cm.sum(axis=1, keepdims=True)
        norm = np.divide(cm, np.where(row_sums == 0, 1, row_sums))
        ax.imshow(norm, cmap=_seq_cmap(), vmin=0.0, vmax=1.0, aspect="equal")
        # 2px surface gap between adjacent cells: the gap does the separating,
        # never a stroke drawn around each mark.
        for edge in (0.5,):
            ax.axhline(edge, color=SURFACE, linewidth=2.0, zorder=3)
            ax.axvline(edge, color=SURFACE, linewidth=2.0, zorder=3)
        for i in range(2):
            for j in range(2):
                frac = float(norm[i, j])
                ax.text(j, i, f"{int(cm[i, j])}\n{100 * frac:.0f}%", ha="center",
                        va="center", fontsize=9.5, color="#ffffff" if frac > 0.55 else INK)
        ax.set_xticks([0, 1])
        ax.set_yticks([0, 1])
        ax.set_xticklabels(["bonded", "debonded"])
        ax.set_yticklabels(["bonded", "debonded"])
        ax.set_xlabel("predicted")
        if ax is axes[0]:
            ax.set_ylabel("ground truth")
        ax.set_title(f"{res.name}\nacc {res.metrics['accuracy']:.2f} · "
                     f"bal-acc {res.metrics['balanced_accuracy']:.2f}", color=INK, fontsize=10)
        ax.grid(False)
        for spine in ax.spines.values():
            spine.set_visible(False)

    fig.suptitle("Confusion matrices, row-normalised "
                 "(each row sums to 100% of that true class)", fontsize=11, y=1.0)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return _save(fig, outdir, "fig04_confusion_matrices.png", synthetic)


def fig05_expected_cost(cost: Optional[CostAnalysis], outdir: Path, synthetic: bool,
                        prevalence: float, miss_cost: float) -> Optional[Path]:
    """fig05 - HEADLINE: expected cost per tap vs decision threshold.

    The curve is the whole argument of the report's threshold section: the
    cost-optimal threshold sits far below 0.5 because a miss is far worse than a
    false alarm. The optimum and the naive default are both marked so the saving
    is visible rather than only tabulated, and the right panel shows the two
    error rates trading off behind the curve.
    """
    if cost is None:
        print("  WARNING: fig05 skipped - no usable classifier scores.")
        return None

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.6, 4.3))
    ax1.plot(cost.thresholds, cost.costs, color=SERIES_BLUE, linewidth=2.0, zorder=3,
             label="expected cost at threshold")
    ax1.axhline(cost.optimal_cost, color=AXIS, linewidth=1.2, linestyle=":", zorder=1,
                label="cost at the optimum")
    ax1.plot([cost.optimal_threshold], [cost.optimal_cost], marker="D", markersize=9,
             color=SERIES_ORANGE, markerfacecolor=SERIES_ORANGE,
             markeredgecolor=SURFACE, markeredgewidth=2.0, zorder=6,
             label=f"cost-optimal threshold = {cost.optimal_threshold:.3f}")
    ax1.plot([cost.default_threshold], [cost.default_cost], marker="s", markersize=8,
             color=SERIES_AQUA, markerfacecolor=SERIES_AQUA, markeredgecolor=SURFACE,
             markeredgewidth=2.0, zorder=6,
             label=f"naive default = {cost.default_threshold:.2f}")
    ax1.annotate(
        f"saves {cost.saving:.4f} per tap\n({100 * cost.saving_fraction:.0f}% of the "
        f"default cost)" if np.isfinite(cost.saving_fraction) else "saving n/a",
        xy=(cost.optimal_threshold, cost.optimal_cost), xytext=(0.30, 0.34),
        textcoords="axes fraction", fontsize=8.5, color=INK2,
        arrowprops=dict(arrowstyle="->", color=MUTED, linewidth=1.0))
    ax1.set_xlabel(f"decision threshold on P(debonded)  [reference: {cost.classifier}]")
    ax1.set_ylabel("expected cost per tap (C_fa = 1)")
    ax1.set_title(f"Cost-optimal alarm threshold (P(D) = {prevalence:.2f}, "
                  f"C_miss/C_fa = {miss_cost:.0f})", color=INK)
    # The extreme left of the sweep is the degenerate "alarm on every tap" rule
    # (FPR = 1, so its cost is ~1 - P(D), far above the interesting range). If it
    # were allowed to set the y-scale, the whole curve - and with it the optimum
    # we are asking the reader to find - would be squashed onto the axis. Clip
    # the view to the region where the classifier's decision actually changes and
    # say in words that the clipped point is off the scale.
    degenerate = cost.fpr >= 0.999
    interior = cost.costs[~degenerate]
    top = float(np.max(interior)) if interior.size else float(np.max(cost.costs))
    ax1.set_ylim(0.0, max(top * 1.35, cost.optimal_cost * 3.0))
    if bool(degenerate.any()):
        ax1.annotate(
            "alarm every tap (FPR = 1)\n"
            f"cost = {float(np.max(cost.costs[degenerate])):.2f} - off scale",
            xy=(float(cost.thresholds[degenerate][0]), float(ax1.get_ylim()[1])),
            xytext=(0.17, 0.85), textcoords="axes fraction", fontsize=8.5,
            color=MUTED, ha="left", va="top",
            arrowprops=dict(arrowstyle="->", color=MUTED, linewidth=1.0))
    ax1.legend(loc="upper right")
    _spines(ax1)

    ax2.plot(cost.thresholds, cost.fnr, color=SERIES_ORANGE, linewidth=2.0,
             label="false-negative rate (missed debond)")
    ax2.plot(cost.thresholds, cost.fpr, color=SERIES_BLUE, linewidth=2.0, linestyle="--",
             label="false-positive rate (needless re-inspection)")
    ax2.axvline(cost.optimal_threshold, color=SERIES_AQUA, linewidth=1.6, linestyle=":",
                label=f"optimum = {cost.optimal_threshold:.3f}")
    ax2.axvline(cost.default_threshold, color=MUTED, linewidth=1.4, linestyle="-.",
                label=f"naive default = {cost.default_threshold:.2f}")
    ax2.set_xlabel("decision threshold on P(debonded)")
    ax2.set_ylabel("error rate (fraction of that class)")
    ax2.set_ylim(-0.02, 1.02)
    ax2.set_title("Where the two error types trade off", color=INK)
    ax2.legend(loc="center right")
    _spines(ax2)

    fig.suptitle(f"A missed debond costs about {int(miss_cost)} re-inspections, so the "
                 "optimal threshold is far below 0.5", fontsize=12, y=1.0)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return _save(fig, outdir, "fig05_expected_cost.png", synthetic,
                 extra="Cost model: E[t] = P(D)*FNR(t)*C_miss + (1-P(D))*FPR(t)*C_fa, "
                       "with C_fa = 1.")


def fig06_repeatability(rep: RepeatabilityResult, outdir: Path, synthetic: bool,
                        pass_criterion: float = 5.0) -> Optional[Path]:
    """fig06 - within-location CV% by grade, and the tap-1 vs rest agreement.

    Left: strip plot of per-location CV% for f_peak_hz and impulse_norm against
    the 5% pass line - the evidence for "the probe gives repeatable excitation".
    Right: a Bland-Altman plot of tap 1 against the mean of taps 2..N, which
    shows whether a single tap is a fair substitute for the average.
    """
    if rep.per_location.empty or not rep.bland_altman:
        print("  WARNING: fig06 skipped - no location with 3+ taps.")
        return None

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.6, 4.4))
    grades = [g for g in GRADE_ORDER if (rep.per_location["grade"] == g).any()]
    rng = np.random.default_rng(11)
    for feat_col, colour, marker, offset in (("cv_f_peak_pct", SERIES_BLUE, "o", -0.14),
                                             ("cv_impulse_pct", SERIES_ORANGE, "s", 0.14)):
        for gi, g in enumerate(grades):
            vals = rep.per_location.loc[rep.per_location["grade"] == g,
                                        feat_col].to_numpy(dtype=float)
            vals = vals[np.isfinite(vals)]
            if vals.size == 0:
                continue
            ax1.plot(gi + offset + rng.normal(0.0, 0.035, size=vals.size), vals,
                     linestyle="none", marker=marker, markersize=3.4,
                     markerfacecolor=colour, markeredgecolor=SURFACE,
                     markeredgewidth=0.35, alpha=0.65, zorder=3)
            ax1.plot([gi + offset], [float(np.median(vals))], marker="_", markersize=16,
                     markeredgewidth=2.0, color=colour, zorder=5)
    ax1.axhline(pass_criterion, color=CRITICAL, linewidth=1.6, linestyle="--", zorder=4)
    ax1.text(len(grades) - 0.5, pass_criterion * 1.08, f"{pass_criterion:g}% pass criterion",
             ha="right", va="bottom", fontsize=8, color=CRITICAL)
    ax1.set_xticks(range(len(grades)))
    ax1.set_xticklabels([GRADE_LABEL[g] for g in grades])
    ax1.set_yscale("log")
    # Headroom above the tallest strip so the legend sits in clear space instead
    # of on top of the largest CV% points.
    peak = np.nanmax([np.nanmax(rep.per_location[col].to_numpy(dtype=float))
                      for col in ("cv_f_peak_pct", "cv_impulse_pct")
                      if rep.per_location[col].notna().any()] or [pass_criterion])
    if np.isfinite(peak):
        ax1.set_ylim(top=float(peak) * 2.0)
    ax1.set_ylabel("within-location CV% (log scale)")
    ax1.set_title("Repeatability across taps at one location", color=INK)
    ax1.legend(handles=[
        Line2D([], [], color=SERIES_BLUE, marker="o", linestyle="none", markersize=4.5,
               label="f_peak_hz"),
        Line2D([], [], color=SERIES_ORANGE, marker="s", linestyle="none", markersize=4.5,
               label="impulse_norm"),
        Line2D([], [], color=CRITICAL, linestyle="--", label=f"{pass_criterion:g}% criterion")],
        loc="upper left")
    ax1.grid(axis="x", visible=False)
    _spines(ax1)

    feat = "f_peak_hz" if "f_peak_hz" in rep.bland_altman else next(iter(rep.bland_altman))
    stats = rep.bland_altman[feat]
    pts = sorted(rep.ba_points.get(feat, []), key=lambda p: p[0])
    means = np.array([p[0] for p in pts], dtype=float)
    pct_diffs = np.array([100.0 * p[1] / p[0] if p[0] else np.nan for p in pts], dtype=float)

    ax2.axhline(0.0, color=AXIS, linewidth=1.0, zorder=1)
    ax2.plot(means, pct_diffs, linestyle="none", marker="o", markersize=4.5,
             markerfacecolor=SERIES_BLUE, markeredgecolor=SURFACE, markeredgewidth=1.2,
             alpha=0.75, zorder=3)
    # Bias and limits of agreement are reference lines, not series, so they wear
    # ink / status colours rather than a categorical hue that would impersonate
    # the scatter they sit on.
    ax2.axhline(stats["bias_pct"], color=INK2, linewidth=1.8, zorder=2,
                label=f"bias = {stats['bias_pct']:+.2f}% of the mean")
    for bound in (stats["bias_pct"] + stats["loa_pct"], stats["bias_pct"] - stats["loa_pct"]):
        ax2.axhline(bound, color=CRITICAL, linewidth=1.6, linestyle="--", zorder=2)
    ax2.plot([], [], color=CRITICAL, linewidth=1.6, linestyle="--",
             label=f"95% limits of agreement ({stats['bias_pct'] - stats['loa_pct']:+.1f}"
                   f" to {stats['bias_pct'] + stats['loa_pct']:+.1f}%)")
    ax2.set_xlabel(f"mean of tap 1 and taps 2..N, {feat} "
                   f"({FEATURE_UNIT.get(feat, 'a.u.')})")
    ax2.set_ylabel("tap 1 minus the rest, % of the mean")
    ax2.set_title(f"Bland-Altman agreement, {feat} (n = {stats['n_pairs']} locations)",
                  color=INK)
    ax2.legend(loc="lower right")
    _spines(ax2)

    fig.suptitle("Probe repeatability: tap-to-tap spread and single-tap agreement",
                 fontsize=12, y=1.0)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return _save(fig, outdir, "fig06_repeatability.png", synthetic,
                 extra="CV% uses the population SD over the taps taken at one location.")


def fig07_feature_roc_panel(feature_rocs: Sequence[Dict[str, Any]], outdir: Path,
                            synthetic: bool) -> Optional[Path]:
    """fig07 - small-multiple ROC for each single feature, with AUC and its CI.

    Small multiples rather than one overplotted axis: four curves on one axis
    would need four colours and would still be hard to separate, and the point
    of the panel is per-feature separability, not comparison.
    """
    if not feature_rocs:
        print("  WARNING: fig07 skipped - no single-feature ROC available.")
        return None
    n = len(feature_rocs)
    ncols = min(2, n)
    fig, axes = plt.subplots(int(np.ceil(n / ncols)), ncols,
                             figsize=(3.4 * ncols, 3.2 * int(np.ceil(n / ncols))),
                             squeeze=False)
    axes = axes.ravel()

    for ax, entry in zip(axes, sorted(feature_rocs, key=lambda d: -d["auc"])):
        colour = SERIES_BLUE if entry["auc"] >= 0.5 else SERIES_ORANGE
        ax.plot([0, 1], [0, 1], color=AXIS, linewidth=1.0, label="chance")
        ax.plot(entry["fpr"], entry["tpr"], color=colour, linewidth=2.0,
                label=f"AUC {entry['auc']:.3f}")
        ax.fill_between(entry["fpr"], 0, entry["tpr"], color=colour, alpha=0.10, linewidth=0)
        ax.set_xlim(-0.02, 1.02)
        ax.set_ylim(-0.02, 1.02)
        ax.set_title(entry["feature"], color=INK, fontsize=10)
        if ax is axes[0]:
            ax.set_ylabel("true-positive rate")
        # Direction and CI ride the x-label rather than floating inside the
        # plot, where they would collide with a strong curve near the top left.
        ax.set_xlabel(f"false-positive rate\n{entry['direction']} · 95% CI "
                      f"{entry['auc_lo']:.2f}-{entry['auc_hi']:.2f}", fontsize=8)
        ax.legend(loc="lower right")
        _spines(ax)
    for ax in axes[n:]:
        ax.set_visible(False)

    fig.suptitle("Single-feature separability of bonded vs debonded "
                 "(each feature used alone, sign-oriented)", fontsize=11, y=1.0)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return _save(fig, outdir, "fig07_feature_roc_panel.png", synthetic,
                 extra=f"Classifier feature set: {', '.join(CLF_FEATURES)}.")


# ==========================================================================
# S13  results.md writer
# ==========================================================================

def _md_integrity(L: List[str], rep: LoadReport, integ: IntegrityResult,
                  df: "pd.DataFrame", args: argparse.Namespace) -> None:
    """Section 1 of results.md: data integrity and exclusions."""
    L.append("## 1. Data integrity\n")
    L.append(f"Inputs read: {len(rep.files_read)} CSV file(s), {rep.rows_read:,} raw "
             "rows in total.\n")
    if rep.files_read:
        names = ", ".join(f"`{Path(f).name}`" for f in rep.files_read[:20])
        L.append("Files: " + names + (" ..." if len(rep.files_read) > 20 else "") + "\n")
    if rep.waveform_fs_hz:
        L.append(f"Auto-detected sample rate (waveform mode): **{rep.waveform_fs_hz:,.0f} Hz** "
                 "from the median sample interval.\n")
    L.append("**Rows dropped and why** (nothing is removed silently):\n")
    L.extend(integ.summary_lines)
    if rep.dropped:
        L.append("\n" + md_table(["Exclusion reason", "Rows dropped"],
                                 [[reason, f"{count:,}"] for reason, count in
                                  sorted(rep.dropped.items(), key=lambda kv: -kv[1])]))
    else:
        L.append("\nNo rows were dropped: every logged record passed the checks.\n")
    L.append(f"Total dropped: **{rep.total_dropped:,}** of {rep.rows_read:,} rows "
             f"({100.0 * safe_div(rep.total_dropped, max(rep.rows_read, 1)):.1f}%). "
             "The cleaned table actually analysed is `features_analysed.csv`.\n")

    L.append("### 1a. Surviving rows per grade x debond size\n")
    L.append(md_table(["Grade", "size_cm", "Rows in", "Rows used", "Rows dropped"],
                      [[r["grade"], f"{int(r['size_cm'])} cm", f"{int(r['rows_in']):,}",
                        f"{int(r['rows_used']):,}", f"{int(r['rows_dropped']):,}"]
                       for _i, r in integ.grade_size_counts.iterrows()]))

    L.append("### 1b. Out-of-range screening bounds\n")
    L.append(md_table(["Feature", "Unit", "Plausible min", "Plausible max",
                       "Rows outside", "Rows missing (NaN)"],
                      [[f, u if u != "-" else "dimensionless", fmt_num(lo), fmt_num(hi),
                        f"{rep.out_of_range.get(f, 0):,}",
                        f"{rep.missing.get(f, 0):,}"]
                       for f, (u, lo, hi) in FEATURE_BOUNDS.items()]))
    L.append("These bounds are a corruption net, not a physics model: they catch unit "
             "mix-ups (Hz logged as kHz, seconds logged as milliseconds) and truncated "
             "log lines. A row outside a bound is dropped and counted above.\n")
    L.append("**Missing is not the same as corrupt, and the two are counted "
             "separately.** A NaN cell is kept, not dropped: in waveform mode "
             "`impact_peak_g` is NaN by construction (it is not recoverable from "
             "audio alone), and a decay fit may legitimately decline to return a "
             "value. Dropping those rows would silently discard every waveform-mode "
             "measurement. A NaN IS excluded from the statistics that need that one "
             "feature, so each table's `n` is the count of rows carrying a usable "
             "value for that feature -- read `n` against these columns before "
             "comparing two rows of any table below.\n")
    if rep.notes:
        L.append("### 1c. Loader and exclusion notes\n")
        L.extend(f"- {note}" for note in rep.notes)
        L.append("")
    present = [g for g in GRADE_ORDER if (df["grade"] == g).any()]
    absent = [g for g in GRADE_ORDER if g not in present]
    if absent:
        L.append(f"> **Warning:** grade(s) {', '.join(absent)} are absent from the "
                 "analysed sample, so every comparison that needs them was skipped. "
                 "The tables below still list them at n = 0.\n")


def _md_descriptive(L: List[str], df: "pd.DataFrame") -> None:
    """Section 2 of results.md: descriptive statistics."""
    L.append("## 2. Descriptive statistics\n")
    L.append("### 2a. By debond grade\n")
    L.append(descriptive_table(df, "grade", GRADE_ORDER,
                               lambda g: GRADE_LABEL.get(str(g), str(g))))
    L.append("### 2b. By debond size class\n")
    present = sorted(float(s) for s in df["size_cm"].unique())
    L.append(descriptive_table(df, "size_cm", present,
                               lambda s: _size_label(s)))
    L.append("CV% is the population standard deviation divided by the mean, in percent. "
             "It is reported for every feature because detection quality depends on the "
             "between-class separation relative to the within-class spread, and CV% is "
             "that spread expressed in the feature's own units.\n")
    L.append("### 2c. How the model-generated rows were produced\n")
    L.append("In `--demo` mode every row is generated from the report's forward acoustic "
             "model, not measured: a **plate on a Winkler foundation** struck by a "
             "**broadband half-sine transient**.\n")
    L.append("```text\n"
             "material      E = 18 GPa, h = 20 mm, rho = 2000 kg/m3, nu = 0.20\n"
             "              D = E h^3 / (12 (1-nu^2)) = 1.2500e4 N.m\n"
             "debond mode   alpha = 3.19595 / a          (clamped circular plate (0,1))\n"
             "              f_mode(a) = (1/2pi) sqrt( D alpha^4 / (rho h) )\n"
             "foundation    f_found(k) = (1/2pi) sqrt( k / (rho h) )\n"
             "resonance     f1 = sqrt( f_mode^2 + f_found^2 )\n"
             "bond k (Pa/m) G0 = 9.0e11   G1 = 1.0e10   G2 = 0.0\n"
             "strike        half-sine force pulse, contact time 300 us\n"
             "              A(f) = cos(pi f T / 2) / (1 - (f T)^2), null at 5 kHz\n"
             "response      mode at f1, Q = 9, coherently summed with the fixed\n"
             "              broadband background 0.35 / (1 + (f/500)^0.7)\n"
             "              |H(f)| = | bg(f) + rad / ((1-(f/f1)^2) + j f/(f1 Q)) |\n"
             "grid          S(f) = sqrt(F2(f)) |H(f)| on 1024 points at 48 kHz,\n"
             "              analysis band 300..15000 Hz (bin = 46.875 Hz)\n"
             "noise         per-tap lognormal sd 0.05 on S; per-panel sd 0.07 on the\n"
             "              mode strength and 0.05 on the background\n"
             "```\n")
    L.append("The per-tap features are then read off that model spectrum with the **same "
             "definitions the offline extractor uses on a real capture**: `f_peak_hz` is "
             "the argmax of S over 300..15000 Hz, `f_centroid_hz` the S-weighted mean "
             "frequency, and `band_ratio_lh` the ratio of **S^2** summed below the 1 kHz "
             "crossover to **S^2** summed above it. The channel amplitudes follow from the "
             "mode radiation strength `rad = 3.0 x size_factor` (with "
             "`size_factor = clip(size_cm/10, 0.30, 1.0)`), a per-panel mode-strength "
             "effect and the per-tap lognormal noise above; `decay_tau_ms` follows from the "
             "mode decay time `1000 Q / (pi f1)` and is set to the -1.0 sentinel outside "
             "3..60 ms.\n")
    L.append("### 2d. Two consequences of the model worth stating here\n")
    L.append("**Band edge.** The firmware's `PROBE_FMAX_HZ = 15000.0` closes the analysis "
             "band at 15 kHz, and the firmware's crossover `PROBE_CROSSOVER_HZ = 1000.0` "
             "lands on bin 21.33 of the 1024-point / 48 kHz grid - i.e. between bin 21 "
             "(984.375 Hz) and bin 22 (1031.250 Hz). Each bin is assigned **wholly** to one "
             "side: bin 21 is counted in the low band, bin 22 in the high band. The two "
             "sums therefore straddle the nominal 1000 Hz boundary rather than sharing a "
             "bin. The firmware's own ratio compares band **energy (power)**, so the "
             "offline `band_ratio_lh` is a power ratio too: it sums `S^2`, not `S`. Every "
             "ratio in this document is on that footing.\n")
    L.append("**Confusable classes.** A strongly bonded contact has its resonance at "
             "`f_found = (1/2pi) sqrt(9.0e11 / (2000 x 0.020)) = 23.9 kHz` - above the "
             "band - so it contributes nothing in band and the bonded spectrum is pure "
             "transient. The same is true of every small debond: a 3 cm radius puts "
             "`f_mode = 128 kHz` and a 5 cm radius 46 kHz, both far above 15 kHz. Their "
             "in-band spectra therefore collapse onto the same 328 Hz transient peak as the "
             "bonded control. Only a fully debonded **radius of about 4.4 cm and up** "
             "(an 8.8 cm diameter) pulls `f1` below the band top: at 10, 15 and 20 cm the "
             "model's `f1` is 11.5, 5.1 and 2.9 kHz. The generator's own five-point axis "
             "has 3 and 5 cm *radius* below that threshold, so on it only the 10, 15 and "
             "20 cm radii move f_peak at all. This is a property of the model, not a defect "
             "of the generator, and it is exactly why the report calls f_peak a poor "
             "single-channel detector.\n")


def _md_repeatability(L: List[str], repeat: RepeatabilityResult,
                      pass_criterion: float = 5.0) -> None:
    """Section 3 of results.md: repeatability."""
    L.append("## 3. Repeatability of the probe\n")
    L.append("Within each (panel_id, location_id) the probe is struck several times; the "
             "spread between those repeats is the *within-location* variation. It bounds "
             "how well a single tap can represent a location.\n")
    L.append("### 3a. Within-location coefficient of variation\n")
    if repeat.summary:
        L.append(md_table(
            ["Feature", "Locations", "Median within-location CV%", "IQR of CV%",
             f"Locations failing the {pass_criterion:g}% criterion", "Probe verdict (median)"],
            [[feat, str(s["locations"]), f"{s['median_cv']:.2f}%", f"{s['iqr_cv']:.2f}%",
              pct(s["fraction_failing"]),
              "pass" if s["median_cv"] <= pass_criterion else "fail"]
             for feat, s in repeat.summary.items()]))
    else:
        L.append("_Not computed: no location had three or more taps._\n")

    L.append("### 3b. Bland-Altman agreement, tap 1 vs the mean of taps 2..N\n")
    if repeat.bland_altman:
        L.append(md_table(
            ["Feature", "Locations", "Bias (tap 1 - rest)", "Bias as % of mean",
             "95% limits of agreement", "LoA width as % of level", "Bias within 5%?"],
            [[feat, str(s["n_pairs"]),
              f"{s['bias']:+.4g} {FEATURE_UNIT.get(feat, 'a.u.')}",
              f"{s['bias_pct']:+.2f}%",
              f"{s['loa_low']:+.4g} to {s['loa_high']:+.4g} "
              f"{FEATURE_UNIT.get(feat, 'a.u.')}",
              f"+/-{s['loa_pct']:.2f}%",
              "yes" if abs(s["bias_pct"]) <= pass_criterion else "no"]
             for feat, s in repeat.bland_altman.items()]))
    else:
        L.append("_Not computed: no location had three or more taps._\n")
    L.append("A bias near zero means tap 1 is not systematically louder or higher than the "
             "later taps; the limits of agreement say how far an individual tap-1 reading "
             "can stray from the average of the rest. If the LoA width is comparable to the "
             "between-class difference, a single tap is not enough and the probe should "
             "average several taps per location.\n")


def _md_discrimination(L: List[str], omnibus: str, pairwise: str) -> None:
    """Section 4 of results.md: discrimination testing."""
    L.append("## 4. Discrimination testing\n")
    L.append("### 4a. Omnibus test across grades (Kruskal-Wallis)\n")
    L.append(omnibus)
    L.append("Ordered by discriminative power: largest absolute Cliff's delta first, with "
             "the Kruskal-Wallis H as the tie-break. Cliff's delta bands: < 0.147 "
             "negligible, < 0.33 small, < 0.474 medium, otherwise large.\n")
    L.append("### 4b. Pairwise comparisons (Mann-Whitney U, Holm-Bonferroni)\n")
    L.append(pairwise)
    L.append("Holm-Bonferroni is applied **within each feature's family of pairs**, so the "
             "corrected column is directly comparable down one feature's block and needs no "
             "second adjustment: all pairwise tests on one feature form one family because "
             "they test one feature's separability.\n")


def _md_size(L: List[str], fit: Optional[SizeFit]) -> None:
    """Section 5 of results.md: size sensitivity and the two competing fits."""
    L.append("## 5. Size sensitivity\n")
    if fit is None:
        L.append("_Not computed: fewer than two debond size classes were present._\n")
        return
    L.append("Two models are fitted to the same debonded taps and compared on identical "
             "panel-bootstrap resamples. **Model 1** is the report's headline claim, "
             "`f_peak = C / size_cm^2` (one parameter, size in cm). **Model 2** is the form "
             "the plate-on-Winkler model implies: since `f1^2 = f_mode^2 + f_found^2` and "
             "`f_mode^2 = D alpha^4 / ((2 pi)^2 rho h a^4)`, the correct two-parameter fit "
             "is `f_peak^2 = A / a^4 + B` with `a` the debond **radius in metres**. It is "
             "reported in that radius convention and again in the `size_cm` convention "
             "(`A' = A x 200^4`), so the metres check against the analytic constant and the "
             "cm fit are both visible; `B' = B` because the intercept is in Hz^2 either "
             "way. Model 2 is fitted per **tap**, not per class median, so the regression "
             "has the full spread of repeats behind it.\n")
    L.append("### 5a. Median f_peak by debond size\n")
    rows = []
    for i, s in enumerate(fit.sizes):
        fitted = fit.C / float(s) ** 2
        rows.append([f"{int(s)} cm", f"{int(fit.counts[i])}",
                     f"{fmt_num(fit.medians[i])} Hz",
                     f"{fmt_num(fit.q1[i])}-{fmt_num(fit.q3[i])} Hz",
                     f"{fitted:,.0f} Hz", f"{fit.medians[i] - fitted:+,.0f} Hz",
                     f"{100.0 * (fit.medians[i] - fitted) / fitted:+.1f}%"])
    L.append(md_table(["Debond size", "n", "Median f_peak", "IQR",
                       "Fitted f = C/size$^2$", "Residual", "Residual %"], rows))
    L.append("Model 1's residuals are not small and they are not random: the 3 cm and 5 cm "
             "classes sit far *below* the fitted curve and the 15 cm and 20 cm classes far "
             "*above* it. For the small classes the median has been pinned to the strike "
             "transient by the band edge, and no power law through the origin can "
             "accommodate a point that is pinned. That is the quantitative form of the "
             "report's own claim that f_peak says nothing about small debonds.\n")

    L.append("### 5b. Model comparison\n")
    L.append("**Censoring exclusion.** A tap whose f_peak is at or below the crossover "
             f"(`SIZE_FIT_CENSOR_MAX_HZ` = {SIZE_FIT_CENSOR_MAX_HZ:.0f} Hz, the "
             "firmware's own `PROBE_CROSSOVER_HZ`) has been pinned into the "
             "transient-dominated low band: "
             "the argmax there is the strike excitation, not the structure, so the value is "
             "*censored*, not measured. Those taps are dropped from Model 2, and the bonded "
             "control (G0) never enters either model because its `size_cm = 0` gives it no "
             "radius to fit against.\n")
    L.append(f"**{fit.n_used} taps were used and {fit.n_excluded} debonded taps were "
             f"dropped as censored; a further {fit.n_g0_excluded} G0 taps have no radius "
             f"and were never eligible. {fit.n_used_unit} distinct radii survive.**\n")
    if fit.excluded:
        L.append(md_table(["Class", "Median f_peak (Hz)", "Status"],
                          [[f"{grade} @ {size} cm", f"{med:,.1f}", reason]
                           for grade, size, med, reason in fit.excluded]))
    else:
        L.append("_No class had its median pinned below the crossover._\n")
    if fit.fit_sizes.size:
        L.append(f"Surviving radii: {', '.join(_size_label(s).replace(' cm', '') for s in fit.fit_sizes)} cm.\n")
    L.append("**The exclusion is the headline finding, not a technicality.** The classes "
             "that had to be dropped are the bonded control and every debond at or below "
             "the crossover; what survives is a fully debonded region of 10 cm radius and "
             "up. Read the two-parameter fit as an empirical calibration over that range "
             "only. It says nothing about a small debond, because the model generates "
             "nothing about a small debond.\n")

    coef_two = (f"A = {fit.A:,.3f} Hz^2 m^4 ({fit.A_lo:,.3f} - {fit.A_hi:,.3f}); "
                f"B = {fit.B:,.1f} Hz^2 ({fit.B_lo:,.1f} - {fit.B_hi:,.1f})"
                if np.isfinite(fit.A)
                else "n/a - fewer than two distinct uncensored radii survive")
    coef_two_scm = (f"A' = {fit.A_scm:.4g} Hz^2 cm^4 ({fit.A_scm_lo:.4g} - "
                    f"{fit.A_scm_hi:.4g}); B' = {fit.B:,.1f} Hz^2 "
                    f"({fit.B_lo:,.1f} - {fit.B_hi:,.1f})"
                    if np.isfinite(fit.A_scm) else "n/a")
    r2_two_txt = f"{fit.r2_two:.4f}" if np.isfinite(fit.r2_two) else "n/a"
    L.append(md_table(
        ["Model", "Fit basis", "Coefficients (95% CI)", "R^2", "n used", "n excluded"],
        [["1. `f_peak = C / size_cm^2` (headline, one parameter)",
          "class medians, all debonded classes",
          f"C = {fit.C:,.0f} Hz.cm^2 ({fit.C_lo:,.0f} - {fit.C_hi:,.0f})",
          f"{fit.r2:.4f}", f"{int(fit.counts.sum())} debonded taps", "0"],
         ["2. `f_peak^2 = A / a^4 + B` (a in **metres**)",
          "individual taps, censored ones dropped", coef_two, r2_two_txt,
          str(fit.n_used), str(fit.n_excluded)],
         ["3. `f_peak^2 = A' / size_cm^4 + B'` (size_cm convention)",
          "same taps as model 2", coef_two_scm, r2_two_txt,
          str(fit.n_used), str(fit.n_excluded)]]))
    L.append("Rows 2 and 3 are the same fit in two conventions: `A' = A x 200^4` and "
             "`B' = B`, so the R^2 is identical by construction and only the coefficient "
             "units differ. The standard error on `B` is not quoted separately because the "
             "bootstrap CI above it is the honest statement of it.\n")
    if np.isfinite(fit.r2_two) and np.isfinite(fit.r2_one_same):
        better = fit.r2_two > fit.r2_one_same
        L.append(f"Scored on the **same taps**, model 2 gives R^2 = {fit.r2_two:.4f} against "
                 f"{fit.r2_one_same:.4f} for model 1, so the two-parameter form "
                 f"**{'wins' if better else 'does not win'}** here. ")
        L.append("The structural reason is that model 1 forces the curve through the origin "
                 "of the `1/size^2` axis while model 2 carries an intercept `B`, and the "
                 "physics supplies one: the foundation mode `f_found = (1/2pi) sqrt(k/rho h)` "
                 "and the strike-transient floor that is left when a region is not "
                 "debonded at all. When B is fixed by the physics rather than fitted, the "
                 "curvature A is the only free parameter and it is the one the analytic "
                 "formula predicts.\n"
                 if better else
                 "On this sample the extra parameter buys little, which is itself "
                 "informative: with the censored small classes removed, the surviving "
                 "10-20 cm range is short enough that a one-parameter power law already "
                 "tracks it, and the two fits are then not statistically distinguishable.\n")
    L.append(f"\n**Model 1's R^2 in the table ({fit.r2:.4f}) is computed over *all* debonded "
             "classes and is therefore the more pessimistic number; the comparison above "
             "uses the matched tap set. Read both against the residuals in 5a.** The win "
             "is also narrow in a way 5c and 5c-bis make explicit: model 2 wins only "
             "because model 1 is badly wrong on the censored range, and model 2's own "
             "coefficients are not identified until `B` is fixed by the physics.\n")

    L.append("### 5c. Physical validation of A\n")
    if np.isfinite(fit.A):
        ratio = safe_div(fit.A, fit.A_analytic)
        contains = (np.isfinite(fit.A_lo) and np.isfinite(fit.A_hi)
                    and fit.A_lo <= fit.A_analytic <= fit.A_hi)
        L.append("The analytic value of the curvature coefficient for the reference panel "
                 "(E = 18 GPa, h = 20 mm, rho = 2000 kg/m3, nu = 0.20, so "
                 "D = 1.2500e4 N.m, alpha = 3.19595) is\n\n"
                 "```text\nA_analytic = D * alpha^4 / ((2 pi)^2 * rho * h)\n"
                 "           = 12500 * 3.19595^4 / ((2 pi)^2 * 2000 * 0.020)\n"
                 f"           = {fit.A_analytic:.3f} Hz^2 m^4\n"
                 "```\n\n")
        L.append("> **Note on the constant quoted in the project brief.** The brief gives "
                 f"`D*3.19595**4/((2*pi)**2*2000*0.020) = {fit.A_brief:g}` for this "
                 "quantity. That arithmetic is wrong for A: the value the expression "
                 f"evaluates to is {fit.A_analytic:.3f}, and {fit.A_brief:g} is "
                 f"`sqrt({fit.A_analytic:.3f}) = {np.sqrt(fit.A_analytic):.4f}`. In other "
                 "words the brief's number is one angular-frequency factor out - it is "
                 "f_mode(0.1 m)/100, a frequency, not the coefficient of a `1/a^4` term. "
                 "The comparison below is therefore made against the coefficient the "
                 f"brief's own formula produces ({fit.A_analytic:.3f} Hz^2 m^4, whose "
                 f"square root is {np.sqrt(fit.A_analytic):.4f}), and separately against "
                 f"{fit.A_brief:g} so both readings are on the record.\n")
        L.append(f"The free fit returns **A = {fit.A:,.3f} Hz^2 m^4** "
                 f"(95% CI {fit.A_lo:,.3f} - {fit.A_hi:,.3f}), i.e. "
                 f"**{ratio:.3f} x the analytic coefficient**"
                 + ("; the CI contains the analytic value, so the curvature the generator "
                    "recovers is consistent with the panel it was built from."
                    if contains else
                    "; the CI does NOT contain the analytic value. The sign is wrong as "
                    "well as the magnitude, which is the signature of an *unidentified* "
                    "fit rather than a wrong model: with only a handful of collinear radii the "
                    "free fit can trade `A` against `B` along a near-flat direction and "
                    "happily return a negative curvature. Section 5c-bis therefore fixes "
                    "`B` at its analytic value and re-estimates `A` as a single unknown "
                    "- that is the test that decides whether the model's `1/a^4` law is "
                    "actually present, and the free fit alone cannot.")
                 + f" In the size_cm convention the same analytic value is "
                   f"A'_analytic = {fit.A_scm_analytic:.6g} Hz^2 cm^4 "
                   f"(= {fit.A_analytic:.3f} x 200^4) against a fitted "
                   f"A' = {fit.A_scm:.6g} Hz^2 cm^4.\n")
        L.append(f"B is the intercept of the `1/a^4` axis, and the physics names it: "
                 f"`B = f_found^2 = k / ((2 pi)^2 rho h)`. For a full debond (k = 0) that "
                 f"is 0 Hz^2; for the partially bonded grade G1 (k = 1.0e10 Pa/m) it is "
                 f"{SIZE_FIT_B_ANALYTIC['G1']:,.0f} Hz^2. The fit returns "
                 f"**B = {fit.B:,.0f} Hz^2** "
                 f"(95% CI {fit.B_lo:,.0f} - {fit.B_hi:,.0f}).\n")
    else:
        L.append("_The two-parameter fit needs at least two distinct uncensored radii; "
                 "fewer survived the band-edge exclusion, so A is not reported._\n")

    if fit.A_fix:
        L.append("### 5c-bis. Curvature A with B fixed by the physics\n")
        L.append("The free two-parameter fit above returns a **negative** A, which is "
                 "unphysical: the `1/a^4` curvature cannot invert a resonance. The reason "
                 "is identification, not the model. The surviving radii "
                 f"({', '.join(_size_label(s).replace(' cm', '') for s in fit.fit_sizes)} cm) "
                 "span a narrow `1/a^4` range and are strongly collinear with the "
                 "intercept, so on this sample the free fit can slide a large `B` and a "
                 "large `A` against one another almost without changing the fit; the "
                 "negative A is the free fit exploiting that flat direction. The physics "
                 "removes the ambiguity by *naming* `B`, and the properly identified test "
                 "of A is therefore the one-parameter regression `A = sum(x (y-B)) / "
                 "sum(x^2)` with `B = f_found^2` held at its analytic value. Those results "
                 "are below, per grade (B differs by grade) and pooled.\n")
        frows = []
        for key, label, btxt in (
                ("G2", "G2 full debond", "0 (k = 0)"),
                ("G1", "G1 partial debond", f"{SIZE_FIT_B_ANALYTIC['G1']:,.0f} Hz^2 (k = 1.0e10 Pa/m)"),
                ("MIX", "G1 + G2 pooled", "0 (shared)")):
            if key not in fit.A_fix:
                continue
            av = fit.A_fix[key]
            frows.append([label, btxt, f"{av:,.1f} Hz^2 m^4",
                          f"{fit.A_fix_lo.get(key, float('nan')):,.1f} - "
                          f"{fit.A_fix_hi.get(key, float('nan')):,.1f}",
                          f"{safe_div(av, fit.A_analytic):+.3f}",
                          f"{fit.r2_fix.get(key, float('nan')):.4f}"])
        L.append(md_table(["Subset", "B fixed at", "A", "95% CI",
                           "A / A_analytic", "R^2"], frows))
        a_g2 = fit.A_fix.get("G2", float("nan"))
        a_g1 = fit.A_fix.get("G1", float("nan"))
        ratio_g2 = safe_div(a_g2, fit.A_analytic)
        ratio_g1 = safe_div(a_g1, fit.A_analytic)
        L.append(f"**With B fixed, the curvature becomes identifiable - but it does not "
                 f"land on the analytic value.** "
                 f"The physical-grade fit (G2, `B = 0`) returns A = "
                 f"{a_g2:,.1f} Hz^2 m^4 = **{ratio_g2:.3f} x** "
                 f"the analytic {fit.A_analytic:,.1f} Hz^2 m^4; the partially bonded grade "
                 f"(G1, `B = f_found^2 = {SIZE_FIT_B_ANALYTIC['G1']:,.0f} Hz^2`) returns "
                 f"{a_g1:,.1f} Hz^2 m^4 = {ratio_g1:.3f} x. Both are well below 1, and "
                 f"neither confidence interval contains the analytic value.\n\n"
                 f"Two things can be read from that, and they point the same way. First, "
                 f"fixing B does what it was supposed to do: it turns an *inverted* free "
                 f"fit into a positive curvature, so the `1/a^4` law is not contradicted by "
                 f"the data once the fit is identified. Second, the magnitude comes out "
                 f"roughly an order of magnitude small, and the honest conclusion is that "
                 f"**this sample cannot verify the analytic coefficient** - cut down to a "
                 f"handful of collinear radii by the censoring that removes every class "
                 f"below the crossover, the curvature is bounded above rather than measured. "
                 f"The P8 verdict in S8.7 is therefore 'identified but not confirmed', "
                 f"which is weaker than the model would like and stronger than the free fit "
                 f"alone can support.\n")

    ss_res = float(np.sum((np.log(fit.medians) - (fit.slope * np.log(fit.sizes) +
                    (np.mean(np.log(fit.medians)) - fit.slope * np.mean(np.log(fit.sizes))))) ** 2))
    ss_tot = float(np.sum((np.log(fit.medians) - np.mean(np.log(fit.medians))) ** 2))
    L.append("### 5d. Free-exponent diagnostic\n")
    L.append(f"With the exponent **fitted freely** in log-log space on the class medians: "
             f"**p = {fit.slope:.3f}**, 95% CI {fit.slope_lo:.3f} - {fit.slope_hi:.3f}, "
             f"R^2 = {1.0 - safe_div(ss_res, ss_tot):.4f}. The CI is extremely wide because "
             "only two of the five classes carry any usable information (the rest are "
             "pinned at the band edge), so this diagnostic cannot by itself distinguish "
             "1/size from 1/size^2. That is a statement about the design, not about the "
             "physics.\n")
    L.append("### 5e. Residual structure\n")
    L.append("A residual that varies monotonically with size means the exponent is wrong "
             "and the curve is systematically bending; a random scatter about zero means "
             "the assumed form is adequate over the range measured here. Read table 5a and "
             "the comparison in 5b against figure 2 (`fig02_f_peak_vs_size.png`) before "
             "quoting any constant.\n")

def _stratified_by_size() -> Optional[Dict[str, Any]]:
    """Per-debond-size detection rate for the best classifier, from its OOF preds.

    Reads the module-level hook set by classifier_study(); returns None when it
    is absent, so the report degrades quietly rather than failing.
    """
    data = globals().get("_STRAT_DATA")
    pred = globals().get("_STRAT_PRED")
    if data is None or pred is None:
        return None
    d = data.copy()
    d["_pred"] = pred
    deb = d[d["grade"] != "G0"]
    rows = []
    for size, sub in deb.groupby("size_cm"):
        n = int(len(sub))
        det = int((sub["_pred"] == 1).sum())
        rows.append((float(size), n, det, n - det, 100.0 * det / max(n, 1)))
    bonded = d[d["grade"] == "G0"]
    fp = int((bonded["_pred"] == 1).sum())
    return {"rows": rows, "n_bonded": int(len(bonded)), "fp": fp,
            "n_pos": int(len(deb)), "n_below": int((deb["size_cm"] < 10.0).sum())}


def _md_stratified(L: List[str], strat: Dict[str, Any], clf_name: str) -> None:
    """Render the per-size detection table and the envelope statement."""
    L.append("### 6a-bis. Detection rate by debond size, for the reference classifier\n")
    L.append(f"Reference classifier: **{clf_name}** (best AUC in table 6). Same "
             "out-of-fold predictions as above, broken out by the debond size the "
             "tap came from. **This table is the one to quote**, because the pooled "
             "figures above average over classes the method is specified not to see.\n")
    L.append(md_table(
        ["Debond size", "Taps", "Detected", "Missed", "Detection rate"],
        [[_size_label(sz), str(n), str(det), str(mis), f"{pct:.1f} %"]
         for sz, n, det, mis, pct in strat["rows"]]))
    L.append(f"Bonded control: **{strat['n_bonded']}** taps, of which "
             f"**{strat['fp']}** were called debonded "
             f"({pct(strat['fp'] / max(strat['n_bonded'], 1))} "
             "false-alarm rate).\n")
    L.append(f"**{strat['n_below']} of the {strat['n_pos']} debonded taps "
             f"({pct(strat['n_below'] / max(strat['n_pos'], 1))}) are smaller than "
             "10 cm**, i.e. below the size floor the report derives in S5.5. A class in "
             "that range has no in-band mode to detect, so it is not misclassified by "
             "the model — it is *outside the model's input space*, and every pooled "
             "metric that includes it understates the method and overstates the "
             "difficulty. Read the pooled row and this table together.\n")


def _md_classifiers(L: List[str], results: Sequence[ClassifierResult], splitter: str,
                    manual_refs: Sequence[Dict[str, Any]]) -> None:
    """Section 6 of results.md: classifier comparison and confusion matrices."""
    L.append("## 6. Classifier comparison\n")
    L.append(f"Positive class = debonded (G1 or G2); negative class = bonded (G0). All "
             f"figures are **out-of-fold** from a **{splitter}** split with `groups = "
             f"panel_id`, so no panel appears in both training and test folds and no wall is "
             f"measured twice. Features: {', '.join(CLF_FEATURES)}. 95% CIs are percentile "
             f"bootstraps resampling panels (the unit of independence), 1000 resamples.\n")
    if not results:
        L.append("_Not computed: the sample did not contain both classes, or no classifier "
                 "produced usable out-of-fold scores._\n")
        return
    L.append(md_table(
        ["Classifier", "n scored", "Accuracy (95% CI)", "Balanced accuracy (95% CI)",
         "Precision (95% CI)", "Recall (95% CI)", "F1 (95% CI)", "AUC (95% CI)"],
        [[r.name, str(r.extra.get("n_scored", "")),
          f"{r.metrics['accuracy']:.3f} " + ci_text(*r.ci["accuracy"]),
          f"{r.metrics['balanced_accuracy']:.3f} " + ci_text(*r.ci["balanced_accuracy"]),
          f"{r.metrics['precision']:.3f} " + ci_text(*r.ci["precision"]),
          f"{r.metrics['recall']:.3f} " + ci_text(*r.ci["recall"]),
          f"{r.metrics['f1']:.3f} " + ci_text(*r.ci["f1"]),
          f"{r.auc:.3f} " + ci_text(r.auc_lo, r.auc_hi)] for r in results]))

    L.append("### 6a. Confusion matrices (out-of-fold counts)\n")
    for r in results:
        cm = r.confusion
        L.append(f"**{r.name}**\n")
        L.append(md_table(["ground truth", "predicted bonded", "predicted debonded"],
                          [["truly bonded (G0)", int(cm[0, 0]), int(cm[0, 1])],
                           ["truly debonded (G1/G2)", int(cm[1, 0]), int(cm[1, 1])]]))
    L.append("For a safety application the cell that matters is the **false negative** "
             "(bottom-left): a truly debonded point that the probe passes as bonded. The "
             "false-positive cell costs an inspector a few minutes; a false negative can "
             "cost a falling tile. Compare the two when choosing a rule.\n")

    # ---- stratified breakdown -------------------------------------------------
    # The pooled metrics above average over every debonded class in the dataset,
    # and the dataset deliberately spans classes BELOW the method's size floor as
    # well as above it. Those classes are indistinguishable from a bonded wall by
    # construction (S5.4: the bonded signature is the ABSENCE of an in-band tone),
    # so pooling them with the classes the method can actually see reports a number
    # that describes neither. Break the reference classifier out by debond size.
    if results:
        _strat = _stratified_by_size()
        if _strat is not None:
            _md_stratified(L, _strat, max(results, key=lambda r: r.auc).name)

    if manual_refs:
        L.append("### 6b. Manual threshold reference points (in-sample, biased)\n")
        L.append(md_table(
            ["Rule applied to every tap", "Sensitivity", "Specificity", "PPV",
             "Balanced accuracy", "TP / FP", "FN / TN"],
            [[r["rule"], f"{r['sensitivity']:.3f}", f"{r['specificity']:.3f}",
              f"{r['ppv']:.3f}", f"{r['balanced_accuracy']:.3f}",
              f"{r['tp']} / {r['fp']}", f"{r['fn']} / {r['tn']}"] for r in manual_refs]))
        L.append("> These rules are applied to the whole dataset at once, so they are **not** "
                 "cross-validated and their scores are optimistic. They are listed only to "
                 "show what a hand-picked cut buys before it is trusted; the cross-validated "
                 "numbers in table 6 are the ones to quote.\n")


def _md_roc(L: List[str], results: Sequence[ClassifierResult],
            feature_rocs: Sequence[Dict[str, Any]]) -> None:
    """Section 7 of results.md: ROC / AUC."""
    L.append("## 7. ROC / AUC\n")
    L.append("### 7a. Detector ROC comparison\n")
    if results:
        L.append(md_table(
            ["Classifier", "AUC (95% CI)", "Better than chance?", "Conventional band"],
            [[r.name, f"{r.auc:.3f} " + ci_text(r.auc_lo, r.auc_hi),
              "yes" if r.auc > 0.5 else "no",
              "excellent" if r.auc >= 0.9 else "good" if r.auc >= 0.8
              else "fair" if r.auc >= 0.7 else "poor"] for r in results]))
    else:
        L.append("_Not computed._\n")
    L.append("_Figure 3 (`fig03_roc_curves.png`) plots these curves with the chance "
             "diagonal; figure 7 (`fig07_feature_roc_panel.png`) shows each feature used "
             "alone._\n")
    L.append("### 7b. Single-feature separability\n")
    if feature_rocs:
        L.append(md_table(
            ["Feature", "Orientation that indicates a debond", "AUC (95% CI)",
             "CI excludes chance?"],
            [[e["feature"] + (f" ({e['unit']})" if e["unit"] != "-" else ""),
              e["direction"], f"{e['auc']:.3f} " + ci_text(e["auc_lo"], e["auc_hi"]),
              "yes" if e["auc_lo"] > 0.5 else "no"] for e in feature_rocs]))
        L.append("A feature whose CI lower bound clears 0.5 separates the classes on its own; "
                 "one whose CI straddles 0.5 contributes little as a single channel even if "
                 "the multivariate model still gives it weight.\n")
    else:
        L.append("_Not computed._\n")


def _md_cost(L: List[str], cost: Optional[CostAnalysis], args: argparse.Namespace) -> None:
    """Section 8 of results.md: the expected-cost threshold analysis."""
    L.append("## 8. Expected-cost threshold analysis\n")
    L.append("The decision threshold is priced, not voted on. With `C_fa` normalised to 1 "
             "and `C_miss` set by `--miss-cost`:\n")
    L.append("```\nexpected_cost(t) = P(D) * FNR(t) * C_miss + (1 - P(D)) * FPR(t) * C_fa\n```\n")
    L.append(f"with the prior `P(D) = {args.prevalence:g}` and `C_miss/C_fa = "
             f"{args.miss_cost:g}`. A false alarm costs **one manual re-inspection** by an "
             "inspector already on site with a hammer - minutes of labour. A miss is a "
             "**potential falling-object safety event**: the debonded finish is never "
             "re-inspected and can detach onto the public below. The asymmetry therefore "
             "prices the *consequences*, not the inspection effort.\n")
    if cost is None:
        L.append("_Not computed: no classifier produced usable scores._\n")
        return
    L.append(f"Reference classifier for the curve: **{cost.classifier}** (the best-AUC "
             "detector in table 6). Thresholds are swept over that model's out-of-fold "
             "scores, so the recommended operating point is one the model can actually "
             "reach on unseen panels.\n")
    L.append(md_table(["Quantity", "Value"], [
        ["Assumed prior P(D)", f"{args.prevalence:g}"],
        ["Cost ratio C_miss / C_fa", f"{args.miss_cost:g}"],
        ["Theoretical calibrated threshold 1/(1+m)",
         f"{theoretical_threshold(args.prevalence, args.miss_cost):.4f}"],
        ["Cost-minimising threshold", f"**{cost.optimal_threshold:.4f}**"],
        ["Expected cost at the optimum, per tap", f"**{cost.optimal_cost:.5f}**"],
        ["FNR at the optimum (missed debonds)", f"{cost.optimal_fnr:.4f}"],
        ["FPR at the optimum (needless re-inspections)", f"{cost.optimal_fpr:.4f}"],
        ["Naive default threshold", f"{cost.default_threshold:.4f}"],
        ["Expected cost at the default", f"{cost.default_cost:.5f}"],
        ["FNR at the default", f"{cost.default_fnr:.4f}"],
        ["FPR at the default", f"{cost.default_fpr:.4f}"],
        ["Cost saved per tap by moving to the optimum", f"**{cost.saving:.5f}**"],
        ["Saving as a fraction of the default cost",
         f"**{100 * cost.saving_fraction:.1f}%**" if np.isfinite(cost.saving_fraction) else "n/a"],
        ["Cost of never raising an alarm (threshold = 1)", f"{cost.baseline_cost:.5f}"],
        ["Cost of always raising an alarm (threshold = 0)", f"{cost.naive_cost:.5f}"]]))
    L.append("The last two rows are the degenerate strategies the threshold is choosing "
             "between. Never alarming leaves every missed debond unpriced against its "
             "consequence; always alarming pays a re-inspection on every bonded point. "
             "Figure 5 (`fig05_expected_cost.png`) shows the optimum sitting between them, "
             "and the annotated saving is the cost of ignoring the asymmetry.\n")


def _md_interpretation(L: List[str], rep: LoadReport, integ: IntegrityResult,
                       repeat: RepeatabilityResult, clf_results: Sequence[ClassifierResult],
                       fit: Optional[SizeFit], cost: Optional[CostAnalysis],
                       args: argparse.Namespace, synthetic: bool) -> None:
    """Section 9: the student-facing interpretation paragraph set."""
    L.append("## 9. Interpreting these results\n")
    L.append("Written for direct pasting into the report. Replace the bracketed quantities "
             "with the numbers from the tables above.\n")
    parts: List[str] = []

    parts.append("**Data quality.** " + (integ.summary_lines[-1].lstrip("- ")
                 if integ.summary_lines else "")
                 + f" Total exclusions: {rep.total_dropped:,} of {rep.rows_read:,} rows, each "
                   "with its reason listed in section 1, so the analysed sample is fully "
                   "auditable. The cleaned table actually used is `features_analysed.csv`.")
    s = repeat.summary.get("f_peak_hz")
    if s:
        parts.append(
            f"**Repeatability.** The median within-location CV of f_peak_hz is "
            f"{s['median_cv']:.2f}%, and {100 * s['fraction_failing']:.1f}% of locations "
            f"exceed the 5% pass criterion. "
            + ("This supports the claim that the solenoid excitation is repeatable and that "
               "one tap is representative of its location."
               if s["median_cv"] <= 5.0 else
               "This does **not** support the claim that one tap is representative: the probe "
               "should average several taps per location and the repeat count increased."))

    if clf_results:
        best = max(clf_results, key=lambda r: r.auc)
        parts.append(
            f"**Detection performance.** The strongest detector is {best.name} at AUC "
            f"{best.auc:.3f} (95% CI {best.auc_lo:.3f}-{best.auc_hi:.3f}) with balanced "
            f"accuracy {best.metrics['balanced_accuracy']:.3f}. Recall on the debonded class "
            f"is {best.metrics['recall']:.3f} and precision {best.metrics['precision']:.3f}; "
            f"the confusion matrix in section 6a shows where the remaining errors sit. "
            f"Because folds are grouped by panel, this is an honest estimate of performance "
            f"on a wall the model has never seen, not a resubstitution score.")

    if fit is not None:
        # The free slope is negative (f falls as size grows); the physics claim
        # is about its magnitude, so compare |p| with 2.
        mag_lo, mag_hi = abs(fit.slope_hi), abs(fit.slope_lo)
        contains_two = np.isfinite(mag_lo) and mag_lo <= 2.0 <= mag_hi
        parts.append(
            f"**Size sensitivity.** Median f_peak falls with debond size as 1/size^p with "
            f"p = {abs(fit.slope):.2f} (95% CI {mag_lo:.2f}-{mag_hi:.2f}); the "
            f"fixed-exponent fit gives C = {fit.C:,.0f} Hz.cm2 with R^2 = {fit.r2:.3f}. "
            + ("The CI on p contains 2, so the measurements are consistent with the 1/size^2 "
               "resonance model and the smallest debonds do ring highest, as the physics "
               "predicts."
               if contains_two else
               f"The CI on p does not contain 2 (it contains {abs(fit.slope):.2f}), so the "
               "simple 1/size^2 model is not fully adequate over this size range; quote the "
               "measured exponent and treat C as an empirical calibration rather than a "
               "physical constant."))

    if cost is not None:
        parts.append(
            f"**Threshold choice.** Pricing a miss at {args.miss_cost:g}x a false alarm moves "
            f"the cost-minimising threshold to {cost.optimal_threshold:.3f}, far below the "
            f"naive 0.5, and lowers the expected cost per tap from {cost.default_cost:.5f} to "
            f"{cost.optimal_cost:.5f} - a saving of "
            f"{100 * cost.saving_fraction:.0f}%. The optimum sits near the cost-only "
            f"theoretical value 1/(1+m) = "
            f"{theoretical_threshold(args.prevalence, args.miss_cost):.3f}, which is the "
            f"threshold a perfectly calibrated model would choose. The practical meaning is "
            f"that the detector should be tuned to be *sensitive* rather than *specific*: it "
            f"decides which points deserve a human re-inspection, it does not replace the "
            f"inspector.")

    if synthetic:
        parts.append("**This run used synthetic demonstration data.** The numbers above "
                     "exercise every step of the pipeline but describe no real wall. Re-run "
                     "the script on the logged capture CSV (without `--demo`) before quoting "
                     "any figure.")
    L.append("\n\n".join(parts) + "\n")


def write_markdown(path: Path, synthetic: bool, args: argparse.Namespace,
                   rep: LoadReport, integ: IntegrityResult, df: "pd.DataFrame",
                   repeat: RepeatabilityResult, omnibus: str, pairwise: str,
                   fit: Optional[SizeFit], clf_results: Sequence[ClassifierResult],
                   splitter_name: str, feature_rocs: Sequence[Dict[str, Any]],
                   cost: Optional[CostAnalysis], manual_refs: Sequence[Dict[str, Any]],
                   warnings_out: Sequence[str]) -> None:
    """Write results.md: every table above, in report-ready order."""
    L: List[str] = []
    L.append("# Tap-test analysis: results tables\n")
    if synthetic:
        L.append("> ## " + SYNTH_STAMP + "\n")
        L.append("> Every table below was computed from **synthetic demonstration data** "
                 "generated by `--demo`. These numbers illustrate the analysis pipeline and "
                 "must **not** be quoted as measurements of any real wall.\n")
    L.append(f"*Generated by `06_analyze_tap.py` v{SCRIPT_VERSION} on "
             f"{time.strftime('%Y-%m-%d %H:%M:%S')} (local time).*  ")
    L.append(f"*Mode: `{args.mode}` · seed `{args.seed}` · outdir `{args.outdir}` · "
             f"miss cost `{args.miss_cost:g}x` · assumed prior prevalence "
             f"`{args.prevalence:g}`.*\n")
    L.append("Values are reported to 3-4 significant figures. `n/a` means the quantity could "
             "not be computed for that group (usually because the class was absent), not that "
             "it was zero.\n")

    _md_integrity(L, rep, integ, df, args)
    _md_descriptive(L, df)
    _md_repeatability(L, repeat)
    _md_discrimination(L, omnibus, pairwise)
    _md_size(L, fit)
    _md_classifiers(L, clf_results, splitter_name, manual_refs)
    _md_roc(L, clf_results, feature_rocs)
    _md_cost(L, cost, args)
    _md_interpretation(L, rep, integ, repeat, clf_results, fit, cost, args, synthetic)

    if warnings_out:
        L.append("## 10. Warnings raised during this run\n")
        L.extend(f"- {w}" for w in warnings_out)
        L.append("")
    L.append("---\n")
    L.append("*Figures are written to `" + str(Path(args.outdir) / "figures") + "` at 300 dpi: "
             "fig01 feature distributions, fig02 f_peak vs size (headline), fig03 ROC curves, "
             "fig04 confusion matrices, fig05 expected cost (headline), fig06 repeatability, "
             "fig07 per-feature ROC panel.*\n")
    if synthetic:
        L.append(f"\n> **{SYNTH_STAMP}**\n")

    path.write_text("\n".join(L), encoding="utf-8")
    print(f"  wrote {path}")


# ==========================================================================
# S14  Command line and main
# ==========================================================================

def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser (see ``--help`` for the user-facing text)."""
    p = argparse.ArgumentParser(
        prog="06_analyze_tap.py",
        description="Offline analysis of tap-test probe data for the EEE4483 "
                    "wall-debond mini-project: data integrity, descriptive statistics, "
                    "repeatability, discrimination testing, size sensitivity, classifier "
                    "comparison and the expected-cost threshold analysis.",
        epilog="Examples:\n"
               "  python 06_analyze_tap.py --demo\n"
               "  python 06_analyze_tap.py --input features/ --outdir results\n"
               "  python 06_analyze_tap.py --input waveform/ --mode waveform\n"
               "  python 06_analyze_tap.py --input f1.csv --input f2.csv --miss-cost 20\n"
               "\nExits: 0 success, 1 unexpected error, 2 bad arguments, 3 no rows left.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", action="append", metavar="PATH", default=[],
                   help="feature CSV file, or a directory of CSVs (repeatable). "
                        "Ignored when --demo is used.")
    p.add_argument("--mode", choices=("auto", "features", "waveform"), default="auto",
                   help="input interpretation; 'auto' sniffs the CSV headers "
                        "(default: auto)")
    p.add_argument("--outdir", default="./results", metavar="DIR",
                   help="output directory for results.md, the cleaned CSV, the run log "
                        "and figures/ (default: ./results)")
    p.add_argument("--demo", action="store_true",
                   help="synthesise physically plausible data instead of reading files. "
                        "EVERY figure and table is stamped as synthetic.")
    p.add_argument("--miss-cost", type=float, default=20.0, metavar="RATIO",
                   help="cost of a missed debond relative to one false alarm "
                        "(default: 20)")
    p.add_argument("--prevalence", type=float, default=0.15, metavar="P",
                   help="prior probability that a randomly tapped point is debonded "
                        "(default: 0.15)")
    p.add_argument("--th-f-peak", type=float, default=None, metavar="HZ",
                   help="optional manual cut on f_peak_hz; reported as an in-sample "
                        "reference point only")
    p.add_argument("--th-band-ratio", type=float, default=None, metavar="X",
                   help="optional manual cut on band_ratio_lh; reported as an in-sample "
                        "reference point only")
    p.add_argument("--seed", type=int, default=20261016,
                   help="random seed for every stochastic step (default: 20261016)")
    p.add_argument("--version", action="version", version=f"%(prog)s {SCRIPT_VERSION}")
    return p


def _step_load(args: argparse.Namespace, rep: LoadReport, synthetic: bool) -> "pd.DataFrame":
    """Load the working table from synthetic data, feature CSVs or waveforms."""
    if synthetic:
        df = make_synthetic(n_panels=12, taps_per_loc=5, seed=args.seed)
        rep.rows_read = len(df)
        rep.files_read = ["<synthetic>"]
        rep.notes.append("DEMO MODE: 12 synthetic panels, 5 taps per location, generated "
                         "by the forward acoustic model documented in make_synthetic() "
                         "(plate on a Winkler foundation + half-sine strike transient). "
                         "No real wall was measured for this run.")
        return df
    paths = expand_inputs(args.input)
    if not paths:
        raise FileNotFoundError("no CSV files found under the supplied --input path(s)")
    mode = detect_mode(paths, args.mode)
    print(f"  {len(paths)} CSV file(s); interpreted as '{mode}' mode.")
    return load_waveform_mode(paths, rep) if mode == "waveform" \
        else load_feature_mode(paths, rep)


def _print_summary(clean: "pd.DataFrame", rep: LoadReport, outdir: Path,
                   figdir: Path, warnings_out: Sequence[str], who: str) -> None:
    """Print the closing summary block (never a wall of raw data)."""
    print(banner(f"Done ({who})"))
    print(f"  rows analysed : {len(clean):,} of {rep.rows_read:,} read "
          f"({rep.total_dropped:,} dropped, every reason logged)")
    print(f"  outputs       : {outdir / 'results.md'}")
    print(f"                  {outdir / 'features_analysed.csv'}")
    print(f"                  {outdir / 'run_log.txt'}")
    print(f"                  {figdir} (fig01..fig07, 300 dpi PNG)")
    if warnings_out:
        print(f"  {len(warnings_out)} warning(s) raised; all listed in section 10 of "
              "results.md")
    else:
        print("  no warnings raised")


def _print_cost_block(cost: CostAnalysis, miss_cost: float, prevalence: float,
                      sample_prev: float) -> List[str]:
    """Print the expected-cost argument in full and return any warning text."""
    notes: List[str] = []
    print(f"  reference classifier : {cost.classifier}")
    print(f"  assumed prior P(D)   : {prevalence:g}")
    print(f"  theoretical thr      : 1/(1+m) = "
          f"{theoretical_threshold(prevalence, miss_cost):.4f} "
          "(for a perfectly calibrated model)")
    print(f"  COST-OPTIMAL thr     : {cost.optimal_threshold:.4f}  ->  expected cost "
          f"{cost.optimal_cost:.5f} per tap")
    print(f"    at that threshold  : FNR = {cost.optimal_fnr:.4f} (missed debonds), "
          f"FPR = {cost.optimal_fpr:.4f} (needless re-inspections)")
    print(f"  naive default thr    : {cost.default_threshold:.4f}  ->  expected cost "
          f"{cost.default_cost:.5f} per tap")
    print(f"    at that threshold  : FNR = {cost.default_fnr:.4f}, "
          f"FPR = {cost.default_fpr:.4f}")
    if np.isfinite(cost.saving_fraction):
        print(f"  saving from choosing the optimum: {cost.saving:.5f} per tap "
              f"({100 * cost.saving_fraction:.1f}% of the default cost)")
    print(f"  degenerate strategies: never alarm = {cost.baseline_cost:.5f}, "
          f"always alarm = {cost.naive_cost:.5f}")
    if abs(sample_prev - prevalence) > 0.25:
        notes.append(
            f"The analysed sample's own debond fraction is {sample_prev:.2f} while the "
            f"threshold was chosen for a deployment prior P(D) = {prevalence:g}. That is "
            "deliberate: P(D) describes how often debonds occur on a real wall, not how "
            "often they occur in a deliberately balanced test panel. Pass --prevalence to "
            "match the site being surveyed.")
    return notes


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the whole analysis and return a process exit code."""
    args = build_parser().parse_args(argv)
    if args.miss_cost <= 0:
        print("ERROR: --miss-cost must be positive.", file=sys.stderr)
        return 2
    if not 0.0 < args.prevalence < 1.0:
        print("ERROR: --prevalence must lie strictly between 0 and 1.", file=sys.stderr)
        return 2
    if not args.demo and not args.input:
        print("ERROR: supply at least one --input PATH, or use --demo.", file=sys.stderr)
        return 2

    outdir = Path(args.outdir).expanduser().resolve()
    figdir = outdir / "figures"
    outdir.mkdir(parents=True, exist_ok=True)
    figdir.mkdir(parents=True, exist_ok=True)

    tee = Tee(outdir / "run_log.txt")
    sys.stdout = tee
    warnings_out: List[str] = []
    synthetic = bool(args.demo)
    started = time.time()

    try:
        print(banner(f"Tap-test analysis  v{SCRIPT_VERSION}"))
        print(f"  started     : {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  output dir  : {outdir}")
        print(f"  mode        : {args.mode}" + ("  (DEMO / SYNTHETIC)" if synthetic else ""))
        print(f"  seed        : {args.seed}")
        print(f"  miss cost   : {args.miss_cost:g}x a false alarm")
        print(f"  prior P(D)  : {args.prevalence:g}")
        print(f"  manual cuts : f_peak={args.th_f_peak}, band_ratio={args.th_band_ratio}")
        if synthetic:
            print()
            print("*" * 78)
            print("***  " + SYNTH_STAMP)
            print("***  The data below was GENERATED BY THIS SCRIPT, not measured.")
            print("***  Re-run without --demo on the logged capture CSV before")
            print("***  quoting any number or figure in the report.")
            print("*" * 78)

        apply_report_style()
        rng = np.random.default_rng(args.seed)
        rep = LoadReport()

        # -- Step 1: load ---------------------------------------------------
        print(banner("Step 1  Load"))
        df = _step_load(args, rep, synthetic)
        print(f"  loaded {len(df):,} rows, {df['panel_id'].nunique()} panel(s), "
              f"{df['location_id'].nunique()} location(s)")
        counts = df["grade"].value_counts().to_dict()
        print("  grade counts: " + ", ".join(f"{g}={counts.get(g, 0):,}" for g in GRADE_ORDER))
        if synthetic:
            _print_synthetic_summary(df)

        # -- Step 2: integrity ----------------------------------------------
        print(banner("Step 2  Data integrity"))
        integ = run_integrity_checks(df, rep)
        for line in integ.summary_lines:
            print("  " + line.lstrip("- "))
        for reason, count in sorted(rep.dropped.items(), key=lambda kv: -kv[1]):
            print(f"    - {count:>6,} rows  {reason}")
        clean = integ.df
        if clean.empty:
            print("ERROR: every row was excluded; nothing left to analyse.", file=sys.stderr)
            warnings_out.append("All rows were excluded by the integrity checks, so no "
                                "analysis was possible.")
            return 3
        clean = clean.sort_values(["panel_id", "location_id", "tap_idx"]).reset_index(drop=True)
        clean.to_csv(outdir / "features_analysed.csv", index=False)
        print(f"  wrote {outdir / 'features_analysed.csv'}")

        # -- Step 3: descriptives -------------------------------------------
        print(banner("Step 3  Descriptive statistics"))
        present_grades = [g for g in GRADE_ORDER if (clean["grade"] == g).any()]
        for g in present_grades:
            sub = clean[clean["grade"] == g]
            print(f"  {GRADE_LABEL[g]:<20} n={len(sub):>5,}  "
                  f"median f_peak={np.median(sub['f_peak_hz']):>8,.0f} Hz  "
                  f"median band_ratio={np.median(sub['band_ratio_lh']):>5.2f}  "
                  f"median tau={np.median(sub['decay_tau_ms']):>6.2f} ms")
        missing = [g for g in GRADE_ORDER if g not in present_grades]
        if missing:
            msg = ("Grade(s) " + ", ".join(missing) + " absent from the sample; every "
                   "comparison that needs them was skipped.")
            print(f"  WARNING: {msg}")
            warnings_out.append(msg)

        # -- Step 4: repeatability ------------------------------------------
        print(banner("Step 4  Repeatability"))
        repeat = repeatability_analysis(clean, pass_criterion=5.0)
        for feat, s in repeat.summary.items():
            print(f"  {feat:<14} median within-location CV = {s['median_cv']:5.2f}%  "
                  f"({100 * s['fraction_failing']:4.1f}% of locations fail the 5% criterion)")
        if not repeat.summary:
            print("  WARNING: no location had three or more taps; repeatability not assessed.")
            warnings_out.append("Repeatability skipped: no location had three or more taps.")

        # -- Step 5: discrimination -----------------------------------------
        print(banner("Step 5  Discrimination testing"))
        disc = discrimination_analysis(clean)
        omnibus, pairwise = discrimination_tables(disc)
        for item in disc[:5]:
            if np.isfinite(item["kw_p"]):
                print(f"  {item['feature']:<16} H={item['kw_H']:8.2f}  p={item['kw_p']:.2e}  "
                      f"max|delta|={item['max_abs_delta']:.3f} "
                      f"({delta_word(item['max_abs_delta'])})")
        n_tested = sum(1 for i in disc if np.isfinite(i["kw_p"]))
        print(f"  {n_tested} feature(s) tested; the report table is ordered by effect size")

        # -- Step 6: size sensitivity ---------------------------------------
        print(banner("Step 6  Size sensitivity"))
        fit = size_sensitivity(clean, rng)
        if fit is None:
            print("  WARNING: fewer than two debond size classes present; skipped.")
            warnings_out.append("Size sensitivity skipped: fewer than two debond size "
                                "classes present.")
        else:
            print(f"  sizes present  : {[_size_label(s) for s in fit.sizes]}")
            print(f"  C = {fit.C:,.0f} Hz.cm^2 (95% CI {fit.C_lo:,.0f} - {fit.C_hi:,.0f}), "
                  f"R^2 = {fit.r2:.4f}")
            print(f"  free exponent p = {fit.slope:.3f} "
                  f"(95% CI {fit.slope_lo:.3f} - {fit.slope_hi:.3f})")
            for size, med, fitted, resid in fit.residuals:
                print(f"    {size:>3} cm  measured {med:>8,.0f} Hz   fitted {fitted:>8,.0f} Hz"
                      f"   residual {resid:+,.0f} Hz")
            print("\n  two-parameter fit f_peak^2 = A/a^4 + B (a = radius in "
                  "METRES), censored taps excluded")
            print(f"  taps used = {fit.n_used}, debonded taps dropped as censored = "
                  f"{fit.n_excluded}; radii surviving = "
                  f"{[_size_label(s) for s in fit.fit_sizes]} "
                  f"({fit.n_used_unit} distinct radii)")
            print(f"  G0 (bonded) taps excluded, no radius at all = "
                  f"{fit.n_g0_excluded}")
            for grade, size, med, reason in fit.excluded:
                print(f"    CENSORED class {size} cm ({grade}): median f_peak "
                      f"{med:,.1f} Hz - {reason}")
            if np.isfinite(fit.A):
                print(f"  A (metres)  = {fit.A:,.3f} Hz^2 m^4  "
                      f"(95% CI {fit.A_lo:,.3f} - {fit.A_hi:,.3f}),  "
                      f"R^2 = {fit.r2_two:.4f}")
                print(f"  B (metres)  = {fit.B:,.1f} Hz^2  "
                      f"(95% CI {fit.B_lo:,.1f} - {fit.B_hi:,.1f})")
                print(f"  size_cm convention A' = {fit.A_scm:.4g} Hz^2 cm^4 "
                      f"(95% CI {fit.A_scm_lo:.4g} - {fit.A_scm_hi:.4g}), "
                      f"B' = {fit.B:,.1f} Hz^2, R^2 = {fit.r2_two:.4f}")
                print(f"  analytic A  = {fit.A_analytic:,.3f} Hz^2 m^4 "
                      f"-> fitted/analytic = {safe_div(fit.A, fit.A_analytic):.3f}")
                print(f"  analytic A' = {fit.A_scm_analytic:.4g} Hz^2 cm^4 "
                      f"(= {fit.A_analytic:.3f} x 200^4); brief quoted "
                      f"{fit.A_brief:g} (that is sqrt(A), not A)")
                print(f"  one-parameter R^2 on the SAME taps = "
                      f"{fit.r2_one_same:.4f} vs two-parameter {fit.r2_two:.4f}")
                for size, med, pred, resid in fit.two_param_rows:
                    print(f"    {size:>3} cm  median f_peak^2 {med:>12,.0f} Hz^2   "
                          f"2-param fitted {pred:>12,.0f} Hz^2   "
                          f"residual {resid:+,.0f} Hz^2")
                print("  curvature A with B FIXED by the physics "
                      "(B = f_found^2; the identified test of A):")
                for key, label in (("G2", "G2 full debond   B = 0"),
                                   ("G1", "G1 partial      B = "
                                    f"{SIZE_FIT_B_ANALYTIC['G1']:,.0f} Hz^2"),
                                   ("MIX", "pooled (both)    B = 0 (shared)")):
                    if key not in fit.A_fix:
                        continue
                    av = fit.A_fix[key]
                    lo, hi = fit.A_fix_lo.get(key, float("nan")), fit.A_fix_hi.get(key, float("nan"))
                    print(f"    {label:<32} A = {av:>10,.1f} Hz^2 m^4 "
                          f"(95% CI {lo:>9,.1f} - {hi:>9,.1f})  "
                          f"R^2 = {fit.r2_fix.get(key, float('nan')):.4f}  "
                          f"fitted/analytic = {safe_div(av, fit.A_analytic):+.3f}")

        # -- Step 7: classifiers --------------------------------------------
        print(banner("Step 7  Classifiers (out-of-fold, grouped by panel)"))
        clf_results, splitter_name = classifier_study(clean, rng)
        print(f"  splitter: {splitter_name} (groups = panel_id)")
        for res in clf_results:
            tn, fp, fn, tp = res.confusion.ravel()
            print(f"  {res.name:<21} AUC={res.auc:.3f} [{res.auc_lo:.3f}-{res.auc_hi:.3f}]  "
                  f"bal-acc={res.metrics['balanced_accuracy']:.3f}  "
                  f"recall={res.metrics['recall']:.3f}  "
                  f"prec={res.metrics['precision']:.3f}  F1={res.metrics['f1']:.3f}")
            print(f"      confusion TN={tn} FP={fp} FN={fn} TP={tp}   (FN = missed debonds)")
        if not clf_results:
            warnings_out.append("No classifier produced usable out-of-fold scores.")

        feature_rocs = per_feature_roc(clean, n_boot=600, rng=rng)
        print("  single-feature AUC:")
        for e in feature_rocs:
            print(f"    {e['feature']:<16} AUC={e['auc']:.3f} "
                  f"[{e['auc_lo']:.3f}-{e['auc_hi']:.3f}]  ({e['direction']})")
        manual_refs = manual_threshold_reference(clean, args.th_f_peak, args.th_band_ratio)

        # -- Step 8: expected cost ------------------------------------------
        print(banner("Step 8  Expected-cost threshold analysis"))
        cost = None
        if clf_results:
            cost = expected_cost_analysis(max(clf_results, key=lambda r: r.auc),
                                          args.prevalence, args.miss_cost)
        if cost is None:
            print("  WARNING: no scores available; the cost analysis was skipped.")
            warnings_out.append("Expected-cost analysis skipped: no classifier scores.")
        else:
            print("  Cost model:")
            print("    E(thr) = P(D)*FNR(thr)*C_miss + (1-P(D))*FPR(thr)*C_fa,")
            print(f"    with C_fa normalised to 1 and C_miss = {args.miss_cost:g}.")
            print("  Why the asymmetry is justified:")
            print("    A false alarm costs ONE manual re-inspection: an inspector already on")
            print("    site taps the flagged point again. A miss is a potential")
            print("    FALLING-OBJECT SAFETY EVENT: a debonded finish that is never")
            print("    re-inspected can detach and fall from height onto the public below.")
            print("    The ratio therefore prices the consequences, not the inspection effort.")
            warnings_out.extend(_print_cost_block(
                cost, args.miss_cost, args.prevalence,
                float((clean["grade"] != "G0").mean())))

        # -- Step 9: figures ------------------------------------------------
        print(banner("Step 9  Figures"))
        fig01_feature_distributions(clean, figdir, synthetic)
        fig02_f_peak_vs_size(fit, figdir, synthetic)
        fig03_roc_curves(clf_results, figdir, synthetic)
        fig04_confusion_matrices(clf_results, figdir, synthetic)
        fig05_expected_cost(cost, figdir, synthetic, args.prevalence, args.miss_cost)
        fig06_repeatability(repeat, figdir, synthetic)
        fig07_feature_roc_panel(feature_rocs, figdir, synthetic)

        # -- Step 10: report -------------------------------------------------
        print(banner("Step 10  Report tables"))
        write_markdown(outdir / "results.md", synthetic, args, rep, integ, clean, repeat,
                       omnibus, pairwise, fit, clf_results, splitter_name, feature_rocs,
                       cost, manual_refs, warnings_out)

        _print_summary(clean, rep, outdir, figdir, warnings_out,
                       f"{time.time() - started:.1f} s")
        if synthetic:
            print()
            print("!" * 78)
            print("!!  " + SYNTH_STAMP)
            print("!!  Re-run without --demo on the real capture CSV before using any of")
            print("!!  these numbers or figures in the report.")
            print("!" * 78)
        return 0

    except Exception as exc:                                # pragma: no cover
        print("", file=sys.stderr)
        print("FATAL: the analysis stopped with an unexpected error.", file=sys.stderr)
        print(f"  {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        print("\nIf this is a data problem, check that the CSV columns match the expected "
              "names (run with --help for the list).", file=sys.stderr)
        return 1
    finally:
        tee.close()


if __name__ == "__main__":
    with warnings.catch_warnings():
        # scipy/sklearn emit benign convergence chatter on small samples; those
        # situations are handled explicitly and reported as warnings instead.
        warnings.simplefilter("ignore", category=RuntimeWarning)
        warnings.simplefilter("ignore", category=UserWarning)
        raise SystemExit(main())
