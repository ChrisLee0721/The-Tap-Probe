/*
 * probe_config.h  --  Tap-test probe firmware, SINGLE SOURCE OF TRUTH
 * ---------------------------------------------------------------------------
 * EEE4483 "Internet-of-Things Planning and Deployment" -- end-of-module project
 * Embedded firmware appendix.
 *
 * EVERY pin assignment, timing constant and feature threshold lives in THIS
 * file.  If you need to change a number while tuning the probe, change it here
 * (or in menuconfig, for the entries flagged as tunables) and nowhere else.
 * The application code (app_main.c) must not contain magic numbers.
 *
 * Physical summary of the instrument:
 *   - A 12 V intermittent-duty solenoid gives the wall a single mechanical tap.
 *   - An I2S MEMS microphone (ICS-43434 / INMP441) is the PRIMARY sensor.  It
 *     records the tap tone; the deliberate "ring" of a debonded (hollow) finish
 *     is longer and lower in frequency than the short "click" of a well-bonded
 *     one.
 *   - An MPU6050 accelerometer is an AUXILIARY channel only.  It measures how
 *     well the probe was held against the wall (contact/mount compliance), i.e.
 *     it is a QUALITY-CONTROL channel for the operator's technique.
 *     *** The accelerometer does NOT detect debonding.  It cannot. ***
 *
 * Pin map targets an ESP32-WROOM-32 / ESP32-DevKitC.  On ESP32-S3, ESP32-C3
 * etc. only GPIO21/22 (I2C) and the input-only pins differ -- adjust and re-run
 * `idf.py menuconfig` -> nothing breaks at compile time, but the wiring does.
 */

#ifndef PROBE_CONFIG_H
#define PROBE_CONFIG_H

#include <stdint.h>
#include <stdbool.h>
#include "driver/gpio.h"

/*
 * Toolchain note: the MPU6050 driver uses driver/i2c_master.h, which the ESP-IDF
 * v5 line introduced in v5.2.  Build with v5.2 or later, or port accel_init() /
 * mpu_write_reg() / mpu_read_regs() to the legacy driver/i2c.h API.  Either way,
 * use ONE of the two APIs; do not mix them.
 */

/* Suggested sdkconfig settings that this firmware relies on (each is the v5.2
 * default, listed here so the appendix records its dependencies):
 *   CONFIG_MBEDTLS_CERTIFICATE_BUNDLE=y   -- required by esp_crt_bundle_attach()
 *   CONFIG_ESP_TASK_WDT_INIT=y            -- task watchdog active
 *   CONFIG_ESP_WIFI_STATIC_RX_BUFFER_NUM >= 10
 */

/* =========================================================================
 * 1. FIRMWARE IDENTITY
 * ========================================================================= */

#define PROBE_FW_VERSION      "1.0.0"
#define PROBE_HW_REV          "rev-C"
#define PROBE_LOG_TAG         "PROBE"

/* NVS namespace holding the per-device credentials and calibration. */
#define PROBE_NVS_NAMESPACE   "probe"

/* =========================================================================
 * 2. BUILD-TIME TUNABLES
 *    Each of these can be overridden in `idf.py menuconfig` -> "Tap-test
 *    probe configuration" (see main/Kconfig.projbuild).  If the Kconfig symbol
 *    is absent (e.g. the file was not picked up) the #else default applies, so
 *    the firmware always builds.
 * ========================================================================= */

#ifdef CONFIG_PROBE_MIN_STRIKE_INTERVAL_MS
#define PROBE_MIN_STRIKE_INTERVAL_MS    CONFIG_PROBE_MIN_STRIKE_INTERVAL_MS
#else
#define PROBE_MIN_STRIKE_INTERVAL_MS    2000    /* ms between two strikes      */
#endif

#ifdef CONFIG_PROBE_MAX_STRIKE_DURATION_MS
#define PROBE_MAX_STRIKE_DURATION_MS    CONFIG_PROBE_MAX_STRIKE_DURATION_MS
#else
#define PROBE_MAX_STRIKE_DURATION_MS    120     /* ms HARD failsafe limit      */
#endif

#ifdef CONFIG_PROBE_STRIKE_PULSE_MS
#define PROBE_STRIKE_PULSE_MS           CONFIG_PROBE_STRIKE_PULSE_MS
#else
#define PROBE_STRIKE_PULSE_MS           25      /* ms normal energising pulse  */
#endif

#ifdef CONFIG_PROBE_DUTY_WINDOW_MS
#define PROBE_DUTY_WINDOW_MS            CONFIG_PROBE_DUTY_WINDOW_MS
#else
#define PROBE_DUTY_WINDOW_MS            30000   /* thermal averaging window    */
#endif

#ifdef CONFIG_PROBE_DUTY_MAX_STRIKES
#define PROBE_DUTY_MAX_STRIKES          CONFIG_PROBE_DUTY_MAX_STRIKES
#else
#define PROBE_DUTY_MAX_STRIKES          15      /* 15/30 s == 1 per 2 s        */
#endif

#ifdef CONFIG_PROBE_DUTY_COOLDOWN_MS
#define PROBE_DUTY_COOLDOWN_MS          CONFIG_PROBE_DUTY_COOLDOWN_MS
#else
#define PROBE_DUTY_COOLDOWN_MS          60000   /* forced rest after overheat  */
#endif

#ifdef CONFIG_PROBE_SIMULATION_MODE
#define PROBE_CFG_SIMULATION_DEFAULT    CONFIG_PROBE_SIMULATION_MODE
#else
#define PROBE_CFG_SIMULATION_DEFAULT    0
#endif

#ifdef CONFIG_PROBE_MQTT_QOS
#define PROBE_MQTT_QOS                  CONFIG_PROBE_MQTT_QOS
#else
#define PROBE_MQTT_QOS                  1
#endif

#ifdef CONFIG_PROBE_NTP_SERVER
#define PROBE_NTP_SERVER                CONFIG_PROBE_NTP_SERVER
#else
#define PROBE_NTP_SERVER                "pool.ntp.org"
#endif

#ifdef CONFIG_PROBE_ENABLE_CONSOLE
#define PROBE_ENABLE_CONSOLE            CONFIG_PROBE_ENABLE_CONSOLE
#else
#define PROBE_ENABLE_CONSOLE            1
#endif

#ifdef CONFIG_PROBE_ENABLE_ACCEL
#define PROBE_ENABLE_ACCEL              CONFIG_PROBE_ENABLE_ACCEL
#else
#define PROBE_ENABLE_ACCEL              1
#endif

/* =========================================================================
 * 3. PIN ASSIGNMENTS
 *    Keep this table identical to the README pinout table.
 * ========================================================================= */

/* --- I2S MEMS microphone (PRIMARY SENSOR) --- */
#define PROBE_PIN_I2S_BCLK    GPIO_NUM_26   /* SCK  : bit clock  (out)       */
#define PROBE_PIN_I2S_WS      GPIO_NUM_25   /* WS   : word select (out)      */
#define PROBE_PIN_I2S_DIN     GPIO_NUM_33   /* SD   : mic data   (in)        */

/* --- MPU6050 accelerometer (AUXILIARY, contact-quality channel only) --- */
#define PROBE_PIN_I2C_SDA     GPIO_NUM_21
#define PROBE_PIN_I2C_SCL     GPIO_NUM_22
#define PROBE_PIN_MPU_INT     GPIO_NUM_35   /* input-only, RESERVED/unused    */
#define PROBE_I2C_PORT        0
#define PROBE_I2C_FREQ_HZ     400000
#define PROBE_MPU6050_ADDR    0x68          /* AD0 tied low                   */

/* --- Solenoid drive (logic-level N-MOSFET low-side switch) --- */
#define PROBE_PIN_SOLENOID    GPIO_NUM_27   /* -> 220 ohm -> IRLZ44N gate     */
#define PROBE_SOLENOID_ACTIVE_LEVEL  1

/* --- Operator interface --- */
#define PROBE_PIN_TRIGGER     GPIO_NUM_32   /* momentary button to GND        */
#define PROBE_PIN_STATUS_LED  GPIO_NUM_2    /* on-board LED, heartbeat/link   */

/* =========================================================================
 * 4. MICROPHONE / CAPTURE TIMING
 *
 * Sampling-rate rationale: 48 kHz is used because the analysis band of
 * interest extends to 15 kHz.  Nyquist at 48 kHz is 24 kHz, so the highest
 * analysed frequency sits at only 62.5 % of Nyquist: the analogue
 * anti-alias filter inside the MEMS microphone is well into its stop-band
 * there, and the 1024-point FFT resolves the band into 46.9 Hz bins.
 * No decimation stage is therefore needed, which keeps the DSP path short
 * enough to be checked by hand in a student report.
 * ========================================================================= */

#define PROBE_SAMPLE_RATE_HZ        48000
#define PROBE_CAPTURE_SAMPLES       4096    /* 85.3 ms @ 48 kHz           */
#define PROBE_CAPTURE_TIMEOUT_MS    250
#define PROBE_I2S_DMA_DESC_NUM      4
#define PROBE_I2S_DMA_FRAME_NUM     512

/* Mic data format: 24 valid bits left-justified in a 32-bit slot, i.e. the
 * sample is `raw >> 8` and full scale is 2^23.  True for ICS-43434 and
 * INMP441 in their 24-bit I2S mode. */
#define PROBE_MIC_DATA_BITS         24
#define PROBE_MIC_FULL_SCALE        8388608.0f   /* 2^23 */

/* =========================================================================
 * 5. DSP PARAMETERS
 * ========================================================================= */

#define PROBE_FFT_N                 1024    /* must be a power of two     */
#define PROBE_FFT_LOG2_N            10

/* The capture buffer is drained (DMA emptied) immediately before the read is
 * started, so sample 0 of the buffer is approximately the instant the capture
 * began.  The solenoid is then fired PROBE_STRIKE_LEAD_US later, and the FFT is
 * applied to a 1024-sample window that starts PROBE_FFT_OFFSET_SAMPLES into the
 * buffer:
 *
 *   sample 0                      = capture start      (t = 0.00 ms)
 *   PROBE_STRIKE_LEAD_US          = energising edge     (t = 2.00 ms)
 *   PROBE_FFT_OFFSET_SAMPLES      = FFT window start    (t = 4.00 ms)
 *   FFT window                    = t = 4.00 .. 25.33 ms
 *
 * i.e. the window opens ~2 ms after the energising edge, which skips the
 * MOSFET switching edge, the flyback-diode spike and the solenoid armature
 * click, and still covers the mechanical impact and the first, most energetic
 * ~21 ms of the ring-down.  The alignment is good to roughly +/-0.3 ms; that
 * jitter is dominated by FreeRTOS scheduling, not by the DMA. */
#define PROBE_STRIKE_LEAD_US        2000
#define PROBE_FFT_OFFSET_SAMPLES    192     /* 4.00 ms @ 48 kHz           */

/* Analysis band.  Below 300 Hz is dominated by handling noise and the mains /
 * solenoid thump; above 15 kHz there is little panel information left. */
#define PROBE_FMIN_HZ               300.0f
#define PROBE_FMAX_HZ               15000.0f

/* band_ratio_lh = energy( FMIN_HZ .. CROSSOVER ) / energy( CROSSOVER .. FMAX ) */
#define PROBE_CROSSOVER_HZ          1000.0f

/* Envelope / decay-tau estimation.
 * The RMS envelope is formed in blocks of PROBE_ENV_BLOCK_SAMPLES over the
 * LAST PROBE_ENV_TAIL_FRACTION of the whole capture, then a straight line is
 * least-squares fitted to ln(envelope) versus time; tau = -1/slope.
 *
 * KNOWN LIMITATION, state this in the report: with an 85.3 ms capture the tail
 * window spans 34.1 ms .. 85.3 ms.  A decay much faster than ~7 ms has already
 * reached the noise floor by 34 ms, and a decay much slower than ~50 ms has not
 * decayed appreciably inside the window.  decay_tau_ms is therefore reported as
 * -1.0 when the fit is not trustworthy (see PROBE_TAU_MIN_MS / PROBE_TAU_MAX_MS)
 * and should be treated as a relative indicator, not an absolute measurement. */
#define PROBE_ENV_BLOCK_SAMPLES     32
#define PROBE_ENV_TAIL_FRACTION     0.60f
#define PROBE_TAU_MIN_MS            3.0f
#define PROBE_TAU_MAX_MS            60.0f
#define PROBE_TAU_INVALID           (-1.0f)

/* =========================================================================
 * 6. CLASSIFICATION THRESHOLDS
 *
 * Grade semantics (see README, "Interpretation" -- and be honest about them):
 *   G0  no indication of debonding  (short, high-frequency click)
 *   G1  uncertain / re-test         (intermediate)
 *   G2  debonding indicated         (longer, lower-frequency ring)
 *
 * These defaults are PLACEHOLDERS that give a sane out-of-the-box behaviour on
 * the student's reference panels.  They are NOT a validated model and MUST be
 * re-fitted with the calibration procedure described in the README before any
 * result is quoted in the report.  `set th <band_ratio> <fpeak_hz>` updates the
 * G2 pair at run time and stores it in NVS.
 * ========================================================================= */

#define PROBE_TH_RATIO_G2_DEFAULT   0.70f   /* >= -> "low frequencies dominate" */
#define PROBE_TH_FPEAK_G2_DEFAULT   700.0f  /* <= -> "peak has moved down"      */
#define PROBE_TH_RATIO_G0_DEFAULT   0.45f
#define PROBE_TH_FPEAK_G0_DEFAULT   1400.0f

/* Contact-quality acceptance window, applied to the AUXILIARY accelerometer.
 * It does not grade the wall; it grades the operator.  Outside this window the
 * measurement is flagged and the dashboard should ask for a re-test. */
#define PROBE_CONTACT_MIN_G         0.35f   /* too light / probe lifted off      */
#define PROBE_CONTACT_MAX_G         8.00f   /* operator banged the probe        */
#define PROBE_CONTACT_MIN_IMPULSE   0.040f  /* g, RMS over the strike window    */

/* =========================================================================
 * 7. ACCELEROMETER (AUXILIARY CHANNEL)
 * ========================================================================= */

#define PROBE_ACCEL_WINDOW_MS       60      /* sampled after the strike edge    */
#define PROBE_ACCEL_PERIOD_MS       1       /* ~1 kHz polling of a FIFO-less p/n */
#define PROBE_ACCEL_RANGE_G         4       /* AFS_SEL = 1 -> 8192 LSB/g        */
#define PROBE_ACCEL_LSB_PER_G       8192.0f
#define PROBE_ACCEL_SETTLE_MS       5       /* discard first samples (shock)    */

/* =========================================================================
 * 8. SOLENOID / THERMAL BUDGET
 *
 * The solenoid is a 23 W, 12 V INTERMITTENT-DUTY part: at 12 V it draws about
 * 1.92 A and dissipates ~23 W in the coil continuously, which will cook it in
 * well under a minute.  It is only ever meant to be energised for a few tens of
 * milliseconds.  The numbers below keep the worst-case duty cycle around
 * 25 ms / 2000 ms = 1.25 %, and cap the sustained rate at one strike per two
 * seconds even if the operator holds the button down.
 * ========================================================================= */

#define PROBE_SOLENOID_SUPPLY_V     12.0f
#define PROBE_SOLENOID_NOMINAL_W    22.0f
#define PROBE_SOLENOID_DUTY_MAX     0.10f   /* refuse anything above 10 %       */

/* =========================================================================
 * 9. NETWORKING
 * ========================================================================= */

#define PROBE_WIFI_MAX_RETRY        8       /* per backoff round                */
#define PROBE_WIFI_BACKOFF_MIN_MS   1000
#define PROBE_WIFI_BACKOFF_MAX_MS   60000

#define PROBE_MQTT_KEEPALIVE_S      30
#define PROBE_MQTT_RECONNECT_MS     5000
#define PROBE_MQTT_NET_TIMEOUT_MS   10000
#define PROBE_MQTT_BUFFER_SIZE      2048

#define PROBE_NTP_SYNC_TIMEOUT_MS   30000   /* publish only after sync          */
#define PROBE_STATUS_PERIOD_MS      60000   /* retained status heartbeat        */

#define PROBE_TOPIC_BASE            "probe"
#define PROBE_TOPIC_MEASUREMENT     "measurement"
#define PROBE_TOPIC_STATUS          "status"
#define PROBE_TOPIC_EVENT           "event"
/* RESERVED, not used by this revision: a downlink command topic for remote
 * reconfiguration.  Deliberately left undefined in the firmware so that no
 * unfinished feature is reachable. */
#define PROBE_TOPIC_COMMAND         "cmd"

/* =========================================================================
 * 10. TASK / RESOURCE SIZING
 *
 * Tasks that actually exist:
 *   measurement_task  (probe_meas)     consumes the measure queue
 *   capture_helper_task (probe_rx)     short-lived, one per measurement
 *   console_task      (probe_console)  UART commands
 *   app_main's own loop                trigger button, LED, counter persistence
 *
 * The accelerometer is sampled INLINE inside the measurement task (see
 * accel_capture in app_main.c) rather than in a task of its own.  That is
 * deliberate: the window has to be opened at a known instant relative to the
 * strike, and adding a task would add scheduling jitter to a 60 ms window for no
 * benefit at 1 kHz polling.  The two constants below are therefore reserved and
 * would only be used if that design were revisited.
 * ========================================================================= */

#define PROBE_TASK_MEAS_STACK       6144
#define PROBE_TASK_MEAS_PRIO        6
#define PROBE_TASK_ACCEL_STACK      3584
#define PROBE_TASK_ACCEL_PRIO       7
#define PROBE_TASK_CONSOLE_STACK    4096
#define PROBE_TASK_CONSOLE_PRIO     3
#define PROBE_MEAS_QUEUE_LEN        4

/* Update the NVS strike counter only every N strikes, to spare the flash. */
#define PROBE_STRIKES_NVS_SAVE_EVERY 10

/* =========================================================================
 * 11. DEFAULT DEVICE IDENTITY
 *    Overwritten by `provision`.  Until then the device names itself from the
 *    WiFi station MAC address (probe-AABBCC).
 * ========================================================================= */

#define PROBE_DEFAULT_DEV_PREFIX    "probe-"
#define PROBE_DEFAULT_DEV_ID        "probe-unprovisioned"

/* Compile-time guard: the FFT length must match the log2 used by the
 * bit-reversal table, and must be a power of two. */
#if (1 << PROBE_FFT_LOG2_N) != PROBE_FFT_N
#error "PROBE_FFT_N must equal 2^PROBE_FFT_LOG2_N"
#endif

#endif /* PROBE_CONFIG_H */
