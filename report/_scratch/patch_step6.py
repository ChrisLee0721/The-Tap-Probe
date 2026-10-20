import pathlib

p = pathlib.Path(r"F:\Internet_of_thinks\report\06_analyze_tap.py")
src = p.read_text(encoding="utf-8")

i = src.index("two-parameter fit f_peak^2 = A/a^4 + B (a = radius")
i = src.rindex("\n", 0, src.rindex("print", 0, i)) + 1
j = src.index("# -- Step 7: classifiers", i)
j = src.rindex("\n", 0, j) + 1

new = '''            print("\\n  two-parameter fit f_peak^2 = A/a^4 + B (a = radius in "
                  "METRES), censored taps excluded")
            print(f"  taps used = {fit.n_used}, debonded taps dropped as censored = "
                  f"{fit.n_excluded}; radii surviving = "
                  f"{[int(s) for s in fit.fit_sizes]} "
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

'''

out = src[:i] + new + src[j:]
p.write_text(out, encoding="utf-8")
import ast
ast.parse(out)
print("ok")
