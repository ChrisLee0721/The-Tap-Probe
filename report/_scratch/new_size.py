# ==========================================================================
# S8  Size sensitivity: the two-parameter resonance fit
# ==========================================================================

# A size class whose median f_peak sits in the band-edge cluster is a CENSORED
# observation, not a measured mode: the transient peak at 328 Hz (bins 7-9 of
# the 46.875 Hz grid) is all that is visible, so its "frequency" says nothing
# about the debond. The censoring boundary is the first three in-band bins.
SIZE_FIT_CENSOR_MAX_HZ = BAND_LO_HZ + 3.0 * _SYNTH_BIN_HZ     # 440.625 Hz

# Analytic value of the two-parameter fit's curvature coefficient, in METRES:
#   A = D alpha^4 / ((2pi)^2 rho h),  alpha = 3.19595
#     = 12500 * 3.19595^4 / ((2pi)^2 * 2000 * 0.020) = 28.737 Hz^2 m^4
SIZE_FIT_A_ANALYTIC = 28.737


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

    # ---- added for the two-parameter model f_peak^2 = A / a^4 + B ----------
    n_used: int = 0
    n_excluded: int = 0
    excluded: List[Tuple[str, int, float, str]] = field(default_factory=list)
    # ^ (grade, size_cm, median f_peak, reason) for every dropped size class
    fit_sizes: np.ndarray = field(default_factory=lambda: np.array([]))
    fit_a_m: np.ndarray = field(default_factory=lambda: np.array([]))
    fit_median: np.ndarray = field(default_factory=lambda: np.array([]))
    fit_n: np.ndarray = field(default_factory=lambda: np.array([]))
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
    B_scm: float = float("nan")
    B_scm_lo: float = float("nan")
    B_scm_hi: float = float("nan")
    r2_two_scm: float = float("nan")
    A_analytic: float = SIZE_FIT_A_ANALYTIC
    A_scm_analytic: float = SIZE_FIT_A_ANALYTIC * 200.0 ** 4   # 4.5979e10
    two_param_rows: List[Tuple[int, float, float, float]] = field(default_factory=list)


def _fit_two_param(x: np.ndarray, y: np.ndarray) -> Tuple[float, float, float]:
    """OLS of y = A*x + B. Returns (A, B, R^2) with R^2 relative to mean(y)."""
    if x.size < 3:
        return (float("nan"), float("nan"), float("nan"))
    design = np.vstack([x, np.ones_like(x)]).T
    coef = np.linalg.lstsq(design, y, rcond=None)[0]
    a, b = float(coef[0]), float(coef[1])
    pred = a * x + b
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - float(np.mean(y))) ** 2))
    return a, b, 1.0 - safe_div(ss_res, ss_tot)


def size_sensitivity(df: "pd.DataFrame",
                     rng: np.random.Generator) -> Optional[SizeFit]:
    """Median f_peak_hz vs debond size, with two competing resonance fits.

    Model 1 (the chapter's headline claim, one parameter, size in cm):
        f_peak = C / size_cm^2
    Model 2 (the two-parameter form that the plate-on-Winkler model actually
    implies, since f1^2 = f_mode^2 + f_found^2 and f_mode^2 is proportional to
    1/a^4) is fitted BOTH ways, and both are reported:
        radius convention :  f_peak^2 = A / a^4 + B,   a = size_cm/200 in METRES
        size_cm convention:  f_peak^2 = A' / size_cm^4 + B'
    The two are the same fit: a^4 = size_cm^4 / 200^4, so A' = A * 200^4. Both
    are shown because the metres form is what the analytic value is quoted in.

    Censoring. A size class whose median f_peak sits in the band-edge cluster
    (<= SIZE_FIT_CENSOR_MAX_HZ, the first three in-band bins) is not a mode
    measurement - the strike transient dominates and the reading is pinned at
    the band edge. Those classes (the bonded control and every small debond)
    are excluded from the fits, because including a pinned 328 Hz point would
    fit the excitation, not the structure. Only G2 and G1 classes whose f_peak
    genuinely rises above the transient cluster are used; how many points were
    used and dropped, and why, is reported in results.md.

    A is validated against the analytic value A = D alpha^4/((2pi)^2 rho h)
    = 28.737 Hz^2 m^4 for the reference panel (D = 1.25e4 N.m, alpha = 3.19595,
    rho = 2000 kg/m3, h = 0.020 m): A_analytic = A_analytic_scm / 200^4.

    Both CIs and both R^2 are percentile bootstraps over panels (the unit of
    independence), so the two models are compared on identical resamples.
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

    # ---- two-parameter model, censored classes dropped --------------------
    excluded: List[Tuple[str, int, float, str]] = []
    used_sizes: List[int] = []
    for s in present:
        sub = debonded[debonded["size_cm"] == s]
        if float(np.median(sub["f_peak_hz"])) <= SIZE_FIT_CENSOR_MAX_HZ:
            grades = "+".join(sorted(set(sub["grade"])))
            excluded.append((grades, int(s), float(np.median(sub["f_peak_hz"])),
                             "band-edge-pinned (censored): median f_peak "
                             f"<= {SIZE_FIT_CENSOR_MAX_HZ:.1f} Hz"))
            continue
        used_sizes.append(int(s))

    fit_sizes = np.array(used_sizes, dtype=float)
    fit_a_m = fit_sizes / 200.0                       # radius in METRES
    fit_median = np.array([float(np.median(debonded.loc[debonded["size_cm"] == s,
                                                         "f_peak_hz"]))
                           for s in used_sizes])
    fit_n = np.array([int((debonded["size_cm"] == s).sum()) for s in used_sizes])
    A = B = r2_two = float("nan")
    A_scm = B_scm = r2_two_scm = float("nan")
    if fit_sizes.size >= 3:
        A, B, r2_two = _fit_two_param(fit_a_m ** 4, fit_median ** 2)
        A_scm, B_scm, r2_two_scm = _fit_two_param(fit_sizes ** -4, fit_median ** 2)

    # ---- bootstrap over panels, shared by both models and both CIs --------
    panels = debonded["panel_id"].to_numpy()
    uniq = np.unique(panels)
    boots_C, boots_A, boots_B, boots_R2 = [], [], [], []
    boots_As, boots_Bs, boots_R2s = [], [], []
    for _ in range(2000):
        pick = rng.choice(uniq, size=uniq.size, replace=True)
        sub = debonded.iloc[np.concatenate([np.flatnonzero(panels == p) for p in pick])]

        vals = []
        for s in present:
            arr = sub.loc[sub["size_cm"] == s, "f_peak_hz"].to_numpy(dtype=float)
            arr = arr[np.isfinite(arr)]
            vals.append(float(np.median(arr)) if arr.size else float("nan"))
        vals_arr = np.asarray(vals, dtype=float)
        good = np.isfinite(vals_arr) & (vals_arr > 0)
        if int(good.sum()) >= 2:
            boots_C.append(float(np.exp(np.mean(np.log(vals_arr[good]) + 2.0 * x[good]))))

        # the two-parameter fits, on the classes that are not censored in this
        # resample either - the censoring rule is re-applied, not frozen
        keep_s, keep_m = [], []
        for s, m_obs in zip(fit_sizes, fit_median):
            arr = sub.loc[sub["size_cm"] == int(s), "f_peak_hz"].to_numpy(dtype=float)
            arr = arr[np.isfinite(arr)]
            if arr.size == 0:
                continue
            m = float(np.median(arr))
            if m > SIZE_FIT_CENSOR_MAX_HZ:
                keep_s.append(float(s))
                keep_m.append(m)
        if len(keep_s) >= 3:
            ks, km = np.array(keep_s), np.array(keep_m)
            a_s, b_s, r_s = _fit_two_param(ks ** -4, km ** 2)
            boots_As.append(a_s)
            boots_Bs.append(b_s)
            boots_R2s.append(r_s)
            boots_A.append(a_s * 200.0 ** 4)
            boots_B.append(b_s)
            boots_R2.append(r_s)

    def _ci(vals: Sequence[float]) -> Tuple[float, float]:
        arr = np.asarray(vals, dtype=float)
        arr = arr[np.isfinite(arr)]
        if arr.size < 20:
            return float("nan"), float("nan")
        return float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))

    C_lo, C_hi = _ci(boots_C)
    A_lo, A_hi = _ci(boots_A)
    B_lo, B_hi = _ci(boots_B)
    A_scm_lo, A_scm_hi = _ci(boots_As)
    B_scm_lo, B_scm_hi = _ci(boots_Bs)
    r2_two = float(np.median(boots_R2)) if len(boots_R2) >= 20 else r2_two

    two_param_rows = []
    if fit_sizes.size:
        pred = A * fit_a_m ** 4 + B
        two_param_rows = [(int(s), float(m), float(p), float(m - p))
                          for s, m, p in zip(fit_sizes, fit_median, pred)]
    residuals = [(int(s), float(m), float(C / s ** 2), float(m - C / s ** 2))
                 for s, m in zip(present, medians)]
    return SizeFit(
        sizes, medians, q1, q3, counts, C, C_lo, C_hi, float(r2),
        float(slope), slope_lo, slope_hi, residuals,
        n_used=int(fit_sizes.size), n_excluded=int(len(excluded)), excluded=excluded,
        fit_sizes=fit_sizes, fit_a_m=fit_a_m, fit_median=fit_median, fit_n=fit_n,
        A=A, A_lo=A_lo, A_hi=A_hi, B=B, B_lo=B_lo, B_hi=B_hi,
        r2_two=r2_two if np.isfinite(r2_two) else float("nan"),
        A_scm=A_scm, A_scm_lo=A_scm_lo, A_scm_hi=A_scm_hi,
        B_scm=B_scm, B_scm_lo=B_scm_lo, B_scm_hi=B_scm_hi,
        r2_two_scm=r2_two_scm, two_param_rows=two_param_rows)


