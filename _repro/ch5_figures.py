#!/usr/bin/env python3
"""
ch5_figures.py — generate the Chapter 5 model figures for the EEE4483 report.

These are ANALYTIC figures: they plot the closed-form model of report section 5.1,
not measurements. They carry no SYNTHETIC stamp because they are not a dataset —
they are the model itself, and the report labels them "Analytic" in Appendix E.

Run:  python -I ch5_figures.py --outdir ../results/figures
Deps: numpy, matplotlib

Feeds:
  fig_m1_f1_vs_diameter.png   -> section 5.4 / Table 5.3
  fig_m2_detection_limits.png -> section 5.5 / Table 5.4
  fig_m3_pulse_energy.png     -> section 5.6 / Table 5.5
  fig_m4_helmholtz.png        -> section 5.9 / Table 5.6

Colour: a single-hue ordinal ramp per material, colour-blind safe, and every series
also carries its own marker + linestyle so the figure survives greyscale printing.
"""

from __future__ import annotations

import argparse
import os
from typing import Dict, List, Sequence, Tuple

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ----- design tokens (consistent with the report's chart language) -----------
INK = "#1a1a1a"
MUTED = "#6b6b6b"
GRID = "#d9d9d9"
BAND_FILL = "#eef3fa"
# ordinal ramp, dark -> light, readable in greyscale
RAMP = ["#12457f", "#2a78d6", "#7aa9e8", "#b9d2f2"]
CRITICAL = "#c0392b"

SETTINGS = {
    "font.size": 9,
    "axes.edgecolor": MUTED,
    "axes.labelcolor": INK,
    "axes.titlesize": 10,
    "axes.titleweight": "semibold",
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "grid.color": GRID,
    "grid.linewidth": 0.5,
    "legend.frameon": False,
}

FMIN, FMAX = 300.0, 15000.0           # analysis band (matches PROBE_FMIN/FMAX_HZ)
K_BOND, K_PART, K_FREE = 9.0e11, 1.0e10, 0.0

MATERIALS: Dict[str, Dict[str, float]] = {
    "Ceramic tile 8 mm":      dict(h=0.008, E=55e9, rho=2400.0, nu=0.22, Q=20.0),
    "Cement render 20 mm":    dict(h=0.020, E=18e9, rho=2000.0, nu=0.20, Q=10.0),
    "Stone cladding 25 mm":   dict(h=0.025, E=40e9, rho=2600.0, nu=0.25, Q=15.0),
}

ALPHA_NUM = 3.19595                    # (alpha*a)^2 for clamped circular mode (0,1)


def f1(k: float | np.ndarray, a: np.ndarray, m: Dict[str, float]) -> np.ndarray:
    """Fundamental frequency [Hz] of a clamped circular plate on a Winkler foundation."""
    D = m["E"] * m["h"] ** 3 / (12.0 * (1.0 - m["nu"] ** 2))
    return (1.0 / (2.0 * np.pi)) * np.sqrt(
        (D * ALPHA_NUM ** 4 / a ** 4 + k) / (m["rho"] * m["h"])
    )


def _style(ax, title: str = "", xlabel: str = "", ylabel: str = "") -> None:
    ax.grid(True, which="major", axis="both")
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    if title:
        ax.set_title(title, loc="left")
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)


# ---------------------------------------------------------------------------
# M1 — f1 vs debond diameter, all three materials, both bond states
# ---------------------------------------------------------------------------
def fig_m1(outdir: str) -> str:
    d_mm = np.linspace(40.0, 400.0, 900)      # diameter in mm
    a = (d_mm / 1000.0) / 2.0                 # radius in m
    fig, axes = plt.subplots(1, 3, figsize=(11.0, 3.6), sharey=True)
    styles = [(K_FREE, "fully debonded", "o"),
              (K_PART, "partially bonded", "s"),
              (K_BOND, "intact (bonded)", "^")]

    for ax, (name, m) in zip(axes, MATERIALS.items()):
        ax.axhspan(FMIN, FMAX, color=BAND_FILL, zorder=0)
        if ax is axes[0]:
            ax.text(52, FMAX * 0.55, "analysis band\n300 Hz – 15 kHz",
                    fontsize=7.4, color=MUTED, va="top", ha="left")
        for i, (k, label, marker) in enumerate(styles):
            y = f1(k, a, m)
            ax.plot(d_mm, y, color=RAMP[i], lw=1.6, ls="-", marker=marker,
                    markevery=110, ms=3.6, label=label)
        ax.set_yscale("log")
        ax.set_ylim(FMIN * 0.7, 5e5)
        ax.set_xlim(40, 400)
        _style(ax, title=name, xlabel="debond diameter [mm]",
               ylabel="fundamental frequency $f_1$ [Hz]" if ax is axes[0] else "")
        # annotate where the fully-debonded curve enters the band
        yf = f1(K_FREE, a, m)
        idx = np.where(yf <= FMAX)[0]
        if idx.size:
            d_in = d_mm[idx[0]]
            ax.axvline(d_in, color=CRITICAL, lw=1.0, ls=(0, (4, 2)), zorder=1)
            ax.annotate(f"{d_in/10:.1f} cm", xy=(d_in, FMAX),
                        xytext=(d_in + 22, FMAX * 2.3), color=CRITICAL, fontsize=8,
                        arrowprops=dict(arrowstyle="-", color=CRITICAL, lw=0.8))
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=8.2,
               bbox_to_anchor=(0.5, -0.015))
    fig.suptitle("Figure M1 — Modelled fundamental frequency of a debonded finish layer\n"
                 "Clamped circular plate on a Winkler foundation; dashed red marks the size at which "
                 "a fully debonded region first rings inside the analysis band",
                 x=0.01, ha="left", fontsize=9.4, color=INK)
    fig.tight_layout(rect=(0, 0.075, 1, 0.90))
    path = os.path.join(outdir, "fig_m1_f1_vs_diameter.png")
    fig.savefig(path, dpi=300)
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# M2 — the detection limit is 2-D (size x bond stiffness), not a size alone
# ---------------------------------------------------------------------------
def _kth(a: float, m: Dict[str, float], fmax: float = FMAX) -> float:
    """Largest bond stiffness still ringing inside the band at radius a. <=0 means
    the fully-debonded tone is already above the band, i.e. below the size floor."""
    D = m["E"] * m["h"] ** 3 / (12.0 * (1.0 - m["nu"] ** 2))
    return (2.0 * np.pi * fmax) ** 2 * m["rho"] * m["h"] - D * ALPHA_NUM ** 4 / a ** 4


def fig_m2(outdir: str) -> str:
    K_BOND_REF = 9.0e11
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.6, 3.5))

    # --- left: the size floor (fully debonded) -----------------------------
    names: List[str] = []
    dmin: List[float] = []
    for name, m in MATERIALS.items():
        lo, hi = 0.002, 0.6
        for _ in range(200):
            mid = (lo + hi) / 2.0
            if float(f1(K_FREE, np.array(mid), m)) > FMAX:
                lo = mid
            else:
                hi = mid
        names.append(name)
        dmin.append(2.0 * hi * 1000.0)

    ypos = np.arange(len(names))
    ax1.barh(ypos, dmin, color=RAMP[1], height=0.5)
    for y, v in zip(ypos, dmin):
        ax1.text(v + 4, y, f"{v/10:.1f} cm", va="center", fontsize=8.4, color=INK)
    ax1.set_yticks(ypos)
    ax1.set_yticklabels(names, fontsize=8.4)
    ax1.set_xlim(0, max(dmin) * 1.45)
    ax1.invert_yaxis()
    _style(ax1, title="Size floor (fully debonded, $k\\to0$)",
           xlabel="diameter [mm]")

    # --- right: k_th(a) as a fraction of intact, i.e. the usable k window ---
    d_mm = np.linspace(70.0, 400.0, 700)
    for i, (name, m) in enumerate(MATERIALS.items()):
        frac = np.array([_kth(0.5 * d / 1000.0, m) / K_BOND_REF * 100.0 for d in d_mm])
        frac = np.where(frac <= 0.0, np.nan, np.minimum(frac, 100.0))
        ax2.plot(d_mm, frac, color=RAMP[i], lw=1.7, ls="-",
                 marker=("o", "s", "^")[i], markevery=70, ms=4.0, label=name)
    ax2.axhline(100.0, color=MUTED, lw=0.8, ls=":")
    ax2.text(76, 103, "intact bond", fontsize=7.6, color=MUTED)
    ax2.set_ylim(0, 108)
    ax2.set_xlim(70, 400)
    _style(ax2, title="Bond stiffness still observable, at that size",
           xlabel="debond diameter [mm]",
           ylabel="observable $k$ range [% of intact bond]")
    ax2.legend(loc="lower right", fontsize=7.8)

    fig.suptitle("Figure M2 — The detection limit is two-dimensional: a size floor alone overstates "
                 "the capability.\nAt the floor only a near-free plate is visible; the observable "
                 "bond-stiffness window widens with size, then saturates.",
                 x=0.01, ha="left", fontsize=9.4, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    path = os.path.join(outdir, "fig_m2_detection_limits.png")
    fig.savefig(path, dpi=300)
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# M3 — strike pulse energy fraction vs contact time
# ---------------------------------------------------------------------------
def _energy_fraction(fc: float, T: float) -> float:
    f = np.linspace(1.0, 60000.0, 240000)
    A = np.cos(np.pi * f * T / 2.0) / (1.0 - (f * T) ** 2)
    P = A ** 2
    return float(np.trapezoid(P[f <= fc], f[f <= fc]) / np.trapezoid(P, f))


def fig_m3(outdir: str) -> str:
    Ts = np.logspace(np.log10(40e-6), np.log10(2500e-6), 220)
    bands: Sequence[Tuple[float, str, str]] = [
        (2000.0, "energy below 2 kHz", "o"),
        (5000.0, "energy below 5 kHz", "s"),
        (15000.0, "energy below 15 kHz (whole band)", "^"),
    ]
    fig, ax = plt.subplots(figsize=(6.6, 3.6))
    for i, (fc, label, marker) in enumerate(bands):
        y = [_energy_fraction(fc, T) for T in Ts]
        ax.plot(Ts * 1e6, y, color=RAMP[i], lw=1.6, ls="-", marker=marker,
                markevery=22, ms=3.6, label=label)
    ax.axvline(300.0, color=CRITICAL, lw=1.0, ls=(0, (4, 2)))
    ax.annotate("selected: T = 300 µs\n(null at 5 kHz)", xy=(300.0, 0.45),
                xytext=(430.0, 0.30), color=CRITICAL, fontsize=8,
                arrowprops=dict(arrowstyle="->", color=CRITICAL, lw=0.8))
    ax.set_xscale("log")
    ax.set_xlim(40, 2500)
    ax.set_ylim(0, 1.02)
    _style(ax, title="Strike excitation: how much of the energy lands in the analysis band",
           xlabel="contact time $T$ [µs]", ylabel="fraction of strike energy")
    ax.legend(loc="center left", fontsize=8)
    fig.suptitle("Figure M3 — Half-sine strike pulse. Long contact times cannot excite the "
                 "higher wall modes at all.",
                 x=0.01, ha="left", fontsize=9.4, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    path = os.path.join(outdir, "fig_m3_pulse_energy.png")
    fig.savefig(path, dpi=300)
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# M4 — microphone cavity Helmholtz resonance
# ---------------------------------------------------------------------------
def fig_m4(outdir: str) -> str:
    c = 343.0
    V = np.linspace(20.0, 1200.0, 400)          # mm^3
    ports: Sequence[Tuple[float, float, str, str]] = [
        (3.0, 3.0, "port 3.0 mm, L 3.0 mm", "o"),
        (2.0, 1.5, "port 2.0 mm, L 1.5 mm", "s"),
        (1.5, 1.0, "port 1.5 mm, L 1.0 mm", "^"),
        (1.0, 0.8, "port 1.0 mm, L 0.8 mm", "D"),
    ]
    fig, ax = plt.subplots(figsize=(6.6, 3.6))
    ax.axhspan(FMIN, FMAX, color=BAND_FILL, zorder=0, label="analysis band")
    for i, (d, L, label, marker) in enumerate(ports):
        A = np.pi * ((d * 1e-3) / 2.0) ** 2
        fh = (c / (2.0 * np.pi)) * np.sqrt(A / ((V * 1e-9) * (L * 1e-3)))
        ax.plot(V, fh, color=RAMP[i], lw=1.6, ls="-", marker=marker,
                markevery=40, ms=3.6, label=label)
    ax.axvline(200.0, color=CRITICAL, lw=1.0, ls=(0, (4, 2)))
    ax.annotate("design target: V ≤ 200 mm³\n(seal the cavity)", xy=(200.0, FMAX * 0.75),
                xytext=(280.0, FMAX * 1.7), color=CRITICAL, fontsize=8,
                arrowprops=dict(arrowstyle="->", color=CRITICAL, lw=0.8))
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(20, 1200)
    ax.set_ylim(FMIN * 0.7, 3e4)
    _style(ax, title="Probe front-cavity resonance vs cavity volume",
           xlabel="cavity volume $V$ [mm³]", ylabel="Helmholtz frequency $f_H$ [Hz]")
    ax.legend(loc="lower left", fontsize=7.6)
    fig.suptitle("Figure M4 — $f_H = (c/2\\pi)\\sqrt{A/VL}$. An unminimised cavity resonates "
                 "inside the measurement band,\ninjecting a contact-dependent artefact.",
                 x=0.01, ha="left", fontsize=9.4, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    path = os.path.join(outdir, "fig_m4_helmholtz.png")
    fig.savefig(path, dpi=300)
    plt.close(fig)
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", default=".")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    plt.rcParams.update(SETTINGS)
    for fn in (fig_m1, fig_m2, fig_m3, fig_m4):
        print("wrote", fn(args.outdir))


if __name__ == "__main__":
    main()
