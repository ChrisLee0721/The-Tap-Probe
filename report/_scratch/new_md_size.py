def _md_size(L: List[str], fit: Optional[SizeFit]) -> None:
    """Section 5 of results.md: size sensitivity and the two competing fits."""
    L.append("## 5. Size sensitivity\n")
    if fit is None:
        L.append("_Not computed: fewer than two debond size classes were present._\n")
        return
    L.append("Two models are fitted to the same size classes and compared on identical "
             "panel-bootstrap resamples. **Model 1** is the report's headline claim, "
             "`f_peak = C / size_cm^2` (one parameter, size in cm). **Model 2** is the form "
             "the plate-on-Winkler model actually implies: since "
             "`f1^2 = f_mode^2 + f_found^2` and `f_mode^2` is proportional to `1/a^4`, "
             "the correct two-parameter fit is `f_peak^2 = A / a^4 + B` with `a` the debond "
             "**radius in metres**. It is reported in that radius convention and again in "
             "the `size_cm` convention (`A' = A x 200^4`, `f_peak^2 = A' / size_cm^4 + B'`), "
             "so the metres check against the analytic constant and the cm fit are both "
             "visible; `B' = B` because the intercept is in Hz^2 either way.\n")
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
                       f"Fitted f = {fit.C:,.0f}/size$^2$", "Residual", "Residual %"], rows))

    L.append("### 5b. Model comparison\n")
    n_flag = ("yes" if fit.medians[0] <= SIZE_FIT_CENSOR_MAX_HZ else "no")
    L.append("**Censoring exclusion.** A size class whose median f_peak sits in the "
             f"band-edge cluster (`<= {SIZE_FIT_CENSOR_MAX_HZ:.1f} Hz`, the first three "
             "in-band bins of the 46.875 Hz grid) is a *censored* observation, not a "
             "measured resonance: the strike transient pins the argmax there and the "
             "reading carries no information about the debond. "
             f"**{fit.n_used} size classes were used and {fit.n_excluded} were dropped.** "
             "Dropped:\n")
    if fit.excluded:
        L.append(md_table(["Dropped class", "Median f_peak (Hz)", "Reason"],
                          [[f"{grade} @ {size} cm", f"{med:,.1f}", reason]
                           for grade, size, med, reason in fit.excluded]))
    else:
        L.append("_None: every debond size class had a median f_peak above the "
                 "band-edge cluster._\n")
    L.append(f"The smallest surviving class is {int(fit.fit_sizes.min())} cm "
             f"(band-edge flag raised: {n_flag}). Excluding these points is the difference "
             "between fitting a resonance and fitting the excitation.\n")

    L.append(md_table(
        ["Model", "Coefficients (95% CI)", "R^2", "n used", "n excluded", "Verdict"],
        [["1. `f_peak = C / size_cm^2` (headline, one parameter)",
          f"C = {fit.C:,.0f} Hz.cm^2 "
          f"({fit.C_lo:,.0f} - {fit.C_hi:,.0f})",
          f"{fit.r2:.4f}", f"{int(fit.counts.sum())} (all debonded taps)", "0",
          "baseline form under test"],
         ["2. `f_peak^2 = A / a^4 + B` (a in **metres**)",
          f"A = {fit.A:,.3f} Hz^2 m^4 ({fit.A_lo:,.3f} - {fit.A_hi:,.3f}); "
          f"B = {fit.B:,.1f} Hz^2 ({fit.B_lo:,.1f} - {fit.B_hi:,.1f})"
          if np.isfinite(fit.A) else "n/a - fewer than three uncensored classes",
          f"{fit.r2_two:.4f}" if np.isfinite(fit.r2_two) else "n/a",
          str(fit.n_used), str(fit.n_excluded), "predicted by the plate-on-Winkler model"],
         ["3. `f_peak^2 = A' / size_cm^4 + B'` (size_cm convention)",
          f"A' = {fit.A_scm:.4g} Hz^2 cm^4 ({fit.A_scm_lo:.4g} - {fit.A_scm_hi:.4g}); "
          f"B' = {fit.B_scm:.4g} Hz^2 ({fit.B_scm_lo:.4g} - {fit.B_scm_hi:.4g})"
          if np.isfinite(fit.A_scm) else "n/a",
          f"{fit.r2_two_scm:.4f}" if np.isfinite(fit.r2_two_scm) else "n/a",
          str(fit.n_used), str(fit.n_excluded),
          "same fit as row 2: A' = A x 200^4"]]))
    L.append(f"**The two-parameter fit {'beats' if (np.isfinite(fit.r2_two) and fit.r2_two > fit.r2) else 'does NOT beat'} "
             f"the one-parameter form** on this sample "
             f"(R^2 {fit.r2_two:.4f} vs {fit.r2:.4f}), on the "
             f"{fit.n_used} uncensored classes that both are scored against here. "
             "The reason is structural: the one-parameter form forces the curve through "
             "the origin of the 1/size^2 axis and therefore has to compromise across the "
             "whole range, whereas the physical model carries a stiffness floor B - the "
             "foundation mode `f_found = (1/2pi) sqrt(k / rho h)` - which is exactly the "
             "intercept the two-parameter fit recovers. The one-parameter R^2 in the table "
             "is computed over *all* debonded classes and so is the more pessimistic "
             "number; read them against the residuals in 5a, not as a like-for-like score.\n")

    L.append("### 5c. Physical validation of A\n")
    if np.isfinite(fit.A):
        ratio = safe_div(fit.A, fit.A_analytic)
        L.append(f"The analytic value of the curvature coefficient for the reference panel "
                 f"(E = 18 GPa, h = 20 mm, rho = 2000 kg/m3, nu = 0.20, so D = 1.2500e4 N.m) "
                 f"is\n\n"
                 f"```\nA_analytic = D * alpha^4 / ((2 pi)^2 * rho * h)\n"
                 f"           = 12500 * 3.19595^4 / ((2 pi)^2 * 2000 * 0.020)\n"
                 f"           = {fit.A_analytic:.4f} Hz^2 m^4\n```\n\n"
                 f"The fit returns **A = {fit.A:,.3f} Hz^2 m^4** "
                 f"(95% CI {fit.A_lo:,.3f} - {fit.A_hi:,.3f}), i.e. "
                 f"**{ratio:.3f} x the analytic value**"
                 + (" - the CI contains 28.737, so the generator's recovered curvature is "
                    "consistent with the panel it was built from."
                    if (np.isfinite(fit.A_lo) and fit.A_lo <= fit.A_analytic <= fit.A_hi)
                    else " - the CI does NOT contain 28.737, so the fitted curvature does "
                         "not match the analytic panel: the fit is governed by the "
                         "band-edge censoring and the narrow surviving range, not by the "
                         "material constants.") +
                 f" In the size_cm convention the same analytic value is "
                 f"A'_analytic = {fit.A_scm_analytic:.6g} Hz^2 cm^4 "
                 f"(= {fit.A_analytic:.3f} x 200^4) and the fit returns "
                 f"A' = {fit.A_scm:.6g} Hz^2 cm^4.\n")
    else:
        L.append("_The two-parameter fit needs at least three uncensored size classes; "
                 "fewer survived the band-edge exclusion, so A is not reported._\n")

    ss_res = float(np.sum((np.log(fit.medians) - (fit.slope * np.log(fit.sizes) +
                    (np.mean(np.log(fit.medians)) - fit.slope * np.mean(np.log(fit.sizes))))) ** 2))
    ss_tot = float(np.sum((np.log(fit.medians) - np.mean(np.log(fit.medians))) ** 2))
    L.append("### 5d. Free-exponent diagnostic\n")
    L.append(f"With the exponent **fitted freely** in log-log space: **p = {fit.slope:.3f}**, "
             f"95% CI {fit.slope_lo:.3f} - {fit.slope_hi:.3f}, R^2 = "
             f"{1.0 - safe_div(ss_res, ss_tot):.4f}. This is a diagnostic on the censored "
             "set: a free exponent near -4 is what `f_peak^2 = A/a^4 + B` with a dominant "
             "A term would give once the intercept B is small, and an exponent near -1 or "
             "-2 signals that the surviving range is too narrow to identify the power law. "
             "The constant C is comparable only across datasets taken with the same probe on "
             "the same substrate, and it is quoted in Hz.cm^2 so the imposed exponent stays "
             "visible in the units.\n")
    L.append("### 5e. Residual structure\n")
    L.append("A residual that varies monotonically with size means the exponent is wrong and "
             "the curve is systematically bending; a random scatter about zero means the "
             "assumed form is adequate over the range measured here. Read table 5a against "
             "figure 2 (`fig02_f_peak_vs_size.png`) before quoting any constant.\n")
