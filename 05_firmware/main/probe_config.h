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
 *   - Two LSM6DS3 modules replace the microphone as the vibration sensing
 *     channel.  LSM6DS3-1 is mounted near the wall/contact tip and LSM6DS3-2
 *     is mounted on the probe body as a reference for striker/base motion.
 *     They are on the shared I2C bus at 0x6A and 0x6B.
 *   - A VL53L0X time-of-flight sensor is reserved for the shared I2C bus at
 *     0x29.  Its distance channel is for UI/position context, not debonding.
 *
 * Pin map targets an ESP32-S3-DevKitC-1 with the default flash/PSRAM pins and
 * USB-JTAG pins left alone.  Other ESP32-S3 boards may expose a different set
 * of safe GPIOs; verify the board schematic before wiring.
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

/*
 * GPIO4/5/6 are intentionally left unassigned; no I2S microphone is fitted.
 */
#define PROBE_PIN_I2S_BCLK    GPIO_NUM_4
#define PROBE_PIN_I2S_WS      GPIO_NUM_5
#define PROBE_PIN_I2S_DIN     GPIO_NUM_6

/* --- LSM6DS3 vibration sensors (primary + reference) --- */
#define PROBE_PIN_I2C_SDA     GPIO_NUM_8
#define PROBE_PIN_I2C_SCL     GPIO_NUM_9
#define PROBE_PIN_IMU1_INT     GPIO_NUM_40  /* optional, currently unused      */
#define PROBE_PIN_IMU2_INT     GPIO_NUM_41  /* optional, currently unused      */
#define PROBE_PIN_TOF_XSHUT    GPIO_NUM_42  /* optional, hold high if unused   */
#define PROBE_I2C_PORT        0
#define PROBE_I2C_FREQ_HZ     400000

/* ---- Accelerometer bus ---------------------------------------------------
 *
 * I2C cannot carry the full 6.66 kHz output rate.  One sample is six data
 * bytes = 48 data bits plus six ACK bits = 54 bus bits, which at 400 kHz is
 * 135 us against a 150 us sample period: 90 % of the bus before a single
 * address byte or a VL53L1X ranging cycle is counted.  SPI at 10 MHz moves the
 * same sample in about 6 us, so the part is switched to SPI and the I2C bus is
 * left to the time-of-flight sensor.
 *
 * These four pins are free in this build: the legacy I2S microphone code in
 * app_main.c belongs to a different environment and is no longer built.
 */
#define PROBE_IMU_USE_SPI     1
#define PROBE_PIN_IMU_SCLK    GPIO_NUM_1
#define PROBE_PIN_IMU_MOSI    GPIO_NUM_2
#define PROBE_PIN_IMU_MISO    GPIO_NUM_4
#define PROBE_PIN_IMU_CS      GPIO_NUM_5
#define PROBE_IMU_SPI_HOST    SPI3_HOST
#define PROBE_IMU_SPI_HZ      (10 * 1000 * 1000)
/* The register-polling path is paced from esp_timer.  The period is set a few
 * microseconds LONGER than the sensor's own 150.2 us sample interval (6.66 kHz):
 * a tick that lands early finds the data-ready flag clear and has to be
 * skipped, which costs a whole sample, whereas a tick that lands late simply
 * picks up the newest sample. 155 us trades 3 % of the samples for zero
 * duplicate reads. */
#define PROBE_IMU_SAMPLE_US   150
#define PROBE_LSM6DS3_ADDR_1  0x6A          /* SA0/SDO tied low               */
#define PROBE_LSM6DS3_ADDR_2  0x6B          /* SA0/SDO tied high              */
#define PROBE_VL53L0X_ADDR    0x29
/* Kept only so the legacy MPU6050 source still compiles during migration. */
#define PROBE_MPU6050_ADDR    0x68

/* --- SPI TFT displays (ST7735-class 128x160 modules) --- */
#define PROBE_PIN_TFT_SCLK    GPIO_NUM_13
#define PROBE_PIN_TFT_MOSI    GPIO_NUM_14
#define PROBE_PIN_TFT_MISO    GPIO_NUM_15   /* optional on write-only modules */
#define PROBE_PIN_TFT1_CS     GPIO_NUM_16
#define PROBE_PIN_TFT1_DC     GPIO_NUM_17
#define PROBE_PIN_TFT1_RST    GPIO_NUM_18
#define PROBE_PIN_TFT2_CS     GPIO_NUM_21
#define PROBE_PIN_TFT2_DC     GPIO_NUM_47
#define PROBE_PIN_TFT2_RST    GPIO_NUM_6

/* --- Two-axis joystick module --- */
/* Joystick thresholds.  The module outputs roughly 0..4095 with the stick
 * centred near 2048; the release band is deliberately wide so that a stick
 * which does not spring fully back cannot produce a permanent direction. */
#define PROBE_JOY_ADC_MAX           4095
#define PROBE_JOY_RELEASE_LOW       1500
#define PROBE_JOY_RELEASE_HIGH      2600
#define PROBE_JOY_SAMPLE_MS         20
#define PROBE_JOY_SW_DEBOUNCE_MS    40
/* Stick conditioning.
 *
 * The joystick shares the enclosure with the accelerometer, so a tap on the
 * housing shakes the stick and the ADC output spikes for a few milliseconds --
 * long enough for a single sample to look like a full deflection and move the
 * menu selection.  Three defences, cheapest first:
 *   1. median-of-5 on each axis, which removes a spike without lagging a real
 *      deflection by more than two sample periods;
 *   2. the direction has to persist for N samples before it is armed, so a
 *      one-off transient never becomes a move;
 *   3. any stick activity within PROBE_TAP_MUTE_MS of a tap is discarded, which
 *      covers the mechanical ring-down rather than just the impact.
 *
 * The mute is capped by a budget.  A burst of heavy strikes re-arms the window
 * every PROBE_TAP_REARM_MS, so an uncapped mute (it was 400 ms) stayed asserted
 * for the whole burst and the menu went deaf -- a hard enough tap made the
 * instrument look locked up.  The budget bounds the total deaf time of one
 * burst no matter how many strikes land in it. */
#define PROBE_JOY_MEDIAN_N          5
#define PROBE_JOY_CONFIRM_SAMPLES   3
#define PROBE_TAP_MUTE_MS           150
#define PROBE_TAP_MUTE_BUDGET_MS    250

#define PROBE_PIN_JOYSTICK_X  GPIO_NUM_10   /* ADC input, 0..3.3 V            */
#define PROBE_PIN_JOYSTICK_Y  GPIO_NUM_11   /* ADC input, 0..3.3 V            */
#define PROBE_PIN_JOYSTICK_SW GPIO_NUM_46   /* input-only; active low          */

/* --- Solenoid drive (logic-level N-MOSFET low-side switch) --- */
#define PROBE_PIN_SOLENOID    GPIO_NUM_7    /* -> 220 ohm -> IRLZ44N gate     */
#define PROBE_SOLENOID_ACTIVE_LEVEL  1

/* --- Operator interface --- */
#define PROBE_PIN_TRIGGER     GPIO_NUM_12   /* momentary button to GND        */
#define PROBE_PIN_STATUS_LED  GPIO_NUM_39   /* external LED + series resistor */
#define PROBE_PIN_ONBOARD_RGB GPIO_NUM_48   /* DevKitC-1 WS2812 data */

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

/* Mic data format: 24 valid bits, LEFT-JUSTIFIED in a 32-bit I2S slot.  The
 * ICS-43434 and INMP441 both transmit MSB-first at the start of the slot, so in
 * `I2S_DATA_BIT_WIDTH_32BIT` the value the driver hands back is
 *
 *     raw = sample_24bit << 8
 *
 * and the raw word's full scale is therefore 2^23 << 8 = 2^31, NOT 2^23.
 * Dividing `raw` by 2^23 (which an earlier revision of this header implied by
 * describing the value as "raw >> 8" while nothing in the capture path actually
 * shifted) reports every amplitude 256x too large: a full-scale sample would
 * publish peak_au = 256.0 against a documented full scale of 1.0, and the
 * noise-floor test in dsp_decay_tau() would be comparing against a threshold
 * 256x off.  The scale constant below is the raw word's full scale.
 *
 * BENCH CHECK (Appendix C.2): with the probe held against a lapped steel block,
 * `peak_au` should land in the 0.05-1.0 range.  A reading near 256 means the
 * shift convention is the other one on your module; a reading near 0.004 means
 * it is this one and something else is wrong.  Verify this before quoting any
 * amplitude, because every threshold above the raw spectrum is unaffected but
 * every published amplitude is. */
#define PROBE_MIC_DATA_BITS         24
#define PROBE_MIC_FULL_SCALE        2147483648.0f   /* 2^31 = 2^23 << 8 */

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
 *   G2  debonding indicated         (hollow ring: a mode has entered the band)
 *
 * ---------------------------------------------------------------------------
 * WHICH WAY `band_ratio_lh` MOVES, AND WHY IT IS NOT THE OBVIOUS WAY
 * ---------------------------------------------------------------------------
 * band_ratio_lh = energy(300..1000 Hz) / energy(1000..15000 Hz).
 *
 *   BONDED wall : the layer is clamped to the substrate, so its resonance sits
 *                 at f_found = (1/2pi)sqrt(k/rho h) = 23.9 kHz for 20 mm
 *                 render -- ABOVE the 15 kHz band top.  Nothing modal is in
 *                 band, so the spectrum is the strike transient times the
 *                 broadband substrate response, both low-frequency weighted.
 *                 => band_ratio_lh is HIGH (measured ~0.80).
 *
 *   DEBONDED    : the layer becomes a clamped plate on a vanishing foundation,
 *                 and its fundamental lands INSIDE the band -- 14.8 kHz at
 *                 8.8 cm diameter falling to 1.3 kHz at 30 cm.  That resonance
 *                 puts a large amount of energy ABOVE the 1 kHz crossover, so
 *                 the denominator grows and the ratio FALLS.
 *                 => band_ratio_lh is LOW (measured 0.03 .. 0.19).
 *
 * So a debond drives `band_ratio_lh` DOWN, not up.  An earlier version of this
 * header had the comparison inverted (G2 required ratio >= 0.70), which called
 * every bonded point debonded and every debonded point bonded.  The report's
 * prediction P4 records the same correction: "band_ratio_lh falls, bonded 0.800
 * against debonded 0.19" (Ch. 8.7).  Do not re-invert it.
 *
 * ---------------------------------------------------------------------------
 * KNOWN BLIND SPOT AT THE LARGE END -- state this in any survey report
 * ---------------------------------------------------------------------------
 * The rule is a *band* detector, not a monotone severity scale.  Because the
 * test is "has the mode come down INTO the 1000..15000 Hz band", a debond large
 * enough for its mode to fall BELOW the 1 kHz crossover looks bonded again:
 * f1 = 994 Hz at 34 cm, 718 Hz at 40 cm, 460 Hz at 50 cm, and band_ratio_lh
 * climbs back through 1.9 / 62 / 674.  The instrument therefore sees a *window*,
 * roughly 8.8 cm to 32 cm of diameter on 20 mm render -- blind below it (mode
 * above the band top) and blind above it (mode below the crossover).  The lower
 * edge is the size floor of Ch. 5.5; the upper edge is this crossover, and it
 * moves with the crossover, not with the finish.
 *
 * These defaults are PLACEHOLDERS that give a sane out-of-the-box behaviour on
 * the student's reference panels.  They are NOT a validated model and MUST be
 * re-fitted with the calibration procedure described in the README before any
 * result is quoted in the report.  `set th <band_ratio> <fpeak_hz>` updates the
 * G2 pair at run time and stores it in NVS.
 * ========================================================================= */

/* G2 (debond indicated): the mode has entered the band.  The binding condition
 * is the RATIO test -- a low ratio is the mode's presence.  The f_peak test is
 * deliberately non-binding (set at the 300 Hz band floor, so it is satisfied by
 * any in-band peak): a debond's mode is detectable as *added energy above the
 * crossover* from about 8.8 cm, but does not become the spectrum's argmax until
 * it is larger, so a tight f_peak bound here would veto exactly the small end
 * the design is specified to catch.  f_peak is the SIZING channel, not the
 * presence channel -- see Ch. 6.5. */
#define PROBE_TH_RATIO_G2_DEFAULT   0.45f   /* <= -> mode in band (see above)   */
#define PROBE_TH_FPEAK_G2_DEFAULT   300.0f  /* >= band floor; non-binding       */

/* G0 (no indication): high ratio AND a low peak -- the whole spectrum is the
 * strike transient and the substrate.  Both conditions bind: a probe artefact
 * that puts a spurious peak above 700 Hz drops the reading to G1 (re-test)
 * rather than passing it as bonded, which is the safe direction. */
#define PROBE_TH_RATIO_G0_DEFAULT   0.70f   /* >= -> nothing modal in band      */
#define PROBE_TH_FPEAK_G0_DEFAULT   700.0f  /* <= -> argmax is the transient    */

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
#define PROBE_SOLENOID_NOMINAL_W    23.0f
#define PROBE_SOLENOID_DUTY_MAX     0.10f   /* refuse anything above 10 %       */

/* Compile-time guard: the pulse width and the minimum interval must be chosen
 * CONSISTENTLY, because sol_strike() refuses any pulse whose worst-case duty
 * (pulse / minimum interval) exceeds PROBE_SOLENOID_DUTY_MAX.  The Kconfig
 * ranges allow pulse 5..120 ms against an interval as low as 500 ms, i.e. a
 * duty of 0.24 -- a configuration in which EVERY strike is refused at run time
 * with nothing but a log line to say why, which is a miserable thing to debug
 * on a wall.  Better to fail the build.
 *
 * Written as integer arithmetic because the preprocessor cannot evaluate
 * PROBE_SOLENOID_DUTY_MAX (a float): "duty <= 0.10" is "pulse * 10 <= interval".
 * If PROBE_SOLENOID_DUTY_MAX is ever changed, update the 10 here with it.
 *
 * If you need a longer pulse, raise PROBE_MIN_STRIKE_INTERVAL_MS with it:
 * 25 ms / 500 ms = 0.05 passes, 120 ms / 500 ms = 0.24 does not. */
#if (PROBE_STRIKE_PULSE_MS) * 10 > (PROBE_MIN_STRIKE_INTERVAL_MS)
#error "PROBE_STRIKE_PULSE_MS / PROBE_MIN_STRIKE_INTERVAL_MS exceeds PROBE_SOLENOID_DUTY_MAX: every strike would be refused at run time. Raise PROBE_MIN_STRIKE_INTERVAL_MS or lower the pulse width."
#endif

/* =========================================================================
 * 9. NETWORKING
 * ========================================================================= */

/* WiFi credentials.
 *
 * This repository is public, so the committed defaults are placeholders and
 * no real access point is published.  Two ways to give a board its AP:
 *
 *   1. Drop a probe_secrets.h next to this header (it is git-ignored):
 *          #define PROBE_SECRETS_SSID "my-ssid"
 *          #define PROBE_SECRETS_PASS "my-password"
 *      The build then uses those strings instead of the placeholders.
 *   2. Leave it out and pick the AP once from the joystick menu (WIFI page).
 *      What the probe joined is written to NVS and reused on every boot, so
 *      this is a one-time step per board, not per power cycle. */
#if defined(__has_include)
#  if __has_include("probe_secrets.h")
#    include "probe_secrets.h"
#  endif
#endif
#ifdef PROBE_SECRETS_SSID
#  define PROBE_WIFI_SSID_DEFAULT   PROBE_SECRETS_SSID
#  define PROBE_WIFI_PASS_DEFAULT   PROBE_SECRETS_PASS
#else
#  define PROBE_WIFI_SSID_DEFAULT   "your-ssid"
#  define PROBE_WIFI_PASS_DEFAULT   ""
#endif

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
#define PROBE_DEFAULT_DEV_ID        "probe-01"

/* Compile-time guard: the FFT length must match the log2 used by the
 * bit-reversal table, and must be a power of two. */
#if (1 << PROBE_FFT_LOG2_N) != PROBE_FFT_N
#error "PROBE_FFT_N must equal 2^PROBE_FFT_LOG2_N"
#endif

/* Compile-time guard: the motorola tick rate must be fast enough that every
 * millisecond delay the measurement path relies on survives pdMS_TO_TICKS().
 *
 * At the ESP-IDF default of 100 Hz, pdMS_TO_TICKS(2) and pdMS_TO_TICKS(5) both
 * evaluate to 0.  A zero-tick vTaskDelay does not block at all, so
 * do_measurement() would never yield to the lower-priority capture reader
 * before firing the solenoid, and the strike could land outside the FFT window.
 * sdkconfig.defaults sets CONFIG_FREERTOS_HZ=1000; this stops a build that has
 * lost that setting from shipping the defect silently.
 *
 * CONFIG_FREERTOS_HZ is what the IDF exposes; fall back to the legacy
 * configTICK_RATE_HZ name if this is built against an older v5 point release. */
#if defined(CONFIG_FREERTOS_HZ)
#  if CONFIG_FREERTOS_HZ < 1000
#    error "CONFIG_FREERTOS_HZ must be >= 1000: at 100 Hz, pdMS_TO_TICKS(2)==0 and the strike lead, the capture-reader waits and the accelerometer poll all collapse to zero-delay spins. See sdkconfig.defaults."
#  endif
#elif defined(configTICK_RATE_HZ)
#  if configTICK_RATE_HZ < 1000
#    error "configTICK_RATE_HZ must be >= 1000: sub-10 ms delays round to zero ticks. See sdkconfig.defaults."
#  endif
#else
#  warning "neither CONFIG_FREERTOS_HZ nor configTICK_RATE_HZ is defined at this point; the tick-rate guard did not run. Confirm the project's FreeRTOS tick rate is 1000 Hz (sdkconfig.defaults)."
#endif

/* =========================================================================
 * MQTT BROKER DEFAULTS
 * Default target: a Beaver IoT broker on the same LAN as this rig.  The
 * broker port used by a self-hosted Beaver deployment is 1883; the Web UI
 * itself is served on 8080 and is NOT an MQTT endpoint -- do not publish to it.
 * Override at run time with the console command `setmqtt <uri>` (stored in NVS).
 * ========================================================================= */
#define PROBE_MQTT_BROKER_URI_DEFAULT   "mqtt://192.168.3.12:1883"
#define PROBE_MQTT_CLIENT_ID_PREFIX     "probe-"
#define PROBE_MQTT_STATUS_PERIOD_MS     30000

/* =========================================================================
 * 12. TAP WAVEFORM CAPTURE
 *
 * The web analyser needs the raw acceleration waveform of a tap, not just a
 * summary.  The accelerometer therefore runs from its own FIFO and a triggered
 * window is published as one base64 message (see tools/mqtt_demo/PROTOCOL.md).
 * ========================================================================= */

#define PROBE_IMU_ODR_HZ            6660.0f   /* CTRL1_XL ODR_XL = 1010b        */
#define PROBE_IMU_LSB_PER_G         8192.0f   /* +/-4 g full scale: 0.122 mg/LSB */
/* The FIFO is hardware-buffered (4096 words = 1365 samples = 205 ms), so the
 * capture task only has to wake every 20 ms and pull one burst: about 133
 * samples = 1600 bytes, roughly 1.3 ms of SPI at 10 MHz.  That leaves the CPU
 * idle instead of polling the output registers. */
#define PROBE_FIFO_POLL_MS          20        /* FIFO drain period (133 sets)  */
#define PROBE_FIFO_BATCH_MAX        256       /* sample sets drained per poll  */

#define PROBE_TAP_RING_LEN          2048      /* analysis ring, one frame = xyz */
/* At 6.5 kHz a 512-frame window is 79 ms, while a tap on tile rings down with
 * a measured time constant near 58 ms: that is barely one time constant, which
 * is not enough to fit decay_tau.  1024 frames is 158 ms, about 2.7 tau.  The
 * payload grows to 6 kB of samples, 8 kB as base64; see the MQTT out_size. */
#define PROBE_TAP_WINDOW            1024      /* frames published per tap      */
#define PROBE_TAP_PRE               128       /* frames kept before the trigger (~20 ms) */
#define PROBE_TAP_THRESH_G          0.25f     /* default trigger level, g      */
#define PROBE_TAP_REARM_MS          250       /* refractory period             */
#define PROBE_TAP_MIN_G             0.05f     /* below this a window is noise  */

#define PROBE_TOPIC_WAVEFORM        "waveform"
#define PROBE_TOPIC_CMD             "cmd"
/* Continuous 6.66 kHz sample batches (20 ms each) for live spectrograms. */
#define PROBE_TOPIC_STREAM          "stream"

/* Menu geometry.  Items are a real 5x7 font drawn at scale 2 (10x14 px glyph,
 * 12 px advance), so six rows fit under the 14 px title bar with room for the
 * value bar and the key legend. */
#define PROBE_MENU_ROWS             6
#define PROBE_MENU_ROW_PITCH        18
#define PROBE_MENU_TITLE_H          14

/* Menu-adjustable defaults.  These are run-time state, not compile-time
 * constants, but the power-on values live here with everything else. */
#define PROBE_DEFAULT_MQTT_QOS      0
#define PROBE_DEFAULT_PUB_PERIOD_MS 2000

#endif /* PROBE_CONFIG_H */

