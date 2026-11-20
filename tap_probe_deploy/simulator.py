#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Synthetic probe for the tap-test demo (no hardware required).

Publishes PROTOCOL.md-shaped MQTT traffic to the local broker:

    probe/<dev>/status       "online" / "offline"   (retained, LWT)
    probe/<dev>/waveform     one synthetic tap per interval (QoS 0)
    probe/<dev>/measurement  2 s summary (QoS 1)
    probe/<dev>/event        {"ev":"tap"} / {"ev":"ack"} notices

The waveform generator models a gravity-preloaded accelerometer tap: a signed
damped oscillation on top of the 1 g rest vector, quantised to int16 at
``scale`` LSB/g exactly like the firmware does.  Two classes are produced:

    bonded   resonance in the low band  -> band_ratio_lh well above 0.45
    debond   resonance in the high band -> band_ratio_lh well below 0.45

so analyzer.py classifies them BONDED / DEBOND.  The mode can be switched while
running over MQTT (``{"cmd":"sim","mode":"debond"}``) or with --mode.

Usage
-----
    python simulator.py                          # 3 taps/s, bonded, forever
    python simulator.py --mode debond
    python simulator.py --mode alternate         # flips class every tap
    python simulator.py --mode auto --switch-every 6
    python simulator.py --count 30 --mode bonded # finite run, exits by itself
"""

from __future__ import annotations

import argparse
import base64
import json
import random
import sys
import time

import numpy as np

try:
    import paho.mqtt.client as mqtt
except ImportError:                                          # pragma: no cover
    sys.stderr.write("FATAL: paho-mqtt is required.\n  pip install paho-mqtt\n")
    raise SystemExit(2)


def log(msg: str) -> None:
    print("[simulator] " + msg, flush=True)


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


def _safe_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Synthetic waveform
# ---------------------------------------------------------------------------
# tuned against the reduced band [30, 0.45*fs] with crossover 0.45*fs/3 at
# Resonance frequencies are expressed as multiples of the reduced-band
# crossover (0.45*fs/3), so the same two clusters work at any fs the probe
# publishes.  At fs=500 Hz the crossover is 75 Hz, i.e. bonded ~75 Hz (just at
# the crossover, ratio ~1.0-1.5) and debond ~105 Hz (1.4x, ratio ~0.1-0.2).
CLASS_PARAMS = {
    "bonded": {"f0_x_crossover": 1.00, "f0_jitter": 0.006, "tau_ms": 17.0,
               "amp_g": 0.70, "amp_jitter": 0.25, "label": "BONDED"},
    "debond": {"f0_x_crossover": 1.40, "f0_jitter": 0.02, "tau_ms": 9.0,
               "amp_g": 0.48, "amp_jitter": 0.25, "label": "DEBOND"},
}
BAND_HI_FACTOR = 0.45          # PROTOCOL.md section 6
CROSSOVER_DIVISOR = 3.0        # PROTOCOL.md section 6


def resonance_multiplier(fs: float) -> float:
    """Where the synthetic bonded resonance sits relative to the crossover.

    The demo rate is 500 Hz (PROTOCOL.md section 1 example): at 1.00x the
    reduced-band crossover a bonded tap comes out at band_ratio_lh ~1.0-1.5,
    i.e. comfortably above the 0.45 threshold.  At the firmware's 1666 Hz the
    band is much wider and the same 1.00x resonance would straddle the
    crossover, so the multiplier is pulled to 0.90x; the synthetic class then
    stays far from the threshold instead of flickering.
    """
    t = min(1.0, max(0.0, (float(fs) - 500.0) / 1166.0))
    return 1.0 - 0.10 * t


def synth_tap(kind: str, fs: float, n: int, pre: int, scale: float,
              rng: np.random.Generator):
    """Return (int16 (n,3) array, dict of truth metadata)."""
    p = CLASS_PARAMS[kind]
    crossover_hz = BAND_HI_FACTOR * fs / CROSSOVER_DIVISOR
    mult = (resonance_multiplier(fs) if kind == "bonded"
            else p["f0_x_crossover"])
    f0 = mult * crossover_hz * (1.0 + rng.normal(0.0, p["f0_jitter"]))
    tau_ms = p["tau_ms"] * float(rng.uniform(0.88, 1.12))
    amp_g = p["amp_g"] * float(rng.uniform(1.0 - p["amp_jitter"],
                                           1.0 + p["amp_jitter"]))
    noise_g = float(rng.uniform(0.00025, 0.00055))

    # gravity rest vector: 1 g mostly on +z plus a small tilt
    gravity = np.array([rng.normal(0.02, 0.010),
                        rng.normal(-0.01, 0.010),
                        1.0 + rng.normal(0.0, 0.012)])
    acc = np.tile(gravity, (n, 1)) + rng.normal(0.0, noise_g, (n, 3))

    t = np.arange(n) / fs
    t_local = t - pre / fs
    on = t_local >= 0.0
    env = np.exp(-np.maximum(t_local, 0.0) / (tau_ms / 1000.0))
    # contact force builds up over a few ms; a C1-smooth onset keeps the
    # template's 1%-of-peak envelope gate on the ring-down instead of on the
    # Hilbert tail of a mathematical step (which at 500 Hz is above the gate
    # for most of the window and would bias decay_tau_ms upwards).
    rise_ms = 3.0 if kind == "bonded" else 2.5
    ramp = np.zeros(n)
    ramp[on] = 1.0 - np.exp(-t_local[on] / (rise_ms / 1000.0))
    osc = np.zeros(n)
    osc[on] = (amp_g * env[on] * ramp[on]
               * np.sin(2.0 * np.pi * f0 * np.maximum(t_local[on], 0.0)))
    # the tap excites z hardest, with a smaller in-plane component
    acc[:, 2] += osc
    acc[:, 0] += 0.35 * osc
    # broadband contact click, two samples
    click = float(rng.uniform(0.03, 0.07))
    acc[pre:pre + 2, 2] += click
    acc[pre:pre + 2, 0] += 0.5 * click
    # a little structural ring-down at the second mode
    if kind == "debond":
        ring_hz = 2.27 * crossover_hz
        ring = np.zeros(n)
        ring[on] = (0.15 * amp_g * env[on] * ramp[on]
                    * np.sin(2.0 * np.pi * ring_hz
                             * np.maximum(t_local[on], 0.0)))
        acc[:, 2] += ring

    q = np.clip(np.round(acc * scale), -32768, 32767).astype("<i2")
    truth = {"kind": kind, "label": p["label"], "f0_hz": f0,
             "tau_ms": tau_ms, "amp_g": amp_g, "noise_g": noise_g,
             "gravity_g": float(np.linalg.norm(gravity))}
    return q, truth


def encode_waveform(q: np.ndarray) -> str:
    return base64.b64encode(q.astype("<i2").tobytes()).decode("ascii")


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------
class Simulator:
    def __init__(self, args):
        self.args = args
        self.dev = args.dev
        self.fs = float(args.fs)
        self.n = int(args.n)
        self.pre = int(args.pre)
        self.scale = float(args.scale)
        self.mode = args.mode
        self.seq = 0
        self.tap = 0
        self.kind_index = 0
        self.stream_on = True
        self.publish_on = True
        self.connected = False
        self.started = time.time()
        self.published_waveforms = 0
        self.published_measurements = 0
        self.stop = False
        self.seed_base = args.seed
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id="tap-simulator-%d" % random.randrange(9999),
                                  clean_session=True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.will_set("probe/%s/status" % self.dev, "offline", qos=1,
                             retain=True)
        self.client.reconnect_delay_set(min_delay=1, max_delay=8)

    # -- mqtt --------------------------------------------------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        self.connected = _connect_ok(reason_code)
        if not self.connected:
            log("MQTT connect refused: %s" % (reason_code,))
            return
        log("connected to %s:%d as %s" % (self.args.broker,
                                          self.args.broker_port, self.dev))
        client.subscribe("probe/%s/cmd" % self.dev, qos=1)
        client.publish("probe/%s/status" % self.dev, "online", qos=1, retain=True)
        log("status online (retained); mode=%s rate=%.1f Hz fs=%.0f"
            % (self.mode, self.args.rate, self.fs))

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return
        if not isinstance(payload, dict):
            return
        cmd = payload.get("cmd")
        ok, note = True, cmd
        if cmd == "stream":
            self.stream_on = bool(payload.get("on", True))
            note = "stream %s" % ("on" if self.stream_on else "off")
        elif cmd == "publish":
            self.publish_on = bool(payload.get("on", True))
            note = "publish %s" % ("on" if self.publish_on else "off")
        elif cmd == "zero":
            note = "zero"
        elif cmd == "reboot":
            self.seq = 0
            self.tap = 0
            client.publish("probe/%s/status" % self.dev, "online", qos=1,
                           retain=True)
            note = "reboot"
        elif cmd == "sim":
            mode = str(payload.get("mode") or "").lower()
            if mode in ("bonded", "debond", "alternate", "auto"):
                self.mode = mode
                note = "sim mode=%s" % mode
            else:
                ok, note = False, "sim mode unknown: %s" % mode
        else:
            log("command ignored: %s" % (payload,))
            return
        log("command %s -> %s" % (cmd, note))
        self.client.publish("probe/%s/event" % self.dev,
                            json.dumps({"dev": self.dev, "ev": "ack",
                                        "cmd": cmd, "ok": ok,
                                        "note": note}), qos=1)

    # -- class selection ---------------------------------------------------
    def current_kind(self, now: float) -> str:
        if self.mode in ("bonded", "debond"):
            return self.mode
        if self.mode == "alternate":
            self.kind_index += 1
            return "bonded" if self.kind_index % 2 else "debond"
        # auto: cycle classes every --switch-every seconds
        phase = int((now - self.started) / max(1.0, self.args.switch_every))
        return "bonded" if phase % 2 == 0 else "debond"

    # -- publishing --------------------------------------------------------
    def publish_waveform(self):
        now = time.time()
        kind = self.current_kind(now)
        rng = np.random.default_rng(self.seed_base + self.seq)
        q, truth = synth_tap(kind, self.fs, self.n, self.pre, self.scale, rng)
        self.seq += 1
        self.tap += 1
        trig = int(np.max(np.abs(q.astype(int)[:max(self.pre + 8, 16)])))
        payload = {
            "dev": self.dev,
            "pt": self.args.point,
            "sp": True,
            "seq": self.seq,
            "tap": self.tap,
            "fs": int(round(self.fs)),
            "n": self.n,
            "scale": self.scale,
            "pre": self.pre,
            "trig": trig,
            "d": encode_waveform(q),
        }
        self.client.publish("probe/%s/waveform" % self.dev,
                            json.dumps(payload), qos=0)
        self.client.publish("probe/%s/event" % self.dev,
                            json.dumps({"dev": self.dev, "ev": "tap",
                                        "n": self.tap, "sp": True,
                                        "pt": self.args.point}), qos=1)
        self.published_waveforms += 1
        log("tap %d seq=%d %s f0=%.1f Hz tau=%.1f ms amp=%.2f g ratio_expect=%s"
            % (self.tap, self.seq, truth["label"], truth["f0_hz"],
               truth["tau_ms"], truth["amp_g"],
               "high" if kind == "bonded" else "low"))

    def publish_measurement(self):
        rng = np.random.default_rng(self.seed_base + 900000 + self.seq)
        t1 = [round(float(rng.normal(0.02, 0.001)), 5),
              round(float(rng.normal(-0.01, 0.001)), 5),
              round(float(1.0 + rng.normal(0, 0.001)), 5)]
        rms1 = round(float(rng.uniform(0.0012, 0.0022)), 5)
        pk1 = round(rms1 * float(rng.uniform(1.7, 2.4)), 5)
        payload = {"dev": self.dev, "pt": self.args.point, "sp": True,
                   "n": 230, "t1": t1, "rms1": rms1, "pk1": pk1,
                   "rssi": int(rng.integers(-38, -24))}
        self.client.publish("probe/%s/measurement" % self.dev,
                            json.dumps(payload), qos=1)
        self.published_measurements += 1

    def run(self):
        self.client.connect_async(self.args.broker, self.args.broker_port,
                                  keepalive=30)
        self.client.loop_start()
        deadline = time.time() + 15
        while not self.connected and time.time() < deadline:
            time.sleep(0.1)
        if not self.connected:
            log("FATAL: no broker at %s:%d" % (self.args.broker,
                                               self.args.broker_port))
            self.client.loop_stop()
            return 2

        interval = 1.0 / max(0.2, float(self.args.rate))
        next_tap = time.time()
        next_measure = time.time() + 0.5
        try:
            while not self.stop:
                now = time.time()
                if self.publish_on and now >= next_measure:
                    self.publish_measurement()
                    next_measure = now + 1.0 / max(0.1, float(self.args.measurement_rate))
                if self.stream_on and now >= next_tap:
                    self.publish_waveform()
                    next_tap = now + interval
                    if self.args.count and self.published_waveforms >= self.args.count:
                        break
                time.sleep(0.02)
        except KeyboardInterrupt:
            log("interrupted")
        finally:
            try:
                self.client.publish("probe/%s/status" % self.dev, "offline",
                                    qos=1, retain=True)
                self.client.publish("probe/%s/status" % self.dev, "", qos=1,
                                    retain=True)
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass
        log("published %d waveform(s) and %d measurement(s) in %.1f s"
            % (self.published_waveforms, self.published_measurements,
               time.time() - self.started))
        return 0


def main(argv=None) -> int:
    _safe_console()
    ap = argparse.ArgumentParser(
        description="Synthetic tap-probe publisher for the demo dashboard")
    ap.add_argument("--broker", default="127.0.0.1")
    ap.add_argument("--broker-port", type=int, default=1883)
    ap.add_argument("--dev", default="sim-01",
                    help="device id to publish as; the default is deliberately "
                         "NOT probe-01 so synthetic taps never land in a real "
                         "probe's point buckets")
    ap.add_argument("--point", default="P0",
                    help="measurement point label (PROTOCOL.md section 7.1)")
    ap.add_argument("--fs", type=float, default=500.0,
                    help="sample rate in Hz (PROTOCOL.md section 1 field fs)")
    ap.add_argument("--n", type=int, default=256)
    ap.add_argument("--pre", type=int, default=48)
    ap.add_argument("--scale", type=float, default=4096.0,
                    help="LSB per g (PROTOCOL.md section 1 field scale)")
    ap.add_argument("--rate", type=float, default=3.0,
                    help="taps per second (2-5 is the protocol demo range)")
    ap.add_argument("--measurement-rate", type=float, default=0.5)
    ap.add_argument("--mode", default="bonded",
                    choices=["bonded", "debond", "alternate", "auto"])
    ap.add_argument("--switch-every", type=float, default=6.0,
                    help="seconds per class in --mode auto")
    ap.add_argument("--count", type=int, default=0,
                    help="publish N taps then exit (0 = run forever)")
    ap.add_argument("--seed", type=int, default=20261120)
    ap.add_argument("--duration", type=float, default=0.0,
                    help="stop after N seconds (0 = run until Ctrl+C)")
    args = ap.parse_args(argv)
    log("#" * 66)
    log("#  SIMULATED DATA - this publisher is NOT a measurement")
    log("#  every payload carries \"sp\":true, dev=%s, point=%s"
        % (args.dev, args.point))
    log("#  never quote these numbers as bench or field results")
    log("#" * 66)
    sim = Simulator(args)
    if args.duration:
        import threading
        timer = threading.Timer(args.duration, lambda: setattr(sim, "stop", True))
        timer.daemon = True
        timer.start()
    return sim.run()


if __name__ == "__main__":
    raise SystemExit(main())
