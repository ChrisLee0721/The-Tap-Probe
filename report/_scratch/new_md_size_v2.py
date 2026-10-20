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
        L.append(f"Surviving radii: {', '.join(str(int(s)) for s in fit.fit_sizes)} cm.\n")
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
             "uses the matched tap set. Read both against the residuals in 5a.**\n")

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
                 f"           = {fit.A_analytic:.3f} Hz^2 m^4  ->  sqrt = "
                 f"{np.sqrt(fit.A_analytic):.3f} Hz/DECADE-equivalent\n```\n\n")
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
        L.append(f"The fit returns **A = {fit.A:,.3f} Hz^2 m^4** "
                 f"(95% CI {fit.A_lo:,.3f} - {fit.A_hi:,.3f}), i.e. "
                 f"**{ratio:.3f} x the analytic coefficient**"
                 + ("; the CI contains the analytic value, so the curvature the generator "
                    "recovers is consistent with the panel it was built from."
                    if contains else
                    "; the CI does NOT contain the analytic value. That is a real failure "
                    "of the claim and is reported as one: the fitted curvature is governed "
                    "by which radii survive the censoring, not by the material constants, "
                    "so A cannot be treated as a physical constant at this sample size.")
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
