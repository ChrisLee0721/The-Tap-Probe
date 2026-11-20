#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tap-probe real-time analysis service.

Subscribes to the probe MQTT topics defined in PROTOCOL.md, turns every
``probe/<dev>/waveform`` packet into the feature vector produced by
``06_analyze_tap.py::extract_features_from_waveform`` and serves the result to
dashboard.html over HTTP + WebSocket on port 8082.

Design notes
------------
* The feature code is NOT re-implemented here.  The template at the repository
  root is loaded by path with importlib and its
  ``extract_features_from_waveform`` is called for every tap.
* The template hard-codes the analysis band to 300..15000 Hz with a 1 kHz
  crossover (it was written for a 44.1 kHz I2S microphone).  At LSM6DS3 rates
  (a few hundred Hz) that band is empty and the template raises ValueError.
  PROTOCOL.md section 6 therefore mandates
  ``band = [band_lo_hz, 0.45*fs]`` and ``crossover = 0.45*fs/3``.
  The template has no band arguments, so the three band literals inside the
  function body are parameterised at load time from the template's own source
  (``inspect.getsource`` -> three literal substitutions -> ``exec`` in the
  template module namespace).  The algorithm, every other line and every
  helper (``safe_div``, ``cv_percent``, ``describe``) stay the template's.
  ``/api/health`` publishes the template sha256 and the transformation used,
  and calling the transformed function with the template defaults reproduces
  the template bit-for-bit (checked in verify.md).
* ``band_ratio_lh <= th_band_ratio`` -> DEBOND, otherwise BONDED (PROTOCOL.md
  section 6).  The threshold is a config value, not a literal in the HTML.

Usage
-----
    python analyzer.py                       # broker 127.0.0.1:1883, HTTP :8082
    python analyzer.py --broker 192.168.3.12 --http-port 8082

Endpoints
---------
    GET  /api/health
    GET  /api/latest
    GET  /api/history?limit=50
    GET  /api/stats
    GET  /api/config           POST /api/config
    GET  /api/stream           (WebSocket)
    POST /api/cmd
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import inspect
import json
import math
import sys
import textwrap
import threading
import time
from collections import Counter, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import parse_qs, urlparse

import numpy as np

try:
    import paho.mqtt.client as mqtt
except ImportError:                                          # pragma: no cover
    sys.stderr.write("FATAL: paho-mqtt is required.\n  pip install paho-mqtt\n")
    raise SystemExit(2)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_BROKER = "127.0.0.1"
DEFAULT_BROKER_PORT = 1883
DEFAULT_HTTP_PORT = 8082
DEFAULT_DEVICE = "probe-01"
DEFAULT_TH_BAND_RATIO = 0.45
DEFAULT_BAND_LO_HZ = 30.0
DEFAULT_WINDOW = 200

# Session persistence.  A survey is a physical procedure: the operator taps a
# wall for twenty minutes and the numbers are the only record of it.  Keeping
# them in RAM meant every restart of this service -- a code change, a crash, a
# reboot of the PC -- silently threw the session away, and the next restart
# compared nothing.  Taps are appended to a JSONL file as they arrive; only
# real taps are stored, so a simulator run can never be replayed as a survey.
SESSION_DIR = Path(__file__).resolve().parent / ".session"
SESSION_TAPS = SESSION_DIR / "taps.jsonl"
SESSION_REF = SESSION_DIR / "reference.json"

# -- differential grading (PROTOCOL.md section 7) ---------------------------
# Two-level rule on rho = band_ratio_lh(point) / band_ratio_lh(reference).
# The defaults are PLACEHOLDERS: they have to be re-derived from the rho
# distribution of real bonded / debonded samples (report appendix C.4), not
# assumed.  Lower rho means "more likely debonded", the same direction as the
# absolute band_ratio_lh rule.
DEFAULT_GRADE_T1 = 0.80          # rho >= T1 -> G0 (bonded)
DEFAULT_GRADE_T2 = 0.50          # T2 <= rho < T1 -> G1 ; rho < T2 -> G2
GRADE_T1_MIN, GRADE_T1_MAX = 0.30, 1.20
GRADE_T2_MIN = 0.05
BOOTSTRAP_N = 2000               # resamples per point
BOOTSTRAP_SEED = 20261120        # fixed: the same taps always give the same CI
BOOTSTRAP_CI = (5.0, 95.0)       # percentiles reported as the rho interval
# Second condition: direction-agnostic CONSISTENCY check on d_f = f_peak/f_ref.
#
# The report's 328 -> 468 Hz rise was measured in the microphone's 300..15000 Hz
# band; this chain is an accelerometer with a fixed 30..1000 Hz signal band and
# the live f_peak sits at 210..280 Hz, i.e. the direction is not merely
# uncalibrated here, it can even be opposite.  Asserting a direction before the
# calibration exists would be invention, so the default mode is "either":
# a debonded point is only "consistent" when its peak frequency has MOVED (in
# either direction) by at least fpeak_tol; "up"/"down" pin one direction once
# real bonded/debonded samples have settled it.
# Grading mode.  "rank" (default) grades points RELATIVE TO EACH OTHER by
# their rho quantile, because a fixed T1/T2 only moves the absolute threshold
# from band_ratio onto rho: with every point above T1 the panel degenerates to
# all-G0.  "threshold" keeps the old fixed-T1/T2 rule for when the thresholds
# have actually been calibrated on real bonded/debonded panels.
DEFAULT_GRADE_MODE = "group"
# -- measurement grid ---------------------------------------------------------
# The web owns the grid: the device only knows a flat point index, the browser
# decides what row and column that index sits at.  POINT_MAX_INDEX bounds the
# index so a stray command cannot create point ids without limit.
POINT_MAX_INDEX = 63
GRID_MAX_SIDE = 8
DEFAULT_GRID_ROWS = 3
DEFAULT_GRID_COLS = 3
GRID_Z_THRESHOLD = 2.0
GRADE_MODES = ("group", "rank", "threshold")
RANK_BOOTSTRAP_N = 1000          # joint resamples for the order bootstrap
FPEAK_BAND_EDGE_FACTOR = 1.2     # f_ref <= band_lo*1.2 -> second condition blind
DEFAULT_FPEAK_MODE = "either"    # "either" | "up" | "down"
FPEAK_MODES = ("either", "up", "down")
DEFAULT_FPEAK_TOL = 0.15         # |d_f - 1| (or one-sided margin) needed
FPEAK_TOL_MIN, FPEAK_TOL_MAX = 0.02, 0.60
INCONSISTENT_FACTOR = 0.5
POOR_CONTACT_FACTOR = 0.6
POOR_CONTACT_SHARE = 0.5         # contact_ok share below this -> poor contact
BAND_CLAMPED_SHARE = 0.30        # clamped share above this -> poor contact
MIN_TAPS_PER_POINT = 3           # fewer valid taps -> NODATA, never graded
# contact_ok: the firmware flag wins; the firmware's pkg (peak acceleration at
# the trigger, in g) is the documented second source (report A.6.5 window);
# only when neither is present does the backend fall back to a heuristic based
# on peak_au / crest_factor, and then the point says contact_source="heuristic".
CONTACT_PKG_MIN_G = 0.05
CONTACT_PKG_MAX_G = 8.0
CONTACT_MIN_PEAK_G = 0.05        # heuristic only
CONTACT_MIN_CREST = 3.0          # heuristic only
CONTACT_SOURCES = ("firmware", "heuristic", "missing")
POINT_MISSING = "P?"             # bucket for taps whose payload has no pt
GRADE_ORDER = ("G0", "G1", "G2")

# -- automatic group grading (PROTOCOL.md section 7.10) ---------------------
# Instead of asking the operator which point is good (the first point may be
# the debonded one!), all real points are pooled and a 1-D Gaussian mixture is
# fitted to the per-point ln(band_ratio).  k=1 vs k=2 is decided by BIC, but a
# k=2 fit has to clear a separation floor as well: BIC is far too permissive at
# these sample sizes.
GROUP_MIN_POINTS = 3            # fewer measured points -> fall back to rank
GROUP_MIN_CLUSTER_POINTS = 2    # a split needs one group with at least 2 points
GROUP_SEP_Z = 2.5               # |mu1-mu2| / sqrt((s1^2+s2^2)/2) acceptance floor
GROUP_EM_STARTS = 5             # multi-start EM for the final fit
GROUP_EM_ITERS = 200
GROUP_BOOTSTRAP_N = 1000        # joint resamples for group_prob / p_grouping
GROUP_EM_BOOT_ITERS = 40        # EM iterations inside each bootstrap draw
GROUP_PROB_AMBIG_LOW = 0.30     # 0.30 .. 0.70 on group_prob -> G1
GROUP_PROB_AMBIG_HIGH = 0.70
GROUP_ACCEPT_P = 0.90           # p_grouping >= 0.9 -> claim the grouping
GROUP_MEMBER_AGREE = 0.80       # bootstrap "same grouping" membership agreement

# The analysis band is FIXED, not derived from each message's fs.
#
# An earlier version followed PROTOCOL.md literally and computed
# band_hi = 0.45*fs, crossover = 0.45*fs/3 per tap.  That looked principled and
# was wrong in practice, for two reasons:
#
#   1. fs is MEASURED on the device, and it is not constant: the poll loop
#      reports 2498-2654 Hz depending on how much the Wi-Fi stack preempts it.
#      A derived band therefore moves between taps (band_hi 1124-1194 Hz), so
#      f_peak, f_centroid and band_ratio_lh are computed on a slightly
#      different axis every time and two taps are not strictly comparable --
#      which defeats the whole point of a repeatability statistic.
#
#   2. Nothing physical pinned the crossover to band_hi/3; it was a ratio
#      inherited from the microphone design (15000/1000).  At accelerometer
#      rates that puts the split at 386 Hz by accident.
#
# The band is now [band_lo, band_hi] with band_hi and crossover explicit,
# adjustable at run time through /api/config.  The Nyquist guard below stays:
# whatever is configured, the upper edge can never exceed 0.45*fs, so a slow
# poll interval degrades the band instead of aliasing into it.
DEFAULT_BAND_HI_HZ = 1000.0     # safely under 0.45*fs for fs ~2500 Hz
DEFAULT_CROSSOVER_HZ = 300.0
NYQUIST_GUARD = 0.45            # band_hi <= 0.45 * fs, always
CROSSOVER_MAX_FRACTION = 0.80   # crossover must stay below band_hi
MAX_HISTORY = 2000           # hard cap on retained taps
SOURCE_TAG = "06_analyze_tap.extract_features_from_waveform"
FEATURES = ["f_peak_hz", "f_centroid_hz", "band_ratio_lh", "decay_tau_ms",
            "peak_au", "rms_au", "crest_factor", "kurtosis"]
# The analysis source lives at the repo root, four levels up from the usual
# tools/mqtt_demo/ location.  A copy of this file dropped into a flat folder
# (the portable deploy bundle) has no parents[3], so fall back to a sibling.
_HERE = Path(__file__).resolve()
_CANDIDATES = [(_HERE.parents[3] / "06_analyze_tap.py")] if len(_HERE.parents) > 3 else []
_CANDIDATES.append(_HERE.with_name("06_analyze_tap.py"))
TEMPLATE_PATH = next((c for c in _CANDIDATES if c.exists()), _CANDIDATES[-1])

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def log(msg: str) -> None:
    """One line per event, flushed, ASCII-safe on any Windows console."""
    print("[analyzer] " + msg, flush=True)


def _safe_console() -> None:
    """Never let a console code page abort the service over a stray symbol."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Template loading and band re-parameterisation
# ---------------------------------------------------------------------------
def load_template_module(path: Path):
    """Import 06_analyze_tap.py by path (its name starts with a digit).

    The module is registered in sys.modules before exec_module: the template
    decorates dataclasses at module level and dataclasses look the defining
    module up in sys.modules while decorating.
    """
    if not path.is_file():
        raise FileNotFoundError("analysis template not found: " + str(path))
    mod_name = "tap_analysis_template"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:                  # pragma: no cover
        raise ImportError("cannot load analysis template: " + str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def build_banded_feature_fn(mod, template_path=None):
    """Return (fn, meta) where fn(t_s, amp, fs, band_lo, band_hi, crossover).

    Preferred path: the template already exposes band parameters.  Otherwise
    the three hard-coded band literals in the template source are replaced by
    arguments; the rest of the function is executed verbatim from the
    template's own source, so the feature maths stays the template's.
    """
    template_path = Path(template_path or TEMPLATE_PATH)
    fn = mod.extract_features_from_waveform
    params = list(inspect.signature(fn).parameters)
    sha = hashlib.sha256(template_path.read_bytes()).hexdigest()
    meta = {
        "template": template_path.name,
        "template_sha256": sha,
        "function": "extract_features_from_waveform",
        "source": SOURCE_TAG,
    }
    native = {"band_lo_hz", "band_hi_hz", "crossover_hz"}.issubset(params)
    if native:
        meta["parameterisation"] = "native band arguments exposed by the template"
        meta["band_parameterisation"] = "native"
        return fn, meta

    src = textwrap.dedent(inspect.getsource(fn))
    tail = ") -> Dict[str, float]:"
    if src.count(tail) != 1:
        raise RuntimeError(
            "cannot reparameterise the template band: signature tail not unique")
    src = src.replace(
        tail,
        ",\n        band_lo_hz: float = 300.0, band_hi_hz: float = 15000.0,"
        "\n        crossover_hz: float = 1000.0" + tail)
    edits = [
        ("(freqs >= 300.0) & (freqs <= 15000.0)",
         "(freqs >= float(band_lo_hz)) & (freqs <= float(band_hi_hz))"),
        ('raise ValueError("sample rate too low for the 300..15000 Hz band")',
         'raise ValueError(f"sample rate too low for the '
         '{band_lo_hz:g}..{band_hi_hz:g} Hz band at fs={fs_hz:g} Hz")'),
        ("fb < 1000.0", "fb < float(crossover_hz)"),
    ]
    for old, new in edits:
        if src.count(old) != 1:
            raise RuntimeError(
                "cannot reparameterise the template band: literal not found "
                "exactly once: " + old)
        src = src.replace(old, new)

    ns = dict(mod.__dict__)     # np / spsig / sps / safe_div / cv_percent ...
    code = compile(src, "<" + template_path.name + "::extract_features_from_waveform"
                        " [band parameters bound]>", "exec")
    exec(code, ns)
    banded = ns["extract_features_from_waveform"]
    banded.__doc__ = fn.__doc__
    meta["band_parameterisation"] = (
        "source-level: the three hard-coded band literals in the template "
        "function are bound to arguments band_lo_hz / band_hi_hz / "
        "crossover_hz; the function body is otherwise executed verbatim from "
        "the template source and its helpers are the template's own")
    meta["band_defaults"] = {"band_lo_hz": 300.0, "band_hi_hz": 15000.0,
                             "crossover_hz": 1000.0}
    return banded, meta


def check_banded_equivalence(original, banded) -> Dict[str, Any]:
    """Prove the reparameterised function equals the template at its defaults."""
    rng = np.random.default_rng(0)
    fs = 44100.0
    t = np.arange(int(0.06 * fs)) / fs
    sig = (0.5 * np.exp(-t / 0.010) * np.sin(2 * np.pi * 1800.0 * t)
           + 0.3 * np.exp(-t / 0.004) * np.sin(2 * np.pi * 9000.0 * t))
    sig = sig + rng.normal(0.0, 0.02, sig.size)
    a = original(t, sig, fs)
    b = banded(t, sig, fs, band_lo_hz=300.0, band_hi_hz=15000.0,
               crossover_hz=1000.0)
    diffs = {}
    for key, va in a.items():
        vb = b.get(key)
        try:
            fa, fb_ = float(va), float(vb)
        except (TypeError, ValueError):
            continue
        if np.isfinite(fa) and np.isfinite(fb_):
            diffs[key] = abs(fa - fb_)
    return {"max_abs_diff": max(diffs.values()) if diffs else 0.0,
            "n_features_compared": len(diffs),
            "identical": bool(diffs) and max(diffs.values()) == 0.0}


# ---------------------------------------------------------------------------
# JSON helpers: NaN/Inf are not valid JSON, numpy scalars are not JSON types
# ---------------------------------------------------------------------------
def json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        val = float(obj)
        return val if math.isfinite(val) else None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return [json_safe(v) for v in obj.tolist()]
    return obj


def dumps(obj: Any) -> bytes:
    return json.dumps(json_safe(obj), ensure_ascii=False, allow_nan=False).encode("utf-8")


def finite(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def normalise_point(value: Any) -> str:
    """Normalise the MQTT 'pt' field to a short point label.

    The device sends "P0".."P5" (PROTOCOL.md section 1); an integer 2 or "2" is
    accepted as convenience.  A tap without a usable label is bucketed as
    "P?" -- it cannot be graded differentially, but it still counts as a tap.
    """
    if value is None:
        return POINT_MISSING
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        n = int(value)
        return "P%d" % n if n >= 0 else POINT_MISSING
    s = str(value).strip().upper()
    if not s:
        return POINT_MISSING
    if s.startswith("P") and s[1:].isdigit():
        return s
    if s.isdigit():
        return "P" + s
    return POINT_MISSING


def parse_cmd_point(value: Any) -> Optional[str]:
    """Parse a point id; None when it is not a valid index.

    Accepts "P12", "p12", 12 and "12".  The index is a flat grid index
    (row * cols + col); the grid size lives on the web side, so only the
    overall bound is enforced here.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, np.integer)):
        idx = int(value)
        return "P%d" % idx if 0 <= idx <= POINT_MAX_INDEX else None
    if isinstance(value, str):
        s = value.strip().upper()
        if s.startswith("P") and s[1:].isdigit():
            idx = int(s[1:])
            return "P%d" % idx if 0 <= idx <= POINT_MAX_INDEX else None
        if s.isdigit():
            idx = int(s)
            return "P%d" % idx if 0 <= idx <= POINT_MAX_INDEX else None
    return None


def median_or_none(values: Sequence[Any]) -> Optional[float]:
    """Median of the finite values, or None when there is nothing to take."""
    arr = [float(v) for v in values if finite(v)]
    return float(np.median(arr)) if arr else None

def _gmm1d_logpdf(x, means, variances):
    """(N, k) log N(x | mean_j, var_j), variances floored."""
    return (-0.5 * np.log(2.0 * np.pi * variances)[None, :]
            - (x[:, None] - means[None, :]) ** 2 / (2.0 * variances[None, :]))


def _gmm1d_loglik(x, weights, means, variances):
    comp = _gmm1d_logpdf(x, means, variances) + np.log(weights)[None, :]
    m = np.max(comp, axis=1, keepdims=True)
    return float(np.sum(m[:, 0] + np.log(np.sum(np.exp(comp - m), axis=1))))


def _gmm1d_fit(x, k, rng, restarts=GROUP_EM_STARTS, iters=GROUP_EM_ITERS):
    """Fit a 1-D Gaussian mixture with multi-start EM; numpy only."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = x.size
    if k == 1 or n < 4:
        mu = float(np.mean(x)) if n else 0.0
        var = float(np.var(x)) if n > 1 else 1.0
        var = max(var, 1e-9)
        w = np.array([1.0])
        mu_arr, var_arr = np.array([mu]), np.array([var])
        return {"weights": w, "means": mu_arr, "variances": var_arr,
                "loglik": _gmm1d_loglik(x, w, mu_arr, var_arr)}
    best = None
    starts = []
    order = np.sort(x)
    for frac in (0.25, 0.5, 0.75):
        cut = int(n * frac)
        cut = min(max(cut, 1), n - 1)
        lo, hi = order[:cut], order[cut:]
        starts.append((np.array([lo.mean(), hi.mean()]),
                       np.array([max(lo.var(), 1e-9), max(hi.var(), 1e-9)]),
                       np.array([cut / n, 1.0 - cut / n])))
    for _ in range(max(0, restarts - len(starts))):
        idx = rng.choice(n, size=2, replace=False)
        mu = np.sort(x[idx])
        var = np.full(2, max(float(np.var(x)), 1e-9))
        w = np.array([0.5, 0.5])
        starts.append((mu, var, w))
    for mu, var, w in starts:
        mu = mu.astype(float).copy()
        var = np.maximum(var.astype(float), 1e-9)
        w = w.astype(float) / w.sum()
        prev = -np.inf
        for _ in range(iters):
            comp = _gmm1d_logpdf(x, mu, var) + np.log(w)[None, :]
            m = np.max(comp, axis=1, keepdims=True)
            logsum = m[:, 0] + np.log(np.sum(np.exp(comp - m), axis=1))
            ll = float(np.sum(logsum))
            resp = np.exp(comp - logsum[:, None])
            nk = resp.sum(axis=0) + 1e-12
            w = nk / nk.sum()
            mu = (resp * x[:, None]).sum(axis=0) / nk
            var = np.maximum(((resp * (x[:, None] - mu[None, :]) ** 2).sum(axis=0)
                              / nk), 1e-9)
            if abs(ll - prev) < 1e-10:
                break
            prev = ll
        if best is None or ll > best["loglik"]:
            best = {"weights": w, "means": mu, "variances": var, "loglik": ll}
    return best


def _gmm1d_bic(fit, n_samples, k):
    n_params = 3 * k - 1          # k=1: mu,var ; k=2: pi + two (mu,var)
    return -2.0 * fit["loglik"] + n_params * float(np.log(max(n_samples, 2)))


def _group_separation_z(means, variances):
    denom = np.sqrt((variances[0] ** 2 + variances[1] ** 2) / 2.0)
    return float(abs(means[0] - means[1]) / denom) if denom > 0 else float("inf")



def _connect_ok(reason_code) -> bool:
    """paho 2.x ReasonCode is not an int; accept 0 / "Success" / is_failure."""
    val = getattr(reason_code, "value", reason_code)
    try:
        return int(val) == 0
    except (TypeError, ValueError):
        pass
    failure = getattr(reason_code, "is_failure", None)
    if failure is not None:
        return not failure
    return str(reason_code).strip().lower() in ("0", "success")


# ---------------------------------------------------------------------------
# WebSocket plumbing (text frames out, control frames handled)
# ---------------------------------------------------------------------------
class WsClient:
    """One dashboard websocket.  Server -> client only, plus ping/close."""

    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr
        self.alive = True
        self._q = deque(maxlen=64)
        self._cond = threading.Condition()
        self._tx = threading.Thread(target=self._sender, daemon=True,
                                    name="ws-sender")
        self._rx = threading.Thread(target=self._reader, daemon=True,
                                    name="ws-reader")
        self._last_send = time.time()

    # -- framing helpers ----------------------------------------------------
    @staticmethod
    def _frame(opcode: int, payload: bytes) -> bytes:
        head = bytearray([0x80 | opcode])
        n = len(payload)
        if n < 126:
            head.append(n)
        elif n < 65536:
            head.append(126)
            head += n.to_bytes(2, "big")
        else:
            head.append(127)
            head += n.to_bytes(8, "big")
        return bytes(head) + payload

    def start(self) -> None:
        self._tx.start()
        self._rx.start()

    def push(self, text: str) -> None:
        if not self.alive:
            return
        payload = text.encode("utf-8")
        with self._cond:
            self._q.append(payload)
            self._cond.notify_all()

    def _send(self, opcode: int, payload: bytes) -> None:
        self.sock.sendall(self._frame(opcode, payload))

    def _sender(self) -> None:
        while self.alive:
            payload = None
            with self._cond:
                if not self._q:
                    self._cond.wait(timeout=1.0)
                if self._q:
                    payload = self._q.popleft()
            if payload is None:
                if time.time() - self._last_send > 20.0:
                    try:
                        self._send(0x9, b"hb")
                        self._last_send = time.time()
                    except OSError:
                        self.close()
                continue
            try:
                self._send(0x1, payload)
                self._last_send = time.time()
            except OSError:
                self.close()

    def _reader(self) -> None:
        """Consume client frames so ping/close are honoured and EOF is seen."""
        buf = b""
        try:
            while self.alive:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while len(buf) >= 2:
                    b0, b1 = buf[0], buf[1]
                    opcode = b0 & 0x0F
                    masked = b1 & 0x80
                    ln = b1 & 0x7F
                    pos = 2
                    if ln == 126:
                        if len(buf) < 4:
                            break
                        ln = int.from_bytes(buf[2:4], "big")
                        pos = 4
                    elif ln == 127:
                        if len(buf) < 10:
                            break
                        ln = int.from_bytes(buf[2:10], "big")
                        pos = 10
                    mask = b""
                    if masked:
                        if len(buf) < pos + 4:
                            break
                        mask = buf[pos:pos + 4]
                        pos += 4
                    if len(buf) < pos + ln:
                        break
                    data = bytearray(buf[pos:pos + ln])
                    if masked:
                        for i in range(len(data)):
                            data[i] ^= mask[i % 4]
                    buf = buf[pos + ln:]
                    if opcode == 0x8:                      # close
                        self.close()
                        return
                    if opcode == 0x9:                      # ping -> pong
                        try:
                            self._send(0xA, bytes(data))
                        except OSError:
                            self.close()
                            return
                    # 0x1/0x2/0xA: dashboards are read-only, nothing to do
        except OSError:
            pass
        finally:
            self.close()

    def close(self) -> None:
        if not self.alive:
            return
        self.alive = False
        with self._cond:
            self._cond.notify_all()
        try:
            self.sock.close()
        except OSError:
            pass


def ws_handshake(sock, headers: Dict[str, str]) -> bool:
    key = headers.get("sec-websocket-key")
    if not key:
        return False
    accept = base64.b64encode(
        hashlib.sha1((key + WS_GUID).encode("ascii")).digest()).decode("ascii")
    response = ("HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                "Sec-WebSocket-Accept: " + accept + "\r\n"
                "\r\n")
    sock.sendall(response.encode("ascii"))
    return True


# ---------------------------------------------------------------------------
# Probe state
# ---------------------------------------------------------------------------
class ProbeState:
    def __init__(self, feature_fn, template_module, meta, broker, broker_port):
        self.lock = threading.RLock()
        self.feature_fn = feature_fn
        self.mod = template_module
        self.meta = meta
        self.broker = broker
        self.broker_port = broker_port
        self.http_port = DEFAULT_HTTP_PORT
        self.grid_rows = DEFAULT_GRID_ROWS
        self.grid_cols = DEFAULT_GRID_COLS

        self.config = {"th_band_ratio": DEFAULT_TH_BAND_RATIO,
                       "band_lo_hz": DEFAULT_BAND_LO_HZ,
                       "band_hi_hz": DEFAULT_BAND_HI_HZ,
                       "crossover_hz": DEFAULT_CROSSOVER_HZ,
                       "window": DEFAULT_WINDOW,
                       "grade_mode": DEFAULT_GRADE_MODE,
                       "grade_t1": DEFAULT_GRADE_T1,
                       "grade_t2": DEFAULT_GRADE_T2,
                       "fpeak_mode": DEFAULT_FPEAK_MODE,
                       "fpeak_tol": DEFAULT_FPEAK_TOL}
        # Reference region of the two-surface differential measurement
        # (report section 7.7.1).  Set by POST /api/reference; None means the
        # survey has no baseline yet and no point may be graded.
        self.reference = None
        self.taps = deque(maxlen=MAX_HISTORY)
        self.latest = None
        self.last_measurement = None
        self.devices: Dict[str, dict] = {}
        self.events = deque(maxlen=50)
        self.errors = deque(maxlen=50)
        self.counts = Counter()
        self.mqtt_connected = False
        self.mqtt_client = None
        self.ws_clients: List[WsClient] = []
        self.started_at = time.time()
        self.last_tap_at = None
        self.fs_last = None
        # Which measurement point the device is on.  Two sources, the device's
        # point-command ack first, then the pt of the latest real tap:
        #   {"dev": ..., "pt": "P2", "ms": <epoch ms>}
        self.last_real_tap = None
        # Last device that sent a real (sp != true) measurement frame.  The
        # command path needs a target device before the operator has tapped
        # anything: measurement frames arrive every couple of seconds, taps do
        # not, so waiting for a tap made "switch point from the web page" throw
        # 409 straight after a restart.
        self.last_real_device = None
        self.last_point_ack = None
        self._persist_warned = False
        self._load_session()

    # -- session persistence ------------------------------------------------
    def _load_session(self) -> None:
        """Restore the taps and the reference of the previous run, if any."""
        n = 0
        try:
            if SESSION_REF.exists():
                self.reference = json.loads(SESSION_REF.read_text(encoding="utf-8"))
                log("session: reference restored (%s)"
                    % (self.reference or {}).get("point"))
        except Exception as exc:                       # noqa: BLE001
            log("session: reference restore failed: %s" % exc)
        try:
            if SESSION_TAPS.exists():
                with SESSION_TAPS.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            tap = json.loads(line)
                        except Exception:              # noqa: BLE001
                            continue
                        self.taps.append(tap)
                        self.latest = tap
                        self.fs_last = tap.get("fs")
                        n += 1
                        if not tap.get("sp"):
                            self.last_real_tap = {"dev": tap.get("dev"),
                                                  "pt": tap.get("pt"),
                                                  "ms": tap.get("t_ms")}
                        if tap.get("dev") and not tap.get("sp"):
                            self.last_real_device = {"dev": tap.get("dev"),
                                                     "ms": tap.get("t_ms") or 0}
        except Exception as exc:                       # noqa: BLE001
            log("session: tap restore failed: %s" % exc)
        if n:
            self.last_tap_at = time.time()
            log("session: restored %d tap(s) from %s" % (n, SESSION_TAPS))

    def _persist_tap(self, tap: dict) -> None:
        """Append one real tap.  Never raises: a full disk must not stop a
        measurement, it only costs the record."""
        if tap.get("sp"):
            return
        try:
            SESSION_DIR.mkdir(parents=True, exist_ok=True)
            with SESSION_TAPS.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(tap, ensure_ascii=False) + "\n")
        except Exception as exc:                       # noqa: BLE001
            if not self._persist_warned:
                self._persist_warned = True
                log("session: cannot persist taps: %s" % exc)

    def _persist_reference(self) -> None:
        try:
            SESSION_DIR.mkdir(parents=True, exist_ok=True)
            if self.reference is None:
                if SESSION_REF.exists():
                    SESSION_REF.unlink()
            else:
                SESSION_REF.write_text(
                    json.dumps(self.reference, ensure_ascii=False, indent=1),
                    encoding="utf-8")
        except Exception as exc:                       # noqa: BLE001
            log("session: cannot persist reference: %s" % exc)

    def _wipe_session_files(self) -> None:
        for path in (SESSION_TAPS, SESSION_REF):
            try:
                if path.exists():
                    path.unlink()
            except Exception:                          # noqa: BLE001
                pass

    # -- config -------------------------------------------------------------
    def get_config(self) -> dict:
        with self.lock:
            return dict(self.config)

    def set_config(self, patch: dict) -> dict:
        updated = {}
        with self.lock:
            if "th_band_ratio" in patch:
                v = float(patch["th_band_ratio"])
                if not (0.0 <= v <= 2.0):
                    raise ValueError("th_band_ratio must be within [0, 2]")
                self.config["th_band_ratio"] = round(v, 4)
                updated["th_band_ratio"] = self.config["th_band_ratio"]
            if "band_lo_hz" in patch:
                v = float(patch["band_lo_hz"])
                if not (1.0 <= v <= 2000.0):
                    raise ValueError("band_lo_hz must be within [1, 2000] Hz")
                self.config["band_lo_hz"] = round(v, 3)
                updated["band_lo_hz"] = self.config["band_lo_hz"]
            if "band_hi_hz" in patch:
                v = float(patch["band_hi_hz"])
                if not (50.0 <= v <= 5000.0):
                    raise ValueError("band_hi_hz must be within [50, 5000] Hz")
                self.config["band_hi_hz"] = round(v, 1)
                updated["band_hi_hz"] = self.config["band_hi_hz"]
            if "crossover_hz" in patch:
                v = float(patch["crossover_hz"])
                hi = float(self.config["band_hi_hz"])
                if not (10.0 <= v <= hi * CROSSOVER_MAX_FRACTION):
                    raise ValueError(
                        "crossover_hz must be within [10, %.1f] Hz"
                        % (hi * CROSSOVER_MAX_FRACTION))
                self.config["crossover_hz"] = round(v, 1)
                updated["crossover_hz"] = self.config["crossover_hz"]
            if "window" in patch:
                v = int(patch["window"])
                if not (5 <= v <= MAX_HISTORY):
                    raise ValueError("window must be within [5, %d]" % MAX_HISTORY)
                self.config["window"] = v
                updated["window"] = self.config["window"]
            if "grade_mode" in patch:
                mode = str(patch["grade_mode"]).strip().lower()
                if mode not in GRADE_MODES:
                    raise ValueError("grade_mode must be one of %s"
                                     % (", ".join(GRADE_MODES),))
                self.config["grade_mode"] = mode
                updated["grade_mode"] = mode
            if "grade_t1" in patch or "grade_t2" in patch:
                t1 = float(patch.get("grade_t1", self.config["grade_t1"]))
                t2 = float(patch.get("grade_t2", self.config["grade_t2"]))
                if not (GRADE_T1_MIN <= t1 <= GRADE_T1_MAX):
                    raise ValueError("grade_t1 must be within [%.2f, %.2f]"
                                     % (GRADE_T1_MIN, GRADE_T1_MAX))
                if not (GRADE_T2_MIN <= t2 <= t1 - 0.05):
                    raise ValueError(
                        "grade_t2 must be within [%.2f, grade_t1-0.05=%.2f]"
                        % (GRADE_T2_MIN, t1 - 0.05))
                self.config["grade_t1"] = round(t1, 4)
                self.config["grade_t2"] = round(t2, 4)
                updated["grade_t1"] = self.config["grade_t1"]
                updated["grade_t2"] = self.config["grade_t2"]
            if "fpeak_mode" in patch:
                mode = str(patch["fpeak_mode"]).strip().lower()
                if mode not in FPEAK_MODES:
                    raise ValueError("fpeak_mode must be one of %s"
                                     % (", ".join(FPEAK_MODES),))
                self.config["fpeak_mode"] = mode
                updated["fpeak_mode"] = mode
            if "fpeak_tol" in patch:
                tol = float(patch["fpeak_tol"])
                if not (FPEAK_TOL_MIN <= tol <= FPEAK_TOL_MAX):
                    raise ValueError("fpeak_tol must be within [%.2f, %.2f]"
                                     % (FPEAK_TOL_MIN, FPEAK_TOL_MAX))
                self.config["fpeak_tol"] = round(tol, 4)
                updated["fpeak_tol"] = self.config["fpeak_tol"]
            if updated:
                self._reclassify_locked()
        return updated

    def _reclassify_locked(self) -> None:
        """Re-apply the (possibly new) threshold to the taps already stored.

        The dashboard slider must change the visible labels immediately, not
        only from the next tap on; the feature vectors are untouched, only the
        band_ratio_lh comparison is re-run.
        """
        th = float(self.config["th_band_ratio"])
        for tap in self.taps:
            feats = tap.get("features") or {}
            ratio = feats.get("band_ratio_lh")
            if finite(ratio):
                verdict = "DEBOND" if float(ratio) <= th else "BONDED"
            else:
                verdict = "UNKNOWN"
            tap["verdict"] = verdict
            tap["th_band_ratio"] = th
        # self.latest is the same dict object as the last entry of self.taps,
        # so it has been re-labelled above already.
        if self.latest is not None:
            self.latest["th_band_ratio"] = th


    # -- differential grading (PROTOCOL.md section 7) ----------------------
    def _point_groups_locked(self) -> Dict[tuple, dict]:
        """Aggregate the taps of each measurement point inside the window.

        The grouping key is (dev, pt) rather than pt alone.  A survey is one
        probe, but the simulator (dev sim-01, sp:true) can run at the same
        time; grouping by pt only would silently merge simulated taps into the
        real point bucket, which is exactly what the report's "simulated data
        must be unmistakable" rule forbids.  Taps without a usable pt go to the
        P? bucket of their own device.
        """
        groups: Dict[tuple, List[dict]] = {}
        for tap in self._window_taps():
            key = (str(tap.get("dev") or ""), normalise_point(tap.get("pt")))
            groups.setdefault(key, []).append(tap)
        out: Dict[tuple, dict] = {}
        for key, group in groups.items():
            valid = [t for t in group
                     if finite((t.get("features") or {}).get("band_ratio_lh"))
                     and finite((t.get("features") or {}).get("f_peak_hz"))]
            ratios = [float((t.get("features") or {})["band_ratio_lh"])
                      for t in valid]
            peaks = [float((t.get("features") or {})["f_peak_hz"])
                     for t in valid]
            rms = [(t.get("features") or {}).get("rms_au") for t in valid]
            contact = [bool(t.get("contact_ok")) for t in valid]
            clamped = [bool(t.get("band_clamped")) for t in valid]
            sources = [str(t.get("contact_source") or "missing") for t in valid]
            if "heuristic" in sources:
                contact_source = "heuristic"
            elif "missing" in sources:
                contact_source = "missing"
            else:
                contact_source = "firmware"
            simulated_flags = [bool(t.get("sp")) for t in group]
            out[key] = {
                "key": key,
                "dev": key[0],
                "point": key[1],
                "n_taps": len(group),
                "n_valid": len(valid),
                "simulated": any(simulated_flags),
                "n_simulated": sum(1 for flag in simulated_flags if flag),
                "ratios": ratios,
                "peaks": peaks,
                "median_band_ratio": median_or_none(ratios),
                "median_f_peak_hz": median_or_none(peaks),
                "median_rms_au": median_or_none(rms),
                "contact_ok_share": (sum(contact) / len(contact)) if contact else None,
                "contact_source": contact_source if valid else "missing",
                "band_clamped_share": (sum(clamped) / len(clamped)) if clamped else None,
                "last_tap_ms": group[-1].get("t_ms") if group else None,
            }
        return out

    def set_reference(self, point) -> dict:
        """Establish the bonded reference region of the differential survey.

        "auto" picks the point with the highest median band_ratio_lh among
        those that already have MIN_TAPS_PER_POINT valid taps -- that is the
        point the operator is implicitly saying "this is bonded".
        """
        with self.lock:
            groups = self._point_groups_locked()
            if not groups:
                raise ValueError("no taps yet: tap a point before setting a "
                                 "reference")
            want = str(point or "").strip()
            real = [g for g in groups.values() if not g["simulated"]]
            if want.lower() == "auto":
                candidates = [g for g in real
                              if g["n_valid"] >= MIN_TAPS_PER_POINT
                              and finite(g["median_band_ratio"])]
                if not candidates:
                    if not real and groups:
                        raise ValueError(
                            "only simulated taps (sp:true) are present; a "
                            "reference must come from a real measurement")
                    raise ValueError(
                        "no real point has %d valid taps yet; cannot choose a "
                        "reference automatically" % MIN_TAPS_PER_POINT)
                chosen = max(candidates, key=lambda g: g["median_band_ratio"])
                source = "auto"
            else:
                label = normalise_point(want)
                matches = [g for g in real if g["point"] == label]
                if not matches:
                    simulated = [g for g in groups.values()
                                 if g["point"] == label and g["simulated"]]
                    if simulated:
                        raise ValueError(
                            "point %s has only simulated taps (sp:true); a "
                            "reference must come from a real measurement"
                            % label)
                    raise ValueError("point %s has no taps in the current "
                                     "window" % label)
                if len(matches) > 1:
                    raise ValueError(
                        "point %s is ambiguous across devices (%s); use one "
                        "probe per survey"
                        % (label, ", ".join(sorted(g["dev"] for g in matches))))
                chosen = matches[0]
                if chosen["n_valid"] < 1:
                    raise ValueError("point %s has no analysable tap yet"
                                     % label)
                source = "manual"
            r_ref = float(chosen["median_band_ratio"])
            f_ref = float(chosen["median_f_peak_hz"])
            if not (finite(r_ref) and finite(f_ref)) or r_ref <= 0:
                raise ValueError("point %s cannot serve as a reference "
                                 "(no usable median)" % chosen["point"])
            self.reference = {
                "point": chosen["point"],
                "dev": chosen["dev"],
                "r_ref": r_ref,
                "f_ref": f_ref,
                "set_ms": int(time.time() * 1000),
                "source": source,
                "n_taps": int(chosen["n_valid"]),
            }
            self._persist_reference()
            return dict(self.reference)

    def clear_reference(self) -> None:
        with self.lock:
            self.reference = None
            self._persist_reference()

    def reset(self) -> dict:
        """Start a new measurement session.

        A new facade, a new probe or a new reference makes every stored tap
        and every reference stale: leaving them in place would silently compare
        rho across sessions.  Clears the tap history, the point table (derived
        from the taps), the reference, the error log and the session counters.
        Configuration (band, thresholds, fpeak_mode/tol, window) is KEPT -- it
        is an instrument setting, not measurement data.
        """
        with self.lock:
            n_taps = len(self.taps)
            had_ref = dict(self.reference) if self.reference else None
            n_errors = len(self.errors)
            counts_before = dict(self.counts)
            self.taps.clear()
            self.latest = None
            self.reference = None
            self.fs_last = None
            self.last_tap_at = None
            self.errors.clear()
            self.events.clear()
            self.counts.clear()
            self.last_real_tap = None
            self.last_point_ack = None
            self._wipe_session_files()
            # last_real_device is deliberately NOT cleared: it is "which probe
            # is talking to me", not measurement data, and clearing it would
            # make POST /api/point answer 409 for a few seconds right after
            # every reset -- exactly when the operator wants to set the first
            # point of the new session.
        cleared = {
            "taps": n_taps,
            "reference": had_ref["point"] if had_ref else None,
            "reference_dev": had_ref.get("dev") if had_ref else None,
            "errors": n_errors,
            "counters": bool(counts_before),
        }
        log("reset: cleared %d taps (reference was %s)"
            % (n_taps, cleared["reference"]))
        return cleared

    def points(self) -> dict:
        with self.lock:
            return self._points_locked()

    # -- measurement grid ---------------------------------------------------
    # No reference point: every cell is compared against the whole session.
    # A cell is only called hollow when it is both statistically off AND
    # spatially contiguous with another off cell, because a debond is a patch,
    # not a single tap landing oddly.

    def grid(self) -> dict:
        with self.lock:
            rows, cols = self.grid_rows, self.grid_cols
            taps = [t for t in self.taps if not t.get("sp")]
        agg: Dict[str, Dict[str, list]] = {}
        for t in taps:
            pt = t.get("pt") or t.get("point")
            if not pt:
                continue
            feats = t.get("features") or {}
            slot = agg.setdefault(pt, {"br": [], "fc": [], "tau": [], "n": 0})
            slot["n"] += 1
            for key, name in (("band_ratio_lh", "br"),
                              ("f_centroid_hz", "fc"),
                              ("decay_tau_ms", "tau")):
                val = feats.get(key)
                if finite(val):
                    slot[name].append(float(val))

        def med(vals: list) -> Optional[float]:
            return float(np.median(vals)) if vals else None

        cells = []
        for idx in range(rows * cols):
            slot = agg.get("P%d" % idx)
            n = int(slot["n"]) if slot else 0
            cells.append({
                "idx": idx,
                "row": idx // cols,
                "col": idx % cols,
                "point": "P%d" % idx,
                "n_taps": n,
                "median_band_ratio": med(slot["br"]) if slot else None,
                "median_f_centroid_hz": med(slot["fc"]) if slot else None,
                "median_decay_tau_ms": med(slot["tau"]) if slot else None,
                "z": None,
                "grade": "empty" if n == 0 else "normal",
            })

        note = ""
        measured = [c for c in cells if c["n_taps"] > 0
                    and finite(c["median_band_ratio"])]
        if len(measured) < 4:
            note = "至少需要 4 个测点的数据才能做相对判断（当前 %d 个）" % len(measured)
        else:
            arr = np.array([c["median_band_ratio"] for c in measured], dtype=float)
            centre = float(np.median(arr))
            mad = float(np.median(np.abs(arr - centre)))
            sigma = 1.4826 * mad
            if sigma <= 1e-9:
                note = "本组数值几乎相同，无法区分"
            else:
                zs = {c["idx"]: (c["median_band_ratio"] - centre) / sigma
                      for c in measured}
                flagged = {i for i, z in zs.items() if abs(z) >= GRID_Z_THRESHOLD}
                clustered = self._grid_clusters(flagged, rows, cols)
                for c in cells:
                    if c["idx"] in zs:
                        c["z"] = round(float(zs[c["idx"]]), 2)
                    if c["idx"] in flagged:
                        c["grade"] = ("hollow" if c["idx"] in clustered
                                      else "suspect")
        return {"rows": rows, "cols": cols, "cells": cells,
                "done": sum(1 for c in cells if c["n_taps"] > 0),
                "total": rows * cols, "note": note}

    @staticmethod
    def _grid_clusters(indices: set, rows: int, cols: int) -> set:
        """Indices that belong to a connected group of at least two cells."""
        out = set()
        seen = set()
        for start in indices:
            if start in seen:
                continue
            stack, comp = [start], []
            seen.add(start)
            while stack:
                cur = stack.pop()
                comp.append(cur)
                r, c = divmod(cur, cols)
                for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                    if not (0 <= nr < rows and 0 <= nc < cols):
                        continue
                    nb = nr * cols + nc
                    if nb in indices and nb not in seen:
                        seen.add(nb)
                        stack.append(nb)
            if len(comp) >= 2:
                out.update(comp)
        return out

    def set_grid(self, rows: Any, cols: Any) -> dict:
        try:
            rows = int(rows)
            cols = int(cols)
        except (TypeError, ValueError):
            raise ValueError("rows and cols must be integers")
        rows = max(2, min(rows, GRID_MAX_SIDE))
        cols = max(2, min(cols, GRID_MAX_SIDE))
        with self.lock:
            self.grid_rows, self.grid_cols = rows, cols
        return self.grid()

    def _points_locked(self) -> dict:
        groups = self._point_groups_locked()
        t1 = float(self.config["grade_t1"])
        t2 = float(self.config["grade_t2"])
        grade_mode = str(self.config.get("grade_mode", DEFAULT_GRADE_MODE))
        ref = dict(self.reference) if self.reference else None
        r_ref = ref["r_ref"] if ref else None
        f_ref = ref["f_ref"] if ref else None
        band_lo = float(self.config["band_lo_hz"])
        fpeak_limited = bool(ref and f_ref is not None
                             and f_ref <= band_lo * FPEAK_BAND_EDGE_FACTOR)
        manual_reference = ref is not None

        points = []
        ratios_by_key = {}
        for key in sorted(groups):
            g = groups[key]
            entry = {
                "point": g["point"],
                "dev": g["dev"],
                "simulated": g["simulated"],
                "n_simulated": g["n_simulated"],
                "n_taps": g["n_taps"],
                "n_valid": g["n_valid"],
                "median_band_ratio": g["median_band_ratio"],
                "median_f_peak_hz": g["median_f_peak_hz"],
                "median_rms_au": g["median_rms_au"],
                "contact_ok_share": g["contact_ok_share"],
                "contact_source": g["contact_source"],
                "band_clamped_share": g["band_clamped_share"],
                "last_tap_ms": g["last_tap_ms"],
                "rank": None,
                "grade": "NODATA",
                "rho_grade": None,
                "confidence": None,
                "confidence_pct": None,
                "grade_confidence": None,
                "rank_confidence": None,
                "p_debond": None,
                "rho": None,
                "rho_ci": None,
                "d_f": None,
                "inconsistent": False,
                "poor_contact": False,
                "is_reference": bool(ref and g["point"] == ref["point"]
                                    and g["dev"] == ref.get("dev")),
                "comparable": False,
                "group": None,
                "group_prob": None,
                "ref_drift": None,
                "ref_drift_pct": None,
                "reason": None,
            }
            r = g["median_band_ratio"]
            f = g["median_f_peak_hz"]
            valid = (r is not None and f is not None
                     and g["n_valid"] >= MIN_TAPS_PER_POINT)
            if r is not None and r_ref:
                entry["rho"] = float(r) / r_ref
            if f is not None and f_ref:
                entry["d_f"] = float(f) / f_ref
            if entry["is_reference"]:
                r_now = g["median_band_ratio"]
                drift = (float(r_now) / r_ref) if finite(r_now) else None
                entry.update({
                    "grade": "G0",
                    "rho_grade": "G0",
                    "rho": 1.0,
                    "ref_drift": drift,
                    "ref_drift_pct": ((drift - 1.0) * 100.0
                                      if drift is not None else None),
                })
            elif (valid and not entry["simulated"]
                  and (grade_mode == "group" or ref is not None)):
                entry["comparable"] = True
                ratios_by_key[key] = [float(v) for v in g["ratios"]
                                      if finite(v) and v > 0]
            points.append(entry)

        comparable = [p for p in points if p["comparable"]]
        n_comparable = len(comparable)
        grouped = False
        p_grouping = None
        separation_z = None
        group_gap = None
        suspicious_group = []
        baseline_group = []
        cluster_conflict = False
        ranked_only = False
        grouping_fallback = None
        p_order_significant = None
        spread = None
        p_debond_meaning = "relative_top_third"

        if grade_mode == "group" and not manual_reference:
            if n_comparable >= GROUP_MIN_POINTS:
                gr = self._group_grade(comparable, ratios_by_key)
                grouped = gr["grouped"]
                p_grouping = gr["p_grouping"]
                separation_z = gr["separation_z"]
                group_gap = gr["group_gap"]
                suspicious_group = gr["suspicious_group"]
                baseline_group = gr["baseline_group"]
                cluster_conflict = gr["cluster_conflict"]
                ranked_only = gr["ranked_only"]
                p_debond_meaning = "group_suspicious_prob"
                for p in comparable:
                    p.update(gr["per_point"][(p["dev"], p["point"])])
            else:
                self._fallback_quantile_grade(comparable)
                ranked_only = True
                grouping_fallback = "too_few_points"
                p_debond_meaning = "rank_quantile"
        elif grade_mode == "group" and manual_reference:
            # Manual reference is now only an OPTIONAL override: it pauses the
            # automatic grouping and grades against the operator's origin.
            p_order_significant, spread = self._apply_rank_grades(
                comparable, ratios_by_key, r_ref)
            p_debond_meaning = "relative_top_third" if n_comparable >= 2 else "prob_rho_below_reference"
        elif grade_mode == "rank":
            if manual_reference:
                p_order_significant, spread = self._apply_rank_grades(
                    comparable, ratios_by_key, r_ref)
                if n_comparable >= 2:
                    p_debond_meaning = "relative_top_third"
                else:
                    p_debond_meaning = "prob_rho_below_reference"
            else:
                for p in comparable:
                    p["reason"] = "NO_REFERENCE"
        else:  # threshold
            if manual_reference:
                for p in comparable:
                    key = (p["dev"], p["point"])
                    p.update(self._threshold_grade(p, ratios_by_key[key],
                                                   r_ref, t1, t2))
                p_debond_meaning = "prob_rho_below_t1"
            else:
                for p in comparable:
                    p["reason"] = "NO_REFERENCE"

        # ---- ranks: reference 0, then comparable by median band_ratio asc ----
        if ref is not None:
            for entry in points:
                if entry["is_reference"]:
                    entry["rank"] = 0
        if grouped and suspicious_group:
            order_key = {}
            for i, name in enumerate(suspicious_group):
                order_key[name] = i
            base_start = len(suspicious_group)
            for i, name in enumerate(baseline_group):
                order_key[name] = base_start + i
            ranked = sorted([p for p in comparable],
                            key=lambda p: order_key.get(p["point"], 10 ** 6))
        else:
            ranked = sorted([p for p in comparable],
                            key=lambda p: (p["median_band_ratio"]
                                           if p["median_band_ratio"] is not None
                                           else float("inf")))
        for i, entry in enumerate(ranked, start=1):
            entry["rank"] = i
        non_ranked = [p for p in points if p["rank"] is None
                      and not p["is_reference"]]
        simulated_points = [p for p in non_ranked if p["simulated"]]
        simulated_points.sort(key=lambda p: (p["point"], p["dev"]))
        sim_ids = {id(p) for p in simulated_points}
        ordered = []
        seen = set()
        for bucket in ([p for p in points if p["is_reference"]],
                       ranked, simulated_points,
                       [p for p in non_ranked if id(p) not in sim_ids]):
            for entry in bucket:
                if id(entry) in seen:
                    continue
                seen.add(id(entry))
                ordered.append(entry)
        most_likely = (ranked[0]["point"] if ranked else None) if (
            not grouped or suspicious_group) else None
        n_simulated = len(simulated_points)
        n_real = len(points) - n_simulated

        notes = []
        if grade_mode == "group" and not manual_reference:
            notes.append(
                "分级方式：自动分组（grade_mode=group）。不预设哪个点是好的：把所有真实测点"
                "的 ln(band_ratio) 放在一起拟合 1D 高斯混合，BIC 选 k=1/k=2，且 k=2 需满足"
                "分离度 z>=2.5；可疑组按「少数派」与「低 band_ratio」两个判据确定，冲突时以"
                "少数派为准并告警。")
            notes.append(
                "分组仍是相对判定：它回答「这几组里哪组不像其余」，不回答「这里一定是空鼓」；"
                "判据方向（band_ratio 低者为可疑）在这条加速度计链上尚未标定。")
            if grouped and p_grouping is not None and p_grouping < GROUP_ACCEPT_P:
                notes.append("分组证据不足（p_grouping=%.2f < %.2f）：结论只作提示，"
                             "建议增加每点敲击数后重看。" % (p_grouping, GROUP_ACCEPT_P))
            if ranked_only and grouping_fallback != "too_few_points":
                notes.append("本场未检测到分组（k=1）：所有点落在同一分布内，"
                             "这是唯一可以说「没有相对可疑点」的场合，但仍不等于「墙体全部合格」。")
        elif grade_mode == "group" and manual_reference:
            notes.append("当前为手动基准模式：操作者手动指定的参考点已覆盖自动分组"
                         "（自动分组已暂停）；结论只相对于这个参考点。")
        elif grade_mode == "rank":
            notes.append(
                "分级方式：相对排名（grade_mode=rank）。T1=%.2f／T2=%.2f 不参与分级；"
                "分档取本场可比测点 rho 升序的分位数（q=(k-1)/(n-1)：q<=1/3→G2、"
                "<=2/3→G1、其余 G0）。" % (t1, t2))
            notes.append(
                "相对排名模式永远会给出一个名次，包括全部合格的情况；名次只在排序置信度"
                "（p_order_significant）高时才有意义，且它衡量的是相对可疑程度，"
                "不是空鼓的绝对概率。")
        else:
            notes.append(
                "分级方式：固定阈值（grade_mode=threshold）。T1=%.2f／T2=%.2f 是待标定的"
                "占位值：必须用真实粘接／脱粘样本的 rho 分布重新确定（报告附录 C.4 的"
                "标定流程），不能当作定论。" % (t1, t2))
        notes.append(
            "band_ratio_lh 与 f_peak_hz 在固定信号带 [%.0f, %.0f] Hz、交叉点 "
            "%.0f Hz 上计算（受 Nyquist 保护 0.45×fs 限制），与报告 "
            "300–15000 Hz 麦克风音频带数值不可直接比较。"
            % (band_lo, self.config["band_hi_hz"], self.config["crossover_hz"]))
        notes.append("分级是相对量：换建筑、换探头或换场次都必须重新建立基准点/重新分组。")
        notes.append(
            "f_peak 的方向还没有标定：报告音频带里脱粘时峰值升高（328→468 Hz），"
            "这条加速度计链的固定信号带与峰值落点（210–280 Hz）不同，结论不能直接搬。"
            "默认 fpeak_mode=\"either\"（只看峰值是否移动，不押方向）是刻意的保守选择，"
            "等真实粘接／脱粘样本出来再钉死方向。")
        if cluster_conflict:
            notes.insert(0, "两组分离明显，但「少数派」与「低 ratio 组」不是同一组："
                            "方向判据与多数先验冲突，本场结论对方向假设敏感，请复核。")
        if fpeak_limited:
            notes.insert(0,
                         "基准峰 f_ref=%.1f Hz 贴在信号带下沿（band_lo=%.0f Hz 的 1.2 倍"
                         "以内）：第二条件（f_peak 一致性）本场无分辨力，判据实际上只剩 rho。"
                         % (f_ref, band_lo))
        if n_simulated:
            notes.insert(0, "本面板含 %d 个仿真测点（sp:true，%s）：它们不参与排序与结论，"
                         "不是测量结果；真实测量请接入探头或先清空本次测量。"
                         % (n_simulated,
                            "、".join("%s/%s" % (p["point"], p["dev"])
                                     for p in simulated_points)))
        if ref is None and grade_mode in ("rank", "threshold"):
            notes.insert(0, "尚未建立基准点：rank/threshold 模式需要参考点。")
        elif ref is not None and not any(p["is_reference"] for p in points):
            notes.insert(0, "基准点 %s 当前窗口内已没有样本，仅保留其基准值。"
                         % ref["point"])

        if grade_mode in ("rank", "threshold") and ref is None:
            verdict = ("当前为 %s 模式但尚未建立基准点：rank/threshold 需要参考点；"
                       "可以手动建立基准，或把分级方式切回「自动分组」。" % grade_mode)
        elif grade_mode == "group" and not manual_reference:
            verdict = self._group_verdict(
                comparable, grouped, p_grouping, separation_z, group_gap,
                suspicious_group, baseline_group, cluster_conflict,
                ranked_only, grouping_fallback, n_comparable)
        elif manual_reference and ref is not None and n_comparable == 0:
            ref_bucket = next((p for p in points if p["is_reference"]), None)
            ref_taps = (ref_bucket["n_taps"] if ref_bucket is not None
                        else ref.get("n_taps"))
            try:
                nxt_idx = (int(ref["point"][1]) + 1) % 6
            except (TypeError, ValueError, IndexError):
                nxt_idx = 1
            verdict = ("当前手动基准 %s（%d 拍），还没有第二个可比测点——请用页面上的 "
                       "P0..P5 按钮或设备菜单换到 P%d 再测。")
            verdict = verdict % (ref["point"], ref_taps, nxt_idx)
        elif grade_mode == "rank" or manual_reference:
            verdict = self._rank_verdict(ranked, ref,
                                         p_order_significant, spread)
        else:
            verdict = self._grade_verdict(ordered, ref, ranked, t1, t2,
                                          n_simulated)
        current = self.current_point()
        return {
            "reference": ref,
            "points": ordered,
            "grade_rule": {"t1": t1, "t2": t2,
                           "fpeak_mode": self.config["fpeak_mode"],
                           "fpeak_tol": self.config["fpeak_tol"]},
            "grade_mode": grade_mode,
            "manual_reference": manual_reference,
            "grouped": grouped,
            "p_grouping": p_grouping,
            "separation_z": separation_z,
            "group_gap": group_gap,
            "suspicious_group": suspicious_group,
            "baseline_group": baseline_group,
            "cluster_conflict": cluster_conflict,
            "ranked_only": ranked_only,
            "grouping_fallback": grouping_fallback,
            "most_likely_debonded": most_likely,
            "verdict": verdict,
            "p_order_significant": p_order_significant,
            "spread": spread,
            "p_debond_meaning": p_debond_meaning,
            "fpeak_resolution_limited": fpeak_limited,
            "n_simulated_points": n_simulated,
            "n_real_points": n_real,
            "n_comparable": n_comparable,
            "has_simulated": bool(n_simulated),
            "current_point": current["current_point"],
            "current_point_dev": current["current_point_dev"],
            "current_point_ms": current["current_point_ms"],
            "current_point_source": current["current_point_source"],
            "ts": int(time.time() * 1000),
            "notes": notes,
        }

    def _apply_rank_grades(self, comparable, ratios_by_key, r_ref):
        n = len(comparable)
        if n == 0:
            return None, None
        if n >= 2:
            jb = self._rank_bootstrap(comparable, ratios_by_key, r_ref)
            for p in comparable:
                key = (p["dev"], p["point"])
                info = jb["points"][key]
                rho_grade = GRADE_ORDER[info["grade_numeric"]]
                grade, quality, poor = self._quality_gate(p, rho_grade)
                p.update({
                    "grade": grade,
                    "rho_grade": rho_grade,
                    "grade_confidence": info["grade_confidence"],
                    "rank_confidence": info["rank_confidence"],
                    "p_debond": info["p_top_third"],
                    "rho_ci": info["rho_ci"],
                    "confidence": info["grade_confidence"] * quality,
                    "confidence_pct": round(
                        100.0 * info["grade_confidence"] * quality, 1),
                    "inconsistent": False,
                    "poor_contact": poor,
                })
            return jb["p_order_significant"], jb["spread"]
        p = comparable[0]
        key = (p["dev"], p["point"])
        single = self._single_point_ci(ratios_by_key[key], r_ref)
        grade, quality, poor = self._quality_gate(p, single["grade"])
        p.update({
            "grade": grade,
            "rho_grade": single["grade"],
            "grade_confidence": single["grade_confidence"],
            "rank_confidence": None,
            "p_debond": single["p_debond"],
            "rho_ci": single["rho_ci"],
            "confidence": (single["grade_confidence"] * quality
                           if single["grade_confidence"] is not None else None),
            "confidence_pct": (round(100.0 * single["grade_confidence"] * quality, 1)
                               if single["grade_confidence"] is not None else None),
            "inconsistent": False,
            "poor_contact": poor,
            "reason": single["reason"],
        })
        return None, None

    def _fallback_quantile_grade(self, comparable):
        ranked = sorted(comparable,
                        key=lambda p: p["median_band_ratio"]
                        if p["median_band_ratio"] is not None else float("inf"))
        n = len(ranked)
        for k, p in enumerate(ranked):
            if n <= 1:
                grade = "G0"
            else:
                q = k / float(n - 1)
                grade = "G2" if q <= 1.0 / 3.0 else (
                    "G1" if q <= 2.0 / 3.0 else "G0")
            g, quality, poor = self._quality_gate(p, grade)
            p.update({
                "grade": g,
                "rho_grade": grade,
                "grade_confidence": None,
                "rank_confidence": None,
                "p_debond": None,
                "rho_ci": None,
                "confidence": None,
                "confidence_pct": None,
                "inconsistent": False,
                "poor_contact": poor,
                "band_ratio_ci": None,
            })

    def _group_grade(self, comparable, ratios_by_key):
        keys = [(p["dev"], p["point"]) for p in comparable]
        arrays = []
        samples = []
        cis = {}
        for k in keys:
            arr = np.asarray(ratios_by_key[k], dtype=float)
            arr = arr[np.isfinite(arr) & (arr > 0)]
            arrays.append(arr)
            samples.append(np.log(arr))
            lo, hi = np.percentile(arr, [5.0, 95.0])
            cis[k] = [float(lo), float(hi)]
        pooled = np.concatenate(samples)
        rng = np.random.default_rng(BOOTSTRAP_SEED)
        fit1 = _gmm1d_fit(pooled, 1, rng)
        fit2 = _gmm1d_fit(pooled, 2, rng)
        bic1 = _gmm1d_bic(fit1, pooled.size, 1)
        bic2 = _gmm1d_bic(fit2, pooled.size, 2)
        sep_z = _group_separation_z(fit2["means"], fit2["variances"])
        order = np.argsort(fit2["means"])
        # per-point posterior, components sorted by mean (ascending)
        posts = []
        for arr in samples:
            c = _gmm1d_logpdf(arr, fit2["means"], fit2["variances"]) + np.log(fit2["weights"])[None, :]
            cm = c - np.max(c, axis=1, keepdims=True)
            resp = np.exp(cm)
            resp /= resp.sum(axis=1, keepdims=True)
            posts.append(resp.mean(axis=0)[order])
        means = fit2["means"][order]
        variances = fit2["variances"][order]
        labels = np.asarray([int(np.argmax(post)) for post in posts])
        counts = np.bincount(labels, minlength=2) if len(labels) else np.array([0, 0])
        enough_points = (len(labels) >= GROUP_MIN_POINTS
                         and int(counts.min()) >= 1
                         and int(counts.max()) >= GROUP_MIN_CLUSTER_POINTS)
        accepted = bool(bic2 < bic1 and sep_z >= GROUP_SEP_Z and enough_points)
        out = {
            "grouped": accepted,
            "p_grouping": None,
            "separation_z": sep_z,
            "group_gap": None,
            "suspicious_group": [],
            "baseline_group": [],
            "cluster_conflict": False,
            "ranked_only": not accepted,
            "per_point": {},
        }
        if not accepted:
            out["separation_z"] = None
            for p in comparable:
                g, quality, poor = self._quality_gate(p, "G0")
                out["per_point"][(p["dev"], p["point"])] = {
                    "grade": g, "rho_grade": "G0",
                    "grade_confidence": None, "rank_confidence": None,
                    "p_debond": None, "rho_ci": None,
                    "confidence": None, "confidence_pct": None,
                    "inconsistent": False, "poor_contact": poor,
                    "group": None, "group_prob": None,
                    "band_ratio_ci": cis.get((p["dev"], p["point"])),
                    "reason": None,
                }
            return out
        # majority prior (A: smaller point count) vs direction (B: lower mean)
        count_a = int(np.argmin(counts))
        dir_b = 0 if means[0] <= means[1] else 1
        if counts[0] == counts[1]:
            suspicious_comp = dir_b
            conflict = False
        else:
            suspicious_comp = count_a
            conflict = (count_a != dir_b)
        if conflict:
            suspicious_comp = count_a
        baseline_comp = 1 - suspicious_comp
        suspicious_group = []
        baseline_group = []
        for i, p in enumerate(comparable):
            name = p["point"]
            if labels[i] == suspicious_comp:
                suspicious_group.append(name)
            else:
                baseline_group.append(name)
        group_gap = float(np.exp(means[suspicious_comp]
                                 - means[baseline_comp]))
        # bootstrap membership probabilities
        boot = self._group_bootstrap(arrays, labels, means,
                                     suspicious_comp)
        out.update({
            "p_grouping": boot["p_grouping"],
            "group_gap": group_gap,
            "suspicious_group": suspicious_group,
            "baseline_group": baseline_group,
            "cluster_conflict": bool(conflict),
        })
        for i, p in enumerate(comparable):
            key = (p["dev"], p["point"])
            group = "suspicious" if labels[i] == suspicious_comp else "baseline"
            gprob = boot["group_prob"][i]
            grade = "G2" if group == "suspicious" else "G0"
            if (gprob is not None
                    and GROUP_PROB_AMBIG_LOW <= gprob <= GROUP_PROB_AMBIG_HIGH):
                grade = "G1"
            g, quality, poor = self._quality_gate(p, grade)
            out["per_point"][key] = {
                "grade": g, "rho_grade": grade,
                "grade_confidence": gprob,
                "rank_confidence": None,
                "p_debond": (gprob if group == "suspicious"
                             else (1.0 - gprob if gprob is not None else None)),
                "rho_ci": None,
                "confidence": (gprob * quality if gprob is not None else None),
                "confidence_pct": (round(100.0 * gprob * quality, 1)
                                   if gprob is not None else None),
                "inconsistent": False, "poor_contact": poor,
                "group": group, "group_prob": gprob,
                "band_ratio_ci": cis.get(key),
                "reason": None,
            }
        return out

    def _group_bootstrap(self, arrays, final_labels, means, suspicious_comp):
        m = len(arrays)
        sizes = np.asarray([a.size for a in arrays], dtype=int)
        rng = np.random.default_rng(BOOTSTRAP_SEED)
        B = GROUP_BOOTSTRAP_N
        resampled = []
        for arr in arrays:
            idx = rng.integers(0, arr.size, size=(B, arr.size))
            resampled.append(np.log(arr[idx]))
        Y = np.concatenate(resampled, axis=1) if resampled else np.zeros((B, 0))
        point_med = np.stack([np.median(r, axis=1) for r in resampled], axis=1)
        # per-draw k=1 log-likelihood
        mu1 = np.mean(Y, axis=1)
        var1 = np.maximum(np.var(Y, axis=1), 1e-9)
        ll1 = np.sum(-0.5 * np.log(2.0 * np.pi * var1)[:, None]
                     - (Y - mu1[:, None]) ** 2 / (2.0 * var1[:, None]), axis=1)
        # vectorised EM for k=2, median-split start
        med = np.median(Y, axis=1)
        lower = Y < med[:, None]
        n_lo = np.maximum(lower.sum(axis=1), 1)
        n_hi = np.maximum((~lower).sum(axis=1), 1)
        mu = np.stack([np.sum(np.where(lower, Y, 0.0), axis=1) / n_lo,
                       np.sum(np.where(lower, 0.0, Y), axis=1) / n_hi], axis=1)
        var = np.tile(np.maximum(np.var(Y, axis=1), 1e-9)[:, None], (1, 2))
        w = np.full((B, 2), 0.5)
        ll2 = np.full(B, -np.inf)
        for _ in range(GROUP_EM_BOOT_ITERS):
            log_comp = (-0.5 * np.log(2.0 * np.pi * var)[:, None, :]
                        - (Y[:, :, None] - mu[:, None, :]) ** 2 / (2.0 * var)[:, None, :]
                        + np.log(np.maximum(w, 1e-12))[:, None, :])
            mx = np.max(log_comp, axis=2, keepdims=True)
            lse = mx[:, :, 0] + np.log(np.sum(np.exp(log_comp - mx), axis=2))
            resp = np.exp(log_comp - lse[:, :, None])
            nk = resp.sum(axis=1) + 1e-12
            w = nk / nk.sum(axis=1, keepdims=True)
            mu = np.sum(resp * Y[:, :, None], axis=1) / nk
            var = np.maximum(np.sum(resp * (Y[:, :, None] - mu[:, None, :]) ** 2,
                                    axis=1) / nk, 1e-9)
            ll2 = np.sum(lse, axis=1)
        bic1 = -2.0 * ll1 + 2.0 * np.log(max(Y.shape[1], 2))
        bic2 = -2.0 * ll2 + 5.0 * np.log(max(Y.shape[1], 2))
        sep = np.abs(mu[:, 0] - mu[:, 1]) / np.sqrt((var[:, 0] ** 2 + var[:, 1] ** 2) / 2.0)
        accepted = (bic2 < bic1) & (sep >= GROUP_SEP_Z)
        # align each draw's components to the final group labels
        final_means = np.asarray(means, dtype=float)
        label_of_comp = np.zeros((B, 2), dtype=int)
        for j in range(2):
            d0 = np.abs(mu[:, j] - final_means[0])
            d1 = np.abs(mu[:, j] - final_means[1])
            label_of_comp[:, j] = np.where(d0 <= d1, 0, 1)
        draw_labels = np.full((B, m), -1, dtype=int)
        same_membership = np.zeros(B)
        for b in range(B):
            if not accepted[b]:
                continue
            d = np.abs(point_med[b][:, None] - mu[b][None, :])
            chosen = np.argmin(d, axis=1)
            draw_labels[b] = label_of_comp[b][chosen]
            if np.mean(draw_labels[b] == final_labels) >= GROUP_MEMBER_AGREE:
                same_membership[b] = 1.0
        group_prob = np.mean(draw_labels == np.asarray(final_labels)[None, :],
                             axis=0)
        p_grouping = float(np.mean(same_membership))
        return {"p_grouping": p_grouping, "group_prob": group_prob.tolist()}

    @staticmethod
    def _group_verdict(comparable, grouped, p_grouping, separation_z, group_gap,
                       suspicious_group, baseline_group, cluster_conflict,
                       ranked_only, grouping_fallback, n_comparable):
        if ranked_only and grouping_fallback == "too_few_points":
            return ("测点太少（%d 个可比测点，自动分组至少需要 %d 个）：暂用相对排名"
                    "分级，结论只作排序参考。" % (n_comparable, GROUP_MIN_POINTS))
        if not grouped:
            return ("本场未检测到分组（全部 %d 个点落在同一分布内）："
                    "各点差异在噪声范围内，没有相对可疑的点。" % n_comparable)
        ztxt = separation_z if separation_z is not None else 0.0
        if cluster_conflict:
            return ("两组分离明显（分离度 z=%.1f），但「少数派」与「低 ratio 组」不是同一组"
                    "（少数派 %s 的 ratio 反而更高）；方向判据与多数先验冲突，本场结论对"
                    "方向假设敏感，请复核。分组置信度 %.0f%%。"
                    % (ztxt, "、".join(suspicious_group),
                       100.0 * (p_grouping or 0.0)))
        if p_grouping is not None and p_grouping >= GROUP_ACCEPT_P:
            return ("本场分两组（分离度 z=%.1f，可疑组 band_ratio 约为基准组的 %.2f 倍）："
                    "可疑组 %s（G2）；其余 %s 为基准组（G0）。分组置信度 %.0f%%。"
                    % (ztxt, group_gap if group_gap is not None else float("nan"),
                       "、".join(suspicious_group) or "—",
                       "、".join(baseline_group) or "—", 100.0 * p_grouping))
        return ("疑似分成两组但证据不足（分组置信度 %.0f%%，分离度 z=%.1f）：%s 的 "
                "band_ratio 系统性偏低，建议增加每点敲击数后重看。"
                % (100.0 * (p_grouping or 0.0), ztxt,
                   "、".join(suspicious_group) or "—"))

    def _quality_gate(self, entry, grade):
        # Measurement-quality gate: a point measured with poor contact cannot
        # keep its relative rank as a firm grade; it is downgraded one step and
        # its confidence is discounted.
        quality = 1.0
        poor = False
        share = entry.get("contact_ok_share")
        clamp = entry.get("band_clamped_share")
        if ((share is not None and share < POOR_CONTACT_SHARE)
                or (clamp is not None and clamp > BAND_CLAMPED_SHARE)):
            idx = GRADE_ORDER.index(grade)
            grade = GRADE_ORDER[max(0, idx - 1)]
            poor = True
            quality *= POOR_CONTACT_FACTOR
        return grade, quality, poor

    def _threshold_grade(self, entry, ratios, r_ref, t1, t2):
        rho = entry["rho"]
        d_f = entry["d_f"]
        if rho >= t1:
            rho_grade = "G0"
        elif rho >= t2:
            rho_grade = "G1"
        else:
            rho_grade = "G2"
        grade = rho_grade
        inconsistent = False
        quality = 1.0
        if grade in ("G1", "G2") and d_f is not None:
            mode = str(self.config["fpeak_mode"])
            tol = float(self.config["fpeak_tol"])
            if mode == "up":
                consistent = float(d_f) >= 1.0 + tol
            elif mode == "down":
                consistent = float(d_f) <= 1.0 - tol
            else:
                consistent = abs(float(d_f) - 1.0) >= tol
            if not consistent:
                if grade == "G2":
                    grade = "G1"
                inconsistent = True
                quality *= INCONSISTENT_FACTOR
        grade, gate_quality, poor = self._quality_gate(entry, grade)
        quality *= gate_quality
        boot = self._bootstrap_rho(ratios, r_ref, t1, t2, rho_grade)
        return {
            "grade": grade,
            "rho_grade": rho_grade,
            "grade_confidence": boot["grade_confidence"],
            "rank_confidence": None,
            "p_debond": boot["p_debond"],
            "rho_ci": boot["rho_ci"],
            "confidence": boot["grade_confidence"] * quality,
            "confidence_pct": round(100.0 * boot["grade_confidence"] * quality, 1),
            "inconsistent": inconsistent,
            "poor_contact": poor,
        }

    def _rank_bootstrap(self, comparable, ratios_by_key, r_ref):
        # Joint bootstrap over all comparable points: it is the ORDER that is
        # resampled, not each point in isolation, because the grade of a point
        # now depends on where the other points land in the same draw.
        m = len(comparable)
        keys = [(p["dev"], p["point"]) for p in comparable]
        arrays = [np.asarray(ratios_by_key[k], dtype=float) for k in keys]
        med = np.asarray([p["rho"] for p in comparable], dtype=float)
        final_order = np.argsort(med, kind="stable")
        final_rank = np.empty(m, dtype=int)
        final_rank[final_order] = np.arange(m)
        q_final = final_rank / float(m - 1)
        grade_final = np.where(q_final <= 1.0 / 3.0, 2,
                               np.where(q_final <= 2.0 / 3.0, 1, 0))
        rng = np.random.default_rng(BOOTSTRAP_SEED)
        stars = np.empty((m, RANK_BOOTSTRAP_N), dtype=float)
        for i, arr in enumerate(arrays):
            n = arr.size
            if n < 1:
                stars[i] = np.nan
                continue
            idx = rng.integers(0, n, size=(RANK_BOOTSTRAP_N, n))
            stars[i] = np.median(arr[idx], axis=1) / r_ref
        order_star = np.argsort(stars, axis=0, kind="stable")
        rank_star = np.argsort(order_star, axis=0, kind="stable")
        q_star = rank_star / float(m - 1)
        grade_star = np.where(q_star <= 1.0 / 3.0, 2,
                              np.where(q_star <= 2.0 / 3.0, 1, 0))
        same_order = (order_star == final_order[:, None]).all(axis=0)
        p_order = float(np.mean(same_order))
        rest_med = float(np.median(med[final_order[1:]])) if m >= 2 else 0.0
        spread = (float(med[final_order[0]] / rest_med)
                  if rest_med else None)
        out = {"p_order_significant": p_order, "spread": spread, "points": {}}
        for i, key in enumerate(keys):
            lo, hi = (float(v) for v in
                      np.percentile(stars[i], list(BOOTSTRAP_CI)))
            out["points"][key] = {
                "grade_numeric": int(grade_final[i]),
                "grade_confidence": float(np.mean(grade_star[i] == grade_final[i])),
                "rank_confidence": float(np.mean(rank_star[i] == final_rank[i])),
                "p_top_third": float(np.mean(grade_star[i] == 2)),
                "rho_ci": [lo, hi],
            }
        return out

    def _single_point_ci(self, ratios, r_ref):
        arr = np.asarray([float(v) for v in ratios if finite(v)], dtype=float)
        n = arr.size
        if n < 2 or not finite(r_ref) or r_ref <= 0:
            return {"grade": "NODATA", "grade_confidence": None,
                    "p_debond": None, "rho_ci": None,
                    "reason": "TOO_FEW_TAPS"}
        rng = np.random.default_rng(BOOTSTRAP_SEED)
        idx = rng.integers(0, n, size=(BOOTSTRAP_N, n))
        stars = np.median(arr[idx], axis=1) / r_ref
        lo, hi = (float(v) for v in np.percentile(stars, list(BOOTSTRAP_CI)))
        p_below = float(np.mean(stars < 1.0))
        p_above = float(np.mean(stars > 1.0))
        if hi < 1.0:
            grade, reason = "G2", None
            grade_conf = p_below
        elif lo > 1.0:
            grade, reason = "G0", None
            grade_conf = p_above
        else:
            grade, reason = "G1", "CI straddles reference"
            grade_conf = None
        return {"grade": grade, "grade_confidence": grade_conf,
                "p_debond": p_below, "rho_ci": [lo, hi],
                "reason": reason}

    @staticmethod
    def _rank_verdict(graded, ref, p_order, spread):
        if not graded:
            return ("还没有可比测点（非基准、>=%d 次有效敲击），暂不能排名；"
                    "基准点为 %s。" % (MIN_TAPS_PER_POINT,
                                     ref["point"] if ref else "—"))
        best = graded[0]
        if p_order is None:
            # only one comparable point: CI against the reference, no ranking
            ci = best.get("rho_ci") or [None, None]
            lo, hi = ci[0], ci[1]
            if best["grade"] == "G2":
                return ("%s 相对基准显著偏低：rho=%.2f（95%% CI [%.2f, %.2f]），"
                        "判为 G2（相对档位）；本场只有一个可比测点，没有排序。"
                        % (best["point"], best["rho"], lo, hi))
            if best["grade"] == "G0":
                return ("%s 相对基准显著偏高：rho=%.2f（95%% CI [%.2f, %.2f]），"
                        "判为 G0；本场只有一个可比测点，没有排序。"
                        % (best["point"], best["rho"], lo, hi))
            return ("%s 与基准无显著差异（95%% CI [%.2f, %.2f] 跨过 1.0）："
                    "证据不足（CI straddles reference），建议复测或换基准后重比。"
                    % (best["point"], lo, hi))
        others = [p["rho"] for p in graded[1:]]
        other_med = float(np.median(others)) if others else None
        drop = abs(1.0 - best["rho"]) * 100.0
        if p_order >= 0.9:
            return ("%s 相对最可疑：rho=%.2f，与本场其余点分离（排序置信度 %.0f%%），"
                    "较基准下降 %.0f%%；分级 %s 是相对档位，不是绝对严重度。"
                    % (best["point"], best["rho"], 100.0 * p_order, drop,
                       best["grade"]))
        return ("本场各点差异未超出噪声（排序置信度 %.0f%%）：%s 的 rho 最低"
                "（%.2f vs 其余中位 %.2f）但不可据此判缺陷，建议对该点复测或"
                "换基准后重比。"
                % (100.0 * p_order, best["point"], best["rho"],
                   other_med if other_med is not None else float("nan")))

    def _bootstrap_rho(self, ratios, r_ref: float, t1: float, t2: float,
                       rho_grade: str) -> dict:
        """Percentile bootstrap of the point's median band_ratio_lh.

        Resampling the point's own taps answers the only question the field
        data can answer: if this point were re-measured, how often would the
        grade come out the same?  Fixed seed -> identical output for identical
        taps, which is what makes the number reportable.
        """
        arr = np.asarray([float(v) for v in ratios if finite(v)], dtype=float)
        n = arr.size
        target = GRADE_ORDER.index(rho_grade)
        if n < 2 or not finite(r_ref) or r_ref <= 0:
            return {"grade_confidence": 0.0, "p_debond": None, "rho_ci": None}
        rng = np.random.default_rng(BOOTSTRAP_SEED)
        idx = rng.integers(0, n, size=(BOOTSTRAP_N, n))
        rho_star = np.median(arr[idx], axis=1) / r_ref
        classes = np.where(rho_star >= t1, 0,
                           np.where(rho_star >= t2, 1, 2))
        grade_conf = float(np.mean(classes == target))
        p_debond = float(np.mean(rho_star < t1))
        lo, hi = (float(v) for v in
                  np.percentile(rho_star, list(BOOTSTRAP_CI)))
        return {"grade_confidence": grade_conf, "p_debond": p_debond,
                "rho_ci": [lo, hi]}

    @staticmethod
    def _grade_verdict(ordered, ref, graded, t1: float, t2: float,
                       n_simulated: int = 0) -> str:
        if ref is None:
            return ("尚未建立基准点：差分测量必须先测一个已知粘接良好的区域，"
                    "再开始逐点比较。")
        if not graded:
            if n_simulated:
                return ("当前只有仿真测点（sp:true），不构成测量结论；"
                        "请接入真实探头或先清空本次测量。")
            return ("还没有测点达到 %d 次有效敲击，暂不能分级；基准点为 %s。"
                    % (MIN_TAPS_PER_POINT, ref["point"]))
        best = graded[0]
        rho = best["rho"]
        conf = best["confidence_pct"]      # already 0..100
        p_deb = best["p_debond"]
        drop = abs(1.0 - rho) * 100.0
        move = "下降" if rho <= 1.0 else "上升"
        if best["grade"] in ("G1", "G2"):
            text = ("%s 最可能空鼓：rho=%.2f（%s，分级稳定度 %.0f%%，空鼓概率 "
                    "%.0f%%），相对基准 %s %s %.0f%%"
                    % (best["point"], rho, best["grade"], conf,
                       100.0 * p_deb, ref["point"], move, drop))
            if best["poor_contact"]:
                text += "；该点接触质量不足，结论已降级"
            if best["inconsistent"]:
                text += "；峰值频率没有随 band_ratio 明显移动，两个条件未互相印证"
            return text
        return ("各测点与基准 %s 无明显差异：最接近空鼓的 %s rho=%.2f（%s，"
                "分级稳定度 %.0f%%，空鼓概率 %.0f%%），相对基准%s %.0f%%"
                % (ref["point"], best["point"], rho, best["grade"],
                   conf, 100.0 * p_deb, move, drop))

    # -- taps --------------------------------------------------------------
    def add_tap(self, tap: dict) -> dict:
        with self.lock:
            self.taps.append(tap)
            self.latest = tap
            self.last_tap_at = time.time()
            self.fs_last = tap.get("fs")
            self._persist_tap(tap)
            return self._stats_locked()

    def history(self, limit: int) -> dict:
        with self.lock:
            rows = [self._row(t) for t in list(self.taps)[-limit:]]
            columns = (["t_ms", "dev", "pt", "tap", "seq", "fs", "band_lo_hz",
                        "band_hi_hz", "crossover_hz"]
                       + FEATURES + ["impulse_norm", "contact_ok",
                                     "band_clamped", "sp", "verdict"])
        return {"n": len(rows), "columns": columns, "rows": rows}

    @staticmethod
    def _row(tap: dict) -> dict:
        row = {"t_ms": tap.get("t_ms"), "dev": tap.get("dev"),
               "pt": tap.get("pt"),
               "tap": tap.get("tap"), "seq": tap.get("seq"),
               "fs": tap.get("fs"),
               "contact_ok": tap.get("contact_ok"),
               "band_clamped": tap.get("band_clamped"),
               "sp": tap.get("sp"),
               "band_lo_hz": (tap.get("band") or [None, None])[0],
               "band_hi_hz": (tap.get("band") or [None, None])[1],
               "crossover_hz": tap.get("crossover_hz"),
               "verdict": tap.get("verdict")}
        feats = tap.get("features") or {}
        for key in FEATURES:
            row[key] = feats.get(key)
        row["impulse_norm"] = feats.get("impulse_norm")
        return row

    # -- statistics --------------------------------------------------------
    def _window_taps(self) -> List[dict]:
        return list(self.taps)[-int(self.config["window"]):]

    def _stats_locked(self) -> dict:
        taps = self._window_taps()
        describe = self.mod.describe

        def blocks(subset):
            out = {}
            for feat in FEATURES + ["impulse_norm"]:
                out[feat] = describe([(t.get("features") or {}).get(feat)
                                      for t in subset])
            return out

        verdicts = [t.get("verdict", "UNKNOWN") for t in taps]
        counts = Counter(verdicts)
        by_verdict = {}
        for name in ("BONDED", "DEBOND"):
            subset = [t for t in taps if t.get("verdict") == name]
            by_verdict[name] = {"n": len(subset), "features": blocks(subset)}
        return {
            "n": len(taps),
            "window": int(self.config["window"]),
            "th_band_ratio": self.config["th_band_ratio"],
            "band_lo_hz": self.config["band_lo_hz"],
            "band_hi_hz": self.config["band_hi_hz"],
            "crossover_hz": self.config["crossover_hz"],
            "features": blocks(taps),
            "by_verdict": by_verdict,
            "verdict_counts": {"BONDED": counts.get("BONDED", 0),
                               "DEBOND": counts.get("DEBOND", 0),
                               "UNKNOWN": counts.get("UNKNOWN", 0)},
            "last_tap_ms": taps[-1].get("t_ms") if taps else None,
        }

    def stats(self) -> dict:
        with self.lock:
            return self._stats_locked()

    # -- fan-out -----------------------------------------------------------
    def broadcast(self, message: dict) -> None:
        if not self.ws_clients:
            return
        text = dumps(message).decode("utf-8")
        with self.lock:
            clients = list(self.ws_clients)
        for client in clients:
            client.push(text)

    def add_client(self, client: WsClient) -> None:
        with self.lock:
            self.ws_clients.append(client)
        client.start()
        log("websocket client from %s (total %d)"
            % (client.addr[0], len(self.ws_clients)))
        with self.lock:
            hello = {"type": "hello", "config": dict(self.config),
                     "stats": self._stats_locked(), "latest": self.latest,
                     "points": self._points_locked(),
                     "source": SOURCE_TAG}
        client.push(dumps(hello).decode("utf-8"))

    def remove_client(self, client: WsClient) -> None:
        with self.lock:
            if client in self.ws_clients:
                self.ws_clients.remove(client)
            n = len(self.ws_clients)
        log("websocket client gone (total %d)" % n)

    # -- decode + analyse --------------------------------------------------
    def analyse_waveform(self, payload: dict) -> Optional[dict]:
        dev = str(payload.get("dev") or DEFAULT_DEVICE)
        try:
            fs = float(payload["fs"])
            n_declared = int(payload["n"])
            scale = float(payload.get("scale") or 4096.0)
            raw = base64.b64decode(payload["d"], validate=True)
        except Exception as exc:
            self._record_error({"stage": "decode", "dev": dev, "error": str(exc)})
            return None
        if fs <= 0 or scale <= 0:
            self._record_error({"stage": "decode", "dev": dev,
                                "error": "fs/scale must be positive"})
            return None
        frame_bytes = 6
        n_available = len(raw) // frame_bytes
        if n_available < 8:
            self._record_error({"stage": "decode", "dev": dev,
                                "error": "payload holds %d frames" % n_available})
            return None
        n = n_declared if 0 < n_declared <= n_available else n_available
        arr = np.frombuffer(raw[:n * frame_bytes], dtype="<i2").reshape(n, 3)
        acc = arr.astype(float) / scale                    # g
        mag = np.linalg.norm(acc, axis=1)                  # |a| in g
        pre = int(payload.get("pre") or 0)
        pre = max(0, min(pre, n))
        if pre >= 4:
            baseline = float(np.median(mag[:pre]))
            baseline_vec = acc[:pre].mean(axis=0)
        else:
            baseline = float(np.median(mag))
            baseline_vec = acc.mean(axis=0)
        amp = mag - baseline                               # PROTOCOL: mag - baseline
        t_s = np.arange(n) / fs

        band_lo = float(self.config["band_lo_hz"])
        want_hi = float(self.config["band_hi_hz"])
        want_x = float(self.config["crossover_hz"])
        # Nyquist guard: a slow poll interval narrows the band rather than
        # letting content above Nyquist alias into it.
        band_hi = min(want_hi, NYQUIST_GUARD * fs)
        crossover = min(want_x, band_hi * CROSSOVER_MAX_FRACTION)
        band_clamped = band_hi < want_hi - 1e-9
        self.counts["waveform"] += 1
        try:
            feats = self.feature_fn(t_s, amp, fs, band_lo_hz=band_lo,
                                    band_hi_hz=band_hi, crossover_hz=crossover)
        except Exception as exc:
            self._record_error({"stage": "features", "dev": dev,
                                "fs": fs, "error": "%s: %s"
                                % (type(exc).__name__, exc)})
            self.counts["feature_errors"] += 1
            return None

        raw_sp = payload.get("sp")
        if isinstance(raw_sp, bool):
            sp = raw_sp
        else:
            sp = str(raw_sp).strip().lower() in ("true", "1", "yes", "sim")
        ratio = feats.get("band_ratio_lh")
        if finite(ratio):
            verdict = ("DEBOND" if float(ratio) <= float(self.config["th_band_ratio"])
                       else "BONDED")
        else:
            verdict = "UNKNOWN"
        # Contact quality, three sources in priority order (PROTOCOL.md 7.5):
        #   1. the firmware's own contact_ok flag in the payload;
        #   2. the firmware's pkg = peak acceleration at the trigger, in g,
        #      judged against the report A.6.5 window [0.05, 8.0] g;
        #   3. a backend heuristic on peak_au / crest_factor (flagged as such,
        #      so the point table can say the quality gate was guessed).
        pt = normalise_point(payload.get("pt"))
        raw_contact = payload.get("contact_ok")
        pkg_g = None
        pkg_raw = payload.get("pkg")
        if pkg_raw is not None:
            try:
                pkg_val = float(pkg_raw)
                pkg_g = pkg_val if finite(pkg_val) else None
            except (TypeError, ValueError):
                pkg_g = None
        if isinstance(raw_contact, bool):
            contact_ok = raw_contact
            contact_source = "firmware"
        elif pkg_g is not None:
            contact_ok = bool(CONTACT_PKG_MIN_G <= pkg_g <= CONTACT_PKG_MAX_G)
            contact_source = "firmware"
        else:
            peak_au = feats.get("peak_au")
            crest = feats.get("crest_factor")
            if finite(peak_au) and finite(crest):
                contact_ok = bool(float(peak_au) >= CONTACT_MIN_PEAK_G
                                  and float(crest) >= CONTACT_MIN_CREST)
                contact_source = "heuristic"
            else:
                contact_ok = False
                contact_source = "missing"
        self.counts["tap"] += 1
        self.counts[verdict.lower()] += 1

        env = _downsample(np.abs(amp), 96)
        tap = {
            "type": "tap",
            "t_ms": int(time.time() * 1000),
            "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "dev": dev,
            "pt": pt,
            "sp": sp,
            "tap": payload.get("tap"),
            "seq": payload.get("seq"),
            "fs": fs,
            "n": n,
            "pre": pre,
            "trig_lsb": payload.get("trig"),
            "baseline_g": baseline,
            "baseline_vec_g": [float(v) for v in baseline_vec],
            "band": [band_lo, band_hi],
            "crossover_hz": crossover,
            "band_requested_hz": [band_lo, want_hi, want_x],
            "band_clamped": bool(band_clamped),
            "th_band_ratio": self.config["th_band_ratio"],
            "contact_ok": contact_ok,
            "contact_source": contact_source,
            "pkg_g": pkg_g,
            "features": feats,
            "verdict": verdict,
            "source": SOURCE_TAG,
            "template_sha256": self.meta["template_sha256"],
            "band_parameterisation": self.meta["band_parameterisation"],
            "wave": {
                "fs": fs, "n": n, "pre": pre,
                "duration_ms": round(1000.0 * n / fs, 2),
                "peak_g": float(np.max(amp)),
                "rms_g": float(np.sqrt(np.mean(amp ** 2))),
                "env": env,
            },
        }
        tap = json_safe(tap)
        if not sp:
            # Remember which point the real probe is on: this is the fallback
            # source for GET /api/point when the firmware has not acked a
            # point command (e.g. the operator used the device menu).
            self.last_real_tap = {"dev": dev, "pt": pt, "ms": tap["t_ms"]}
        stats = self.add_tap(tap)
        points = self.points()
        self.broadcast({"type": "tap", "tap": tap, "stats": stats})
        self.broadcast({"type": "points", "points": points})
        return tap

    def _record_error(self, item: dict) -> None:
        item["t_ms"] = int(time.time() * 1000)
        with self.lock:
            self.errors.append(item)
        log("ERROR " + json.dumps(json_safe(item), ensure_ascii=True))

    # -- other topics ------------------------------------------------------
    def on_measurement(self, payload: dict) -> None:
        self.counts["measurement"] += 1
        with self.lock:
            self.last_measurement = payload
            dev = str(payload.get("dev") or "")
            entry = self.devices.setdefault(dev, {})
            now_ms = int(time.time() * 1000)
            entry.update({"last_measurement": payload,
                          "last_measurement_ms": now_ms})
            if dev and not bool(payload.get("sp")):
                self.last_real_device = {"dev": dev, "ms": now_ms}
        self.broadcast({"type": "measurement", "measurement": payload})

    def on_status(self, payload: str, dev: str) -> None:
        self.counts["status"] += 1
        with self.lock:
            entry = self.devices.setdefault(dev, {})
            now_ms = int(time.time() * 1000)
            entry.update({"status": payload, "status_ms": now_ms})
            # Only a fallback for the very first seconds after a restart, when
            # no measurement frame has arrived yet.  The simulator publishes a
            # status too, so a "sim-" id never becomes the command target.
            if (payload == "online" and dev
                    and not dev.startswith("sim-")
                    and self.last_real_device is None):
                self.last_real_device = {"dev": dev, "ms": now_ms}
        self.broadcast({"type": "status", "dev": dev, "status": payload})

    def on_event(self, payload: dict, dev: str) -> None:
        self.counts["event"] += 1
        point_ack = None
        # The firmware names each ack after the command it answers, so a point
        # ack arrives as ev="point"; the generic form ev="ack" is accepted too
        # so the contract does not depend on which of the two is used.
        if (str(payload.get("cmd") or "") == "point"
                and str(payload.get("ev") or "") in ("ack", "point")):
            pt = parse_cmd_point(payload.get("pt"))
            if pt is not None:
                point_ack = {"dev": dev, "pt": pt,
                             "ms": int(time.time() * 1000)}
        with self.lock:
            self.events.append(payload)
            if point_ack is not None:
                self.last_point_ack = point_ack
        self.broadcast({"type": "event", "dev": dev, "event": payload})
        if point_ack is not None:
            self.broadcast({"type": "point_ack",
                            "current_point": point_ack["pt"],
                            "current_point_dev": point_ack["dev"],
                            "current_point_ms": point_ack["ms"]})

    def current_point(self) -> dict:
        """Current measurement point: device point-ack wins, else latest real tap.

        Timestamps decide when both sources exist, so a stale ack cannot
        override a newer tap (e.g. the operator switched points on the device
        menu instead of the web page).
        """
        with self.lock:
            ack = dict(self.last_point_ack) if self.last_point_ack else None
            tap = dict(self.last_real_tap) if self.last_real_tap else None
        if ack is not None and (tap is None or ack["ms"] >= tap["ms"]):
            chosen = ack
            source = "ack"
        elif tap is not None:
            chosen = tap
            source = "tap"
        else:
            return {"current_point": None, "current_point_dev": None,
                    "current_point_ms": None, "current_point_source": None}
        return {"current_point": chosen["pt"],
                "current_point_dev": chosen["dev"],
                "current_point_ms": chosen["ms"],
                "current_point_source": source}

    # -- health ------------------------------------------------------------
    def health(self) -> dict:
        with self.lock:
            counts = dict(self.counts)
            devices = {k: dict(v) for k, v in self.devices.items()}
            latest = self.latest
            n_ws = len(self.ws_clients)
            uptime = time.time() - self.started_at
            errors = list(self.errors)[-5:]
            config = dict(self.config)
            last_measurement = self.last_measurement
            fs_last = self.fs_last
        return {
            "ok": True,
            "service": "tap-probe analyzer",
            "http_port": self.http_port,
            "uptime_s": round(uptime, 1),
            "mqtt": {"connected": self.mqtt_connected,
                     "broker": self.broker, "port": self.broker_port,
                     "subscriptions": ["probe/+/waveform", "probe/+/measurement",
                                       "probe/+/status", "probe/+/event"]},
            "counts": counts,
            "devices": devices,
            "n_taps": len(self.taps),
            "n_ws_clients": n_ws,
            "latest_tap_ms": latest.get("t_ms") if latest else None,
            "last_measurement_ms": (last_measurement or {}).get("_t_ms"),
            "config": config,
            "fs_last": fs_last,
            "band": {"band_lo_hz": config["band_lo_hz"],
                     "band_hi_hz": config["band_hi_hz"],
                     "crossover_hz": config["crossover_hz"],
                     "effective_band_hi_hz": (min(float(config["band_hi_hz"]),
                                                  NYQUIST_GUARD * fs_last)
                                              if fs_last else None),
                     "nyquist_guard": NYQUIST_GUARD,
                     "note": "fixed reduced band; not comparable with the "
                             "300..15000 Hz audio-band numbers in the report"},
            "template": self.meta,
            "recent_errors": errors,
        }


def _downsample(values: np.ndarray, points: int) -> List[float]:
    """Block-max downsample for the dashboard sparkline."""
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return []
    if values.size <= points:
        return [float(v) for v in values]
    edges = np.linspace(0, values.size, points + 1).astype(int)
    out = []
    for i in range(points):
        chunk = values[edges[i]:max(edges[i] + 1, edges[i + 1])]
        out.append(float(np.max(chunk)))
    return out


# ---------------------------------------------------------------------------
# MQTT glue
# ---------------------------------------------------------------------------
def start_mqtt(state: ProbeState) -> None:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id="tap-analyzer-%d" % (int(time.time()) % 100000),
                         clean_session=True)
    state.mqtt_client = client

    def on_connect(cl, userdata, flags, reason_code, properties=None):
        state.mqtt_connected = _connect_ok(reason_code)
        if not state.mqtt_connected:
            log("MQTT connect refused: %s" % (reason_code,))
            return
        log("MQTT connected to %s:%d" % (state.broker, state.broker_port))
        cl.subscribe([("probe/+/waveform", 0), ("probe/+/measurement", 1),
                      ("probe/+/status", 1), ("probe/+/event", 1)])

    def on_disconnect(cl, userdata, flags, reason_code, properties=None):
        state.mqtt_connected = False
        log("MQTT disconnected: %s" % (reason_code,))

    def on_message(cl, userdata, msg):
        topic = msg.topic
        try:
            text = msg.payload.decode("utf-8", errors="replace")
        except Exception:
            return
        parts = topic.split("/")
        dev = parts[1] if len(parts) > 1 else DEFAULT_DEVICE
        leaf = parts[-1]
        try:
            if leaf == "status":
                state.on_status(text.strip(), dev)
                return
            payload = json.loads(text)
            if not isinstance(payload, dict):
                return
            if leaf == "waveform":
                tap = state.analyse_waveform(payload)
                if tap is not None:
                    feats = tap["features"]
                    log("tap %s seq=%s fs=%.0f band=[%.0f, %.0f] ratio=%s -> %s"
                        % (tap.get("dev"), tap.get("seq"), tap["fs"],
                           tap["band"][0], tap["band"][1],
                           ("%.3f" % feats["band_ratio_lh"])
                           if finite(feats.get("band_ratio_lh")) else "nan",
                           tap["verdict"]))
            elif leaf == "measurement":
                payload["_t_ms"] = int(time.time() * 1000)
                state.on_measurement(payload)
            elif leaf == "event":
                state.on_event(payload, dev)
        except Exception as exc:                             # pragma: no cover
            state._record_error({"stage": "message", "topic": topic,
                                 "error": str(exc)})

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=8)
    try:
        client.connect_async(state.broker, state.broker_port, keepalive=30)
    except Exception as exc:                                 # pragma: no cover
        log("MQTT connect_async failed: %s" % (exc,))
    client.loop_start()


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------
class ApiHandler(BaseHTTPRequestHandler):
    state = None                 # injected class attribute (ProbeState)
    server_version = "TapProbeAnalyzer/2.0"

    # -- helpers -----------------------------------------------------------
    def log_message(self, fmt, *args):
        log("HTTP %s %s" % (self.command, self.path))

    def _cors(self) -> None:
        origin = self.headers.get("Origin", "*")
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Vary", "Origin")

    def _json(self, obj, status=200) -> None:
        body = dumps(obj)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        if length > 1_000_000:
            return None
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    # -- routing -----------------------------------------------------------
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        st = self.state

        if path == "/api/stream":
            return self._websocket()
        if path == "/":
            return self._json({"ok": True, "service": "tap-probe analyzer",
                               "endpoints": ["/api/health", "/api/latest",
                                             "/api/history?limit=50",
                                             "/api/stats", "/api/points",
                                             "/api/config",
                                             "/api/stream (WebSocket)",
                                             "POST /api/config",
                                             "GET /api/point",
                                             "POST /api/reference",
                                             "POST /api/reset",
                                             "POST /api/point",
                                             "POST /api/cmd"],
                               "grading": "differential (rho vs reference point), "
                                          "see PROTOCOL.md section 7"})
        if path == "/api/health":
            return self._json(st.health())
        if path == "/api/latest":
            with st.lock:
                latest = st.latest
            return self._json({"ok": True, "source": SOURCE_TAG,
                               "data": latest,
                               "note": "reduced band per PROTOCOL.md section 6"})
        if path == "/api/history":
            try:
                limit = int((query.get("limit") or ["50"])[0])
            except ValueError:
                limit = 50
            limit = max(1, min(limit, MAX_HISTORY))
            return self._json({"ok": True, **st.history(limit)})
        if path == "/api/stats":
            return self._json({"ok": True, "data": st.stats()})
        if path == "/api/points":
            return self._json({"ok": True, **st.points()})
        if path == "/api/grid":
            return self._json({"ok": True, **st.grid()})
        if path == "/api/point":
            return self._json({"ok": True, **st.current_point()})
        if path == "/api/config":
            return self._json({"ok": True, "data": st.get_config(),
                               "limits": {"th_band_ratio": [0.0, 2.0],
                                          "band_lo_hz": [1.0, 2000.0],
                                          "band_hi_hz": [50.0, 5000.0],
                                          "crossover_hz": [10.0, 4000.0],
                                          "window": [5, MAX_HISTORY],
                                          "grade_mode": list(GRADE_MODES),
                                          "grade_t1": [GRADE_T1_MIN, GRADE_T1_MAX],
                                          "grade_t2": [GRADE_T2_MIN, "T1-0.05"],
                                          "fpeak_mode": list(FPEAK_MODES),
                                          "fpeak_tol": [FPEAK_TOL_MIN, FPEAK_TOL_MAX]}})
        return self._json({"ok": False, "error": "unknown endpoint: " + path},
                          404)

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        st = self.state
        body = self._read_json()
        if body is None:
            return self._json({"ok": False, "error": "invalid JSON body"}, 400)

        if path == "/api/config":
            try:
                updated = st.set_config(body)
            except (TypeError, ValueError) as exc:
                return self._json({"ok": False, "error": str(exc)}, 400)
            result = {"ok": True, "updated": updated, "data": st.get_config()}
            st.broadcast({"type": "config", "config": st.get_config()})
            # T1/T2 change the visible grades of points already measured.
            st.broadcast({"type": "points", "points": st.points()})
            return self._json(result)

        if path == "/api/point":
            if "point" in body:
                pt = parse_cmd_point(body.get("point"))
                if pt is None:
                    return self._json({"ok": False,
                                       "error": "point must be P0..P%d (or 0..%d)"
                                                % (POINT_MAX_INDEX, POINT_MAX_INDEX)},
                                      400)
            elif "delta" in body:
                try:
                    delta = int(body["delta"])
                except (TypeError, ValueError):
                    return self._json({"ok": False,
                                       "error": "delta must be an integer"}, 400)
                cur = st.current_point()
                if cur["current_point"] is None:
                    return self._json({"ok": False,
                                       "error": "current point unknown; send "
                                                "{\"point\": \"P0\"} instead"},
                                      409)
                idx = int(cur["current_point"][1]) + delta
                if not (0 <= idx <= 5):
                    return self._json({"ok": False,
                                       "error": "delta would leave P0..P5"}, 400)
                pt = "P%d" % idx
            else:
                return self._json({"ok": False,
                                   "error": "body needs {\"point\": \"P3\"} "
                                            "or {\"delta\": 1}"}, 400)
            with st.lock:
                dev = str(body.get("dev") or "").strip()
                if not dev and st.last_real_tap is not None:
                    dev = str(st.last_real_tap.get("dev") or "")
                if not dev and st.last_real_device is not None:
                    dev = str(st.last_real_device.get("dev") or "")
            if not dev:
                return self._json({"ok": False,
                                   "error": "no real device seen yet"}, 409)
            client = st.mqtt_client
            if client is None or not st.mqtt_connected:
                return self._json({"ok": False,
                                   "error": "MQTT not connected to broker"}, 503)
            payload = {"cmd": "point", "v": int(pt[1:])}
            topic = "probe/%s/cmd" % dev
            info = client.publish(topic, json.dumps(payload), qos=1)
            if info.rc != 0:
                return self._json({"ok": False,
                                   "error": "publish failed rc=%d" % info.rc},
                                  503)
            log("point command -> %s %s (mid %s)" % (dev, pt, info.mid))
            return self._json({"ok": True, "dev": dev, "point": pt,
                               "cmd_mid": info.mid})

        if path == "/api/grid":
            try:
                grid = st.set_grid(body.get("rows"), body.get("cols"))
            except (TypeError, ValueError) as exc:
                return self._json({"ok": False, "error": str(exc)}, 400)
            st.broadcast({"type": "grid", "grid": grid})
            # The device draws the same map, so tell it the new shape.  A
            # failure here is not fatal: the grid is a web-side concept and
            # the measurement still works with the previous badge.
            dev = st.last_real_device.get("dev") or DEFAULT_DEVICE
            client = st.mqtt_client
            sent = False
            if client is not None and st.mqtt_connected:
                cmd = {"cmd": "grid", "rows": grid["rows"], "cols": grid["cols"]}
                info = client.publish("probe/%s/cmd" % dev, json.dumps(cmd), qos=0)
                sent = info.rc == 0
            return self._json({"ok": True, "grid_cmd_sent": sent, **grid})

        if path == "/api/reset":
            cleared = st.reset()
            points = st.points()
            st.broadcast({"type": "reset", "cleared": cleared})
            st.broadcast({"type": "points", "points": points})
            return self._json({"ok": True, "cleared": cleared,
                               "data": points})

        if path == "/api/reference":
            want = body.get("point")
            if want is None:
                return self._json({"ok": False,
                                   "error": 'body needs {"point": "P0"} or '
                                            '{"point": "auto"}'}, 400)
            if str(want).strip().lower() == "clear":
                st.clear_reference()
                points = st.points()
                st.broadcast({"type": "points", "points": points})
                return self._json({"ok": True, "reference": None,
                                   "data": points})
            try:
                ref = st.set_reference(want)
            except (TypeError, ValueError) as exc:
                return self._json({"ok": False, "error": str(exc)}, 400)
            points = st.points()
            st.broadcast({"type": "points", "points": points})
            return self._json({"ok": True, "reference": ref, "data": points})

        if path == "/api/cmd":
            dev = str(body.get("dev") or DEFAULT_DEVICE)
            payload = body.get("payload")
            if payload is None:
                cmd_field = body.get("cmd")
                # two accepted shapes: {"dev":...,"payload":{...}} /
                # {"dev":...,"cmd":"stream","on":true} /
                # {"dev":...,"cmd":{"cmd":"stream","on":true}}
                payload = (cmd_field if isinstance(cmd_field, dict)
                           else {k: v for k, v in body.items() if k != "dev"})
            if not isinstance(payload, dict) or "cmd" not in payload:
                return self._json({"ok": False,
                                   "error": "body needs a cmd object, e.g. "
                                            "{\"dev\":\"probe-01\","
                                            "\"cmd\":{\"cmd\":\"stream\",\"on\":true}}"},
                                  400)
            topic = "probe/%s/cmd" % dev
            published = False
            client = st.mqtt_client
            if client is not None and st.mqtt_connected:
                info = client.publish(topic, json.dumps(payload), qos=1)
                published = info.rc == 0
            return self._json({"ok": published, "topic": topic, "payload": payload,
                               "published": published,
                               "error": None if published
                               else "MQTT not connected to broker"})
        return self._json({"ok": False, "error": "unknown endpoint: " + path}, 404)

    # -- websocket ---------------------------------------------------------
    def _websocket(self):
        headers = {k.lower(): v for k, v in self.headers.items()}
        if headers.get("upgrade", "").lower() != "websocket":
            return self._json({"ok": False,
                               "error": "GET /api/stream requires a WebSocket "
                                        "upgrade"}, 426)
        sock = self.connection
        try:
            if not ws_handshake(sock, headers):
                return
        except OSError:
            return
        client = WsClient(sock, self.client_address)
        self.state.add_client(client)
        self.close_connection = True
        # this handler thread now blocks in the reader until the peer leaves
        try:
            client._rx.join()
        except Exception:
            pass
        finally:
            client.close()
            self.state.remove_client(client)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    _safe_console()
    ap = argparse.ArgumentParser(description="Tap-probe real-time analysis service")
    ap.add_argument("--broker", default=DEFAULT_BROKER, help="MQTT broker host")
    ap.add_argument("--broker-port", type=int, default=DEFAULT_BROKER_PORT)
    ap.add_argument("--http-port", type=int, default=DEFAULT_HTTP_PORT)
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--template", default=str(TEMPLATE_PATH),
                    help="path to 06_analyze_tap.py")
    ap.add_argument("--check-band", action="store_true",
                    help="verify the reparameterised band equals the template "
                         "at its defaults, print the result and exit")
    args = ap.parse_args(argv)

    template_path = Path(args.template).resolve()
    log("template: %s" % template_path)
    try:
        mod = load_template_module(template_path)
        feature_fn, meta = build_banded_feature_fn(mod, template_path)
    except Exception as exc:
        sys.stderr.write("FATAL: cannot prepare the analysis template\n")
        sys.stderr.write("  %s: %s\n" % (type(exc).__name__, exc))
        return 2
    log("template sha256: %s" % meta["template_sha256"])
    log("band parameterisation: %s" % meta["band_parameterisation"])

    check = check_banded_equivalence(mod.extract_features_from_waveform, feature_fn)
    log("template equivalence at default band: %s (max|diff|=%.3g over %d features)"
        % (check["identical"], check["max_abs_diff"], check["n_features_compared"]))
    if args.check_band:
        print(json.dumps({"equivalence": check, "meta": meta}, indent=2))
        return 0 if check["identical"] else 1

    state = ProbeState(feature_fn, mod, meta, args.broker, args.broker_port)
    state.http_port = args.http_port
    start_mqtt(state)

    ApiHandler.state = state
    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer((args.bind, args.http_port), ApiHandler)
    httpd.daemon_threads = True
    log("HTTP API on http://0.0.0.0:%d (ws://<host>:%d/api/stream)"
        % (args.http_port, args.http_port))
    log("subscribed: probe/+/waveform probe/+/measurement probe/+/status probe/+/event")
    log("analysis band: fixed [%.0f, %.0f] Hz, crossover %.0f Hz "
        "(Nyquist guard: band_hi <= %.2f*fs)"
        % (DEFAULT_BAND_LO_HZ, DEFAULT_BAND_HI_HZ, DEFAULT_CROSSOVER_HZ,
           NYQUIST_GUARD))
    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        log("stopping")
    finally:
        httpd.shutdown()
        with state.lock:
            clients = list(state.ws_clients)
            state.ws_clients.clear()
        for client in clients:
            client.close()
        if state.mqtt_client is not None:
            try:
                state.mqtt_client.loop_stop()
                state.mqtt_client.disconnect()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
