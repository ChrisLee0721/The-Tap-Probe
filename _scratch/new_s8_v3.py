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
    present = sorted(int(s) for s in debonded["size_cm"].unique())
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
            excluded.append((grades, int(s), float(np.median(sub["f_peak_hz"])),
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

    # ---- bootstrap over panels, shared by both models and both CIs --------
    uniq = np.unique(panel_all)
    boots_C, boots_A, boots_B = [], [], []
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

    def _ci(vals: Sequence[float]) -> Tuple[float, float]:
        arr = np.asarray(vals, dtype=float)
        arr = arr[np.isfinite(arr)]
        if arr.size < 20:
            return float("nan"), float("nan")
        return float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))

    C_lo, C_hi = _ci(boots_C)
    A_lo, A_hi = _ci(boots_A)
    B_lo, B_hi = _ci(boots_B)

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
        two_param_rows=two_param_rows)


