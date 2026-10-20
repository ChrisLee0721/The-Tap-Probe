        ["Model", "Fit basis", "Coefficients (95% CI)", "R^2", "n used", "n excluded"],
        [["1. `f_peak = C / size_cm^2` (headline, one parameter)",
          "class medians, all debonded classes",
          f"C = {fit.C:,.0f} Hz.cm^2 ({fit.C_lo:,.0f} - {fit.C_hi:,.0f})",
          f"{fit.r2:.4f}", f"{int(fit.counts.sum())} debonded taps", "0"],
         ["2. `f_peak^2 = A / a^4 + B` (a in **metres**)",
          "individual taps, censored ones dropped",
          (f"A = {fit.A:,.3f} Hz^2 m^4 ({fit.A_lo:,.3f} - {fit.A_hi:,.3f}); "
           f"B = {fit.B:,.1f} Hz^2 ({fit.B_lo:,.1f} - {fit.B_hi:,.1f})"
           if np.isfinite(fit.A) else "n/a - fewer than two distinct radii survive"),
          f"{fit.r2_two:.4f}" if np.isfinite(fit.r2_two) else "n/a",
          str(fit.n_used), str(fit.n_excluded)],
         ["3. `f_peak^2 = A' / size_cm^4 + B'` (size_cm convention)",
          "same taps as model 2",
          (f"A' = {fit.A_scm:.4g} Hz^2 cm^4 ({fit.A_scm_lo:.4g} - {fit.A_scm_hi:.4g}); "
           f"B' = {fit.B:,.1f} Hz^2 ({fit.B_lo:,.1f} - {fit.B_hi:,.1f})"
           if np.isfinite(fit.A_scm) else "n/a"),
          f"{fit.r2_two:.4f}" if np.isfinite(fit.r2_two) else "n/a",
          str(fit.n_used), str(fit.n_excluded)]))