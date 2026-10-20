# Appendix A — Embedded firmware: handheld tap-test probe

EEE4483 *Internet-of-Things Planning and Deployment* — end-of-module mini-project.
Higher Diploma in Computer and Electronic Engineering (EG114403 / EG314403 / EG524403).

Firmware revision **1.0.0**, hardware revision **rev-C**, ESP-IDF **v5.2 or later**, C99.

---

## A.1 Purpose

This appendix documents the embedded firmware of a handheld **tap-test probe** used
to look for *debonded* ("hollow") external wall finishes.

The instrument works the way a surveyor taps a wall with a hammer and listens to the
sound: a debonded patch of render or tiling responds with a **longer, lower-pitched
ring**, while a well-bonded area gives a **short, high-pitched click**. The probe
automates that judgement.

One press of the trigger is **one measurement**:

1. A **solenoid** delivers a single mechanical tap to the wall (a short, bounded
   current pulse).
2. An **I²S MEMS microphone** records the resulting tap tone into a fixed buffer.
3. The **ESP32 performs the signal processing on-device**: DC removal, Hann window,
   a 1024-point radix-2 FFT, and from that a small set of spectral and envelope
   features.
4. An **MPU6050 accelerometer** is read at the same instant as a *separate, auxiliary*
   channel that grades how well the probe was held against the wall.
5. The probe assigns a **grade G0 / G1 / G2** locally using a simple two-condition
   rule.
6. The measurement is published as **JSON over MQTT with TLS**, per device, using a
   per-device credential.

### What this instrument is not

State these limitations plainly in the report. They are deliberate design boundaries,
not oversights.

| Not claimed | Why |
|---|---|
| The **accelerometer does not detect debonding.** | An accelerometer at the probe tip measures the probe's own motion, not the wall's acoustic response. It is used **only** to check the *contact quality* of each measurement (was the probe pressed flat and firmly, or lifted/banged?). It is an operator-technique diagnostic. |
| The grade is **not a validated defect classification.** | The G0/G1/G2 rule is a two-threshold box test, fitted — if at all — on two small hand-made reference panels. It is a *screening indicator*. It is not calibrated to any standard, it is not a probability of defect, and it must not be presented as a percentage of defect area. |
| **Repeatability is limited.** | The probe grades *differences in ring-down*, not a physical quantity in SI units. Repeatability is limited by operator technique, strike energy, probe-to-wall angle, the substrate, ambient noise and temperature. Report it as "N measurements on panel P, of which M agreed with the reference" — never as an accuracy figure. |
| **Simulated data is not measured data.** | With the `SIMULATION` build flag set, features are *synthesised* to exercise the MQTT and dashboard path. Every payload then carries `"sp":true` and the boot log shouts about it. Any figure produced in that mode must be labelled as software-path testing. |
| The measured wall is **not characterised by frequency alone.** | `f_peak_hz` and `band_ratio_lh` change with wall thickness, finish material, void depth and probe geometry. Fine for *A/B comparison on the same wall*, weak for absolute statements across different walls. |

---

## A.2 Architecture

```
                    ┌─────────────────────────── HARDWARE ───────────────────────────┐
                    │                                                                │
   ┌─────────┐      │   ┌──────────────┐        ┌──────────────────────────────┐   │
   │ trigger ├──────┼──►│  GPIO 32     │        │ 12 V solenoid (23 W,         │   │
   │ button  │      │   │  (active low)│        │ intermittent duty)           │   │
   └─────────┘      │   └──────┬───────┘        │        ▲                     │   │
                    │          │                │        │ flyback diode       │   │
                    │   ┌──────▼────────────────▼────────┴────┐   ┌──────┐      │   │
                    │   │  ESP32-WROOM-32 (ESP-IDF v5.x)      │   │IRLZ44N│     │   │
                    │   │                                     ├──►│  N-MOS ├──┐  │   │
                    │   │  ┌─────────────────────────────┐    │ G │ gate  │  │  │   │
                    │   │  │ measurement task            │    │   │ R 220Ω│  │  │   │
                    │   │  │  strike → capture → DSP →   │    │   │ R 10kΩ│  │  │   │
                    │   │  │  classify → publish         │    │   └───────┘  │  │   │
                    │   │  └─────────────────────────────┘    │              │  │   │
                    │   │  ┌──────────────┐  ┌────────────┐   │              ▼  │   │
                    │   │  │ console task │  │ MQTT client│   │           GND   │   │
                    │   │  │ (UART cmds)  │  │ + LWT      │   │                 │   │
                    │   │  └──────────────┘  └─────┬──────┘   │                 │   │
                    │   └────┬──────────────┬──────┼──────────┘                 │   │
                    │        │ I²S          │ I²C  │ WiFi/TLS                     │   │
                    │   ┌────▼─────┐   ┌─────▼────┐  │                          │   │
                    │   │ ICS-43434│   │ MPU6050  │  │                          │   │
                    │   │ MEMS mic │   │  AUX     │  │                          │   │
                    │   │ PRIMARY  │   │  only    │  │                          │   │
                    │   └──────────┘   └──────────┘  │                          │   │
                    └────────────────────────────────┼──────────────────────────┘   │
                                                     │                              │
                                                     ▼                              │
                                        ┌────────────────────────┐                  │
                                        │  MQTT broker (TLS)     │◄─────────────────┘
                                        │  broker.example:8883   │
                                        └───────────┬────────────┘
                                                    │
                          probe/<dev>/measurement ──┤
                          probe/<dev>/status    ────┤
                          probe/<dev>/event     ────┘
                                                    │
                                                    ▼
                                        ┌────────────────────────┐
                                        │  Dashboard / logger    │
                                        │  (Node-RED, Grafana,   │
                                        │   Mosquitto subscriber)│
                                        └────────────────────────┘
```

### Firmware structure

```
app_main()
 ├─ nvs_flash_init / nvs_load           per-device credentials, thresholds, strike count
 ├─ sol_gpio_init                        gate pin + independent failsafe timer
 ├─ dsp_make_hann / dsp_make_bitrev      precomputed tables (allocation-free after init)
 ├─ mic_init        (I2S, PRIMARY)       non-fatal on failure → event topic
 ├─ accel_init      (I²C, AUXILIARY)     non-fatal on failure → event topic
 ├─ wifi_start → time_sync (SNTP) → mqtt_start   (all failures non-fatal)
 └─ tasks:
      measurement_task  (prio 6)   consumes the measure queue: strike → capture → DSP → publish
      capture_helper    (prio 5)   short-lived: the single bounded I2S read, started before the strike
      console_task      (prio 3)   UART commands
      app_main loop     (prio 1)   trigger-button poll, LED heartbeat, strike-counter persistence
```

The pipeline per strike:

```
admit?  drain DMA  spawn reader ──► STRIKE (2 ms lead) ──► accel window (60 ms)
                                        │                        │
                                        └─── I2S capture 4096 samples @ 48 kHz (85.3 ms)
                                                                 │
                                     DC removal → Hann window → 512-pt FFT (window at 4.0 ms)
                                                                 │
                          f_peak, f_centroid, band_ratio_lh, decay_tau, peak, rms, crest, kurtosis
                                                                 │
                                            classify G0/G1/G2 → JSON → MQTT publish
```

---

## A.3 Pinout

All of these are defined in **one** place, `main/probe_config.h` section 3. The table
and that file must be kept in step.

| Signal | ESP32 GPIO | Direction | Notes |
|---|---|---|---|
| I2S `BCLK` (mic SCK) | GPIO 26 | out | Bit clock, 48 kHz × 64 = 3.072 MHz |
| I2S `WS` (mic LRCLK) | GPIO 25 | out | Left channel selected; tie the mic's L/R pin as its datasheet requires |
| I2S `DIN` (mic SD) | GPIO 33 | in | 24-bit data left-justified in a 32-bit slot |
| I²C `SDA` (MPU6050) | GPIO 21 | bidir | 400 kHz; 4.7 kΩ pull-ups to 3.3 V (module usually has them) |
| I²C `SCL` (MPU6050) | GPIO 22 | bidir | 400 kHz |
| `MPU_INT` | GPIO 35 | in | **Reserved, currently unused** (input-only pin; polled design) |
| Solenoid gate drive | GPIO 27 | out | → 220 Ω → IRLZ44N gate. 10 kΩ gate pulldown to GND |
| Trigger button | GPIO 32 | in | Active low; internal pull-up enabled; other side to GND |
| Status LED | GPIO 2 | out | On-board LED. Slow blink = idle; fast blink = minimum interval running |
| UART0 TX / RX | GPIO 1 / 3 | — | Console + `idf.py monitor` |

Power rails: **3.3 V** — ESP32, microphone, MPU6050. **12 V** — solenoid only.
Common ground between the 3.3 V and 12 V domains, star-pointed at the MOSFET source.
If the microphone module has a `VDD` of 3.3 V and a separate `GND`, keep its ground
return on the analogue side, away from the solenoid's switching return.

> **Porting note.** This map assumes ESP32-WROOM-32 / ESP32-DevKitC. On ESP32-S3 or
> ESP32-C3 several of these pins are not valid (GPIO 35/36/37/38 do not exist on C3;
> GPIO 33 on S3 is often used by octal PSRAM). Change the `PROBE_PIN_*` macros and
> nothing else — the firmware does not hard-code pin numbers anywhere else.

---

## A.4 Bill of materials (key parts)

| # | Item | Suggested part / spec | Qty | Approx. cost | Notes |
|---|---|---|---|---|---|
| 1 | MCU module | ESP32-WROOM-32 dev board (or ESP32-DevKitC) | 1 | HK$40–70 | Any ESP32 with WiFi; 4 MB flash is plenty |
| 2 | Microphone | **ICS-43434** or **INMP441** I²S MEMS breakout | 1 | HK$25–45 | **Primary sensor.** Both are 24-bit I²S; ICS-43434 has the better SNR |
| 3 | Accelerometer | **MPU6050** breakout (GY-521) | 1 | HK$12–20 | **Auxiliary only** — contact-quality diagnostic |
| 4 | Solenoid | 12 V, **23 W** push-pull solenoid (intermittent duty) | 1 | HK$40–80 | **Intermittent-duty part.** ~1.92 A at 12 V |
| 5 | MOSFET | **IRLZ44N** logic-level N-channel MOSFET (TO-220) | 1 | HK$8 | Logic-level gate is essential; a plain IRF540 will not turn on fully from 3.3 V |
| 6 | Flyback diode | 1N5819 (Schottky, 1 A) or 1N4007 | 1 | HK$2 | **Across the coil, cathode to +12 V.** Non-negotiable |
| 7 | Gate resistor | 220 Ω, ¼ W | 1 | <HK$1 | Limits gate inrush / slows dV/dt |
| 8 | Gate pulldown | 10 kΩ, ¼ W | 1 | <HK$1 | Holds the gate low while the ESP32 is booting/resetting |
| 9 | Bulk capacitor | 1000 µF, 25 V electrolytic | 1 | HK$5 | Across the 12 V rail near the solenoid; absorbs the strike current step |
| 10 | Decoupling | 100 nF ceramic | 2 | <HK$1 | At the MOSFET drain-source rail and the mic supply |
| 11 | Trigger button | Tactile switch, 6 mm | 1 | HK$2 | NO, to GND |
| 12 | 12 V supply | 12 V 2 A mains adaptor **or** 3S Li-ion pack | 1 | HK$80–150 | See safety section |
| 13 | Probe body | 3D-printed or aluminium handheld body | 1 | — | The mic must be rigidly coupled to the tip; a loose mic ruins the measurement |
| 14 | Reference panels | 2 × same finish, one good, one deliberately debonded | 2 | — | **Needed for calibration.** Build a panel with a known void behind the render |
| 15 | Misc | Hookup wire, headers, perfboard | — | HK$20 | Keep the mic wiring short and screened |

Total approximate cost: **HK$250–450**, excluding the reference panels and the supply.

### Wiring diagram (ASCII)

```
   +3V3 ──┬───────────────┬──────────────────┬──────────────
          │               │                  │
        [mic VDD]     [MPU VCC]          [ESP32 3V3]
          │               │                  │
     ┌────┴─────┐    ┌────┴─────┐      ┌─────┴──────┐
     │ICS-43434 │    │ MPU6050  │      │ ESP32      │
     │   or     │    │ (GY-521) │      │            │
     │ INMP441  │    │          │      │            │
     │ SCK ─────┼────┼──────────┼──────┤ GPIO26     │
     │ WS  ─────┼────┼──────────┼──────┤ GPIO25     │
     │ SD  ─────┼────┼──────────┼──────┤ GPIO33     │
     │         ─┼──┐ │ SDA ─────┼───┬──┤ GPIO21     │
     │         ─┼──┤ │ SCL ─────┼─┐ │  │ GPIO22     │
     │ L/R ─────┘  │ │          │ │ │  │            │
     │             │ │          │ │ └──┘            │
     └─────────────┘ └──────────┘ │                 │
          │              │       │                 │
         GND            GND      └─ 4k7 ─ +3V3 (if the module has no pull-ups)
          │              │
   ───────┴──────────────┴─────────── common ground ─────────────  ESP32 GND
                                                                       │
                                                                       │
  +12V ──┬─────────────────────────────────────────────┬───────────────┘
         │                                             │
      [1000µF]                                    ┌────┴─────┐
         │          ┌───►|────┐                   │ solenoid │
        GND         │  1N5819 │                  │  coil    │
                    │  cathode│                  │  12V/22W │
                    └────┬────┘                  └───┬──────┘
                         │  (flyback, across coil)   │
   ESP32 GPIO27 ──[220Ω]─┤                           │
                         │                      ┌────┴─────┐
                      ┌──┴──┐                   │  DRAIN   │
                      │  G  │  IRLZ44N          │          │
                      │     ├───────────────────┤ (tab)    │
                      │  S  │                   └──────────┘
                      └──┬──┘
                         │
                        [10kΩ]        ← gate pulldown to GND
                         │
                        GND

   GND ───┬──────────────────┬───────────────────┬────── GND rail
          │                  │                   │
   ESP32 GND           mosfet source        12 V supply GND
```

> **Important:** the flyback diode goes **across the coil** (cathode to +12 V, anode to
> the drain). Without it, the collapsing field of a 1.92 A inductive load produces a
> voltage spike that will destroy the MOSFET on the first strike, and will also
> couple a large transient straight into the microphone wiring.

---

## A.5 Building and flashing (assumes no prior ESP-IDF experience)

### A.5.1 Install the toolchain (once)

**Windows**

1. Download the *ESP-IDF Windows Installer* (`esp-idf-tools-setup-online-*.exe`) from
   Espressif and run it. Let it install **ESP-IDF v5.2 or later** (the accelerometer
   uses the `driver/i2c_master.h` API, which is not present in v5.0/v5.1) and the Python
   environment in the default locations.
2. At the last step, keep *"Run ESP-IDF PowerShell / Command Prompt"* checked.

**Linux / macOS** — see the official "Standard Toolchain Setup" guide; the short version is:

```bash
mkdir -p ~/esp && cd ~/esp
git clone -b v5.2 --recursive https://github.com/espressif/esp-idf.git
cd esp-idf && ./install.sh esp32
. ./export.sh              # must be run in EVERY new terminal
```

Verify:

```bash
idf.py --version           # must print "ESP-IDF v5.2" or later
```

> If you are stuck on v5.1, the only incompatible part is the MPU6050 driver: replace
> `driver/i2c_master.h` with the legacy `driver/i2c.h` API in `accel_init()`,
> `mpu_write_reg()` and `mpu_read_regs()`, and **change nothing else** — the rest of the
> firmware is v5.1-compatible.

### A.5.2 Get the sources and configure

The firmware lives in this appendix's own folder:

```
report/05_firmware/
├── CMakeLists.txt          project root
├── main/
│   ├── CMakeLists.txt      component registration
│   ├── Kconfig.projbuild   menuconfig tunables
│   ├── probe_config.h      *** all pins, timings and thresholds ***
│   └── app_main.c          the application
└── README.md               this file
```

`probe_config.h` deliberately holds **every** pin number, timing constant and feature
threshold. Start every tuning session there, not in `app_main.c`.

```bash
cd report/05_firmware        # run from inside an ESP-IDF terminal
idf.py set-target esp32
idf.py menuconfig
```

In `menuconfig`, the probe's own options are under
**Tap-test probe configuration**:

* `Strike / thermal limits` — minimum interval, pulse width, duty budget.
* `Sensing and DSP` — enable/disable the accelerometer; a reminder about the DSP band.
* `Connectivity` — MQTT QoS, SNTP server, UART console on/off.
* `Demonstration mode` — `SIMULATION MODE` (see A.5.7 and A.9).

Also confirm, under `Component config → mbedTLS`:
`CONFIG_MBEDTLS_CERTIFICATE_BUNDLE` is **enabled** (it is by default in v5.x). The
firmware uses `esp_crt_bundle_attach()` as the TLS trust anchor, so without the bundle
the handshake has no roots to verify against.

### A.5.3 Build

```bash
idf.py build
```

A clean first build takes 2–5 minutes. If it finishes with
`Project build complete. To flash, run: idf.py flash`, you are good.

### A.5.4 Flash and monitor

```bash
idf.py -p COM5 flash monitor        # Windows, replace COM5 with your port
idf.py -p /dev/ttyUSB0 flash monitor   # Linux (often /dev/ttyACM0 on some boards)
```

To find the port: Windows → Device Manager → *Ports (COM & LPT)*; Linux → `ls /dev/ttyUSB*`.
On Linux you may need to be in the `dialout` group. Exit the monitor with **Ctrl+]**.

### A.5.5 Provision the device

Provisioning stores the WiFi credentials, the MQTT URI and the per-device MQTT
credential in NVS (flash). Do it once per board.

1. Reset the board while holding nothing, and wait for the monitor to show

   ```
   I (1234) PROBE: ready. Type 'help' on the console...
   ```

2. **First, give the device a unique id.** The device id is compiled/flashed, not
   provisioned, so set it in `probe_config.h`:

   ```c
   #define PROBE_DEFAULT_DEV_ID   "probe-01"
   ```

   and rebuild+reflash. (Each probe needs a *unique* id and a *unique* MQTT client id,
   otherwise the broker will kick one device off every time the other connects.)

3. Preset the WiFi/MQTT settings over the console. Network settings are **not** sent
   through the monitor as JSON — just type into the monitor window:

   ```
   provision MyWiFiSSID mywifipassword mqtts://broker.example.com:8883 probe-01 ProbeMqttPass probe-01
   ```

   Fields, in order: `<ssid> <wifi-password> <mqtt-uri> <mqtt-user> <mqtt-password> <client-id>`.
   Note the MQTT URI uses `mqtts://` for TLS on port 8883.

4. Restart so the settings take effect:

   ```
   reboot
   ```

5. If provisioning fails, the console says so:
   `provisioning FAILED: ESP_ERR_NVS_...`. Check that NVS is not full and reflash.

> **Security note.** Provisioning stores the WiFi and MQTT credentials in NVS in
> **plain text**. NVS is not encrypted unless you enable ESP-IDF flash encryption.
> That is acceptable for a lab demo; for a real deployment enable flash encryption and
> secure boot, and consider per-device client certificates instead of a shared
> username/password. Say this explicitly in the report's security discussion.

### A.5.6 Observe the MQTT traffic

The firmware publishes to three topics:

| Topic | Retained? | QoS | When |
|---|---|---|---|
| `probe/<device_id>/measurement` | no | 1 | once per completed measurement |
| `probe/<device_id>/status` | **yes** | 1 | on connect (`online`), every 60 s, and as the LWT (`offline`) |
| `probe/<device_id>/event` | no | 1 | sensor init failure, capture failure, thermal trip, threshold change |

Subscribe with `mosquitto_sub` (install `mosquitto-clients`):

```bash
mosquitto_sub -h broker.example.com -p 8883 \
  --cafile /etc/ssl/certs/ca-certificates.crt \
  -u probe-sub -P 'subscriber-password' \
  -t 'probe/+/measurement' -t 'probe/+/status' -t 'probe/+/event' -v
```

`-v` prints the topic before the payload. A healthy measurement looks like:

```json
probe/probe-01/measurement {"ts":1699999999,"dev":"probe-01","seq":42,"grade":"G1",
"confidence":0.71,"f_peak_hz":912.0,"f_centroid_hz":1180.0,"band_ratio_lh":0.63,
"decay_tau_ms":31.4,"peak_au":0.82,"rms_au":0.11,"crest_factor":3.4,"kurtosis":5.2,
"impact_peak_g":2.1,"impulse_norm":0.34,"sp":false,"fw":"1.0.0","rssi":-61,
"strikes_total":128,"contact_ok":true,"event_flag":""}
```

(The line above is wrapped for readability; the device publishes it on one line.)

Without a TLS broker to hand, use a public test broker such as
`mqtts://test.mosquitto.org:8883` for the first end-to-end check, and **never publish
anything sensitive** to it.

### A.5.7 JSON payload schema

| Field | Type | Units | Meaning |
|---|---|---|---|
| `ts` | int | s | Unix UTC time from SNTP. **`0` means the clock was never set** — do not plot it as 1970 |
| `dev` | str | — | Device id |
| `seq` | int | — | Measurement counter since boot |
| `grade` | str | — | `"G0"` no indication · `"G1"` uncertain, re-test · `"G2"` debonding indicated |
| `confidence` | float | 0–1 | Heuristic margin of the winning grade. **Not a probability** |
| `f_peak_hz` | float | Hz | Largest FFT bin magnitude in 300–15000 Hz, parabolic-interpolated |
| `f_centroid_hz` | float | Hz | Magnitude-weighted mean frequency over the same band |
| `band_ratio_lh` | float | — | energy(< 1000 Hz) ⁄ energy(≥ 1000 Hz) |
| `decay_tau_ms` | float | ms | Log-linear fit to the RMS envelope of the last 60 % of the capture. **`-1.0` means the fit was not usable** (see A.6.4) |
| `peak_au` | float | full-scale | Peak \|sample\| in the analysis window; 1.0 = ADC full scale |
| `rms_au` | float | full-scale | RMS of the same window |
| `crest_factor` | float | — | `peak_au / rms_au` |
| `kurtosis` | float | — | Fourth standardised moment of the window (3.0 = Gaussian) |
| `impact_peak_g` | float | g | **Auxiliary.** Max per-axis \|a\| during the strike window |
| `impulse_norm` | float | g | **Auxiliary.** RMS acceleration over the same window |
| `sp` | bool | — | **`true` = synthesised in SIMULATION mode, not measured** |
| `fw` | str | — | Firmware version |
| `rssi` | int | dBm | WiFi RSSI at publish time |
| `strikes_total` | int | — | Lifetime strike count (NVS-backed) |
| `contact_ok` | bool | — | Auxiliary contact-quality verdict (see A.6.5) |
| `event_flag` | str | — | `""` when clean, else `weak_contact`, `hard_contact`, `capture_timeout`, `accel_unavailable`, `thermal_trip`, … |

`decay_tau_ms` and the `sp` flag are the two fields most likely to be misused in a
report. Read A.6.4 and A.9 before writing either of them up.

---

## A.6 Measurement procedure (SOP)

### A.6.1 Before a session

1. Charge or connect the 12 V supply. Verify it reads 12.0–12.6 V under no load.
2. Power the probe. Watch the boot log for:
   * `mic ready: 48000 Hz, mono, 24-bit data in 32-bit slots` — **required**
   * `MPU6050 ready at 0x68, +/-4 g` — nice to have; the probe still works without it
   * `SNTP synced: ... UTC` — required for meaningful timestamps
   * `connected to broker` — required for publishing
   * If SIMULATION MODE is on, you will see the large warning banner. **Stop and
     disable it before collecting any data you intend to report.**
3. Zero the reference: press the probe tip against the *good* reference panel and take
   one measurement. `f_peak_hz` should be in the high hundreds to low kilohertz with
   `band_ratio_lh` below about 0.5. If it is not, suspect the contact quality first
   (next section), the contact geometry second, and the thresholds last.
4. Check the strike counter with `status`. Record it at the start of the session —
   `strikes_total` is the honest record of how many strikes the solenoid has taken.

### A.6.2 The measurement itself

1. **Press firmly.** Put the probe tip flat against the surface and press until the
   tip's shoulder is seated. Do not press so hard that you deflect the finish. The
   probe is light — a firm, steady press, not a shove.
2. **Hold steady for the whole strike.** The strike plus capture takes well under a
   second. Any sliding or rocking during the window shows up as a `weak_contact` or
   `hard_contact` event flag.
3. **A single tap.** Press the trigger once, then wait. The status LED blinks fast
   while the minimum inter-strike interval is running; wait for the slow blink before
   the next measurement.
4. **Respect the minimum interval — 2000 ms by default.** This is not a suggestion. It
   is enforced in software and it protects an intermittent-duty solenoid. Repeated
   strikes closer than this are refused, the refusal is logged with `ESP_LOGE`, and no
   measurement is produced.
5. **Watch the thermal budget.** The firmware allows at most **15 strikes per 30 s**
   (one per two seconds, sustained). Exceed it and the probe enters a **60 s cooldown**,
   publishes a `thermal_trip` event, and refuses further strikes. On a long wall, work
   in bursts and let the probe rest.
6. **Use a grid.** Mark the wall into a grid (e.g. 300 mm squares). One measurement per
   cell, so that the survey is repeatable and the coverage is defensible in the report.
7. **Repeat at least 3 times per cell** if you intend to quote variation. Report the
   spread; do not quote a single reading as if it were exact.

### A.6.3 Understanding the grade

```
                    band_ratio_lh  (energy <1 kHz / energy >1 kHz)
                              low ◄──────────────────────► high
                  f_peak high  ┌───────────────┬───────────────┐
                               │      G0       │               │
                               │ no indication │      G1       │
                               ├───────────────┤   uncertain   │
                  f_peak low   │               │               │
                               │               ├───────────────┤
                               │               │      G2       │
                               │               │   debonding   │
                               └───────────────┴───────────────┘
             Default boundaries:  G2  if band_ratio_lh ≥ 0.70 AND f_peak_hz ≤ 700
                                  G0  if band_ratio_lh ≤ 0.45 AND f_peak_hz ≥ 1400
                                  G1  otherwise
```

The physical story: a debonded patch is a *plate with a free edge*, so it rings longer
and its energy sits lower in the spectrum. A bonded area is heavily damped, so it clicks
short and bright. That is the whole basis of the rule — and it is why `decay_tau_ms`,
which measures exactly that damping, is worth collecting even though the default rule
does not use it.

`confidence` is the normalised distance from the decision boundary. A reading with
`confidence = 0.95` is comfortably inside a box; `confidence = 0.5` is exactly on the
line and `G1` is the honest answer. It is **not** the probability that the wall is
defective.

### A.6.4 A warning about `decay_tau_ms`

The capture is 4096 samples = **85.3 ms**, and the decay fit uses only the last 60 % of
it — a **34.1 ms → 85.3 ms** window split into 32-sample (0.67 ms) RMS blocks. This
means:

* a ring-down much **faster than ~7 ms** has already hit the noise floor by 34 ms, so
  there is no decay left to fit;
* a ring-down much **slower than ~50 ms** has not decayed appreciably inside the window,
  so the fit is dominated by noise.

The window is bounded by `PROBE_TAU_MIN_MS` and `PROBE_TAU_MAX_MS`, not by these two
illustrative figures: a fitted time constant outside that configured range is reported as
the `-1.0` sentinel.

In either case the firmware **refuses to report a number** and publishes `-1.0`. Do not
plot `-1` as if it were a short decay — it means "not resolvable with this capture
length". If your reference panels fall outside the resolvable window, lengthen the
capture in `probe_config.h` (`PROBE_CAPTURE_SAMPLES`) or move `PROBE_ENV_TAIL_FRACTION`
earlier, and re-validate. Even when valid, `decay_tau_ms` is a **relative** indicator
for comparing measurements made the same way, not an absolute material property.

### A.6.5 Contact-quality check (using the auxiliary channel)

`impact_peak_g` and `impulse_norm` describe how the *probe* moved, which is a statement
about the operator, not the wall. Accept the defaults:

| `impact_peak_g` | Verdict | What happened |
|---|---|---|
| < 0.35 | `weak_contact` | Probe was barely touching or lifted off. **Discard and repeat.** |
| 0.35 – 8.0 | `contact_ok: true` | Good, repeatable contact |
| > 8.0 | `hard_contact` | Probe was banged. **Discard and repeat.** |

A short CSV of `impact_peak_g` per measurement across a session is an excellent figure
for the report: it *quantifies the operator's consistency*, which is exactly what the
accelerometer is there for. It says nothing about debonding, and it must not be
presented as if it did.

---

## A.7 Calibration

The defaults in `probe_config.h` are placeholders that make the probe behave sensibly
out of the box. **They are not a fitted model.** Before quoting any classification
result, calibrate.

### A.7.1 You need

* A **known-good reference panel**: the target finish, fully bonded to the substrate,
  no voids. Ideally a spare piece of the actual wall.
* A **known-debonded reference panel**: the **same** finish and **same** substrate, built
  deliberately with a void behind the render (e.g. a piece of foam or a shallow air gap
  left during setting). Same thickness and same material — otherwise you are measuring
  the panel, not the bond.
* Ideally, both panels instrumented or checked by another method so "known" is honest.

### A.7.2 Procedure

1. **Disable SIMULATION mode** and reflash. Calibration on synthesised data is
   meaningless.
2. Take **at least 10 measurements on each panel**, spread across the surface in a grid,
   respecting the minimum interval. Do not take all ten at one spot.
3. For each, type `dump` on the console. It prints the last result as JSON. Record
   `band_ratio_lh` and `f_peak_hz`, and check `contact_ok` is true.
4. Compute, for each panel, the range of `band_ratio_lh` and of `f_peak_hz`.
5. Look for a **separation**:

   ```
   band_ratio_lh        good panel:  0.21 .. 0.44
                        debonded  :  0.55 .. 0.83
                                     ▲ separation
   ```

   If the two ranges **overlap**, stop. A two-threshold rule cannot separate these
   populations. Say so in the report, with the numbers, and either improve the
   measurement (better coupling, more repeats, a different feature) or narrow the claim.

6. Set the threshold just inside the gap — here, `band_ratio_lh = 0.50`, below the
   debonded floor of 0.55. The device refuses ratios outside 0..20 and peaks outside
   100..20000 Hz:

   ```
   set th 0.50 900
   ```

   This sets the **G2** boundary to `band_ratio_lh ≥ 0.50 AND f_peak_hz ≤ 900 Hz`
   and stores it in NVS, so it survives a reboot. The G0 boundary in the header is left
   alone; if your good panel needs it moved, edit
   `PROBE_TH_RATIO_G0_DEFAULT` / `PROBE_TH_FPEAK_G0_DEFAULT` and reflash.

7. **Re-run both panels** through the classifier. Count:

   * true positives (debonded panel graded G2 / G1)
   * false negatives (debonded panel graded G0) — the dangerous error
   * false positives (good panel graded G2) — the annoying error

   Quote these counts **and the panel sizes** in the report. "8 of 10 struck measurements
   on the debonded panel graded G2 or G1; 1 of 10 on the good panel did" is a defensible
   result. "91 % accuracy" from one panel is not.

8. Record what the calibration does **not** cover: other finishes, other substrates,
   other thicknesses, temperature, moisture, operator. State this as the main limitation.

### A.7.3 If the probe must be used on an uncalibrated wall

Use it **relatively**: the same probe, the same operator, the same session, comparing
one spot against another spot on the same wall. Report the absolute threshold as
unvalidated. Never mix a measurement from one wall with a threshold fitted on another.

---

## A.8 Troubleshooting

| Symptom | Likely cause | Check | Fix |
|---|---|---|---|
| **No microphone data.** Log shows `i2s read failed` or `i2s short read`, or the payload shows `capture_fail` | Mic not wired / not powered; wrong `DIN` pin; WS and SCK swapped | `status` → `mic : FAILED`; scope BCLK and WS at the mic: 3.072 MHz and 48 kHz | Resolder; check the mic's L/R pin selects the channel the firmware reads (`I2S_STD_SLOT_LEFT` in the I2S configuration); confirm 3.3 V at the mic VDD |
| Same, but the mic initialises and the audio is all zeros | Mic module is **not** in 24-bit I²S mode (some INMP441 boards are set to 16-bit), or the channel mask does not match the L/R strap | `dump` and look at `peak_au` — exactly 0.000 means digital silence | Change the mic's L/R strap, or set `PROBE_MIC_DATA_BITS` and the I²S slot width to match the module and adjust `PROBE_MIC_FULL_SCALE` accordingly |
| **WiFi fails.** `connecting to '...'` then `giving up after 8 retries` | Wrong SSID/password; AP is 5 GHz only; the AP requires a captive portal | `status` → `ssid` field; serial monitor for `retry n/8` | Reprint the SSID exactly (it is case sensitive); connect to a 2.4 GHz SSID — the ESP32 has no 5 GHz radio; re-run `provision` |
| WiFi associates but no IP | DHCP pool exhausted or MAC filtering | Monitor shows no `got IP` line | Clear the DHCP lease table; check MAC filtering |
| **MQTT TLS handshake fails.** Log: `error type ... tls stack err ... cert flags 0x...` | Wrong port (using 1883 for TLS, or 8883 without TLS); a self-signed broker certificate; clock not set, so certificate dates do not validate; certificate bundle disabled | `status` → `time synced`; the URI must start `mqtts://` for TLS; in `menuconfig`, `MBEDTLS_CERTIFICATE_BUNDLE` must be on | Use the correct port in the URI; set the SNTP server first so the clock is valid before the handshake; for a lab broker with a private CA, either add that CA to the bundle or use `mqtt://` **inside the lab network only** and say so in the report |
| `measurement ... not published: MQTT down` but measurements are logged locally | Broker unreachable or the client was kicked (duplicate client id) | Another device using the same `client_id`? | Give every probe a unique `dev_id` **and** a unique MQTT client id in `provision` |
| **Solenoid double-fires** (two taps per press) | Trigger switch bounce; or the button is polled faster than the debounce filter; or a second measurement was queued | Count `strikes_total` before and after one press | The firmware debounces the button (200 ms) and refuses strikes inside the minimum interval; if it still double-fires, add a hardware RC debounce (10 kΩ + 100 nF) across the switch. **Never** "fix" this by shortening the minimum interval |
| Solenoid weak / no tap | 12 V supply sagging under the 1.92 A pulse; MOSFET not fully enhanced | Measure the 12 V rail **during** a strike | Fit the 1000 µF bulk capacitor at the solenoid; use a logic-level FET (IRLZ44N, not IRF540); check the gate resistor is 220 Ω and not much larger |
| **Watchdog resets.** `task_wdt: Task ... did not reset the watchdog` | A blocking wait without a timeout, or a task sat in a tight loop | Note which task is named in the log | The shipped code has no unbounded loops and every wait has a timeout. If you add code, keep that discipline — and prefer `vTaskDelay` over busy-waiting. Raise `CONFIG_ESP_TASK_WDT_TIMEOUT_S` only as a last resort |
| Random resets with no WDT message | Brown-out during the strike (12 V rail and 3.3 V rail sharing a weak supply) | `Brownout detector was triggered` in the log | Separate the supplies, or add bulk capacitance. **Never** power a 23 W solenoid from the same USB port as the ESP32 |
| **Overheating** — solenoid coil hot to the touch after a few strikes | Duty budget bypassed, or the pulse is stuck on | Console `status` shows refusals; check the slave log for `THERMAL BUDGET EXCEEDED` | The firmware refuses strikes and forces a cooldown. If the coil is still hot, the MOSFET may be stuck on — power down immediately and check the gate pulldown and the flyback diode |
| `decay_tau_ms` is always `-1.0` | The ring-down is outside the resolvable 4–25 ms window for this capture length | Compare `f_peak_hz` across the panels — is the acoustic difference there at all? | Lengthen `PROBE_CAPTURE_SAMPLES`, or move the envelope window earlier, and re-validate. Do not simply widen the accept range: that hides the problem |
| `contact_ok: false` on almost every measurement | Genuinely poor technique, or the accelerometer is clamped/loose in the body | `impact_peak_g` value in the payload | Re-seat the accelerometer rigidly; then re-train the technique. If the values are absurd (hundreds of g), the sensor is saturating — raise `PROBE_ACCEL_RANGE_G` |
| Grades look random, `confidence` always near 0.5 | Thresholds still at their placeholder defaults, or the two panels overlap | Run the A.7 calibration | Fit the thresholds; if the panels overlap, say so honestly rather than tuning until the numbers look good |
| Every payload carries `"sp":true` and the dashboard greys the rows out | SIMULATION mode is enabled | The boot log banner; `status` → `simulation : ON` | That is the intended behaviour, and it is there so simulated rows *cannot* be mistaken for measurements. Disable the flag in `menuconfig` and reflash before collecting data |

---

## A.9 SIMULATION mode

Sometimes the transducer chain is not finished but the demo, the dashboard and the MQTT
path are. `SIMULATION` mode exists for exactly that.

Enable it in `menuconfig → Tap-test probe configuration → Demonstration mode →
SIMULATION MODE`, or by setting `PROBE_CFG_SIMULATION_DEFAULT 1` in `probe_config.h`.
At boot the log prints:

```
W (812) PROBE: ##############################################################
W (812) PROBE: #  SIMULATION MODE IS ACTIVE                                 #
W (812) PROBE: #  The feature numbers this device publishes are SYNTHESISED #
W (812) PROBE: #  and are NOT measurements. Every payload carries "sp":true #
W (812) PROBE: ##############################################################
```

What simulation does:

* **Synthesises** a plausible feature set (a mixture of "hollow-like" and "good-like"
  draws, so the classifier boundary is exercised on both sides) and fills the auxiliary
  accelerometer fields with plausible numbers.
* **Sets `"sp":true`** in every measurement payload, so the dashboard can grey out or
  filter simulated rows.
* **Still enforces** the strike interlock, the thermal budget and the real timing, so
  the demo exercises the real state machine.

What simulation does **not** do: it does not read the microphone, and the numbers have
no physical meaning. **Data from this mode must never appear in the report as a
measurement.** If a simulated run is shown at all, it must be captioned "software path
test, synthesised data, `sp:true`".

---

## A.10 Safety

This section is part of the deliverable. Read it before powering anything.

**12 V supply.** The solenoid draws roughly 1.92 A at 12 V (23 W). Use an isolated,
fused, certified supply. Do not power the solenoid from the ESP32's 5 V or 3.3 V rail,
and do not share a supply with the logic unless the supply is comfortably rated and
bulk-decoupled. Add an in-line fuse (2 A) on the 12 V feed.

**Inductive kick.** A solenoid is an inductor. Interrupting 1.92 A produces a large
negative voltage spike at the drain. **The flyback diode across the coil is mandatory,
not optional.** Check its orientation (cathode to +12 V) before the first strike. Without
it, expect a dead MOSFET on strike one and a large EMI transient coupled into the
microphone wiring.

**Heat.** The solenoid is an **intermittent-duty** part: at 23 W the coil is only rated
for short pulses, and continuous energisation will overheat it in tens of seconds. The
firmware enforces three separate limits — minimum inter-strike interval (2 s), a sliding
duty/thermal budget (15 strikes per 30 s), and an independent failsafe timer that
de-energises the gate after at most 120 ms. **These are safety limits, not tunable
conveniences.** If you change them, change them in `probe_config.h` and justify it in
the report. Feel the coil after a session: it should be warm, not hot.

**MOSFET.** A failing MOSFET can fail *short*, which energises the coil permanently.
Always have a way to cut the 12 V feed (the fuse, or a switch). If the coil starts
getting hot while idle, disconnect power immediately.

**Lithium supply.** If you run the probe from a Li-ion/LiPo pack instead of a 12 V
adaptor:

* Use a pack with a proper protection/BMS board and a matched charger.
* Never charge an unattended pack, and never charge it inside the probe casing.
* Do not short the pack terminals; the available fault current is very high.
* Do not puncture, crush or expose a pack to heat. A swollen pack is a fire risk —
  dispose of it at a proper collection point.
* A 3S pack is nominally 11.1 V, not 12 V. The tap will be a little weaker; if you need
  the full 23 W, use a 4S pack or a boost converter and check the coil's rated voltage.

**Eyes and ears.** Repeated strikes at close range are loud. Wear hearing protection for
long sessions, and keep the probe tip away from faces — it moves.

**Working at height.** Any real wall survey means ladders. Nothing in this firmware
makes that safer; follow your lab's working-at-height rules.

**Radio.** The ESP32 transmits WiFi. Do not use the probe where radio transmitters are
prohibited (some hospitals, aircraft). Transmit power is low but non-zero.

---

## A.11 Notes for the report

If you are attaching this appendix to your mini-project report, the following mapping
saves you re-deriving anything:

**Which figure goes where**

| Report section | Pull from here |
|---|---|
| System architecture | A.2 — redraw the ASCII block diagram as a proper figure |
| Hardware design / PCB | A.3 pinout table, A.4 BOM and wiring diagram |
| Firmware implementation | A.2 (task structure), and `app_main.c` — quote the pipeline comment block, not the code |
| Signal processing | A.6.4 and the `PROBE_FMIN_HZ` / `PROBE_FFT_N` comments in `probe_config.h`; state the Nyquist margin (15 kHz is 62.5 % of the 24 kHz Nyquist) |
| Detection algorithm | A.6.3 — and be explicit that it is a two-threshold box rule, not a trained model |
| Calibration and validation | A.7 — quote the **counts**, not a percentage |
| Results | A.6.2 + A.7.2 |
| Limitations / future work | The "What this instrument is not" table in A.1, plus A.6.4 and A.7.2 step 5 |
| Safety | A.10 |
| Security | A.5.5 security note (plain-text NVS credentials, TLS bundle vs pinning, flash encryption) |

**Sentences you can safely write**

* "The accelerometer is used only as an auxiliary channel to verify coupling quality;
  it does not contribute to the debonding classification."
* "The classifier is a two-threshold rule fitted on two reference panels; the quoted
  agreement counts apply only to those panels."
* "Measurements in simulation mode are synthesised and are flagged `sp:true`;
  they are not presented as measured data."

**Sentences to avoid**

* "The accelerometer detects hollow areas."
* "The system is 91 % accurate." (unless you have a defensible sample, and even then
  quote the confusion counts alongside)
* "decay_tau_ms measures the material damping." (it is a relative indicator within a
  limited resolvable window)
* Any figure built from a SIMULATION run.

**What to tune first if results look bad**

1. Operator technique and probe coupling — always first, and it is free.
2. Contact geometry: how rigidly the microphone is coupled to the tip.
3. The DSP band and crossover (`PROBE_FMIN_HZ`, `PROBE_CROSSOVER_HZ`).
4. The thresholds (`set th ...`), last, and only against a measured separation.

Do not tune the thresholds first. With a bad coupling, every threshold you try will
merely overfit the noise.

---

## A.12 File manifest

| File | Lines (approx.) | Purpose |
|---|---|---|
| `README.md` | this file | build, flash, provision, SOP, calibration, troubleshooting, safety |
| `CMakeLists.txt` | 20 | project root; `project(tap_probe_rev_c)` |
| `main/CMakeLists.txt` | 25 | component registration and dependencies |
| `main/Kconfig.projbuild` | 130 | `menuconfig` tunables |
| `main/probe_config.h` | 325 | **all** pins, timings, DSP constants, thresholds |
| `main/app_main.c` | 2080 | the application |

No external DSP library is used: the FFT, Hann window and statistics are all in
`app_main.c` and are documented inline so that each step can be checked by hand.
