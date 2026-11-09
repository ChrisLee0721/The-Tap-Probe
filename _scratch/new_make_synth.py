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
      * the same is true of every debond up to 5 cm radius: f1 = 46-128 kHz, so
        those classes collapse onto the identical 328 Hz transient peak and are
        genuinely confusable with the bonded control;
      * only f1 below the 15 kHz band top moves f_peak, i.e. only a full debond
        of 7 cm radius or more (11.5, 5.1, 2.9 kHz at 10, 15, 20 cm);
      * a strong G1 (k = 1e10) bottoms out at f_found = 2.52 kHz, so at 20 cm
        its f1 = 3.82 kHz is inside the band and it is therefore NOT
        indistinguishable from G0 after all - one of the chapter's expectations
        that this generator contradicts;
      * decay_tau_ms is unmeasurable for every bonded region and for every
        partially bonded one, and bimodal (floor vs -1.0 sentinel) for a full
        debond, so it cannot separate the classes on its own.
    """
    rng = np.random.default_rng(seed)
    rows: List[Dict[str, Any]] = []
    counter = 0
    plan: List[Tuple[str, int]] = [("G0", 0)] * 3 + [
        (g, s) for s in (3, 5, 10, 15, 20) for g in ("G2", "G1")]

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
            # strength by how far inside the band it sits.
            size_factor = 1.0 if size == 0 else float(np.clip(size / 10.0, 0.30, 1.0))
            rad = 3.0 * size_factor * mode_eff
            bg = bg_eff
            f1 = f_resonance_hz(size, SYNTH_K_PA_PER_M[grade])

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
