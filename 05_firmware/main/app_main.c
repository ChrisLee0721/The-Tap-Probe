/*
 * app_main.c -- Handheld tap-test probe for debonded external wall finishes.
 *
 * EEE4483 "Internet-of-Things Planning and Deployment" -- end-of-module project.
 * Target: ESP-IDF v5.x, C99, FreeRTOS.  No Arduino.
 *
 * ---------------------------------------------------------------------------
 * WHAT THIS INSTRUMENT IS, AND WHAT IT IS NOT
 * ---------------------------------------------------------------------------
 * The operator presses the probe against a wall finish and fires a single
 * strike. A solenoid gives the surface one mechanical tap. The tap tone is
 * recorded by an I2S MEMS microphone, analysed on-device, and reduced to eight
 * numbers. A grade (G0/G1/G2) is derived locally from two of those numbers with
 * a rule that lives in probe_config.h. The result is published as JSON over
 * MQTT/TLS.
 *
 * The microphone is the PRIMARY and ONLY detection channel.
 *
 * The MPU6050 accelerometer is an AUXILIARY channel. It measures how the probe
 * behaved at the moment of impact, i.e. it is an operator technique / contact
 * quality diagnostic. impact_peak_g and impulse_norm are used to flag a
 * measurement that should be repeated because the probe was lifted, dragged or
 * banged.  *** The accelerometer does not, and cannot, detect debonding. ***
 * Any report text that claims otherwise is wrong.
 *
 * Likewise, when the firmware is built with SIMULATION enabled the feature
 * numbers are SYNTHESISED. They are not measurements. They are published with
 * "sp":true and the boot log says so in capitals. Never present simulated data
 * as measured data.
 *
 * ---------------------------------------------------------------------------
 * MEASUREMENT PIPELINE (one strike == one measurement)
 * ---------------------------------------------------------------------------
 *   1. Thermal/duty interlock check (min interval, duty ceiling, cooldown).
 *   2. Drain the I2S DMA so the capture buffer starts empty.
 *   3. Start the I2S read into a fixed buffer (PROBE_CAPTURE_SAMPLES @ 48 kHz).
 *   4. Fire the solenoid pulse PROBE_STRIKE_LEAD_US later; a hard failsafe
 *      timer is armed independently and forces the pin low after at most
 *      PROBE_MAX_STRIKE_DURATION_MS even if this task is blocked or wedged.
 *   5. Sample the MPU6050 for PROBE_ACCEL_WINDOW_MS around the strike.
 *   6. Wait for the I2S read to complete (bounded timeout, never forever).
 *   7. DSP: integer mean removal (DC), Hann window, 1024-point radix-2
 *      Cooley-Tukey FFT (local, no external DSP library), then
 *      f_peak_hz, f_centroid_hz, band_ratio_lh, decay_tau_ms, peak_au,
 *      rms_au, crest_factor, kurtosis.
 *   8. Classify G0/G1/G2 locally.
 *   9. Build the JSON payload and publish.
 *
 * The DSP is allocation-free after init: the buffers are static and are reused
 * for every strike.
 *
 * ---------------------------------------------------------------------------
 * EMI / TIMING NOTE
 * ---------------------------------------------------------------------------
 * The WiFi radio and the solenoid both inject EMI into a 1.92 A inductive
 * switching node sitting a few centimetres from a MEMS microphone. Two
 * mitigations are built in: (a) the solenoid is fired as early as possible in
 * the measurement so that the burst-over-the-air that the ESP32 does on
 * transmit is not coincident with the strike where practical; (b) the capture
 * is strictly bounded around the strike -- the DMA is drained first, one read
 * is issued, and no other I2S traffic happens during the window. If you
 * re-arrange the code, do not let a publish overlap the capture window.
 *
 * Payload schema (one JSON object per measurement, one line, no trailing
 * whitespace):
 *
 *   ts            int    Unix time, seconds, UTC, from SNTP.
 *   dev           str    Device id, from NVS (default probe-<mac suffix>).
 *   seq           int    Monotonic measurement counter since boot.
 *   grade         str    "G0" | "G1" | "G2".
 *   confidence    float  0..1 heuristic margin of the winning grade.
 *   f_peak_hz     float  Largest FFT bin magnitude in 300..15000 Hz.
 *   f_centroid_hz float  Spectral centroid over the same band.
 *   band_ratio_lh float  energy(<1000 Hz) / energy(>1000 Hz).
 *   decay_tau_ms  float  Log-linear envelope decay constant, -1 if unusable.
 *   peak_au       float  Peak |x| in the analysis window, full scale = 1.0.
 *   rms_au        float  RMS of the analysis window, full scale = 1.0.
 *   crest_factor  float  peak_au / rms_au.
 *   kurtosis      float  Fourth standardised moment (3.0 = Gaussian noise).
 *   impact_peak_g float  AUXILIARY: max per-axis |a| during the strike window.
 *   impulse_norm  float  AUXILIARY: RMS of the same window, g.
 *   sp            bool   true == SYNTHESISED features. Not a measurement.
 *   fw            str    Firmware version.
 *   rssi          int    WiFi RSSI at publish time, dBm.
 *   strikes_total int    Lifetime strike count (NVS-backed).
 *   contact_ok    bool   AUXILIARY contact-quality verdict.
 *   event_flag    str    "" when clean, else a short machine-readable reason.
 *
 * Example:
 *   {"ts":1699999999,"dev":"probe-01","seq":42,"grade":"G1","confidence":0.71,
 *    "f_peak_hz":912.0,"f_centroid_hz":1180.0,"band_ratio_lh":0.63,
 *    "decay_tau_ms":31.4,"peak_au":0.82,"rms_au":0.11,"crest_factor":3.4,
 *    "kurtosis":5.2,"impact_peak_g":2.1,"impulse_norm":0.34,"sp":false,
 *    "fw":"1.0.0","rssi":-61,"strikes_total":128,"contact_ok":true,
 *    "event_flag":""}
 */

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>
#include <time.h>
#include <inttypes.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/event_groups.h"
#include "freertos/semphr.h"

#include "esp_system.h"
#include "esp_mac.h"
#include "esp_log.h"
#include "esp_err.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_sntp.h"
#include "esp_crt_bundle.h"
#include "nvs.h"
#include "nvs_flash.h"

#include "driver/gpio.h"
#include "driver/i2s_std.h"
#include "driver/i2c_master.h"
#include "mqtt_client.h"

#include "probe_config.h"

/* =========================================================================
 * Log tags.  Every error path is logged with ESP_LOGE and a tag.
 * ========================================================================= */
static const char *TAG_MAIN = PROBE_LOG_TAG;
static const char *TAG_WIFI = "PROBE_WIFI";
static const char *TAG_MQTT = "PROBE_MQTT";
static const char *TAG_DSP = "PROBE_DSP";
static const char *TAG_SOL = "PROBE_SOL";
static const char *TAG_ACC = "PROBE_ACC";
static const char *TAG_CON = "PROBE_CON";

/* =========================================================================
 * Shared runtime state
 * ========================================================================= */

typedef struct {
    char dev_id[48];
    char wifi_ssid[33];
    char wifi_pass[65];
    char mqtt_uri[160];
    char mqtt_user[64];
    char mqtt_pass[64];
    char mqtt_clientid[64];
    float th_ratio_g2;
    float th_fpeak_g2;
    float th_ratio_g0;
    float th_fpeak_g0;
} probe_cfg_t;

typedef struct {
    float f_peak_hz;
    float f_centroid_hz;
    float band_ratio_lh;
    float decay_tau_ms;
    float peak_au;
    float rms_au;
    float crest_factor;
    float kurtosis;
} probe_features_t;

typedef struct {
    float impact_peak_g;
    float impulse_norm;
    bool  valid;
} probe_accel_t;

typedef struct {
    uint32_t        seq;
    bool            simulated;
    bool            contact_ok;
    char            event_flag[32];
    probe_features_t feat;
    probe_accel_t    aux;
} probe_result_t;

static probe_cfg_t      s_cfg;
static probe_result_t   s_result;
static SemaphoreHandle_t s_cfg_lock;     /* guards s_cfg                          */
static SemaphoreHandle_t s_state_lock;   /* guards s_result, s_strikes_total      */
static SemaphoreHandle_t s_sol_lock;     /* serialises strikes, backs the interlock */

static volatile uint32_t s_strikes_total = 0;
static volatile uint32_t s_strikes_pending_nvs = 0;
static volatile bool     s_simulation = false;
static volatile bool     s_mqtt_connected = false;
static volatile bool     s_time_synced = false;
static volatile uint32_t s_strikes_refused = 0;   /* interlock refusals since boot */
static volatile int64_t  s_start_us = 0;

/* NTP/status bookkeeping */
static volatile int64_t  s_next_status_us = 0;

/* =========================================================================
 * Thermal / duty housekeeping for the solenoid.
 *
 * The solenoid is a 23 W / 12 V intermittent-duty part. Held on continuously it
 * dissipates 23 W in a coil that is not designed to shed it and will be damaged
 * in tens of seconds. It is only ever energised for tens of milliseconds.
 *
 * Three independent guards are implemented here:
 *   (1) minimum inter-strike interval  -- stops the operator machine-gunning it;
 *   (2) duty budget over a sliding window -- catches a slow but still
 *       unsustainable rate that guard (1) alone would let through, and puts the
 *       probe into a forced cooldown when tripped;
 *   (3) an independent esp_timer failsafe that de-asserts the gate pin even if
 *       the measurement task is blocked, so the MOSFET can never be left on.
 * ========================================================================= */

typedef struct {
    int64_t  last_strike_us;
    int64_t  window_start_us;
    uint32_t strikes_in_window;
    int64_t  cooldown_until_us;
} sol_thermal_t;

static sol_thermal_t s_thermal;
static esp_timer_handle_t s_sol_failsafe_timer = NULL;

typedef enum {
    SOL_OK = 0,
    SOL_TOO_SOON,       /* guard (1) */
    SOL_DUTY_EXCEEDED,  /* guard (2) */
    SOL_IN_COOLDOWN,    /* still resting after a guard (2) trip */
    SOL_BUSY,           /* the strike mutex is held by someone else */
} sol_verdict_t;

static const char *sol_verdict_str(sol_verdict_t v)
{
    switch (v) {
    case SOL_OK:              return "ok";
    case SOL_TOO_SOON:        return "too_soon";
    case SOL_DUTY_EXCEEDED:   return "duty_exceeded";
    case SOL_IN_COOLDOWN:     return "in_cooldown";
    case SOL_BUSY:            return "busy";
    default:                  return "unknown";
    }
}

/* Independent failsafe: drives the gate low and nothing else.
 *
 * Dispatched from the esp_timer service task (ESP_TIMER_TASK), not from an ISR,
 * and deliberately does nothing but write one GPIO.  It is a SECOND line of
 * defence: the strike routine itself de-asserts the gate on the success path, so
 * in the healthy case this callback finds the pin already inactive and writing
 * it again is harmless.  If the measurement task is ever delayed past the pulse
 * width, this fires and the coil is de-energised anyway.  It is not a safety
 * certification -- if the timer service task itself is starved, the gate stays
 * high until the strike routine resumes; that is why the pulse width is short
 * and the drive stage has a hardware gate pulldown. */
static void sol_failsafe_cb(void *arg)
{
    (void)arg;
    gpio_set_level(PROBE_PIN_SOLENOID, !PROBE_SOLENOID_ACTIVE_LEVEL);
}

static void sol_gpio_init(void)
{
    gpio_config_t io = {
        .pin_bit_mask = (1ULL << PROBE_PIN_SOLENOID),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_ENABLE,   /* matches the hardware pulldown */
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&io));
    gpio_set_level(PROBE_PIN_SOLENOID, !PROBE_SOLENOID_ACTIVE_LEVEL);

    const esp_timer_create_args_t fs_args = {
        .callback = sol_failsafe_cb,
        .arg = NULL,
        .dispatch_method = ESP_TIMER_TASK,
        .name = "sol_failsafe",
    };
    ESP_ERROR_CHECK(esp_timer_create(&fs_args, &s_sol_failsafe_timer));
}

/* Non-blocking admission check.  Called with s_sol_lock held by the caller. */
static sol_verdict_t sol_admit(int64_t now_us)
{
    if (now_us < s_thermal.cooldown_until_us) {
        ESP_LOGE(TAG_SOL, "strike refused: thermal cooldown active for %" PRId64 " ms",
                 (s_thermal.cooldown_until_us - now_us) / 1000);
        return SOL_IN_COOLDOWN;
    }

    if (s_thermal.last_strike_us != 0 &&
        (now_us - s_thermal.last_strike_us) < (int64_t)PROBE_MIN_STRIKE_INTERVAL_MS * 1000) {
        ESP_LOGE(TAG_SOL, "strike refused: %" PRId64 " ms since last strike, minimum is %d ms",
                 (now_us - s_thermal.last_strike_us) / 1000,
                 PROBE_MIN_STRIKE_INTERVAL_MS);
        return SOL_TOO_SOON;
    }

    /* Sliding duty window. */
    if (s_thermal.window_start_us == 0 ||
        (now_us - s_thermal.window_start_us) > (int64_t)PROBE_DUTY_WINDOW_MS * 1000) {
        s_thermal.window_start_us = now_us;
        s_thermal.strikes_in_window = 0;
    }
    if (s_thermal.strikes_in_window >= (uint32_t)PROBE_DUTY_MAX_STRIKES) {
        s_thermal.cooldown_until_us = now_us + (int64_t)PROBE_DUTY_COOLDOWN_MS * 1000;
        ESP_LOGE(TAG_SOL, "THERMAL BUDGET EXCEEDED: %u strikes in %d ms window; "
                          "forcing %d ms cooldown",
                 (unsigned)s_thermal.strikes_in_window, PROBE_DUTY_WINDOW_MS,
                 PROBE_DUTY_COOLDOWN_MS);
        return SOL_DUTY_EXCEEDED;
    }
    return SOL_OK;
}

/* Fire a single bounded pulse.  Returns ESP_OK only if the pulse was issued.
 * The GPIO is driven low again in BOTH the success path and the failsafe path;
 * a stuck-high gate is the one failure mode that destroys hardware. */
static esp_err_t sol_strike(uint32_t pulse_ms, sol_verdict_t *verdict_out)
{
    int64_t now_us = esp_timer_get_time();

    if (xSemaphoreTake(s_sol_lock, pdMS_TO_TICKS(20)) != pdTRUE) {
        if (verdict_out) *verdict_out = SOL_BUSY;
        ESP_LOGE(TAG_SOL, "strike refused: solenoid busy");
        return ESP_ERR_INVALID_STATE;
    }

    sol_verdict_t v = sol_admit(now_us);
    if (verdict_out) *verdict_out = v;
    if (v != SOL_OK) {
        xSemaphoreGive(s_sol_lock);
        return ESP_ERR_INVALID_STATE;
    }

    /* Clamp the requested pulse to the hard limit.  Never trust a caller. */
    if (pulse_ms == 0 || pulse_ms > (uint32_t)PROBE_MAX_STRIKE_DURATION_MS) {
        ESP_LOGE(TAG_SOL, "pulse %" PRIu32 " ms out of range, clamping to %d ms",
                 pulse_ms, PROBE_MAX_STRIKE_DURATION_MS);
        pulse_ms = PROBE_MAX_STRIKE_DURATION_MS;
    }

    /* Duty is computed on the worst case the operator is allowed to reach: one
     * pulse every PROBE_MIN_STRIKE_INTERVAL_MS.  For the default pulse this is
     * 25/2000 = 1.25 %, which is the continuous thermal load the coil sees at
     * full rate.  Anything above PROBE_SOLENOID_DUTY_MAX means the pulse and
     * the interlock interval have been configured inconsistently -- refuse
     * rather than cook the solenoid. */
    float duty = (float)pulse_ms / (float)PROBE_MIN_STRIKE_INTERVAL_MS;
    if (duty > PROBE_SOLENOID_DUTY_MAX) {
        ESP_LOGE(TAG_SOL, "refusing pulse: duty %.3f exceeds %.3f (%.1f V, %.0f W part)",
                 duty, PROBE_SOLENOID_DUTY_MAX,
                 PROBE_SOLENOID_SUPPLY_V, PROBE_SOLENOID_NOMINAL_W);
        xSemaphoreGive(s_sol_lock);
        return ESP_ERR_INVALID_STATE;
    }

    /* Arm the independent failsafe FIRST, then energise.  If esp_timer_start
     * fails we must not energise at all. */
    if (esp_timer_start_once(s_sol_failsafe_timer,
                             (uint64_t)pulse_ms * 1000ULL) != ESP_OK) {
        ESP_LOGE(TAG_SOL, "cannot arm failsafe timer, strike aborted");
        xSemaphoreGive(s_sol_lock);
        return ESP_FAIL;
    }

    ESP_LOGI(TAG_SOL, "strike: %" PRIu32 " ms pulse, %.0f V / %.0f W solenoid, "
                      "strike #%" PRIu32 " this window",
             pulse_ms, PROBE_SOLENOID_SUPPLY_V, PROBE_SOLENOID_NOMINAL_W,
             s_thermal.strikes_in_window + 1);

    gpio_set_level(PROBE_PIN_SOLENOID, PROBE_SOLENOID_ACTIVE_LEVEL);
    vTaskDelay(pdMS_TO_TICKS(pulse_ms));
    gpio_set_level(PROBE_PIN_SOLENOID, !PROBE_SOLENOID_ACTIVE_LEVEL);
    esp_timer_stop(s_sol_failsafe_timer);

    s_thermal.last_strike_us = now_us;
    s_thermal.strikes_in_window++;

    xSemaphoreGive(s_sol_lock);
    return ESP_OK;
}

/* =========================================================================
 * I2S microphone -- PRIMARY SENSOR
 * ========================================================================= */

static i2s_chan_handle_t s_rx_chan = NULL;
static bool              s_mic_ok = false;

static int32_t s_raw[PROBE_CAPTURE_SAMPLES];
static float   s_win[PROBE_FFT_N];      /* Hann-windowed, DC-removed samples  */
static float   s_re[PROBE_FFT_N];
static float   s_im[PROBE_FFT_N];
static float   s_mag[PROBE_FFT_N / 2];
static float   s_hann[PROBE_FFT_N];
static uint16_t s_bitrev[PROBE_FFT_N];

static esp_err_t mic_init(void)
{
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_AUTO, I2S_ROLE_MASTER);
    chan_cfg.dma_desc_num = PROBE_I2S_DMA_DESC_NUM;
    chan_cfg.dma_frame_num = PROBE_I2S_DMA_FRAME_NUM;
    chan_cfg.auto_clear    = true;

    esp_err_t err = i2s_new_channel(&chan_cfg, NULL, &s_rx_chan);
    if (err != ESP_OK) {
        ESP_LOGE(TAG_MAIN, "i2s_new_channel failed: %s", esp_err_to_name(err));
        return err;
    }

    i2s_std_config_t std_cfg = {
        .clk_cfg  = I2S_STD_CLK_DEFAULT_CONFIG(PROBE_SAMPLE_RATE_HZ),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT,
                                                        I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = PROBE_PIN_I2S_BCLK,
            .ws   = PROBE_PIN_I2S_WS,
            .dout = I2S_GPIO_UNUSED,
            .din  = PROBE_PIN_I2S_DIN,
            .invert_flags = { .mclk_inv = false, .bclk_inv = false, .ws_inv = false },
        },
    };
    /* The MEMS mic drives the data line only; select the left channel so the
     * ICS-43434/INMP441 are read on their WS-low half-frame. */
    std_cfg.slot_cfg.ws_width  = 32;
    std_cfg.slot_cfg.slot_mask = I2S_STD_SLOT_LEFT;

    err = i2s_channel_init_std_mode(s_rx_chan, &std_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG_MAIN, "i2s_channel_init_std_mode failed: %s", esp_err_to_name(err));
        i2s_del_channel(s_rx_chan);
        s_rx_chan = NULL;
        return err;
    }
    err = i2s_channel_enable(s_rx_chan);
    if (err != ESP_OK) {
        ESP_LOGE(TAG_MAIN, "i2s_channel_enable failed: %s", esp_err_to_name(err));
        i2s_del_channel(s_rx_chan);
        s_rx_chan = NULL;
        return err;
    }

    ESP_LOGI(TAG_MAIN, "mic ready: %d Hz, mono, %d-bit data in 32-bit slots, "
                       "analysis band %.0f..%.0f Hz",
             PROBE_SAMPLE_RATE_HZ, PROBE_MIC_DATA_BITS, PROBE_FMIN_HZ, PROBE_FMAX_HZ);
    s_mic_ok = true;
    return ESP_OK;
}

/* Drain whatever is already in the DMA so the capture starts clean. */
static void mic_drain(void)
{
    if (!s_rx_chan) return;
    int32_t junk[PROBE_I2S_DMA_FRAME_NUM];
    size_t got = 0;
    /* Bounded: at most a handful of short reads. */
    for (int i = 0; i < 8; i++) {
        if (i2s_channel_read(s_rx_chan, junk, sizeof(junk), &got, 0) != ESP_OK || got == 0) {
            break;
        }
    }
}

static esp_err_t mic_capture(void)
{
    if (!s_mic_ok || !s_rx_chan) {
        ESP_LOGE(TAG_MAIN, "capture requested but microphone is not available");
        return ESP_ERR_INVALID_STATE;
    }
    size_t got = 0;
    esp_err_t err = i2s_channel_read(s_rx_chan, s_raw, sizeof(s_raw), &got,
                                     pdMS_TO_TICKS(PROBE_CAPTURE_TIMEOUT_MS));
    if (err != ESP_OK) {
        ESP_LOGE(TAG_MAIN, "i2s read failed: %s", esp_err_to_name(err));
        return err;
    }
    if (got < sizeof(s_raw)) {
        ESP_LOGE(TAG_MAIN, "i2s short read: %u of %u bytes",
                 (unsigned)got, (unsigned)sizeof(s_raw));
        return ESP_ERR_INVALID_SIZE;
    }
    return ESP_OK;
}

/* =========================================================================
 * MPU6050 -- AUXILIARY CONTACT-QUALITY CHANNEL
 *
 * I2C is used via the ESP-IDF v5 `driver/i2c_master.h` API.  (The legacy
 * `driver/i2c.h` API is NOT used anywhere in this project -- pick one and stay
 * consistent.)
 *
 * This device is read ONLY to answer "was the probe held flat and firmly at the
 * instant of impact?".  It is not part of the detection path.
 * ========================================================================= */

#define MPU6050_REG_SMPLRT_DIV   0x19
#define MPU6050_REG_CONFIG       0x1A
#define MPU6050_REG_GYRO_CONFIG  0x1B
#define MPU6050_REG_ACCEL_CONFIG 0x1C
#define MPU6050_REG_ACCEL_XOUT_H 0x3B
#define MPU6050_REG_PWR_MGMT_1   0x6B
#define MPU6050_REG_WHO_AM_I     0x75

static i2c_master_bus_handle_t s_i2c_bus = NULL;
static i2c_master_dev_handle_t s_mpu = NULL;
static bool s_accel_ok = false;

static esp_err_t mpu_write_reg(uint8_t reg, uint8_t val)
{
    uint8_t buf[2] = { reg, val };
    return i2c_master_transmit(s_mpu, buf, 2, 100);
}

static esp_err_t mpu_read_regs(uint8_t reg, uint8_t *out, size_t len)
{
    return i2c_master_transmit_receive(s_mpu, &reg, 1, out, len, 100);
}

static esp_err_t accel_init(void)
{
#if !PROBE_ENABLE_ACCEL
    ESP_LOGW(TAG_ACC, "accelerometer disabled by configuration; "
                      "contact-quality reporting will be absent");
    return ESP_ERR_NOT_SUPPORTED;
#else
    i2c_master_bus_config_t bus_cfg = {
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .i2c_port = PROBE_I2C_PORT,
        .scl_io_num = PROBE_PIN_I2C_SCL,
        .sda_io_num = PROBE_PIN_I2C_SDA,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    esp_err_t err = i2c_new_master_bus(&bus_cfg, &s_i2c_bus);
    if (err != ESP_OK) {
        ESP_LOGE(TAG_ACC, "i2c_new_master_bus failed: %s", esp_err_to_name(err));
        return err;
    }

    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = PROBE_MPU6050_ADDR,
        .scl_speed_hz = PROBE_I2C_FREQ_HZ,
    };
    err = i2c_master_bus_add_device(s_i2c_bus, &dev_cfg, &s_mpu);
    if (err != ESP_OK) {
        ESP_LOGE(TAG_ACC, "i2c_master_bus_add_device failed: %s", esp_err_to_name(err));
        return err;
    }

    uint8_t who = 0;
    err = mpu_read_regs(MPU6050_REG_WHO_AM_I, &who, 1);
    if (err != ESP_OK) {
        ESP_LOGE(TAG_ACC, "WHO_AM_I read failed: %s", esp_err_to_name(err));
        return err;
    }
    if ((who & 0x7E) != 0x68) {
        ESP_LOGE(TAG_ACC, "WHO_AM_I = 0x%02X, expected 0x68 (MPU6050)", who);
        return ESP_ERR_NOT_FOUND;
    }

    if ((err = mpu_write_reg(MPU6050_REG_PWR_MGMT_1, 0x00)) != ESP_OK) goto fail;
    vTaskDelay(pdMS_TO_TICKS(50));                        /* wake-up time      */
    if ((err = mpu_write_reg(MPU6050_REG_PWR_MGMT_1, 0x01)) != ESP_OK) goto fail;
    if ((err = mpu_write_reg(MPU6050_REG_CONFIG, 0x03)) != ESP_OK) goto fail;
    /* Sample rate = 1 kHz / (1 + SMPLRT_DIV).  4 -> 200 Hz. */
    if ((err = mpu_write_reg(MPU6050_REG_SMPLRT_DIV, 0x04)) != ESP_OK) goto fail;
    /* AFS_SEL = 1 -> +/-4 g (8192 LSB/g).  A hand-held tap is a few g; +/-4 g
     * keeps 1 mg resolution while still not clipping a firm strike. */
    if ((err = mpu_write_reg(MPU6050_REG_ACCEL_CONFIG, 0x08)) != ESP_OK) goto fail;
    if ((err = mpu_write_reg(MPU6050_REG_GYRO_CONFIG, 0x00)) != ESP_OK) goto fail;

    ESP_LOGI(TAG_ACC, "MPU6050 ready at 0x%02X, +/-%d g, ~200 Hz (AUXILIARY channel: "
                      "contact quality only)",
             PROBE_MPU6050_ADDR, PROBE_ACCEL_RANGE_G);
    s_accel_ok = true;
    return ESP_OK;

fail:
    ESP_LOGE(TAG_ACC, "MPU6050 configuration failed: %s", esp_err_to_name(err));
    return err;
#endif
}

/* Poll the accelerometer for PROBE_ACCEL_WINDOW_MS and reduce to two numbers.
 *
 * This function never blocks the caller for longer than the window, and it
 * always produces a `valid` verdict -- if the sensor is missing the caller
 * publishes the measurement anyway, with the auxiliary fields marked invalid
 * and an event logged.  A missing accelerometer must not stop the instrument
 * from working, because it is not the detection channel. */
static void accel_capture(probe_accel_t *out)
{
    out->impact_peak_g = 0.0f;
    out->impulse_norm  = 0.0f;
    out->valid = false;

    if (!s_accel_ok) {
        return;
    }

    const int64_t t_end = esp_timer_get_time() + (int64_t)PROBE_ACCEL_WINDOW_MS * 1000;
    double sum_sq = 0.0;
    uint32_t n = 0;
    int64_t t_first = 0;

    while (esp_timer_get_time() < t_end) {
        uint8_t raw[6];
        if (mpu_read_regs(MPU6050_REG_ACCEL_XOUT_H, raw, sizeof(raw)) != ESP_OK) {
            ESP_LOGE(TAG_ACC, "accelerometer read failed mid-window");
            return;
        }
        int16_t ax = (int16_t)((raw[0] << 8) | raw[1]);
        int16_t ay = (int16_t)((raw[2] << 8) | raw[3]);
        int16_t az = (int16_t)((raw[4] << 8) | raw[5]);

        /* Magnitude of the vector, in g.  Static 1 g of gravity is present, so
         * the resting reading is ~1 g; that is why the acceptance window is not
         * centred on zero. */
        float gx = (float)ax / PROBE_ACCEL_LSB_PER_G;
        float gy = (float)ay / PROBE_ACCEL_LSB_PER_G;
        float gz = (float)az / PROBE_ACCEL_LSB_PER_G;
        float mag = sqrtf(gx * gx + gy * gy + gz * gz);

        int64_t t_now = esp_timer_get_time();
        if (t_first == 0) t_first = t_now;
        if ((t_now - t_first) < (int64_t)PROBE_ACCEL_SETTLE_MS * 1000) {
            vTaskDelay(pdMS_TO_TICKS(PROBE_ACCEL_PERIOD_MS));
            continue;   /* discard the first few ms: the solenoid shock itself */
        }

        if (mag > out->impact_peak_g) {
            out->impact_peak_g = mag;
        }
        sum_sq += (double)mag * (double)mag;
        n++;

        vTaskDelay(pdMS_TO_TICKS(PROBE_ACCEL_PERIOD_MS));
    }

    if (n == 0) {
        ESP_LOGE(TAG_ACC, "no accelerometer samples collected");
        return;
    }
    out->impulse_norm = (float)sqrt(sum_sq / (double)n);
    out->valid = true;
}

/* =========================================================================
 * Local DSP -- self-contained, allocation-free after init
 *
 * No external DSP library is used.  Everything below is a plain radix-2
 * Cooley-Tukey decimation-in-time FFT plus the supporting statistics, so a
 * marker can follow it line by line.
 * ========================================================================= */

/* Hann window, periodic form: w[n] = 0.5 * (1 - cos(2*pi*n/N)).
 * The periodic form is used (not the symmetric N-1 denominator) because it is
 * the one whose coherent gain is exactly 0.5. */
static void dsp_make_hann(void)
{
    for (int n = 0; n < PROBE_FFT_N; n++) {
        s_hann[n] = 0.5f * (1.0f - cosf(2.0f * (float)M_PI * (float)n / (float)PROBE_FFT_N));
    }
}

static void dsp_make_bitrev(void)
{
    for (int i = 0; i < PROBE_FFT_N; i++) {
        uint16_t x = (uint16_t)i;
        uint16_t r = 0;
        for (int b = 0; b < PROBE_FFT_LOG2_N; b++) {
            r = (uint16_t)((r << 1) | (x & 1u));
            x = (uint16_t)(x >> 1);
        }
        s_bitrev[i] = r;
    }
}

/* In-place radix-2 DIT FFT.  s_re/s_im must already hold the bit-reversed
 * input.  Uses only stack and static storage. */
static void fft_radix2(float *re, float *im)
{
    for (int len = 2; len <= PROBE_FFT_N; len <<= 1) {
        float ang = -2.0f * (float)M_PI / (float)len;
        float wlen_re = cosf(ang);
        float wlen_im = sinf(ang);
        for (int i = 0; i < PROBE_FFT_N; i += len) {
            float wr = 1.0f, wi = 0.0f;
            for (int k = 0; k < len / 2; k++) {
                int a = i + k;
                int b = i + k + len / 2;
                float tr = re[b] * wr - im[b] * wi;
                float ti = re[b] * wi + im[b] * wr;
                re[b] = re[a] - tr;
                im[b] = im[a] - ti;
                re[a] += tr;
                im[a] += ti;
                float nwr = wr * wlen_re - wi * wlen_im;
                wi = wr * wlen_im + wi * wlen_re;
                wr = nwr;
            }
        }
    }
}

/* Forward transform over the analysis window of the capture. */
static void dsp_transform(void)
{
    /* 1. Integer DC removal over the window actually used by the FFT. */
    int64_t sum = 0;
    for (int n = 0; n < PROBE_FFT_N; n++) {
        sum += s_raw[PROBE_FFT_OFFSET_SAMPLES + n];
    }
    float mean = (float)((double)sum / (double)PROBE_FFT_N);

    /* 2. Scale to full-scale = 1.0, subtract the mean, apply the Hann window
     *    and divide by the window's coherent gain so that a pure tone's peak
     *    bin magnitude is independent of the windowing. */
    const float inv_fs = 1.0f / PROBE_MIC_FULL_SCALE;
    const float inv_cg = 1.0f / 0.5f;   /* Hann coherent gain = 0.5 */

    for (int n = 0; n < PROBE_FFT_N; n++) {
        float x = ((float)s_raw[PROBE_FFT_OFFSET_SAMPLES + n] - mean) * inv_fs;
        s_win[n] = x * s_hann[n] * inv_cg;
    }

    /* 3. Bit-reverse into the complex arrays. */
    for (int n = 0; n < PROBE_FFT_N; n++) {
        s_re[s_bitrev[n]] = s_win[n];
        s_im[s_bitrev[n]] = 0.0f;
    }

    /* 4. Transform and take magnitudes of the single-sided spectrum. */
    fft_radix2(s_re, s_im);
    for (int k = 0; k < PROBE_FFT_N / 2; k++) {
        s_mag[k] = sqrtf(s_re[k] * s_re[k] + s_im[k] * s_im[k]);
    }
}

/* Convert a bin index to Hz (bin width = fs/N). */
static inline float bin_hz(int k)
{
    return (float)k * (float)PROBE_SAMPLE_RATE_HZ / (float)PROBE_FFT_N;
}

static int hz_to_bin(float hz)
{
    int k = (int)lroundf(hz * (float)PROBE_FFT_N / (float)PROBE_SAMPLE_RATE_HZ);
    if (k < 0) k = 0;
    if (k > PROBE_FFT_N / 2 - 1) k = PROBE_FFT_N / 2 - 1;
    return k;
}

static void dsp_spectral_features(probe_features_t *f)
{
    const int k_lo = hz_to_bin(PROBE_FMIN_HZ);
    const int k_hi = hz_to_bin(PROBE_FMAX_HZ);
    const int k_x  = hz_to_bin(PROBE_CROSSOVER_HZ);

    /* --- f_peak_hz: largest bin magnitude in [FMIN, FMAX]. ------------- */
    int k_peak = k_lo;
    float m_peak = 0.0f;
    for (int k = k_lo; k <= k_hi; k++) {
        if (s_mag[k] > m_peak) {
            m_peak = s_mag[k];
            k_peak = k;
        }
    }
    /* Quadratic (parabolic) interpolation across the three bins around the peak
     * gives a sub-bin estimate.  Without it the frequency resolution is only
     * 46.875 Hz (PROBE_FFT_N = 1024 at 48 kHz), which is coarse relative to the
     * FPEAK_SPAN of 700 Hz the classifier compares against, and would quantise
     * f_peak into a visible staircase on the dashboard time series. */
    float f_peak = bin_hz(k_peak);
    if (k_peak > k_lo && k_peak < k_hi) {
        float a = s_mag[k_peak - 1], b = s_mag[k_peak], c = s_mag[k_peak + 1];
        float denom = (a - 2.0f * b + c);
        if (fabsf(denom) > 1e-12f) {
            float d = 0.5f * (a - c) / denom;
            if (d > -1.0f && d < 1.0f) {
                f_peak = bin_hz(k_peak) + d * (float)PROBE_SAMPLE_RATE_HZ / (float)PROBE_FFT_N;
            }
        }
    }
    f->f_peak_hz = f_peak;

    /* --- f_centroid_hz: magnitude-weighted mean frequency over the band. */
    double num = 0.0, den = 0.0;
    for (int k = k_lo; k <= k_hi; k++) {
        num += (double)s_mag[k] * (double)bin_hz(k);
        den += (double)s_mag[k];
    }
    f->f_centroid_hz = (den > 1e-12) ? (float)(num / den) : 0.0f;

    /* --- band_ratio_lh: energy below the crossover / energy above. -----
     * Energy, not magnitude, so the bins are squared. */
    double e_lo = 0.0, e_hi = 0.0;
    for (int k = k_lo; k <= k_hi; k++) {
        double e = (double)s_mag[k] * (double)s_mag[k];
        if (k < k_x) {
            e_lo += e;
        } else {
            e_hi += e;
        }
    }
    f->band_ratio_lh = (e_hi > 1e-15) ? (float)(e_lo / e_hi) : 99.0f;

    /* --- Time-domain statistics over the same analysis window. --------- */
    double sq = 0.0;
    float  pk = 0.0f;
    for (int n = 0; n < PROBE_FFT_N; n++) {
        float x = s_win[n];
        sq += (double)x * (double)x;
        float ax = fabsf(x);
        if (ax > pk) pk = ax;
    }
    float rms = (float)sqrt(sq / (double)PROBE_FFT_N);
    f->peak_au = pk;
    f->rms_au  = rms;
    f->crest_factor = (rms > 1e-9f) ? (pk / rms) : 0.0f;

    /* Kurtosis: 4th standardised moment, using the window mean.  Note the window
     * mean is ~0 by construction (DC was removed), but we recompute it so the
     * statistic is self-consistent if this function is reused. */
    double m1 = 0.0;
    for (int n = 0; n < PROBE_FFT_N; n++) {
        m1 += (double)s_win[n];
    }
    m1 /= (double)PROBE_FFT_N;

    double m2 = 0.0, m4 = 0.0;
    for (int n = 0; n < PROBE_FFT_N; n++) {
        double d = (double)s_win[n] - m1;
        double d2 = d * d;
        m2 += d2;
        m4 += d2 * d2;
    }
    m2 /= (double)PROBE_FFT_N;
    m4 /= (double)PROBE_FFT_N;
    f->kurtosis = (m2 > 1e-18) ? (float)(m4 / (m2 * m2)) : 0.0f;
}

/* --- decay_tau_ms: log-linear fit of ln(RMS envelope) over the tail. ----
 *
 * See the KNOWN LIMITATION comment in probe_config.h.  The tau is a relative
 * indicator only, and is reported as PROBE_TAU_INVALID (a negative sentinel)
 * whenever the fit is not trustworthy, so that downstream code cannot mistake a
 * saturated fit for a real number. */
static float dsp_decay_tau(void)
{
    const int n_tail = (int)((float)PROBE_CAPTURE_SAMPLES * PROBE_ENV_TAIL_FRACTION);
    const int start  = PROBE_CAPTURE_SAMPLES - n_tail;

    /* Remove the capture-wide mean so the envelope is of the AC signal. */
    int64_t sum = 0;
    for (int n = 0; n < PROBE_CAPTURE_SAMPLES; n++) {
        sum += s_raw[n];
    }
    float mean = (float)((double)sum / (double)PROBE_CAPTURE_SAMPLES);

    const int n_blocks = n_tail / PROBE_ENV_BLOCK_SAMPLES;
    if (n_blocks < 4) {
        return PROBE_TAU_INVALID;
    }

    double sx = 0.0, sy = 0.0, sxx = 0.0, sxy = 0.0;
    int    used = 0;

    for (int b = 0; b < n_blocks; b++) {
        double acc = 0.0;
        int base = start + b * PROBE_ENV_BLOCK_SAMPLES;
        for (int i = 0; i < PROBE_ENV_BLOCK_SAMPLES; i++) {
            double v = ((double)s_raw[base + i] - mean) / (double)PROBE_MIC_FULL_SCALE;
            acc += v * v;
        }
        double rms = sqrt(acc / (double)PROBE_ENV_BLOCK_SAMPLES);
        if (rms < 1e-7) {
            continue;   /* block is at the noise floor; ln() would be garbage */
        }
        double t = ((double)base + (double)PROBE_ENV_BLOCK_SAMPLES * 0.5) /
                   (double)PROBE_SAMPLE_RATE_HZ;      /* seconds, block centre */
        double y = log(rms);
        sx  += t;  sy  += y;
        sxx += t * t;  sxy += t * y;
        used++;
    }

    if (used < 4) {
        return PROBE_TAU_INVALID;
    }

    double n = (double)used;
    double denom = n * sxx - sx * sx;
    if (fabs(denom) < 1e-15) {
        return PROBE_TAU_INVALID;
    }
    double slope = (n * sxy - sx * sy) / denom;   /* per second */

    /* A positive slope means the envelope is growing in the tail, which is not
     * a decay.  Reject it rather than returning a negative tau. */
    if (slope >= -1e-3) {
        return PROBE_TAU_INVALID;
    }

    float tau_ms = (float)((-1.0 / slope) * 1000.0);
    if (tau_ms < PROBE_TAU_MIN_MS || tau_ms > PROBE_TAU_MAX_MS) {
        return PROBE_TAU_INVALID;   /* outside the resolvable range: see header */
    }
    return tau_ms;
}

/* =========================================================================
 * Simulation -- NEVER let these numbers look real.
 * ========================================================================= */

static uint32_t s_sim_lcg = 0x12345678u;

static float sim_rand01(void)
{
    /* Deterministic LCG so a demo is repeatable; not cryptographic, and it does
     * not need to be. */
    s_sim_lcg = s_sim_lcg * 1664525u + 1013904223u;
    return (float)((s_sim_lcg >> 8) & 0xFFFFFFu) / (float)0xFFFFFF;
}

/* Synthesise a plausible-looking feature set.  The distribution is shaped so
 * that the classifier boundary is exercised on both sides, which is the whole
 * point of simulation: it lets the MQTT path and the dashboard be demonstrated
 * end-to-end before the transducer chain exists.
 *
 * The values follow the direction documented in probe_config.h: a hollow rings
 * with its plate mode INSIDE the band, so its band_ratio_lh is LOW and its
 * f_peak is a real in-band resonance; a bonded point has nothing modal in band,
 * so its band_ratio_lh is HIGH and its f_peak is the strike transient near the
 * band floor.  Getting this pair the wrong way round makes the simulation
 * demonstrate the opposite of what the hardware does. */
static void sim_features(probe_features_t *f, probe_accel_t *a)
{
    bool hollow = sim_rand01() < 0.35f;
    float jitter = (sim_rand01() - 0.5f) * 0.10f;

    if (hollow) {
        /* Mode in band: ratio driven down, peak is the resonance itself. */
        f->f_peak_hz     = 900.0f  + sim_rand01() * 2400.0f;
        f->f_centroid_hz = 1900.0f + sim_rand01() * 900.0f;
        f->band_ratio_lh = 0.10f   + jitter;
        f->decay_tau_ms  = 24.0f   + sim_rand01() * 16.0f;
    } else {
        /* Nothing modal in band: transient at the floor, ratio high. */
        f->f_peak_hz     = 320.0f  + sim_rand01() * 120.0f;
        f->f_centroid_hz = 1200.0f + sim_rand01() * 500.0f;
        f->band_ratio_lh = 0.79f   + jitter;
        f->decay_tau_ms  = 6.0f    + sim_rand01() * 7.0f;
    }
    f->peak_au      = 0.55f + sim_rand01() * 0.40f;
    f->rms_au       = f->peak_au / (2.6f + sim_rand01() * 1.6f);
    f->crest_factor = f->peak_au / f->rms_au;
    f->kurtosis     = 3.0f + sim_rand01() * 6.0f;

    a->impact_peak_g = 0.9f + sim_rand01() * 2.6f;
    a->impulse_norm  = 0.10f + sim_rand01() * 0.30f;
    a->valid         = true;
}

/* =========================================================================
 * Classification -- local, deliberately simple, and documented as such.
 *
 * The rule is a two-condition box test.  Repeating the direction note from
 * probe_config.h because getting it backwards inverts the instrument: a debond
 * puts its plate mode ABOVE the 1 kHz crossover, so it drives `band_ratio_lh`
 * DOWN (bonded ~0.80, debonded ~0.03..0.19).
 *
 *   G2 (debonding indicated) if band_ratio_lh <= TH_RATIO_G2 AND f_peak >= TH_FPEAK_G2
 *   G0 (no indication)       if band_ratio_lh >= TH_RATIO_G0 AND f_peak <= TH_FPEAK_G0
 *   otherwise G1 (uncertain / re-test)
 *
 * The two boxes are disjoint by construction: TH_RATIO_G2 (0.45) is below
 * TH_RATIO_G0 (0.70), so no reading can satisfy both, and the band between them
 * is G1.  The G2 f_peak bound sits at the band floor and is deliberately
 * non-binding; see probe_config.h for why a tight one would veto the small end.
 *
 * BLIND SPOT: this detects a mode that has come down INTO 1..15 kHz.  A debond
 * whose mode has fallen BELOW the 1 kHz crossover reads as bonded again
 * (~34 cm and up on 20 mm render).  The rule is a window, not a severity scale.
 *
 * confidence is the normalised distance from the decision boundary, NOT a
 * probability.  It is a heuristic margin in 0..1 and must be described as such
 * in the report.  It is computed as the smaller of the two normalised margins
 * of the winning grade.
 * ========================================================================= */

static float clamp01(float x)
{
    if (x < 0.0f) return 0.0f;
    if (x > 1.0f) return 1.0f;
    return x;
}

static const char *classify(const probe_features_t *f, float *confidence)
{
    float thr_r2, thr_f2, thr_r0, thr_f0;
    xSemaphoreTake(s_cfg_lock, portMAX_DELAY);
    thr_r2 = s_cfg.th_ratio_g2;
    thr_f2 = s_cfg.th_fpeak_g2;
    thr_r0 = s_cfg.th_ratio_g0;
    thr_f0 = s_cfg.th_fpeak_g0;
    xSemaphoreGive(s_cfg_lock);

    /* Normalisation spans.  These are the widths of the transition regions. */
    const float RATIO_SPAN = 0.25f;
    const float FPEAK_SPAN = 700.0f;

    /* Both margins are "how far inside the box", so each is >= 0 exactly when
     * its grade's conditions hold.  Note the ratio terms run the opposite way
     * for the two grades: a debond is a LOW ratio, a bonded point a HIGH one. */
    float margin_g2 = fminf((thr_r2 - f->band_ratio_lh) / RATIO_SPAN,
                            (f->f_peak_hz - thr_f2) / FPEAK_SPAN);
    float margin_g0 = fminf((f->band_ratio_lh - thr_r0) / RATIO_SPAN,
                            (thr_f0 - f->f_peak_hz) / FPEAK_SPAN);

    if (margin_g2 >= 0.0f && margin_g2 >= margin_g0) {
        *confidence = clamp01(0.5f + margin_g2 * 0.5f);
        return "G2";
    }
    if (margin_g0 >= 0.0f && margin_g0 > margin_g2) {
        *confidence = clamp01(0.5f + margin_g0 * 0.5f);
        return "G0";
    }
    /* In the transition region. Report how deep into it we are: a measurement
     * that is twice as far from both boundaries is twice as trustworthy. */
    float dist = fminf(fabsf(margin_g2), fabsf(margin_g0));
    *confidence = clamp01(0.5f - dist * 0.5f);
    return "G1";
}

/* =========================================================================
 * NVS
 * ========================================================================= */

static void nvs_load(void)
{
    nvs_handle_t h;
    esp_err_t err = nvs_open(PROBE_NVS_NAMESPACE, NVS_READONLY, &h);
    if (err != ESP_OK) {
        ESP_LOGW(TAG_MAIN, "no NVS namespace '%s' yet (%s): using defaults",
                 PROBE_NVS_NAMESPACE, esp_err_to_name(err));
        return;
    }

    size_t len;

    memset(s_cfg.dev_id, 0, sizeof(s_cfg.dev_id));
    len = sizeof(s_cfg.dev_id);
    if (nvs_get_str(h, "dev_id", s_cfg.dev_id, &len) != ESP_OK) {
        /* Fall back to the compiled-in id, or a MAC-derived one, so an
         * unprovisioned board is still individually identifiable on the broker
         * and two unprovisioned boards do not fight over the same client id. */
        uint8_t mac[6] = {0};
        esp_read_mac(mac, ESP_MAC_WIFI_STA);
        if (strcmp(PROBE_DEFAULT_DEV_ID, PROBE_DEFAULT_DEV_PREFIX "unprovisioned") == 0) {
            snprintf(s_cfg.dev_id, sizeof(s_cfg.dev_id), "%s%02X%02X%02X",
                     PROBE_DEFAULT_DEV_PREFIX, mac[3], mac[4], mac[5]);
        } else {
            strlcpy(s_cfg.dev_id, PROBE_DEFAULT_DEV_ID, sizeof(s_cfg.dev_id));
        }
        ESP_LOGW(TAG_MAIN, "device not provisioned, using id '%s'", s_cfg.dev_id);
    }

    len = sizeof(s_cfg.wifi_ssid);
    nvs_get_str(h, "wifi_ssid", s_cfg.wifi_ssid, &len);
    len = sizeof(s_cfg.wifi_pass);
    nvs_get_str(h, "wifi_pass", s_cfg.wifi_pass, &len);
    len = sizeof(s_cfg.mqtt_uri);
    nvs_get_str(h, "mqtt_uri", s_cfg.mqtt_uri, &len);
    len = sizeof(s_cfg.mqtt_user);
    nvs_get_str(h, "mqtt_user", s_cfg.mqtt_user, &len);
    len = sizeof(s_cfg.mqtt_pass);
    nvs_get_str(h, "mqtt_pass", s_cfg.mqtt_pass, &len);
    len = sizeof(s_cfg.mqtt_clientid);
    nvs_get_str(h, "mqtt_cid", s_cfg.mqtt_clientid, &len);

    /* Lifetime strike count.  Read into a local and copy out: writing through a
     * cast away from `volatile` is not something to leave in the code. */
    uint32_t strikes = 0;
    if (nvs_get_u32(h, "strikes_total", &strikes) == ESP_OK) {
        s_strikes_total = strikes;
    }

    s_cfg.th_ratio_g2 = PROBE_TH_RATIO_G2_DEFAULT;
    s_cfg.th_fpeak_g2 = PROBE_TH_FPEAK_G2_DEFAULT;
    s_cfg.th_ratio_g0 = PROBE_TH_RATIO_G0_DEFAULT;
    s_cfg.th_fpeak_g0 = PROBE_TH_FPEAK_G0_DEFAULT;

    uint32_t tmp;
    if (nvs_get_u32(h, "th_ratio_g2", &tmp) == ESP_OK) s_cfg.th_ratio_g2 = (float)tmp / 1000.0f;
    if (nvs_get_u32(h, "th_fpeak_g2", &tmp) == ESP_OK) s_cfg.th_fpeak_g2 = (float)tmp;
    if (nvs_get_u32(h, "th_ratio_g0", &tmp) == ESP_OK) s_cfg.th_ratio_g0 = (float)tmp / 1000.0f;
    if (nvs_get_u32(h, "th_fpeak_g0", &tmp) == ESP_OK) s_cfg.th_fpeak_g0 = (float)tmp;

    nvs_close(h);
    ESP_LOGI(TAG_MAIN, "config: dev=%s mqtt=%s user=%s strikes=%" PRIu32,
             s_cfg.dev_id, s_cfg.mqtt_uri, s_cfg.mqtt_user, (uint32_t)s_strikes_total);
}

static esp_err_t nvs_save_strikes(void)
{
    nvs_handle_t h;
    esp_err_t err = nvs_open(PROBE_NVS_NAMESPACE, NVS_READWRITE, &h);
    if (err != ESP_OK) {
        ESP_LOGE(TAG_MAIN, "nvs_open(RW) for strike count failed: %s", esp_err_to_name(err));
        return err;
    }
    err = nvs_set_u32(h, "strikes_total", s_strikes_total);
    if (err == ESP_OK) {
        err = nvs_commit(h);
    }
    nvs_close(h);
    if (err != ESP_OK) {
        ESP_LOGE(TAG_MAIN, "saving strike count failed: %s", esp_err_to_name(err));
    }
    return err;
}

/* Thresholds are stored as integers (x1000 for the ratio, Hz for the peak) so
 * that NVS never has to store a float. */
static esp_err_t nvs_save_thresholds(void)
{
    nvs_handle_t h;
    esp_err_t err = nvs_open(PROBE_NVS_NAMESPACE, NVS_READWRITE, &h);
    if (err != ESP_OK) {
        ESP_LOGE(TAG_MAIN, "nvs_open(RW) for thresholds failed: %s", esp_err_to_name(err));
        return err;
    }
    xSemaphoreTake(s_cfg_lock, portMAX_DELAY);
    err  = nvs_set_u32(h, "th_ratio_g2", (uint32_t)(s_cfg.th_ratio_g2 * 1000.0f));
    err |= nvs_set_u32(h, "th_fpeak_g2", (uint32_t)(s_cfg.th_fpeak_g2));
    err |= nvs_set_u32(h, "th_ratio_g0", (uint32_t)(s_cfg.th_ratio_g0 * 1000.0f));
    err |= nvs_set_u32(h, "th_fpeak_g0", (uint32_t)(s_cfg.th_fpeak_g0));
    xSemaphoreGive(s_cfg_lock);
    if (err == ESP_OK) {
        err = nvs_commit(h);
    }
    nvs_close(h);
    if (err != ESP_OK) {
        ESP_LOGE(TAG_MAIN, "saving thresholds failed: %s", esp_err_to_name(err));
    }
    return err;
}

static esp_err_t nvs_save_provision(const char *ssid, const char *pass, const char *uri,
                                    const char *user, const char *mpass, const char *cid,
                                    const char *dev_id)
{
    nvs_handle_t h;
    esp_err_t err = nvs_open(PROBE_NVS_NAMESPACE, NVS_READWRITE, &h);
    if (err != ESP_OK) {
        ESP_LOGE(TAG_MAIN, "nvs_open(RW) for provisioning failed: %s", esp_err_to_name(err));
        return err;
    }
    err  = nvs_set_str(h, "wifi_ssid", ssid);
    err |= nvs_set_str(h, "wifi_pass", pass);
    err |= nvs_set_str(h, "mqtt_uri", uri);
    err |= nvs_set_str(h, "mqtt_user", user);
    err |= nvs_set_str(h, "mqtt_pass", mpass);
    err |= nvs_set_str(h, "mqtt_cid", cid && *cid ? cid : dev_id);
    err |= nvs_set_str(h, "dev_id", dev_id);
    if (err == ESP_OK) {
        err = nvs_commit(h);
    }
    nvs_close(h);
    if (err != ESP_OK) {
        ESP_LOGE(TAG_MAIN, "provisioning write failed: %s", esp_err_to_name(err));
    }
    return err;
}

/* =========================================================================
 * WiFi
 * ========================================================================= */

static EventGroupHandle_t s_wifi_eg;
#define WIFI_BIT_CONNECTED  BIT0
#define WIFI_BIT_FAIL       BIT1

static int s_wifi_retry = 0;
static esp_timer_handle_t s_wifi_retry_timer = NULL;

/* Reconnect from a TIMER, not from inside the event handler.
 *
 * The handler below runs on the system event task, which is also the task that
 * delivers every other default-loop event (IP acquisition, MQTT's socket
 * events, the SNTP callback).  Sleeping there for the backoff would stall all
 * of them -- at the maximum backoff, for a full 60 s, and the log lines from
 * the MQTT task would simply stop appearing while it happened.  The timer
 * callback runs on the esp_timer task and touches nothing but esp_wifi_connect().
 */
static void wifi_retry_cb(void *arg)
{
    (void)arg;
    esp_wifi_connect();
}

static void wifi_retry_schedule(int delay_ms)
{
    if (s_wifi_retry_timer == NULL) {
        const esp_timer_create_args_t args = {
            .callback = &wifi_retry_cb,
            .dispatch_method = ESP_TIMER_TASK,
            .name = "wifi_retry",
        };
        if (esp_timer_create(&args, &s_wifi_retry_timer) != ESP_OK) {
            /* Cannot schedule: fall back to an immediate retry rather than
             * dropping the reconnection entirely. */
            esp_wifi_connect();
            return;
        }
    }
    esp_timer_stop(s_wifi_retry_timer);      /* no-op if not running */
    esp_timer_start_once(s_wifi_retry_timer, (uint64_t)delay_ms * 1000ULL);
}

static void wifi_event_handler(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        s_mqtt_connected = false;
        xEventGroupClearBits(s_wifi_eg, WIFI_BIT_CONNECTED);
        if (s_wifi_retry < PROBE_WIFI_MAX_RETRY) {
            s_wifi_retry++;
            int delay_ms = PROBE_WIFI_BACKOFF_MIN_MS << (s_wifi_retry - 1);
            if (delay_ms > PROBE_WIFI_BACKOFF_MAX_MS) delay_ms = PROBE_WIFI_BACKOFF_MAX_MS;
            ESP_LOGW(TAG_WIFI, "disconnected, retry %d/%d in %d ms",
                     s_wifi_retry, PROBE_WIFI_MAX_RETRY, delay_ms);
            wifi_retry_schedule(delay_ms);
        } else {
            ESP_LOGE(TAG_WIFI, "giving up after %d retries; will retry on the next "
                               "supervised round", PROBE_WIFI_MAX_RETRY);
            xEventGroupSetBits(s_wifi_eg, WIFI_BIT_FAIL);
        }
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *evt = (ip_event_got_ip_t *)data;
        ESP_LOGI(TAG_WIFI, "got IP " IPSTR, IP2STR(&evt->ip_info.ip));
        s_wifi_retry = 0;
        xEventGroupClearBits(s_wifi_eg, WIFI_BIT_FAIL);
        xEventGroupSetBits(s_wifi_eg, WIFI_BIT_CONNECTED);
    }
}

/* Blocking connect with bounded retries.  Returns ESP_OK when an IP is held. */
static esp_err_t wifi_start(void)
{
    xSemaphoreTake(s_cfg_lock, portMAX_DELAY);
    char ssid[sizeof(s_cfg.wifi_ssid)];
    char pass[sizeof(s_cfg.wifi_pass)];
    strlcpy(ssid, s_cfg.wifi_ssid, sizeof(ssid));
    strlcpy(pass, s_cfg.wifi_pass, sizeof(pass));
    xSemaphoreGive(s_cfg_lock);

    if (ssid[0] == '\0') {
        ESP_LOGE(TAG_WIFI, "no SSID provisioned; run 'provision <ssid> <pass> ...' "
                           "on the console");
        return ESP_ERR_INVALID_STATE;
    }

    ESP_ERROR_CHECK(esp_netif_init());
    s_wifi_eg = xEventGroupCreate();
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t init_cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init_cfg));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID,
                                                        &wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP,
                                                        &wifi_event_handler, NULL, NULL));

    wifi_config_t wc = { 0 };
    strlcpy((char *)wc.sta.ssid, ssid, sizeof(wc.sta.ssid));
    strlcpy((char *)wc.sta.password, pass, sizeof(wc.sta.password));
    wc.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;  /* refuse open networks */
    wc.sta.pmf_cfg.capable = true;
    wc.sta.pmf_cfg.required = false;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wc));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG_WIFI, "connecting to '%s'", ssid);
    EventBits_t bits = xEventGroupWaitBits(s_wifi_eg,
                                           WIFI_BIT_CONNECTED | WIFI_BIT_FAIL,
                                           pdFALSE, pdFALSE,
                                           pdMS_TO_TICKS(PROBE_WIFI_BACKOFF_MAX_MS));
    if (bits & WIFI_BIT_CONNECTED) {
        return ESP_OK;
    }
    ESP_LOGE(TAG_WIFI, "initial association failed");
    return ESP_FAIL;
}

/* =========================================================================
 * SNTP -- timestamps are only published once the clock is trustworthy.
 * ========================================================================= */

static esp_err_t time_sync(void)
{
    esp_sntp_setoperatingmode(ESP_SNTP_OPMODE_POLL);
    esp_sntp_setservername(0, PROBE_NTP_SERVER);
    esp_sntp_init();

    const int64_t deadline = esp_timer_get_time() +
                             (int64_t)PROBE_NTP_SYNC_TIMEOUT_MS * 1000;
    while (esp_timer_get_time() < deadline) {
        time_t now = 0;
        time(&now);
        /* Anything after 2023-01-01 is a plausible wall clock. */
        if (now > 1672531200) {
            struct tm tmv;
            gmtime_r(&now, &tmv);
            char buf[32];
            strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", &tmv);
            ESP_LOGI(TAG_MAIN, "SNTP synced: %s UTC", buf);
            s_time_synced = true;
            return ESP_OK;
        }
        vTaskDelay(pdMS_TO_TICKS(250));
    }
    ESP_LOGE(TAG_MAIN, "SNTP did not sync within %d ms; timestamps will be "
                       "published as 0 until it does", PROBE_NTP_SYNC_TIMEOUT_MS);
    return ESP_ERR_TIMEOUT;
}

/* =========================================================================
 * MQTT over TLS
 *
 * The trust anchor comes from the ESP-IDF certificate bundle
 * (esp_crt_bundle_attach) rather than a pinned PEM, so the firmware does not
 * have to be rebuilt when the CA rotates.  For a production device a pinned
 * certificate or mutual TLS would be preferred; that trade-off is discussed in
 * the report.
 *
 * LWT: the broker publishes probe/<id>/status = "offline" for us if the link
 * drops without a clean DISCONNECT, so the dashboard can distinguish "probe is
 * off" from "probe is logged in and idle".
 * ========================================================================= */

static esp_mqtt_client_handle_t s_mqtt = NULL;
static char s_topic_meas[96];
static char s_topic_status[96];
static char s_topic_event[96];

static void mqtt_publish_event(const char *code, const char *detail)
{
    if (!s_mqtt || !s_mqtt_connected) {
        ESP_LOGW(TAG_MQTT, "event '%s' (%s) not published: MQTT down", code, detail);
        return;
    }
    char payload[256];
    snprintf(payload, sizeof(payload),
             "{\"ts\":%" PRId64 ",\"dev\":\"%s\",\"code\":\"%s\",\"detail\":\"%s\","
             "\"fw\":\"%s\"}",
             (int64_t)time(NULL), s_cfg.dev_id, code, detail, PROBE_FW_VERSION);
    esp_mqtt_client_publish(s_mqtt, s_topic_event, payload, 0, PROBE_MQTT_QOS, 0);
}

static void mqtt_publish_status(const char *state, const char *extra)
{
    if (!s_mqtt || !s_mqtt_connected) {
        return;
    }
    char payload[320];
    if (extra && *extra) {
        snprintf(payload, sizeof(payload),
                 "{\"ts\":%" PRId64 ",\"dev\":\"%s\",\"state\":\"%s\",\"extra\":\"%s\","
                 "\"fw\":\"%s\",\"strikes_total\":%" PRIu32 ",\"heap\":%" PRIu32 "}",
                 (int64_t)time(NULL), s_cfg.dev_id, state, extra, PROBE_FW_VERSION,
                 (uint32_t)s_strikes_total, (uint32_t)esp_get_free_heap_size());
    } else {
        snprintf(payload, sizeof(payload),
                 "{\"ts\":%" PRId64 ",\"dev\":\"%s\",\"state\":\"%s\","
                 "\"fw\":\"%s\",\"strikes_total\":%" PRIu32 ",\"heap\":%" PRIu32 "}",
                 (int64_t)time(NULL), s_cfg.dev_id, state, PROBE_FW_VERSION,
                 (uint32_t)s_strikes_total, (uint32_t)esp_get_free_heap_size());
    }
    /* Retained: a dashboard that connects later still sees the last state. */
    esp_mqtt_client_publish(s_mqtt, s_topic_status, payload, 0, PROBE_MQTT_QOS, 1);
}

static void mqtt_event_handler(void *handler_args, esp_event_base_t base,
                               int32_t event_id, void *event_data)
{
    esp_mqtt_event_handle_t event = (esp_mqtt_event_handle_t)event_data;
    (void)handler_args;
    (void)base;

    switch ((esp_mqtt_event_id_t)event_id) {
    case MQTT_EVENT_CONNECTED:
        ESP_LOGI(TAG_MQTT, "connected to broker");
        s_mqtt_connected = true;
        mqtt_publish_status("online", s_simulation ? "SIMULATION MODE" : "");
        break;

    case MQTT_EVENT_DISCONNECTED:
        ESP_LOGW(TAG_MQTT, "disconnected from broker");
        s_mqtt_connected = false;
        break;

    case MQTT_EVENT_ERROR:
        s_mqtt_connected = false;
        if (event->error_handle) {
            esp_mqtt_error_codes_t *e = event->error_handle;
            ESP_LOGE(TAG_MQTT, "error type %d, tls stack err 0x%x, cert flags 0x%x "
                               "(check the system clock and the CA bundle)",
                     e->error_type, (unsigned)e->esp_tls_last_esp_err,
                     (unsigned)e->esp_tls_cert_verify_flags);
        } else {
            ESP_LOGE(TAG_MQTT, "unspecified MQTT error");
        }
        break;

    case MQTT_EVENT_PUBLISHED:
        ESP_LOGD(TAG_MQTT, "publish id %d acknowledged", event->msg_id);
        break;

    default:
        break;
    }
}

static esp_err_t mqtt_start(void)
{
    if (s_cfg.mqtt_uri[0] == '\0') {
        ESP_LOGE(TAG_MQTT, "no MQTT URI provisioned");
        return ESP_ERR_INVALID_STATE;
    }

    /* Refuse a plaintext URI.  The report's security position (Ch. 7.4) is that
     * the device validates the broker with the CA bundle and that credentials
     * never cross the air in the clear; an `mqtt://` URI silently voids both,
     * with no error raised anywhere -- the connection just succeeds and
     * everything is readable.  That is exactly the "verification silently
     * disabled" failure the project warns about, so it is a hard error here
     * rather than a warning.  For a lab broker use `mqtts://` with the CA in
     * the bundle; see README A.8. */
    if (strncmp(s_cfg.mqtt_uri, "mqtts://", 8) != 0) {
        ESP_LOGE(TAG_MQTT, "refusing broker URI '%s': it is not mqtts://. "
                           "Plaintext MQTT would send the device credentials and "
                           "the survey data unencrypted. Reprovision with an "
                           "mqtts:// URI.", s_cfg.mqtt_uri);
        return ESP_ERR_INVALID_ARG;
    }

    snprintf(s_topic_meas,   sizeof(s_topic_meas),   "%s/%s/%s",
             PROBE_TOPIC_BASE, s_cfg.dev_id, PROBE_TOPIC_MEASUREMENT);
    snprintf(s_topic_status, sizeof(s_topic_status), "%s/%s/%s",
             PROBE_TOPIC_BASE, s_cfg.dev_id, PROBE_TOPIC_STATUS);
    snprintf(s_topic_event,  sizeof(s_topic_event),  "%s/%s/%s",
             PROBE_TOPIC_BASE, s_cfg.dev_id, PROBE_TOPIC_EVENT);

    char lwt[96];
    snprintf(lwt, sizeof(lwt),
             "{\"dev\":\"%s\",\"state\":\"offline\",\"fw\":\"%s\"}",
             s_cfg.dev_id, PROBE_FW_VERSION);

    esp_mqtt_client_config_t cfg = {
        .broker.address.uri = s_cfg.mqtt_uri,
        .credentials = {
            .username = s_cfg.mqtt_user,
            .authentication.password = s_cfg.mqtt_pass,
            .client_id = s_cfg.mqtt_clientid[0] ? s_cfg.mqtt_clientid : s_cfg.dev_id,
        },
        .session = {
            .keepalive = PROBE_MQTT_KEEPALIVE_S,
            .last_will = {
                .topic = s_topic_status,
                .msg   = lwt,
                .msg_len = 0,
                .qos   = PROBE_MQTT_QOS,
                .retain = 1,
            },
        },
        .network = {
            .reconnect_timeout_ms = PROBE_MQTT_RECONNECT_MS,
            .timeout_ms = PROBE_MQTT_NET_TIMEOUT_MS,
        },
        .buffer = { .size = PROBE_MQTT_BUFFER_SIZE, .out_size = PROBE_MQTT_BUFFER_SIZE },
    };

    /* Trust anchor: the built-in CA bundle.  Without this the TLS handshake to
     * a public broker fails with a certificate-verify error.  Set after the
     * initialiser so the intent is explicit. */
    cfg.broker.verification.crt_bundle_attach = esp_crt_bundle_attach;

    s_mqtt = esp_mqtt_client_init(&cfg);
    if (!s_mqtt) {
        ESP_LOGE(TAG_MQTT, "esp_mqtt_client_init failed");
        return ESP_FAIL;
    }
    esp_err_t err = esp_mqtt_client_register_event(s_mqtt, ESP_EVENT_ANY_ID,
                                                   mqtt_event_handler, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG_MQTT, "register_event failed: %s", esp_err_to_name(err));
        return err;
    }
    err = esp_mqtt_client_start(s_mqtt);
    if (err != ESP_OK) {
        ESP_LOGE(TAG_MQTT, "client_start failed: %s", esp_err_to_name(err));
        return err;
    }
    ESP_LOGI(TAG_MQTT, "started: %s -> %s", s_cfg.mqtt_uri, s_topic_meas);
    return ESP_OK;
}

/* =========================================================================
 * Payload assembly and publish
 * ========================================================================= */

static esp_err_t publish_measurement(const probe_result_t *r, const char *grade,
                                     float confidence)
{
    if (!s_mqtt || !s_mqtt_connected) {
        ESP_LOGE(TAG_MQTT, "measurement %" PRIu32 " not published: MQTT down",
                 r->seq);
        return ESP_ERR_INVALID_STATE;
    }

    int rssi = 0;
    wifi_ap_record_t ap;
    if (esp_wifi_sta_get_ap_info(&ap) == ESP_OK) {
        rssi = ap.rssi;
    }

    char ts_buf[24];
    if (s_time_synced) {
        snprintf(ts_buf, sizeof(ts_buf), "%" PRId64, (int64_t)time(NULL));
    } else {
        /* Honest sentinel: 0 means "the device clock was not set". Do not
         * substitute an uptime in seconds, which would look like a real epoch. */
        snprintf(ts_buf, sizeof(ts_buf), "0");
        ESP_LOGW(TAG_MQTT, "publishing with ts=0: no time sync yet");
    }

    char payload[768];
    int n = snprintf(payload, sizeof(payload),
        "{\"ts\":%s,\"dev\":\"%s\",\"seq\":%" PRIu32 ",\"grade\":\"%s\","
        "\"confidence\":%.2f,"
        "\"f_peak_hz\":%.1f,\"f_centroid_hz\":%.1f,\"band_ratio_lh\":%.3f,"
        "\"decay_tau_ms\":%.1f,"
        "\"peak_au\":%.3f,\"rms_au\":%.4f,\"crest_factor\":%.2f,\"kurtosis\":%.2f,"
        "\"impact_peak_g\":%.2f,\"impulse_norm\":%.3f,"
        "\"sp\":%s,\"fw\":\"%s\",\"rssi\":%d,\"strikes_total\":%" PRIu32 ","
        "\"contact_ok\":%s,\"event_flag\":\"%s\"}",
        ts_buf, s_cfg.dev_id, r->seq, grade, confidence,
        r->feat.f_peak_hz, r->feat.f_centroid_hz, r->feat.band_ratio_lh,
        r->feat.decay_tau_ms,
        r->feat.peak_au, r->feat.rms_au, r->feat.crest_factor, r->feat.kurtosis,
        r->aux.impact_peak_g, r->aux.impulse_norm,
        r->simulated ? "true" : "false", PROBE_FW_VERSION, rssi,
        (uint32_t)s_strikes_total,
        r->contact_ok ? "true" : "false", r->event_flag);

    if (n <= 0 || n >= (int)sizeof(payload)) {
        ESP_LOGE(TAG_MQTT, "payload truncated (%d bytes); increase "
                           "PROBE_MQTT_BUFFER_SIZE", n);
        return ESP_ERR_INVALID_SIZE;
    }

    int msg_id = esp_mqtt_client_publish(s_mqtt, s_topic_meas, payload, n,
                                         PROBE_MQTT_QOS, 0);
    if (msg_id < 0) {
        ESP_LOGE(TAG_MQTT, "publish failed");
        return ESP_FAIL;
    }
    ESP_LOGI(TAG_MQTT, "published seq=%" PRIu32 " %s conf=%.2f (msg %d)%s",
             r->seq, grade, confidence, msg_id, r->simulated ? " [SIMULATED]" : "");
    return ESP_OK;
}

/* =========================================================================
 * Measurement task
 * ========================================================================= */

static QueueHandle_t s_meas_q = NULL;

/* Context handed to the capture helper task.  Kept at file scope (not a local
 * struct) so that the helper can be a plain static function -- ESP-IDF and C99
 * have no lambdas. */
typedef struct {
    volatile bool      done;
    volatile esp_err_t err;
} capture_ctx_t;

static capture_ctx_t s_cap_ctx = { .done = true, .err = ESP_OK };

/* Short-lived helper: issue the single bounded I2S read and hand control back.
 * The measurement task cannot do this inline, because it has to fire the strike
 * while the DMA read is already blocked waiting for samples. */
static void capture_helper_task(void *arg)
{
    capture_ctx_t *c = (capture_ctx_t *)arg;
    c->err = mic_capture();
    c->done = true;
    vTaskDelete(NULL);
}

/* Forward declaration: used by measurement_task before its definition. */
static void feed_task_watchdog(void);

/* Run one complete measurement.  Bounded work only: every wait has a timeout
 * and every loop is bounded, so the task-based watchdog can always collect. */
static void do_measurement(probe_result_t *r)
{
    memset(r, 0, sizeof(*r));
    r->contact_ok = true;

    xSemaphoreTake(s_state_lock, portMAX_DELAY);
    r->seq = ++s_strikes_total;
    s_strikes_pending_nvs++;
    xSemaphoreGive(s_state_lock);

    r->simulated = s_simulation;

    /* 1. Thermal interlock.  If the budget refuses the strike we do NOT
     *    manufacture a result; we report the refusal and skip the measurement
     *    entirely, so no fake row reaches the dashboard. */
    sol_verdict_t verdict = SOL_OK;

    /* 2. Drain the DMA so the capture window really starts at the strike. */
    mic_drain();

    /* 3. Kick off the reader before the strike, so the I2S peripheral is already
     *    streaming when the impact arrives and no samples are lost to task
     *    start-up latency. */
    s_cap_ctx.done = false;
    s_cap_ctx.err  = ESP_OK;

    TaskHandle_t reader = NULL;
    BaseType_t created = xTaskCreatePinnedToCore(capture_helper_task, "probe_rx", 4096,
                                                 &s_cap_ctx, PROBE_TASK_MEAS_PRIO - 1,
                                                 &reader, 1);
    if (created != pdPASS) {
        ESP_LOGE(TAG_MAIN, "cannot create capture helper task; measurement skipped");
        strlcpy(r->event_flag, "no_task", sizeof(r->event_flag));
        return;
    }

    /* Give the reader a moment to get into its blocking read.
     *
     * This IS the strike lead PROBE_STRIKE_LEAD_US describes, and it must be a
     * real delay, not a round-down to zero: the reader runs at a LOWER priority
     * than this task, so a zero-tick delay never yields and the reader may not
     * be inside i2s_channel_read() when the solenoid fires.  The tick-rate
     * guard below makes that a build error rather than a silent one. */
    vTaskDelay(pdMS_TO_TICKS(PROBE_STRIKE_LEAD_US / 1000));

    /* 4. Strike.  sol_strike() returns once the pulse has been de-asserted, so
     *    the auxiliary accelerometer window opens about PROBE_STRIKE_PULSE_MS
     *    after the energising edge.  The 60 ms window therefore still covers the
     *    mechanical impact and the operator's reaction to it in full; the few
     *    milliseconds of coil-energising transient are discarded inside
     *    accel_capture() by PROBE_ACCEL_SETTLE_MS. */
    esp_err_t serr = sol_strike(PROBE_STRIKE_PULSE_MS, &verdict);
    if (serr != ESP_OK) {
        /* Wait for the reader to time out, so the I2S channel is idle again. */
        int64_t t0 = esp_timer_get_time();
        while (!s_cap_ctx.done && (esp_timer_get_time() - t0) < 500000) {
            vTaskDelay(pdMS_TO_TICKS(5));
        }
        snprintf(r->event_flag, sizeof(r->event_flag), "strike_%s",
                 sol_verdict_str(verdict));
        s_strikes_refused++;
        ESP_LOGE(TAG_MAIN, "measurement aborted: strike refused (%s)",
                 sol_verdict_str(verdict));

        /* Budget refusals are worth telling the fleet about. */
        if (verdict == SOL_DUTY_EXCEEDED || verdict == SOL_IN_COOLDOWN) {
            mqtt_publish_event(verdict == SOL_DUTY_EXCEEDED ? "thermal_trip"
                                                            : "thermal_cooldown",
                               sol_verdict_str(verdict));
        }
        return;
    }

    /* 5. Auxiliary contact-quality channel, sampled around the strike. */
    accel_capture(&r->aux);

    /* 6. Wait for the capture, bounded.
     *
     * In SIMULATION mode the features do not come from the microphone at all,
     * so a missing or unwired mic must NOT abort the measurement -- the entire
     * point of the mode is to exercise the MQTT and dashboard paths before the
     * transducer chain exists (README A.9).  The wait is still performed, so
     * the real system's timing is what gets demonstrated, and the strike
     * interlock above still applies.  The failure is recorded in the event flag
     * rather than swallowed. */
    int64_t t0 = esp_timer_get_time();
    while (!s_cap_ctx.done && (esp_timer_get_time() - t0) <
                          (int64_t)PROBE_CAPTURE_TIMEOUT_MS * 1000 + 200000) {
        vTaskDelay(pdMS_TO_TICKS(5));
    }
    bool capture_ok = s_cap_ctx.done && (s_cap_ctx.err == ESP_OK);
    if (!r->simulated) {
        if (!s_cap_ctx.done) {
            ESP_LOGE(TAG_MAIN, "capture reader did not finish in time");
            strlcpy(r->event_flag, "capture_timeout", sizeof(r->event_flag));
            mqtt_publish_event("capture_timeout", "i2s read did not complete");
            return;
        }
        if (s_cap_ctx.err != ESP_OK) {
            strlcpy(r->event_flag, "capture_fail", sizeof(r->event_flag));
            ESP_LOGE(TAG_MAIN, "capture failed: %s", esp_err_to_name(s_cap_ctx.err));
            mqtt_publish_event("capture_fail", esp_err_to_name(s_cap_ctx.err));
            return;
        }
    } else if (!capture_ok) {
        strlcpy(r->event_flag, "capture_fail_sim", sizeof(r->event_flag));
        ESP_LOGW(TAG_MAIN, "SIMULATION: capture unusable (%s); features are "
                           "synthesised anyway",
                 s_cap_ctx.done ? esp_err_to_name(s_cap_ctx.err) : "timeout");
    }

    /* 7. Features. */
    if (r->simulated) {
        sim_features(&r->feat, &r->aux);
    } else {
        dsp_transform();
        dsp_spectral_features(&r->feat);
        r->feat.decay_tau_ms = dsp_decay_tau();
    }

    /* Contact-quality verdict from the AUXILIARY channel only. */
    if (r->aux.valid) {
        bool ok = (r->aux.impact_peak_g >= PROBE_CONTACT_MIN_G) &&
                  (r->aux.impact_peak_g <= PROBE_CONTACT_MAX_G) &&
                  (r->aux.impulse_norm  >= PROBE_CONTACT_MIN_IMPULSE);
        r->contact_ok = ok;
        if (!ok && r->event_flag[0] == '\0') {
            if (r->aux.impact_peak_g < PROBE_CONTACT_MIN_G) {
                strlcpy(r->event_flag, "weak_contact", sizeof(r->event_flag));
            } else if (r->aux.impact_peak_g > PROBE_CONTACT_MAX_G) {
                strlcpy(r->event_flag, "hard_contact", sizeof(r->event_flag));
            } else {
                strlcpy(r->event_flag, "poor_contact", sizeof(r->event_flag));
            }
        }
    } else if (r->event_flag[0] == '\0') {
        strlcpy(r->event_flag, "accel_unavailable", sizeof(r->event_flag));
    }

    /* 8. Grade. */
    float confidence = 0.0f;
    const char *grade = classify(&r->feat, &confidence);

    /* 9. Publish.  Deliberately after the capture window has closed. */
    publish_measurement(r, grade, confidence);

    ESP_LOGI(TAG_MAIN, "seq=%" PRIu32 " %s conf=%.2f fpk=%.0f Hz br=%.2f "
                       "tau=%.1f ms g=%.2f%s",
             r->seq, grade, confidence, r->feat.f_peak_hz, r->feat.band_ratio_lh,
             r->feat.decay_tau_ms, r->aux.impact_peak_g,
             r->simulated ? "  [SIMULATED DATA]" : "");

    /* Persist the lifetime counter only occasionally, to spare the flash. */
    if (s_strikes_pending_nvs >= PROBE_STRIKES_NVS_SAVE_EVERY) {
        s_strikes_pending_nvs = 0;
        nvs_save_strikes();
    }
}

static void measurement_task(void *arg)
{
    (void)arg;
    probe_result_t r;
    uint8_t slot;

    for (;;) {
        if (xQueueReceive(s_meas_q, &slot, pdMS_TO_TICKS(200)) == pdTRUE) {
            do_measurement(&r);
            xSemaphoreTake(s_state_lock, portMAX_DELAY);
            s_result = r;
            xSemaphoreGive(s_state_lock);
        }

        /* Supervised reconnect: if the broker link is down, try again on a slow
         * cadence.  esp-mqtt also reconnects internally; this is the belt-and-
         * braces path for "gave up" states and for the case where IP was lost.
         *
         * This is ALSO what recovers a probe that booted with no WiFi.  In that
         * case mqtt_start() was never reached and s_mqtt is NULL, so the old
         * `if (s_mqtt)` guard made this loop a permanent no-op and the probe
         * stayed silent forever even after the AP came back -- while the boot
         * log promised "publishing resumes on reconnect".  Now the link is
         * brought up here as soon as an IP is held. */
        if (!s_mqtt_connected) {
            static int64_t next_try = 0;
            int64_t now = esp_timer_get_time();
            if (now >= next_try) {
                next_try = now + (int64_t)PROBE_MQTT_RECONNECT_MS * 1000 * 4;
                if (s_mqtt) {
                    ESP_LOGW(TAG_MQTT, "supervised reconnect attempt");
                    esp_mqtt_client_reconnect(s_mqtt);
                } else if (s_wifi_eg &&
                           (xEventGroupGetBits(s_wifi_eg) & WIFI_BIT_CONNECTED)) {
                    ESP_LOGW(TAG_MQTT, "no MQTT client yet (booted without WiFi?); "
                                       "starting one now");
                    time_sync();          /* cheap no-op if the clock is already set */
                    if (mqtt_start() != ESP_OK) {
                        ESP_LOGE(TAG_MQTT, "MQTT start failed on the supervised path");
                    }
                }
            }
        }

        /* Periodic retained status heartbeat. */
        if (s_mqtt_connected) {
            int64_t now = esp_timer_get_time();
            if (now >= s_next_status_us) {
                s_next_status_us = now + (int64_t)PROBE_STATUS_PERIOD_MS * 1000;
                mqtt_publish_status("online", s_simulation ? "SIMULATION MODE" : NULL);
            }
        }

        feed_task_watchdog();
    }
}

/* Trivial watchdog feed hook.  With CONFIG_ESP_TASK_WDT_USE_ESP_TIMER the task
 * watchdog is fed by the idle tasks; this function exists so that if the project
 * later switches to an explicit subscription this task can call
 * esp_task_wdt_reset() without restructuring anything. */
static void feed_task_watchdog(void)
{
    /* Intentionally empty in the default configuration.  See README, "watchdog
     * resets". */
}

/* =========================================================================
 * UART console -- `measure`, `calibrate`, `set th`, `dump`, `reboot`,
 *                 `status`, `provision`
 * ========================================================================= */

static int console_split(char *line, char *argv[], int max_args)
{
    int argc = 0;
    char *p = line;
    while (*p && argc < max_args) {
        while (*p == ' ' || *p == '\t') p++;
        if (*p == '\0') break;
        argv[argc++] = p;
        while (*p && *p != ' ' && *p != '\t') p++;
        if (*p) *p++ = '\0';
    }
    return argc;
}

static void console_usage(void)
{
    printf("\nTap-test probe console commands:\n"
           "  measure                              take one measurement\n"
           "  calibrate                            guidance for reference panels\n"
           "  set th <band_ratio> <fpeak_hz>       set the G2 thresholds and save\n"
           "  dump                                 print the last result as JSON\n"
           "  reboot                               restart the probe\n"
           "  status                               show config, heap, link state\n"
           "  provision <ssid> <pass> <mqtt_uri> <user> <pass> <clientid>\n"
           "  help\n\n");
}

static void console_status(void)
{
    printf("\ndev_id        : %s\n", s_cfg.dev_id);
    printf("fw / hw       : %s / %s\n", PROBE_FW_VERSION, PROBE_HW_REV);
    printf("ssid          : %s\n", s_cfg.wifi_ssid[0] ? s_cfg.wifi_ssid : "(none)");
    printf("mqtt uri      : %s\n", s_cfg.mqtt_uri[0] ? s_cfg.mqtt_uri : "(none)");
    printf("mqtt state    : %s\n", s_mqtt_connected ? "connected" : "down");
    printf("time synced   : %s\n", s_time_synced ? "yes" : "NO (ts will be 0)");
    printf("mic           : %s\n", s_mic_ok ? "ok" : "FAILED");
    printf("accel         : %s (auxiliary)\n", s_accel_ok ? "ok" : "FAILED");
    printf("simulation    : %s\n", s_simulation ? "ON -- DATA IS SYNTHETIC" : "off");
    printf("thresholds    : G2 r<=%.3f f>=%.0f Hz | G0 r>=%.3f f<=%.0f Hz\n",
           s_cfg.th_ratio_g2, s_cfg.th_fpeak_g2, s_cfg.th_ratio_g0, s_cfg.th_fpeak_g0);
    printf("strikes total : %" PRIu32 "  (refused by interlock: %" PRIu32 ")\n",
           (uint32_t)s_strikes_total, (uint32_t)s_strikes_refused);
    printf("heap free     : %" PRIu32 " bytes\n", (uint32_t)esp_get_free_heap_size());
    printf("uptime        : %" PRId64 " s\n", (esp_timer_get_time() - s_start_us) / 1000000);
    printf("\n");
}

static void console_dump(void)
{
    probe_result_t r;
    xSemaphoreTake(s_state_lock, portMAX_DELAY);
    r = s_result;
    xSemaphoreGive(s_state_lock);

    if (r.seq == 0) {
        printf("no measurement taken yet\n");
        return;
    }
    float confidence = 0.0f;
    const char *grade = classify(&r.feat, &confidence);
    printf("{\"seq\":%" PRIu32 ",\"grade\":\"%s\",\"confidence\":%.2f,"
           "\"f_peak_hz\":%.1f,\"f_centroid_hz\":%.1f,\"band_ratio_lh\":%.3f,"
           "\"decay_tau_ms\":%.1f,\"peak_au\":%.3f,\"rms_au\":%.4f,"
           "\"crest_factor\":%.2f,\"kurtosis\":%.2f,\"impact_peak_g\":%.2f,"
           "\"impulse_norm\":%.3f,\"sp\":%s,\"contact_ok\":%s,"
           "\"event_flag\":\"%s\"}\n",
           r.seq, grade, confidence,
           r.feat.f_peak_hz, r.feat.f_centroid_hz, r.feat.band_ratio_lh,
           r.feat.decay_tau_ms, r.feat.peak_au, r.feat.rms_au,
           r.feat.crest_factor, r.feat.kurtosis, r.aux.impact_peak_g,
           r.aux.impulse_norm, r.simulated ? "true" : "false",
           r.contact_ok ? "true" : "false", r.event_flag);
}

static void console_calibrate(void)
{
    printf("\nCalibration procedure (see the README for the full SOP).\n"
           "You need two reference panels of the SAME finish on the SAME\n"
           "substrate: one known-good (fully bonded) and one known-debonded\n"
           "(deliberately built with a void).\n\n"
           "  1. Take at least 10 measurements on the good panel, spread over\n"
           "     the surface, minimum interval respected.\n"
           "  2. Repeat on the debonded panel.\n"
           "  3. `dump` each result and record band_ratio_lh and f_peak_hz.\n"
           "  4. The two populations separate in OPPOSITE directions:\n"
           "       the GOOD panel has the HIGH band_ratio_lh (~0.8)\n"
           "       the DEBONDED panel has the LOW  band_ratio_lh (~0.03-0.2)\n"
           "     because a debond's plate mode enters the 1..15 kHz band and\n"
           "     pushes energy ABOVE the 1 kHz crossover.\n"
           "     Set the cut between them:\n"
           "       set th <band_ratio> <fpeak_hz>\n"
           "     with band_ratio just ABOVE the debonded ceiling (i.e. below\n"
           "     the good panel's floor) and fpeak_hz at the band floor, 300 Hz.\n"
           "     The fpeak condition is >=, and 300 Hz is satisfied by any\n"
           "     in-band peak, so it acts as a floor check rather than a veto.\n"
           "  5. Re-run both panels. Count the misclassifications and quote\n"
           "     them in the report. If the two populations overlap, the\n"
           "     honest answer is that the two-condition rule cannot separate\n"
           "     them on this sample set.\n\n"
           "A debond larger than about 34 cm reads as BONDED again, because its\n"
           "mode falls below the 1 kHz crossover. This rule is a size window,\n"
           "not a severity scale. See probe_config.h.\n\n"
           "The accelerometer is NOT used in calibration. It only tells you\n"
           "whether the operator's contact was consistent between panels.\n\n");
}

static void console_task(void *arg)
{
    (void)arg;
    char line[256];
    char *argv[10];
    int pos = 0;

    console_usage();
    for (;;) {
        int c = fgetc(stdin);
        if (c == EOF) {
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }
        if (c == '\r' || c == '\n') {
            if (pos == 0) continue;
            line[pos] = '\0';
            pos = 0;
            printf("\n");

            int argc = console_split(line, argv, 10);
            if (argc == 0) continue;

            if (strcmp(argv[0], "measure") == 0) {
                uint8_t slot = 0;
                if (xQueueSend(s_meas_q, &slot, pdMS_TO_TICKS(100)) != pdTRUE) {
                    ESP_LOGE(TAG_CON, "measurement queue full");
                    printf("busy, try again\n");
                } else {
                    printf("measurement queued\n");
                }
            } else if (strcmp(argv[0], "calibrate") == 0) {
                console_calibrate();
            } else if (strcmp(argv[0], "set") == 0 && argc >= 4 && strcmp(argv[1], "th") == 0) {
                float ratio = strtof(argv[2], NULL);
                float fpk   = strtof(argv[3], NULL);
                if (ratio <= 0.0f || ratio > 20.0f || fpk < 100.0f || fpk > 20000.0f) {
                    ESP_LOGE(TAG_CON, "thresholds out of sane range (ratio 0..20, fpeak 100..20000 Hz)");
                    printf("rejected: ratio 0..20, fpeak 100..20000 Hz\n");
                } else {
                    xSemaphoreTake(s_cfg_lock, portMAX_DELAY);
                    s_cfg.th_ratio_g2 = ratio;
                    s_cfg.th_fpeak_g2 = fpk;
                    xSemaphoreGive(s_cfg_lock);
                    nvs_save_thresholds();
                    printf("G2 thresholds set: band_ratio<=%.3f, f_peak>=%.0f Hz (saved)\n",
                           ratio, fpk);
                    mqtt_publish_event("threshold_change", "console set th");
                }
            } else if (strcmp(argv[0], "dump") == 0) {
                console_dump();
            } else if (strcmp(argv[0], "reboot") == 0) {
                printf("rebooting...\n");
                vTaskDelay(pdMS_TO_TICKS(200));
                esp_restart();
            } else if (strcmp(argv[0], "status") == 0) {
                console_status();
            } else if (strcmp(argv[0], "provision") == 0) {
                if (argc < 7) {
                    printf("usage: provision <ssid> <pass> <mqtt_uri> <user> <pass> <clientid>\n"
                           "note: the device id is unchanged; set it with menuconfig or "
                           "reflash for a different id.\n");
                } else {
                    xSemaphoreTake(s_cfg_lock, portMAX_DELAY);
                    strlcpy(s_cfg.wifi_ssid, argv[1], sizeof(s_cfg.wifi_ssid));
                    strlcpy(s_cfg.wifi_pass, argv[2], sizeof(s_cfg.wifi_pass));
                    strlcpy(s_cfg.mqtt_uri, argv[3], sizeof(s_cfg.mqtt_uri));
                    strlcpy(s_cfg.mqtt_user, argv[4], sizeof(s_cfg.mqtt_user));
                    strlcpy(s_cfg.mqtt_pass, argv[5], sizeof(s_cfg.mqtt_pass));
                    strlcpy(s_cfg.mqtt_clientid, argv[6], sizeof(s_cfg.mqtt_clientid));
                    xSemaphoreGive(s_cfg_lock);
                    esp_err_t err = nvs_save_provision(argv[1], argv[2], argv[3],
                                                       argv[4], argv[5], argv[6],
                                                       s_cfg.dev_id);
                    if (err == ESP_OK) {
                        printf("provisioned. `reboot` to apply.\n");
                    } else {
                        printf("provisioning FAILED: %s\n", esp_err_to_name(err));
                    }
                }
            } else if (strcmp(argv[0], "help") == 0) {
                console_usage();
            } else {
                printf("unknown command '%s'\n", argv[0]);
                console_usage();
            }
            continue;
        }
        if (c == 0x08 || c == 0x7F) {   /* backspace */
            if (pos > 0) {
                pos--;
                printf("\b \b");
            }
            continue;
        }
        if (pos < (int)sizeof(line) - 1) {
            line[pos++] = (char)c;
            printf("%c", c);
        }
    }
}

/* =========================================================================
 * app_main
 * ========================================================================= */

void app_main(void)
{
    s_start_us = esp_timer_get_time();

    /* --- NVS --------------------------------------------------------- */
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    s_cfg_lock   = xSemaphoreCreateMutex();
    s_state_lock = xSemaphoreCreateMutex();
    s_sol_lock   = xSemaphoreCreateMutex();
    configASSERT(s_cfg_lock && s_state_lock && s_sol_lock);

    nvs_load();

#if PROBE_CFG_SIMULATION_DEFAULT
    s_simulation = true;
#endif

    /* Loud, unmissable boot warning.  Simulated data must never be mistaken for
     * a measurement. */
    if (s_simulation) {
        ESP_LOGW(TAG_MAIN, "");
        ESP_LOGW(TAG_MAIN, "##############################################################");
        ESP_LOGW(TAG_MAIN, "#  SIMULATION MODE IS ACTIVE                                 #");
        ESP_LOGW(TAG_MAIN, "#  The feature numbers this device publishes are SYNTHESISED #");
        ESP_LOGW(TAG_MAIN, "#  and are NOT measurements. Every payload carries \"sp\":true #");
        ESP_LOGW(TAG_MAIN, "#  This mode exists to demonstrate the MQTT and dashboard path #");
        ESP_LOGW(TAG_MAIN, "#  before the transducer chain is finished.                    #");
        ESP_LOGW(TAG_MAIN, "##############################################################");
        ESP_LOGW(TAG_MAIN, "");
    }

    ESP_LOGI(TAG_MAIN, "tap-test probe %s, fw %s, hw %s",
             s_cfg.dev_id, PROBE_FW_VERSION, PROBE_HW_REV);

    /* --- Pin / peripheral init --------------------------------------- */
    sol_gpio_init();

    /* LED for a coarse heartbeat. */
    gpio_config_t led = {
        .pin_bit_mask = (1ULL << PROBE_PIN_STATUS_LED),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&led);

    /* --- DSP tables -------------------------------------------------- */
    dsp_make_hann();
    dsp_make_bitrev();

    /* --- Sensor init.  Neither failure is fatal. ---------------------- */
    if (mic_init() != ESP_OK) {
        ESP_LOGE(TAG_MAIN, "MICROPHONE INIT FAILED -- measurements are not possible. "
                           "Check wiring, the WS/BCLK frequency and the supply.");
        /* Reported on the event topic below, once MQTT is up. */
    }
    if (accel_init() != ESP_OK) {
        ESP_LOGE(TAG_ACC, "ACCELEROMETER INIT FAILED -- contact-quality reporting "
                          "will be absent. This does NOT stop detection, because the "
                          "accelerometer is not the detection channel.");
    }

    /* --- Network ------------------------------------------------------ */
    if (wifi_start() == ESP_OK) {
        time_sync();     /* may fail; timestamps then publish as 0 */
        if (mqtt_start() != ESP_OK) {
            ESP_LOGE(TAG_MQTT, "MQTT start failed; measurements will still be taken "
                               "and logged locally");
        } else {
            vTaskDelay(pdMS_TO_TICKS(1500));
            if (!s_mic_ok) {
                mqtt_publish_event("mic_init_failed", "I2S microphone not available");
            }
            if (!s_accel_ok) {
                mqtt_publish_event("accel_init_failed", "auxiliary accelerometer not available");
            }
        }
    } else {
        ESP_LOGE(TAG_WIFI, "WiFi unavailable at boot; running offline. Measurements are "
                           "still taken and logged, and publishing resumes on reconnect.");
    }

    /* --- Tasks -------------------------------------------------------- */
    s_meas_q = xQueueCreate(PROBE_MEAS_QUEUE_LEN, sizeof(uint8_t));
    configASSERT(s_meas_q);

    xTaskCreatePinnedToCore(measurement_task, "probe_meas", PROBE_TASK_MEAS_STACK,
                            NULL, PROBE_TASK_MEAS_PRIO, NULL, 1);

#if PROBE_ENABLE_CONSOLE
    xTaskCreatePinnedToCore(console_task, "probe_console", PROBE_TASK_CONSOLE_STACK,
                            NULL, PROBE_TASK_CONSOLE_PRIO, NULL, 0);
#endif

    /* --- Trigger button poll ------------------------------------------ */
    gpio_config_t btn = {
        .pin_bit_mask = (1ULL << PROBE_PIN_TRIGGER),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,     /* active low */
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,       /* polled: no ISR debounce needed */
    };
    gpio_config(&btn);

    ESP_LOGI(TAG_MAIN, "ready. Type 'help' on the console, or press the trigger button.");

    /* Main loop: button polling, LED heartbeat, strike-counter persistence.
     * Every wait in here is bounded and every iteration yields, so this task is
     * watchdog-friendly. */
    int64_t last_led = 0;
    bool led_state = false;
    bool btn_prev = false;
    int64_t btn_last_press = 0;

    for (;;) {
        int64_t now = esp_timer_get_time();

        /* Heartbeat: slow blink when idle, fast when a measurement is due and
         * the minimum interval has not yet elapsed (operator feedback). */
        int64_t interval = 500;
        if ((now - s_thermal.last_strike_us) < (int64_t)PROBE_MIN_STRIKE_INTERVAL_MS * 1000 &&
            s_thermal.last_strike_us != 0) {
            interval = 100;
        }
        if ((now - last_led) > interval * 1000) {
            last_led = now;
            led_state = !led_state;
            gpio_set_level(PROBE_PIN_STATUS_LED, led_state ? 1 : 0);
        }

        bool btn = (gpio_get_level(PROBE_PIN_TRIGGER) == 0);
        if (btn && !btn_prev && (now - btn_last_press) > 200000) {
            btn_last_press = now;
            uint8_t slot = 0;
            if (xQueueSend(s_meas_q, &slot, 0) != pdTRUE) {
                ESP_LOGW(TAG_MAIN, "trigger ignored: measurement queue full");
            }
        }
        btn_prev = btn;

        /* Persist the strike counter on a slow cadence even when idle. */
        static int64_t last_save = 0;
        if (s_strikes_pending_nvs > 0 && (now - last_save) > 30000000) {
            last_save = now;
            s_strikes_pending_nvs = 0;
            nvs_save_strikes();
        }

        vTaskDelay(pdMS_TO_TICKS(10));
    }
}
