/*
 * hardware_bringup.c -- ESP32-S3 wiring smoke test.
 *
 * This temporary application is intentionally small. It validates the
 * currently connected devices before the measurement application is ported:
 * one LSM6DS3, one VL53L1X, two ST7735-class SPI TFTs and one joystick.
 */

#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <math.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "driver/spi_master.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_rom_sys.h"
#include "driver/rmt_tx.h"
#include "driver/rmt_encoder.h"
#include "vl53l1x.h"
/* ---- demo additions: network + menu ---- */
#include <stdbool.h>
 #include <stdlib.h>
 #include "freertos/event_groups.h"
 #include "esp_wifi.h"
 #include "esp_netif.h"
 #include "nvs_flash.h"
 #include "mqtt_client.h"
 #include "esp_timer.h"

#include "probe_config.h"
#include "probe_menu.h"
#include "probe_font.h"

static const char *TAG = "BRINGUP";
static i2c_master_bus_handle_t s_i2c;
static i2c_master_dev_handle_t s_imu;
static spi_device_handle_t s_imu_spi;
static bool s_imu_spi_mode;
static int  s_imu_dummy;           /* SPI: dummy bytes between address and data */
static bool s_use_fifo;
static int  s_fifo_mode_code = -1; /* FIFO_MODE this die accepts, -1 = no FIFO  */
static int  s_fifo_odr_code;
static vl53l1x_t s_tof;
static spi_device_handle_t s_tft1;
static spi_device_handle_t s_tft2;
static adc_oneshot_unit_handle_t s_adc1;
static adc_oneshot_unit_handle_t s_adc2;
static adc_unit_t s_joy_x_unit;
static adc_unit_t s_joy_y_unit;
static adc_channel_t s_joy_x_ch;
static adc_channel_t s_joy_y_ch;
static bool s_joy_x_ready;
static bool s_joy_y_ready;
static bool s_tof_ready;
static float s_accel_history[3][128];
static float s_accel_baseline[3];
static float s_distance_history[128];
static size_t s_wave_index;
static uint16_t s_last_distance_mm;
static bool s_last_distance_valid;
static uint8_t s_tft1_frame[128 * 160 * 2];
static uint8_t s_tft2_frame[128 * 160 * 2];
static uint32_t s_joy_muted;   /* stick moves discarded during a tap ring-down */
static int64_t  s_pump_worst_us;  /* worst publish stall seen, per heartbeat */


static rmt_channel_handle_t s_rgb_channel;
static rmt_encoder_handle_t s_rgb_encoder;

static esp_err_t onboard_rgb_set_green(void)
{
    rmt_tx_channel_config_t channel_cfg = {
        .gpio_num = PROBE_PIN_ONBOARD_RGB,
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = 10000000,
        .mem_block_symbols = 64,
        .trans_queue_depth = 1,
    };
    esp_err_t err = rmt_new_tx_channel(&channel_cfg, &s_rgb_channel);
    if (err != ESP_OK) return err;

    rmt_bytes_encoder_config_t encoder_cfg = {
        .bit0 = {.duration0 = 4, .level0 = 1, .duration1 = 9, .level1 = 0},
        .bit1 = {.duration0 = 8, .level0 = 1, .duration1 = 5, .level1 = 0},
        .flags.msb_first = 1,
    };
    err = rmt_new_bytes_encoder(&encoder_cfg, &s_rgb_encoder);
    if (err != ESP_OK) return err;
    err = rmt_enable(s_rgb_channel);
    if (err != ESP_OK) return err;

    /* WS2812 order is GRB. Keep the green channel at 2/255. */
    const uint8_t grb[3] = {2, 0, 0};
    const rmt_transmit_config_t tx_cfg = {.loop_count = 0};
    err = rmt_transmit(s_rgb_channel, s_rgb_encoder, grb, sizeof(grb), &tx_cfg);
    if (err == ESP_OK) err = rmt_tx_wait_all_done(s_rgb_channel, 100);
    return err;
}

static esp_err_t i2c_write8(i2c_master_dev_handle_t dev, uint8_t reg, uint8_t val)
{
    uint8_t data[2] = {reg, val};
    return i2c_master_transmit(dev, data, sizeof(data), 100);
}

static esp_err_t i2c_read(i2c_master_dev_handle_t dev, uint8_t reg,
                          uint8_t *data, size_t len)
{
    /*
     * Some LSM6DS3 breakout boards NACK the repeated-start transaction used
     * by i2c_master_transmit_receive() for output registers.  Use the
     * controller's two explicit transactions instead.
     */
    esp_err_t err = i2c_master_transmit(dev, &reg, 1, 100);
    if (err != ESP_OK) return err;
    return i2c_master_receive(dev, data, len, 100);
}

static esp_err_t i2c_probe(uint8_t address)
{
    i2c_device_config_t cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = address,
        .scl_speed_hz = PROBE_I2C_FREQ_HZ,
    };
    i2c_master_dev_handle_t dev;
    esp_err_t err = i2c_master_bus_add_device(s_i2c, &cfg, &dev);
    if (err == ESP_OK) {
        err = i2c_master_probe(s_i2c, address, 50);
        i2c_master_bus_rm_device(dev);
    }
    return err;
}

static void i2c_scan(void)
{
    printf("I2C scan:");
    for (uint8_t address = 1; address < 0x78; address++) {
        if (i2c_probe(address) == ESP_OK) {
            printf(" 0x%02X", address);
        }
    }
    printf("\n");
}

/* =======================================================================
 * Accelerometer transport.
 *
 * The part is read over SPI because the I2C bus cannot carry 6.66 kHz (see
 * the note in probe_config.h).  I2C stays as a fallback so that a board which
 * has not been rewired yet still runs the rest of the stack.
 * ===================================================================== */

/* One FIFO drain is PROBE_FIFO_BATCH_MAX samples, so the transfer buffers
 * have to be that large; a fixed 16-byte stack buffer silently rejected every
 * drain of more than ten samples.  These are shared because the accelerometer
 * is only ever touched from the capture task after init has finished. */
static uint8_t s_imu_tx[PROBE_FIFO_BATCH_MAX * 6 + 4];
static uint8_t s_imu_rx[PROBE_FIFO_BATCH_MAX * 6 + 4];

static esp_err_t imu_read(uint8_t reg, uint8_t *data, size_t len)
{
    if (!s_imu_spi_mode) return i2c_read(s_imu, reg, data, len);

    const size_t total = (size_t)(1 + s_imu_dummy) + len;
    if (total > sizeof(s_imu_tx)) return ESP_ERR_INVALID_SIZE;
    memset(s_imu_tx, 0, total);
    memset(s_imu_rx, 0, total);
    s_imu_tx[0] = (uint8_t)(reg | 0x80);
    spi_transaction_t t = {
        .length = total * 8u,
        .tx_buffer = s_imu_tx,
        .rx_buffer = s_imu_rx,
    };
    esp_err_t err = spi_device_polling_transmit(s_imu_spi, &t);
    if (err != ESP_OK) return err;
    memcpy(data, &s_imu_rx[1 + s_imu_dummy], len);
    return ESP_OK;
}

static esp_err_t imu_write8(uint8_t reg, uint8_t val)
{
    if (!s_imu_spi_mode) return i2c_write8(s_imu, reg, val);

    uint8_t tx[2] = {(uint8_t)(reg & 0x7F), val};
    spi_transaction_t t = {.length = 16, .tx_buffer = tx};
    return spi_device_polling_transmit(s_imu_spi, &t);
}

static esp_err_t imu_spi_start(void)
{
    spi_bus_config_t bus = {
        .sclk_io_num = PROBE_PIN_IMU_SCLK,
        .mosi_io_num = PROBE_PIN_IMU_MOSI,
        .miso_io_num = PROBE_PIN_IMU_MISO,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        /* One FIFO drain is PROBE_FIFO_BATCH_MAX samples of six bytes.  With
         * DMA disabled the driver caps a transfer at
         * SOC_SPI_MAXIMUM_BUFFER_SIZE (64 bytes), which silently failed every
         * drain larger than ten samples. */
        .max_transfer_sz = PROBE_FIFO_BATCH_MAX * 6 + 8,
    };
    esp_err_t err = spi_bus_initialize(PROBE_IMU_SPI_HOST, &bus, SPI_DMA_CH_AUTO);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) return err;

    spi_device_interface_config_t cfg = {
        .clock_speed_hz = PROBE_IMU_SPI_HZ,
        .mode = 0,
        .spics_io_num = PROBE_PIN_IMU_CS,
        .queue_size = 1,
    };
    return spi_bus_add_device(PROBE_IMU_SPI_HOST, &cfg, &s_imu_spi);
}

/*
 * Some LSM6DS3 revisions put the first data byte immediately after the
 * address byte, others spend one byte of turnaround first.  Probing beats
 * assuming: the wrong choice reads every register shifted by eight bits and
 * still looks plausible.
 */
static bool imu_spi_probe(void)
{
    uint8_t who = 0;
    /* Route imu_read() through SPI for the duration of the probe.  Leaving the
     * flag clear here made the probe call the I2C path with no device handle,
     * which wedged the I2C driver for a couple of seconds. */
    s_imu_spi_mode = true;
    for (s_imu_dummy = 0; s_imu_dummy <= 1; s_imu_dummy++) {
        if (imu_read(0x0F, &who, 1) == ESP_OK && who == 0x69) return true;
    }
    s_imu_spi_mode = false;
    ESP_LOGW(TAG, "SPI WHO_AM_I is not 0x69 (last 0x%02X)", who);
    return false;
}

/*
 * The FIFO_MODE encoding differs between the LSM6DS3 revisions, and the part
 * on this board did not produce a single sample under the one encoding that
 * was assumed earlier.  Sweep the plausible combinations at boot and keep the
 * first that actually stores something.
 */
static int fifo_diff(void)
{
    uint8_t st[2] = {0, 0};
    if (imu_read(0x3A, st, 2) != ESP_OK) return -1;
    return (int)st[0] | (((int)st[1] & 0x1F) << 8);
}

static void imu_fifo_probe(void)
{
    /* Order matters: the datasheet requires a Bypass write to reset the FIFO
     * content before another mode is selected, and the earlier sweep did not
     * do that.  A mode only counts if it REFILLS after being drained — one
     * trial stored a full buffer and then never stored another sample, which
     * is a triggered mode, not a streaming one. */
    static const uint8_t modes[] = {3, 5, 1, 2, 6, 7, 4};
    static const uint8_t odrs[]  = {10, 9, 8};   /* 10 = 6.66 kHz */
    for (size_t o = 0; o < sizeof(odrs); o++) {
        for (size_t m = 0; m < sizeof(modes); m++) {
            imu_write8(0x0A, 0x00);                 /* Bypass: reset the FIFO */
            vTaskDelay(pdMS_TO_TICKS(5));
            imu_write8(0x0A, (uint8_t)((odrs[o] << 3) | modes[m]));
            vTaskDelay(pdMS_TO_TICKS(40));
            int diff = fifo_diff();
            int refill = 0;
            if (diff > 0) {
                uint8_t tmp[64 * 6];
                int n = diff > 64 ? 64 : diff;
                imu_read(0x3E, tmp, (size_t)n * 6u);
                vTaskDelay(pdMS_TO_TICKS(20));
                refill = fifo_diff();
            }
            ESP_LOGI(TAG, "fifo trial mode=%u odr=%u -> diff=%d refill=%d",
                     modes[m], odrs[o], diff, refill);
            if (diff > 0 && refill > 0) {
                s_fifo_mode_code = modes[m];
                s_fifo_odr_code = odrs[o];
                ESP_LOGI(TAG, "FIFO streaming mode=%u odr=%u",
                         modes[m], odrs[o]);
                /* Sweep the FIFO rate codes around the selected one and report
                 * the word rate each delivers: the accelerometer runs at
                 * 6.66 kHz, so a FIFO running slower than that decimates the
                 * stream without any anti-alias filter. */
                for (int code = 7; code <= 11; code++) {
                    imu_write8(0x0A, 0x00);
                    vTaskDelay(pdMS_TO_TICKS(2));
                    imu_write8(0x0A, (uint8_t)((code << 3) | modes[m]));
                    vTaskDelay(pdMS_TO_TICKS(100));
                    int w = fifo_diff();
                    ESP_LOGI(TAG, "fifo odr code %d -> %d words / 100 ms "
                             "(~%d sets/s at 3 words per set)",
                             code, w, w * 10 / 3);
                }
                imu_write8(0x0A, 0x00);
                vTaskDelay(pdMS_TO_TICKS(2));
                imu_write8(0x0A, (uint8_t)((s_fifo_odr_code << 3) | s_fifo_mode_code));
                return;
            }
        }
    }
    ESP_LOGW(TAG, "FIFO never refilled -> register polling");
}

/* ODR_FIFO encoding on this part: 7 = 833 Hz, 8 = 1.66 kHz, 9 = 3.33 kHz,
 * 10 = 6.66 kHz.  Code 10 is the one that matches the accelerometer ODR; with
 * 9 the FIFO decimated the stream by two, silently halving the rate. */
static int fifo_odr_hz(void)
{
    switch (s_fifo_odr_code) {
    case 10: return 6660;
    case 9:  return 3330;
    case 8:  return 1660;
    case 7:  return 833;
    default: return (int)PROBE_IMU_ODR_HZ;
    }
}

static esp_err_t imu_init_i2c(void)
{
    uint8_t who = 0;
    esp_err_t err = ESP_ERR_NOT_FOUND;
    const uint8_t addresses[] = {
        PROBE_LSM6DS3_ADDR_1,
        PROBE_LSM6DS3_ADDR_2,
    };
    for (size_t i = 0; i < sizeof(addresses); i++) {
        i2c_device_config_t cfg = {
            .dev_addr_length = I2C_ADDR_BIT_LEN_7,
            .device_address = addresses[i],
            .scl_speed_hz = PROBE_I2C_FREQ_HZ,
        };
        if (s_imu != NULL) {
            i2c_master_bus_rm_device(s_imu);
            s_imu = NULL;
        }
        err = i2c_master_bus_add_device(s_i2c, &cfg, &s_imu);
        if (err != ESP_OK) continue;
        err = i2c_read(s_imu, 0x0F, &who, 1);
        if (err == ESP_OK && who == 0x69) {
            ESP_LOGI(TAG, "LSM6DS3 online at 0x%02X", addresses[i]);
            break;
        }
        ESP_LOGW(TAG, "no LSM6DS3 at 0x%02X: err=%s value=0x%02X",
                 addresses[i], esp_err_to_name(err), who);
        i2c_master_bus_rm_device(s_imu);
        s_imu = NULL;
        err = ESP_ERR_NOT_FOUND;
    }
    if (err != ESP_OK || s_imu == NULL) {
        ESP_LOGE(TAG, "LSM6DS3 WHO_AM_I not found at 0x6A or 0x6B");
        return err;
    }
    return ESP_OK;
}

static esp_err_t imu_init(void)
{
    esp_err_t err;

    if (PROBE_IMU_USE_SPI && imu_spi_start() == ESP_OK && imu_spi_probe()) {
        s_imu_spi_mode = true;
        ESP_LOGI(TAG, "LSM6DS3 online on SPI: SCLK=%d MOSI=%d MISO=%d CS=%d @ %d Hz dummy=%d",
                 PROBE_PIN_IMU_SCLK, PROBE_PIN_IMU_MOSI, PROBE_PIN_IMU_MISO,
                 PROBE_PIN_IMU_CS, (int)PROBE_IMU_SPI_HZ, s_imu_dummy);
    } else {
        err = imu_init_i2c();
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "LSM6DS3 not reachable on SPI or I2C");
            return err;
        }
    }

    /* Accelerometer: 6.66 kHz ODR, +/-4 g full scale, high-performance mode.
     *
     * The range is +/-4 g rather than +/-2 g because a hand-held tap on a wall
     * finish routinely exceeds 2 g at the sensor, and a clipped peak destroys
     * both crest factor and kurtosis -- two of the features the analyser uses.
     * The cost is resolution (0.122 mg/LSB instead of 0.061), which is far
     * below the noise floor of this part.
     *
     * ctrl1 = 0xA8: ODR_XL = 1000b (6.66 kHz), FS_XL = 10b (+/-4 g),
     * BW_XL = 00.  With CTRL4_C.XL_BW_SCAL_ODR left at its reset value of 0
     * the analog filter is not used at this ODR, so the analog chain is open
     * to roughly Nyquist: the 30..1000 Hz feature band is alias-free without
     * narrowing it, which is the reason for running the part this fast. */
    err = imu_write8(0x10, 0xA8);
    if (err != ESP_OK) goto init_failed;
    err = imu_write8(0x11, 0x00); /* gyro off */
    if (err != ESP_OK) goto init_failed;
    err = imu_write8(0x12, 0x44); /* BDU + register auto-increment */
    if (err != ESP_OK) goto init_failed;

    /* FIFO: no decimation on either channel, then let imu_fifo_probe() find a
     * FIFO_MODE this die actually honours.  A working FIFO matters much more
     * now than it did at 2.6 kHz: the samples are then stamped by the sensor's
     * own clock, so a 35 ms frame refresh on core 1 cannot punch a hole in the
     * waveform. */
    /* FIFO_CTRL3 (08h) DEC_FIFO_XL[2:0] is a data ROUTE, not a mere rate:
     * 000 means "accelerometer not in FIFO" and 001 means "no decimation".
     * Writing 0x00 here kept the accelerometer out of the FIFO entirely, which
     * is why every FIFO read returned zeros while OUTX_L_XL stayed valid. */
    err = imu_write8(0x08, 0x01); /* XL -> FIFO, no decimation */
    if (err != ESP_OK) goto init_failed;
    err = imu_write8(0x07, 0x00); /* FTH high: DIFF_FIFO is polled, not a threshold */
    if (err != ESP_OK) goto init_failed;
    err = imu_write8(0x06, 0x00); /* FTH low */
    if (err != ESP_OK) goto init_failed;
    vTaskDelay(pdMS_TO_TICKS(20));
    imu_fifo_probe();
    /* Draining a 6.66 kHz FIFO over I2C needs about 40 kB/s against a 50 kB/s
     * bus, i.e. the bus would have to run at full duty and still fall behind.
     * The FIFO is therefore used on SPI only; over I2C the output registers are
     * polled directly, which is what this board did before. */
    s_use_fifo = (s_fifo_mode_code > 0) && s_imu_spi_mode;

    uint8_t ctrl1 = 0, ctrl3 = 0, status = 0;
    esp_err_t read_err = imu_read(0x10, &ctrl1, 1);
    if (read_err == ESP_OK) read_err = imu_read(0x12, &ctrl3, 1);
    if (read_err == ESP_OK) read_err = imu_read(0x1E, &status, 1);
    if (read_err != ESP_OK) {
        err = read_err;
        goto init_failed;
    }
    ESP_LOGI(TAG, "LSM6DS3 config: CTRL1_XL=0x%02X CTRL3_C=0x%02X STATUS=0x%02X",
             ctrl1, ctrl3, status);
    ESP_LOGI(TAG, "capture path: bus=%s, fifo=%s (probe mode=%d odr=%d, %d Hz)",
             s_imu_spi_mode ? "SPI" : "I2C",
             s_use_fifo ? "streaming"
                        : (s_fifo_mode_code > 0 ? "I2C bus too slow" : "unavailable"),
             s_fifo_mode_code, s_fifo_odr_code, fifo_odr_hz());
    if ((ctrl1 & 0xF0) == 0) {
        ESP_LOGE(TAG, "LSM6DS3 accelerometer is powered down (CTRL1_XL=0x%02X)", ctrl1);
        err = ESP_ERR_INVALID_STATE;
        goto init_failed;
    }
    return ESP_OK;

init_failed:
    ESP_LOGE(TAG, "LSM6DS3 initialisation failed: %s", esp_err_to_name(err));
    if (s_imu != NULL) {
        i2c_master_bus_rm_device(s_imu);
        s_imu = NULL;
    }
    s_imu_spi_mode = false;
    return err;
}

static esp_err_t tof_init(void)
{
    esp_err_t err = vl53l1x_init(&s_tof, s_i2c, PROBE_VL53L0X_ADDR);
    if (err != ESP_OK) return err;
    uint16_t sensor_id = 0;
    err = vl53l1x_get_sensor_id(&s_tof, &sensor_id);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "VL53L1X sensor ID read failed: %s", esp_err_to_name(err));
        return err;
    }
    ESP_LOGI(TAG, "VL53L1X sensor ID=0x%04X", sensor_id);
    err = vl53l1x_sensor_init(&s_tof);
    if (err != ESP_OK) {
        return err;
    }
    err = vl53l1x_config_long_100ms(&s_tof);
    if (err != ESP_OK) return err;
    err = vl53l1x_set_macro_timing(&s_tof, 16);
    if (err != ESP_OK) return err;
    err = vl53l1x_set_intermeasurement_ms(&s_tof, 100);
    if (err != ESP_OK) return err;
    err = vl53l1x_start(&s_tof);
    if (err != ESP_OK) return err;
    s_tof_ready = true;
    ESP_LOGI(TAG, "VL53L1X ranging started at 0x%02X", PROBE_VL53L0X_ADDR);
    return ESP_OK;
}

/*
 * Repeatedly read registers that never change value.  A healthy bus returns
 * 0x69 from the LSM6DS3 WHO_AM_I every time and 0xEE from the VL53L0X model
 * ID every time; scattered values mean signal integrity, not protocol.
 */

static void tft_cmd(spi_device_handle_t dev, int dc, uint8_t command);
static void tft_data(spi_device_handle_t dev, int dc, const uint8_t *data, size_t len);

static esp_err_t tof_read_distance_mm(uint16_t *distance_mm)
{
    if (!s_tof_ready || distance_mm == NULL) return ESP_ERR_NOT_FOUND;
    vl53l1x_result_t data = {0};
    esp_err_t err = vl53l1x_read(&s_tof, &data, 150);
    if (err != ESP_OK) return err;
    if (data.status != 0) {
        static unsigned flagged_samples;
        if ((++flagged_samples % 10) == 0) {
            ESP_LOGW(TAG, "VL53L1X flagged sample: status=%u distance=%u sigma=%u signal=%u ambient=%u",
                     data.status, data.distance_mm, data.sigma_mm,
                     data.signal_kcps, data.ambient_kcps);
        }
        if (data.distance_mm == 0 || data.signal_kcps == 0) {
            return ESP_ERR_INVALID_RESPONSE;
        }
    }
    *distance_mm = data.distance_mm;
    return ESP_OK;
}

static void tft_set_window(spi_device_handle_t dev, int dc,
                           uint8_t x0, uint8_t y0, uint8_t x1, uint8_t y1)
{
    uint8_t area[4] = {0, x0, 0, x1};
    tft_cmd(dev, dc, 0x2A);
    tft_data(dev, dc, area, sizeof(area));
    area[0] = 0; area[1] = y0; area[2] = 0; area[3] = y1;
    tft_cmd(dev, dc, 0x2B);
    tft_data(dev, dc, area, sizeof(area));
    tft_cmd(dev, dc, 0x2C);
}

static void frame_clear(uint8_t *frame)
{
    memset(frame, 0, 128 * 160 * 2);
}

static void frame_pixel(uint8_t *frame, int x, int y, uint16_t color)
{
    if (x < 0 || x >= 128 || y < 0 || y >= 160) return;
    size_t i = ((size_t)y * 128U + (size_t)x) * 2U;
    frame[i] = (uint8_t)(color >> 8);
    frame[i + 1] = (uint8_t)color;
}

static void frame_rect(uint8_t *frame, int x, int y, int w, int h, uint16_t color)
{
    for (int yy = y; yy < y + h; yy++)
        for (int xx = x; xx < x + w; xx++)
            frame_pixel(frame, xx, yy, color);
}

/* Same generated 5x7 font the menu uses, so the two panels look like one
 * instrument rather than two prototypes. */
static void frame_text(uint8_t *frame, int x, int y, const char *s,
                       uint16_t color, int scale)
{
    int cx = x;
    for (; *s; s++) {
        const uint8_t *g = probe_font_glyph(*s);
        for (int col = 0; col < PROBE_FONT_W; col++)
            for (int row = 0; row < PROBE_FONT_H; row++)
                if ((g[col] >> row) & 1u)
                    frame_rect(frame, cx + col * scale, y + row * scale,
                               scale, scale, color);
        cx += PROBE_FONT_ADV * scale;
        if (cx > 128) break;
    }
}

static int frame_text_w(const char *s, int scale)
{
    return (int)strlen(s) * PROBE_FONT_ADV * scale;
}

static void frame_present(spi_device_handle_t dev, int dc, uint8_t *frame)
{
    tft_set_window(dev, dc, 0, 0, 127, 159);
    for (int y = 0; y < 160; y += 8) {
        tft_data(dev, dc, frame + y * 128 * 2, 8 * 128 * 2);
    }
}

/* ---- TFT2: instrument readout -------------------------------------------
 *
 * This panel used to draw a rolling strip chart of the accelerometer and the
 * rangefinder.  That was a bring-up aid: it proved the I2C bus was delivering
 * samples, and it stopped being useful once the web dashboard took over the
 * traces.  It is now a readout an operator can actually use on the bench:
 * the range finder distance, the peak of the last tap and the tap count, with
 * the two link states that decide whether any of it reaches the dashboard.
 * ---------------------------------------------------------------------- */

static float   s_last_tap_peak_g;
static uint32_t s_tap_seen;   /* tap counter; the stick task watches it */

static const uint16_t C2_TITLE  = 0x0210;
static const uint16_t C2_TEXT   = 0xFFFF;
static const uint16_t C2_DIM    = 0x8410;
static const uint16_t C2_OK     = 0x07E0;
static const uint16_t C2_BAD    = 0xF800;
static const uint16_t C2_ACCENT = 0xFD20;
static const uint16_t C2_HINT   = 0xFFE0;

/* Mini map of the planned grid with the active cell filled, drawn in the title
 * bar.  The browser owns the grid shape, so this exists purely so the operator
 * can see which cell the trigger will be attributed to without looking at the
 * PC. */
static void draw_grid_badge(void)
{
    int rows = 3, cols = 3;
    probe_menu_grid(&rows, &cols);
    if (rows < 1 || cols < 1) return;

    const int cell = (rows <= 3) ? 4 : (rows <= 5) ? 2 : 1;
    const int gap  = (cols + rows > 12) ? 0 : 1;
    const int w = cols * cell + (cols - 1) * gap;
    const int h = rows * cell + (rows - 1) * gap;
    const int x0 = 126 - w;
    const int y0 = (14 - h) / 2;
    if (y0 < 0) return;

    const int idx = probe_menu_point();
    for (int r = 0; r < rows; r++) {
        for (int c = 0; c < cols; c++) {
            const bool on = (r * cols + c) == idx;
            frame_rect(s_tft2_frame, x0 + c * (cell + gap),
                       y0 + r * (cell + gap), cell, cell,
                       on ? C2_ACCENT : 0x2945);
        }
    }

    int rows2 = 0, cols2 = 0;
    probe_menu_grid(&rows2, &cols2);
    if (cols2 > 0 && idx >= 0 && idx < rows2 * cols2) {
        char buf[16];
        snprintf(buf, sizeof(buf), "%d", idx);
        frame_text(s_tft2_frame, x0 - frame_text_w(buf, 1) - 2, 4, buf,
                   C2_TEXT, 1);
    }
}

static void draw_measure_screen(void)
{
    frame_clear(s_tft2_frame);
    char buf[32];

    frame_rect(s_tft2_frame, 0, 0, 128, 14, C2_TITLE);
    frame_text(s_tft2_frame, 3, 4, "MEASURE", C2_TEXT, 1);
    /* Where this tap will be filed.  The grid badge is the one piece of state
     * an operator must not have to go into a menu to check: a whole session's
     * taps land on whichever cell it shows. */
    draw_grid_badge();

    /* Range finder: the one continuous measurement the probe makes. */
    frame_text(s_tft2_frame, 6, 20, "DISTANCE", C2_DIM, 1);
    if (s_last_distance_valid) {
        snprintf(buf, sizeof(buf), "%u", (unsigned)s_last_distance_mm);
        frame_text(s_tft2_frame, 6, 31, buf, C2_ACCENT, 3);
        frame_text(s_tft2_frame, 6 + frame_text_w(buf, 3) + 4, 44, "MM",
                   C2_DIM, 1);
    } else {
        frame_text(s_tft2_frame, 6, 34, "--", C2_BAD, 3);
    }
    frame_rect(s_tft2_frame, 6, 66, 116, 1, 0x2945);

    /* Last tap.  No verdict here on purpose: the debond/bonded decision is a
     * threshold on spectral features and lives in the analyser, where the
     * threshold can be changed and the whole feature table is visible.  A
     * second, differently-computed verdict on a 1.8 inch panel would only be a
     * second thing to disagree with. */
    frame_text(s_tft2_frame, 6, 72, "LAST TAP", C2_DIM, 1);
    if (s_tap_seen > 0) {
        snprintf(buf, sizeof(buf), "%.2f", (double)s_last_tap_peak_g);
        frame_text(s_tft2_frame, 6, 83, buf, C2_TEXT, 3);
        frame_text(s_tft2_frame, 6 + frame_text_w(buf, 3) + 4, 96, "G",
                   C2_DIM, 1);
    } else {
        frame_text(s_tft2_frame, 6, 86, "NONE YET", C2_DIM, 2);
    }

    snprintf(buf, sizeof(buf), "TAPS %lu", (unsigned long)s_tap_seen);
    frame_text(s_tft2_frame, 6, 116, buf, C2_TEXT, 1);

    /* Links.  Two dots and two words; anything more is dashboard work. */
    frame_rect(s_tft2_frame, 6, 130, 7, 7, probe_wifi_connected() ? C2_OK : C2_BAD);
    frame_text(s_tft2_frame, 17, 130, probe_wifi_connected() ? "WIFI" : "WIFI",
               probe_wifi_connected() ? C2_OK : C2_DIM, 1);
    frame_rect(s_tft2_frame, 62, 130, 7, 7, probe_mqtt_connected() ? C2_OK : C2_BAD);
    frame_text(s_tft2_frame, 73, 130, "MQTT",
               probe_mqtt_connected() ? C2_OK : C2_DIM, 1);
    frame_rect(s_tft2_frame, 6, 143, 7, 7,
               probe_tap_stream_enabled() ? C2_OK : C2_BAD);
    frame_text(s_tft2_frame, 17, 143, "TAP STREAM", C2_HINT, 1);

    frame_present(s_tft2, PROBE_PIN_TFT2_DC, s_tft2_frame);
}

/* ---------------------------------------------------------------------
 *  Tap capture
 *
 *  The FIFO is drained every PROBE_FIFO_POLL_MS and every sample is pushed
 *  through tap_feed().  A triggered window is handed to the menu module, which
 *  owns the (blocking) base64 + MQTT publish and runs it from the display task.
 *
 *  Baseline: the slow-gravity tracker is what makes the trigger range-
 *  independent. The probe is held at some attitude, so each axis carries a DC
 *  offset of up to 1 g; subtracting a tracked baseline means the trigger is
 *  "deviation from the current attitude", not "some absolute acceleration".
 * ------------------------------------------------------------------- */

static int16_t  s_tap_ring[PROBE_TAP_RING_LEN][3];
static size_t   s_tap_head;
static int16_t  s_tap_window[PROBE_TAP_WINDOW * 3];
static float    s_tap_baseline[3];
static int      s_tap_post_left;
static int      s_tap_fill;
static int      s_tap_trig;
static int64_t  s_tap_last_us;
static uint8_t  s_fifo_buf[PROBE_FIFO_BATCH_MAX * 6];
static uint32_t s_tap_emitted;
static uint32_t s_fifo_errors;

static int  s_capture_fs = (int)PROBE_IMU_ODR_HZ;   /* measured, Hz */
static uint32_t s_baseline_seed = 3000;             /* samples of fast seeding */
static int64_t  s_far_since_us;

static void tap_emit(void)
{
    s_tap_seen++;
    s_last_tap_peak_g = (float)s_tap_trig / PROBE_IMU_LSB_PER_G;
    probe_mqtt_publish_waveform(s_tap_window, PROBE_TAP_WINDOW,
                               PROBE_TAP_PRE, s_tap_trig, s_capture_fs);
    probe_menu_note_tap();
    s_tap_emitted++;
    ESP_LOGI(TAG, "tap %lu trigger=%d LSB", (unsigned long)s_tap_emitted, s_tap_trig);
}

static void tap_feed(int16_t x, int16_t y, int16_t z, int64_t now_us)
{
    const float fx = (float)x / PROBE_IMU_LSB_PER_G;
    const float fy = (float)y / PROBE_IMU_LSB_PER_G;
    const float fz = (float)z / PROBE_IMU_LSB_PER_G;

    /* Freeze the gravity tracker while a window is being collected, otherwise
     * the tap itself would be averaged into the baseline it is measured
     * against.
     *
     * Two-stage tracking.  The steady-state tracker must ignore taps, so it
     * only follows a sample while that sample is within 0.30 g of the current
     * baseline.  That gate cannot be the whole story: at power-on the baseline
     * starts at zero while the probe is held at some attitude, so one axis
     * carries up to 1 g and EVERY sample is rejected -- the baseline never
     * converges, the residual stays at 1 g and the trigger fires forever.  A
     * short unconditional seed at start-up, plus a re-seed when the probe is
     * held in a new attitude for longer than any tap, covers both ends. */
    {
        const float f[3] = {fx, fy, fz};
        if (s_baseline_seed > 0) {
            s_baseline_seed--;
            for (int a = 0; a < 3; a++)
                s_tap_baseline[a] += 0.05f * (f[a] - s_tap_baseline[a]);
        } else if (s_tap_post_left == 0) {
            bool far = false;
            for (int a = 0; a < 3; a++)
                if (fabsf(f[a] - s_tap_baseline[a]) > 0.30f) far = true;
            if (far) {
                if (s_far_since_us == 0) s_far_since_us = now_us;
                if (now_us - s_far_since_us > 800000) {
                    /* Held this attitude for longer than a tap can last: the
                     * baseline is stale, re-seat it quickly. */
                    for (int a = 0; a < 3; a++)
                        s_tap_baseline[a] += 0.05f * (f[a] - s_tap_baseline[a]);
                    s_far_since_us = now_us;
                }
            } else {
                s_far_since_us = 0;
                for (int a = 0; a < 3; a++)
                    s_tap_baseline[a] += 0.002f * (f[a] - s_tap_baseline[a]);
            }
        }
    }

    int32_t dx = (int32_t)lrintf((fx - s_tap_baseline[0]) * PROBE_IMU_LSB_PER_G);
    int32_t dy = (int32_t)lrintf((fy - s_tap_baseline[1]) * PROBE_IMU_LSB_PER_G);
    int32_t dz = (int32_t)lrintf((fz - s_tap_baseline[2]) * PROBE_IMU_LSB_PER_G);
    for (int a = 0; a < 3; a++) {
        int32_t *v = (a == 0) ? &dx : (a == 1) ? &dy : &dz;
        if (*v > 32767) *v = 32767;
        if (*v < -32768) *v = -32768;
    }

    s_tap_ring[s_tap_head][0] = (int16_t)dx;
    s_tap_ring[s_tap_head][1] = (int16_t)dy;
    s_tap_ring[s_tap_head][2] = (int16_t)dz;
    s_tap_head = (s_tap_head + 1) % PROBE_TAP_RING_LEN;

    /* Decimated copy for the TFT2 trace: the display ring is 128 points. */
    static int decim;
    if (++decim >= 4) {
        decim = 0;
        s_accel_history[0][s_wave_index] = (float)dx / PROBE_IMU_LSB_PER_G;
        s_accel_history[1][s_wave_index] = (float)dy / PROBE_IMU_LSB_PER_G;
        s_accel_history[2][s_wave_index] = (float)dz / PROBE_IMU_LSB_PER_G;
        s_wave_index = (s_wave_index + 1) & 127;
    }

    const float mag = sqrtf((float)(dx * dx + dy * dy + dz * dz)) / PROBE_IMU_LSB_PER_G;

    if (s_tap_post_left > 0) {
        int f3 = s_tap_fill;
        if (f3 < PROBE_TAP_WINDOW) {
            s_tap_window[f3 * 3 + 0] = (int16_t)dx;
            s_tap_window[f3 * 3 + 1] = (int16_t)dy;
            s_tap_window[f3 * 3 + 2] = (int16_t)dz;
            s_tap_fill = f3 + 1;
            if ((int16_t)(sqrtf((float)(dx*dx+dy*dy+dz*dz))) > s_tap_trig)
                s_tap_trig = (int)sqrtf((float)(dx*dx+dy*dy+dz*dz));
        }
        s_tap_post_left--;
        if (s_tap_post_left == 0) tap_emit();
        return;
    }

    if (mag < probe_tap_thresh_g()) return;
    if (now_us - s_tap_last_us < (int64_t)PROBE_TAP_REARM_MS * 1000) return;
    s_tap_last_us = now_us;

    /* Pre-trigger: copy the PROBE_TAP_PRE frames that led up to the trigger so
     * the analyser sees the quiet baseline before the impact, which is what the
     * decay-tau fit needs. */
    int pre = PROBE_TAP_PRE;
    if (pre > PROBE_TAP_WINDOW) pre = PROBE_TAP_WINDOW;
    for (int i = 0; i < pre; i++) {
        size_t idx = (s_tap_head + PROBE_TAP_RING_LEN - pre + (size_t)i) % PROBE_TAP_RING_LEN;
        s_tap_window[i * 3 + 0] = s_tap_ring[idx][0];
        s_tap_window[i * 3 + 1] = s_tap_ring[idx][1];
        s_tap_window[i * 3 + 2] = s_tap_ring[idx][2];
    }
    s_tap_fill = pre;
    s_tap_post_left = PROBE_TAP_WINDOW - pre;
    s_tap_trig = (int)(mag * PROBE_IMU_LSB_PER_G);
    if (s_tap_trig > 32767) s_tap_trig = 32767;
}

static volatile int cap_last_sets;
static volatile int cap_last_x, cap_last_y, cap_last_z;
static uint32_t s_cap_missed;   /* sample-clock ticks with no fresh sample */
static volatile int s_cap_words; /* DIFF_FIFO as read, before any scaling   */

/* ---- sample clock for the register-polling path ----------------------
 *
 * At 6.66 kHz a sample is due every 150 us, which no FreeRTOS delay can
 * express, and a busy wait would starve the display task sharing core 1.
 * esp_timer therefore drives the loop: the callback only wakes the capture
 * task, the task does the SPI read.  The timestamps that go into the waveform
 * are taken at the read, so the analyser sees the achieved rate rather than a
 * nominal one.
 */
static TaskHandle_t s_cap_task;
static esp_timer_handle_t s_cap_timer;

static void cap_timer_cb(void *arg)
{
    (void)arg;
    if (s_cap_task != NULL) xTaskNotifyGive(s_cap_task);
}

static void sample_clock_start(void)
{
    if (s_cap_timer != NULL) return;
    s_cap_task = xTaskGetCurrentTaskHandle();
    esp_timer_create_args_t args = {
        .callback = cap_timer_cb,
        .name = "capclk",
    };
    if (esp_timer_create(&args, &s_cap_timer) != ESP_OK) {
        ESP_LOGE(TAG, "sample clock create failed");
        s_cap_timer = NULL;
        return;
    }
    esp_timer_start_periodic(s_cap_timer, PROBE_IMU_SAMPLE_US);
    ESP_LOGI(TAG, "sample clock: timer-paced at %d Hz",
             (int)(1000000 / PROBE_IMU_SAMPLE_US));
}

static void imu_capture_task(void *arg)
{
    (void)arg;
    uint32_t polls = 0, frames = 0, empty = 0, fifo_empties = 0;
    int64_t next_diag = 0;
    int64_t fb_t0 = 0;
    uint32_t fb_frames = 0;

    /* A working FIFO is self-clocked; only the polling path needs a clock. */
    if (s_imu_spi_mode && !s_use_fifo) sample_clock_start();
    if (s_use_fifo) {
        /* The FIFO was armed during init and holds 102 ms of data, so it has
         * already overrun by the time this loop starts.  Re-arm it here. */
        imu_write8(0x0A, 0x00);
        imu_write8(0x0A, (uint8_t)((s_fifo_odr_code << 3) | s_fifo_mode_code));
    }

    for (;;) {
        if (s_imu == NULL && !s_imu_spi_mode) {
            vTaskDelay(pdMS_TO_TICKS(200));
            continue;
        }

        if (s_use_fifo) {
            uint8_t st[2] = {0, 0};
            cap_last_sets = 0;
            if (imu_read(0x3A, st, 2) == ESP_OK) {
                int words = (int)st[0] | (((int)st[1] & 0x1F) << 8);
                s_cap_words = words;
                /* DIFF_FIFO counts 16-bit words; a set is three words while
                 * only the accelerometer is routed into the FIFO, so sets =
                 * words/3.  The zero data seen earlier was not a read problem
                 * at all: FIFO_CTRL3 DEC_FIFO_XL was 000, i.e. the
                 * accelerometer was never written to the FIFO. */
                int nsets = words / 3;
                if (nsets > PROBE_FIFO_BATCH_MAX) nsets = PROBE_FIFO_BATCH_MAX;
                if (nsets > 0 &&
                    imu_read(0x3E, s_fifo_buf, (size_t)nsets * 6u) == ESP_OK) {
                    if (polls <= 3) {
                            ESP_LOGI(TAG, "fifo sample reads: words=%d sets=%d "
                                     "s0=%d,%d,%d s1=%d,%d,%d",
                                     words, nsets,
                                     (int16_t)((s_fifo_buf[1] << 8) | s_fifo_buf[0]),
                                     (int16_t)((s_fifo_buf[3] << 8) | s_fifo_buf[2]),
                                     (int16_t)((s_fifo_buf[5] << 8) | s_fifo_buf[4]),
                                     (int16_t)((s_fifo_buf[7] << 8) | s_fifo_buf[6]),
                                     (int16_t)((s_fifo_buf[9] << 8) | s_fifo_buf[8]),
                                     (int16_t)((s_fifo_buf[11] << 8) | s_fifo_buf[10]));
                    }
                    cap_last_sets = nsets;
                    cap_last_x = (int16_t)((s_fifo_buf[1] << 8) | s_fifo_buf[0]);
                    cap_last_y = (int16_t)((s_fifo_buf[3] << 8) | s_fifo_buf[2]);
                    cap_last_z = (int16_t)((s_fifo_buf[5] << 8) | s_fifo_buf[4]);
                    int64_t t0 = esp_timer_get_time();
                    for (int i = 0; i < nsets; i++) {
                        const uint8_t *p = &s_fifo_buf[i * 6];
                        tap_feed((int16_t)((p[1] << 8) | p[0]),
                                 (int16_t)((p[3] << 8) | p[2]),
                                 (int16_t)((p[5] << 8) | p[4]),
                                 t0);
                    }
                    frames += (uint32_t)nsets;
                    probe_mqtt_publish_stream((const int16_t *)s_fifo_buf, nsets,
                                              fifo_odr_hz());
                    if (polls == 1) {
                        /* Layout probe: a FIFO set is either XL only (6 bytes)
                         * or XL+gyro (12 bytes, gyro slots zero while the gyro
                         * is powered down).  Dump the head and the live output
                         * registers side by side to tell them apart. */
                        uint8_t live[6] = {0, 0, 0, 0, 0, 0};
                        imu_read(0x28, live, sizeof(live));
                        ESP_LOGI(TAG, "fifo head: "
                                 "%02X%02X %02X%02X %02X%02X | %02X%02X %02X%02X %02X%02X"
                                 " | %02X%02X %02X%02X %02X%02X",
                                 s_fifo_buf[1], s_fifo_buf[0], s_fifo_buf[3], s_fifo_buf[2],
                                 s_fifo_buf[5], s_fifo_buf[4], s_fifo_buf[7], s_fifo_buf[6],
                                 s_fifo_buf[9], s_fifo_buf[8], s_fifo_buf[11], s_fifo_buf[10],
                                 s_fifo_buf[13], s_fifo_buf[12], s_fifo_buf[15], s_fifo_buf[14],
                                 s_fifo_buf[17], s_fifo_buf[16]);
                        ESP_LOGI(TAG, "live OUTX: %02X%02X %02X%02X %02X%02X",
                                 live[1], live[0], live[3], live[2], live[5], live[4]);
                    }
                }
            }
            polls++;
            if (polls <= 20)
                ESP_LOGI(TAG, "fifo poll %lu: sets=%d status=%02X %02X",
                         (unsigned long)polls, cap_last_sets, st[0], st[1]);
            s_capture_fs = fifo_odr_hz();

            /* Fallback.  If the FIFO has not produced a single sample after
             * ~5 s of polling, the part on this board does not honour the
             * FIFO_CTRL5 write (a known trait of some LSM6DS3 clones).  Rather
             * than lose tap capture, switch to reading OUTX_L_XL directly and
             * MEASURE the achieved rate, which is then published as "fs" so the
             * analyser never assumes a rate the hardware did not deliver. */
            if (frames == 0) fifo_empties++;
            if (fifo_empties >= 100 && frames == 0) {
                /* The boot probe said this mode stored samples, so an empty
                 * FIFO now means the part has stopped storing.  Fall back
                 * rather than capture nothing. */
                s_use_fifo = false;
                fb_t0 = 0;
                ESP_LOGW(TAG, "FIFO went empty -> register polling fallback");
                if (s_imu_spi_mode) sample_clock_start();
            }
            vTaskDelay(pdMS_TO_TICKS(PROBE_FIFO_POLL_MS));
        } else {
            uint8_t raw[6];
            bool fresh = true;
            /* On SPI the read is paced by the sample clock; on I2C the bus
             * itself is the pacer and the loop yields between reads. */
            if (s_imu_spi_mode) {
                ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(200));
                /* Gate on the data-ready flag so a tick that arrives before
                 * the part has converted does not duplicate the previous
                 * sample: duplicates are a zero-order hold, not a sample. */
                uint8_t st = 0;
                for (int spin = 0;; spin++) {
                    if (imu_read(0x1E, &st, 1) != ESP_OK) break;
                    if (st & 0x01) break;              /* XLDA: a new sample */
                    if (spin >= 8) { s_cap_missed++; break; }
                    esp_rom_delay_us(8);               /* bounded, < 70 us */
                }
                if ((st & 0x01) == 0) fresh = false;
            }
            if (fresh && imu_read(0x28, raw, 6) == ESP_OK) {
                cap_last_x = (int16_t)((raw[1] << 8) | raw[0]);
                cap_last_y = (int16_t)((raw[3] << 8) | raw[2]);
                cap_last_z = (int16_t)((raw[5] << 8) | raw[4]);
                int64_t t = esp_timer_get_time();
                tap_feed((int16_t)((raw[1] << 8) | raw[0]),
                         (int16_t)((raw[3] << 8) | raw[2]),
                         (int16_t)((raw[5] << 8) | raw[4]),
                         t);
                frames++;
                if (fb_t0 == 0) {
                    fb_t0 = t;
                } else if ((frames & 0x3FFu) == 0x3FFu) {
                    int64_t dt = t - fb_t0;
                    if (dt > 1000)
                        s_capture_fs = (int)(((int64_t)(frames - 1) * 1000000) / dt);
                }
                fb_frames++;
            }
            if (!s_imu_spi_mode) taskYIELD();
        }

        int64_t now_us = esp_timer_get_time();
        if (now_us > next_diag) {
            next_diag = now_us + 10000000;
            ESP_LOGI(TAG, "capture: bus=%s fifo=%d polls=%lu frames=%lu diff=%d "
                          "empty=%lu missed=%lu fs=%d Hz taps=%lu last=%d,%d,%d thresh=%.2fg",
                     s_imu_spi_mode ? "spi" : "i2c",
                     (int)s_use_fifo, (unsigned long)polls,
                     (unsigned long)frames, s_cap_words,
                     (unsigned long)empty, (unsigned long)s_cap_missed, s_capture_fs,
                     (unsigned long)s_tap_emitted,
                     cap_last_x, cap_last_y, cap_last_z,
                     (double)probe_tap_thresh_g());
        }
        if (cap_last_sets == 0) empty++;
        (void)fb_frames;
    }
}

static void draw_menu_screen(void)
{
    probe_menu_render(s_tft1_frame);
    frame_present(s_tft1, PROBE_PIN_TFT1_DC, s_tft1_frame);
}

/* One second-order statistic over the recent ring buffer, used for the JSON
 * payload.  The window is short on purpose: it is the probe's own motion, not a
 * wall measurement, and the report says so. */
static void accel_window_stats(float *rms_out, float *peak_out)
{
    const int n = 32;
    float acc = 0.0f, peak = 0.0f;
    for (int i = 0; i < n; i++) {
        size_t idx = (s_wave_index + 128 - 1 - (size_t)i) & 127u;
        for (int a = 0; a < 3; a++) {
            float v = s_accel_history[a][idx];
            acc += v * v;
            if (v < 0.0f) v = -v;
            if (v > peak) peak = v;
        }
    }
    *rms_out = sqrtf(acc / (float)(n * 3));
    *peak_out = peak;
}

static void waveform_task(void *arg)
{
    (void)arg;
    ESP_LOGI(TAG, "waveform task entered");
    unsigned tof_errors = 0;
    TickType_t next_display = xTaskGetTickCount();
    TickType_t next_tof = next_display;
    TickType_t next_tft2 = next_display;
    uint32_t last_gen = 0xFFFFFFFFu;
    for (;;) {
        TickType_t now = xTaskGetTickCount();
        if (s_tof_ready && (int32_t)(now - next_tof) >= 0) {
            uint16_t distance = 0;
            esp_err_t tof_err = tof_read_distance_mm(&distance);
            if (tof_err == ESP_OK) {
                s_distance_history[s_wave_index] = distance;
                s_last_distance_mm = distance;
                s_last_distance_valid = true;
                static unsigned tof_samples;
                tof_samples++;
                if ((tof_samples % 10) == 0) {
                    ESP_LOGI(TAG, "VL53L1X distance=%u mm", (unsigned)distance);
                }
            } else {
                s_distance_history[s_wave_index] =
                    s_distance_history[(s_wave_index - 1) & 127];
                if (++tof_errors % 10 == 0) {
                    ESP_LOGW(TAG, "VL53L1X ranging failed %u times: %s",
                             tof_errors, esp_err_to_name(tof_err));
                }
            }
            next_tof = now + pdMS_TO_TICKS(100);
        }

        now = xTaskGetTickCount();

        /* TFT1 (menu) is redrawn only when an input changed the menu state.
         * TFT2 (figures) refreshes at 5 Hz.  Redrawing both panels every frame
         * costs about 35 ms of blocking SPI per pass, which starves the task;
         * with change-driven drawing the loop has time to spare. */
        /* Tap windows are encoded and published here, on the display core,
         * so a slow broker backs up a queue instead of starving the FIFO
         * drain on core 0. */
        /* Timed because this is the one call that can block for an unbounded
         * time on a slow broker, and it shares core 1 with the stick task: a
         * publish that stalls is indistinguishable, from the operator's side,
         * from a dead joystick.  The heartbeat reports the worst case since
         * the last heartbeat so the two can be told apart. */
        int64_t pump_t0 = esp_timer_get_time();
        probe_mqtt_pump();
        int64_t pump_dt = esp_timer_get_time() - pump_t0;
        if (pump_dt > s_pump_worst_us) s_pump_worst_us = pump_dt;
        probe_menu_note_sensor(s_imu != NULL, s_tof_ready, s_last_distance_mm);

        uint32_t gen = probe_menu_generation();
        if (gen != last_gen) {
            last_gen = gen;
            draw_menu_screen();
        }
        if ((int32_t)(now - next_tft2) >= 0) {
            draw_measure_screen();
            next_tft2 = now + pdMS_TO_TICKS(200);
        }

        /* Heartbeat: the serial log is the only window on a board with no
         * JTAG attached, so a slow or blocked task must announce itself. */
        static TickType_t next_hb;
        if ((int32_t)(now - next_hb) >= 0) {
            next_hb = now + pdMS_TO_TICKS(5000);
            ESP_LOGI(TAG, "wf alive, pt=P%d tof_ready=%d mqtt=%d pub=%lu taps=%lu "
                          "joymute=%lu pumpmax=%dms heap=%u",
                     probe_menu_point(),
                     (int)s_tof_ready, (int)probe_mqtt_connected(),
                     (unsigned long)probe_mqtt_published(),
                     (unsigned long)probe_tap_count(),
                     (unsigned long)s_joy_muted,
                     (int)(s_pump_worst_us / 1000),
                     (unsigned)esp_get_free_heap_size());
            s_pump_worst_us = 0;
        }

        vTaskDelayUntil(&next_display, pdMS_TO_TICKS(50));
    }
}

static void bus_health_check(void)
{
    const int rounds = 32;
    if (s_imu == NULL && !s_imu_spi_mode) return;
    unsigned who_hits = 0, accel_hits = 0;
    for (int i = 0; i < rounds; i++) {
        uint8_t who = 0;
        if (imu_read(0x0F, &who, 1) == ESP_OK && who == 0x69) who_hits++;
        uint8_t accel = 0;
        if (imu_read(0x28, &accel, 1) == ESP_OK) accel_hits++;
        vTaskDelay(pdMS_TO_TICKS(2));
    }
    ESP_LOGI(TAG, "bus health LSM6DS3 (%s): WHO_AM_I 0x69 %u/%d, OUTX_L_XL ok %u/%d",
             s_imu_spi_mode ? "SPI" : "I2C", who_hits, rounds, accel_hits, rounds);
}

static void tft_select(spi_device_handle_t dev, int dc, bool command,
                       const uint8_t *data, size_t len)
{
    gpio_set_level((gpio_num_t)dc, command ? 0 : 1);
    spi_transaction_t trans = {
        .length = len * 8,
        .tx_buffer = data,
    };
    ESP_ERROR_CHECK(spi_device_transmit(dev, &trans));
}

static void tft_cmd(spi_device_handle_t dev, int dc, uint8_t command)
{
    tft_select(dev, dc, true, &command, 1);
}

static void tft_data(spi_device_handle_t dev, int dc,
                     const uint8_t *data, size_t len)
{
    tft_select(dev, dc, false, data, len);
}

static void tft_init_one(spi_device_handle_t dev, int dc, int rst, uint16_t color)
{
    gpio_set_level((gpio_num_t)dc, 0);
    gpio_set_level((gpio_num_t)rst, 1);
    vTaskDelay(pdMS_TO_TICKS(5));
    gpio_set_level((gpio_num_t)rst, 0);
    vTaskDelay(pdMS_TO_TICKS(20));
    gpio_set_level((gpio_num_t)rst, 1);
    vTaskDelay(pdMS_TO_TICKS(120));

    tft_cmd(dev, dc, 0x01);
    vTaskDelay(pdMS_TO_TICKS(150));
    tft_cmd(dev, dc, 0x11);
    vTaskDelay(pdMS_TO_TICKS(120));
    uint8_t madctl = 0xC8;
    tft_cmd(dev, dc, 0x36);
    tft_data(dev, dc, &madctl, 1);
    uint8_t colmod = 0x05;
    tft_cmd(dev, dc, 0x3A);
    tft_data(dev, dc, &colmod, 1);
    tft_cmd(dev, dc, 0x29);
    vTaskDelay(pdMS_TO_TICKS(20));

    uint8_t area[4] = {0, 0, 0, 159};
    tft_cmd(dev, dc, 0x2B);
    tft_data(dev, dc, area, sizeof(area));
    area[0] = 0; area[1] = 0; area[2] = 0; area[3] = 127;
    tft_cmd(dev, dc, 0x2A);
    tft_data(dev, dc, area, sizeof(area));
    tft_cmd(dev, dc, 0x2C);

    uint8_t line[128 * 2];
    for (size_t i = 0; i < 128; i++) {
        line[i * 2] = (uint8_t)(color >> 8);
        line[i * 2 + 1] = (uint8_t)color;
    }
    for (size_t y = 0; y < 160; y++) tft_data(dev, dc, (uint8_t *)line, sizeof(line));
}

static esp_err_t display_init(void)
{
    gpio_config_t cs = {
        .pin_bit_mask = (1ULL << PROBE_PIN_TFT1_CS) |
                        (1ULL << PROBE_PIN_TFT2_CS),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&cs));
    gpio_set_level(PROBE_PIN_TFT1_CS, 1);
    gpio_set_level(PROBE_PIN_TFT2_CS, 1);

    gpio_config_t dc_rst = {
        .pin_bit_mask = (1ULL << PROBE_PIN_TFT1_DC) |
                        (1ULL << PROBE_PIN_TFT1_RST) |
                        (1ULL << PROBE_PIN_TFT2_DC) |
                        (1ULL << PROBE_PIN_TFT2_RST),
        .mode = GPIO_MODE_OUTPUT,
    };
    ESP_ERROR_CHECK(gpio_config(&dc_rst));
    gpio_set_level(PROBE_PIN_TFT1_DC, 0);
    gpio_set_level(PROBE_PIN_TFT2_DC, 0);
    gpio_set_level(PROBE_PIN_TFT1_RST, 1);
    gpio_set_level(PROBE_PIN_TFT2_RST, 1);
    spi_bus_config_t bus = {
        .sclk_io_num = PROBE_PIN_TFT_SCLK,
        .mosi_io_num = PROBE_PIN_TFT_MOSI,
        .miso_io_num = PROBE_PIN_TFT_MISO,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 8 * 128 * 2,
    };
    esp_err_t err = spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_CH_AUTO);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) return err;

    spi_device_interface_config_t cfg = {
        .clock_speed_hz = 20 * 1000 * 1000,
        .mode = 0,
        .spics_io_num = PROBE_PIN_TFT1_CS,
        .queue_size = 1,
    };
    err = spi_bus_add_device(SPI2_HOST, &cfg, &s_tft1);
    if (err != ESP_OK) return err;
    cfg.spics_io_num = PROBE_PIN_TFT2_CS;
    err = spi_bus_add_device(SPI2_HOST, &cfg, &s_tft2);
    if (err != ESP_OK) return err;

    tft_init_one(s_tft1, PROBE_PIN_TFT1_DC, PROBE_PIN_TFT1_RST, 0x001F);
    tft_init_one(s_tft2, PROBE_PIN_TFT2_DC, PROBE_PIN_TFT2_RST, 0xF800);
    ESP_LOGI(TAG, "two TFTs initialised: TFT1 CS=%d DC=%d RST=%d; TFT2 CS=%d DC=%d RST=%d",
             PROBE_PIN_TFT1_CS, PROBE_PIN_TFT1_DC, PROBE_PIN_TFT1_RST,
             PROBE_PIN_TFT2_CS, PROBE_PIN_TFT2_DC, PROBE_PIN_TFT2_RST);
    return ESP_OK;
}

static void joystick_init(void)
{
    adc_unit_t unit;
    adc_channel_t channel;
    if (adc_oneshot_io_to_channel(PROBE_PIN_JOYSTICK_X, &unit, &channel) == ESP_OK) {
        adc_oneshot_unit_init_cfg_t cfg = {.unit_id = unit};
        adc_oneshot_new_unit(&cfg, unit == ADC_UNIT_1 ? &s_adc1 : &s_adc2);
        adc_oneshot_chan_cfg_t chan_cfg = {
            .atten = ADC_ATTEN_DB_12,
            .bitwidth = ADC_BITWIDTH_DEFAULT,
        };
        adc_oneshot_config_channel(unit == ADC_UNIT_1 ? s_adc1 : s_adc2,
                                   channel, &chan_cfg);
        s_joy_x_unit = unit; s_joy_x_ch = channel; s_joy_x_ready = true;
    }
    if (adc_oneshot_io_to_channel(PROBE_PIN_JOYSTICK_Y, &unit, &channel) == ESP_OK) {
        adc_oneshot_unit_init_cfg_t cfg = {.unit_id = unit};
        adc_oneshot_unit_handle_t *handle = unit == ADC_UNIT_1 ? &s_adc1 : &s_adc2;
        if ((unit == ADC_UNIT_1 && !s_adc1) || (unit == ADC_UNIT_2 && !s_adc2)) {
            adc_oneshot_new_unit(&cfg, handle);
        }
        adc_oneshot_chan_cfg_t chan_cfg = {
            .atten = ADC_ATTEN_DB_12,
            .bitwidth = ADC_BITWIDTH_DEFAULT,
        };
        adc_oneshot_config_channel(*handle, channel, &chan_cfg);
        s_joy_y_unit = unit; s_joy_y_ch = channel; s_joy_y_ready = true;
    }
    gpio_config_t sw = {
        .pin_bit_mask = 1ULL << PROBE_PIN_JOYSTICK_SW,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&sw));
}

static int joystick_read(adc_unit_t unit, adc_channel_t channel)
{
    int raw = 0;
    adc_oneshot_unit_handle_t handle = unit == ADC_UNIT_1 ? s_adc1 : s_adc2;
    return handle ? adc_oneshot_read(handle, channel, &raw) == ESP_OK ? raw : -1 : -1;
}

/* Publisher task.  Kept separate from the display task on purpose: the MQTT
 * client can block when the broker is slow or the socket is being reconnected,
 * and a blocked publish must never freeze the screen the operator is reading. */
static void publish_task(void *arg)
{
    (void)arg;
    TickType_t next = xTaskGetTickCount();
    for (;;) {
        /* "SEND NOW" from the menu is a one-shot that must work even when the
         * periodic publisher is switched off. */
        if (probe_take_publish_request() && probe_mqtt_connected()) {
            float rms = 0.0f, peak = 0.0f;
            accel_window_stats(&rms, &peak);
            size_t idx = (s_wave_index + 127u) & 127u;
            probe_mqtt_publish_measurement(
                s_accel_history[0][idx], s_accel_history[1][idx],
                s_accel_history[2][idx], 0.0f, 0.0f, 0.0f,
                rms, 0.0f, peak, 0.0f);
        }
        /* "ZERO BASE" re-seats the gravity tracker.  It only has to nudge the
         * state the capture loop owns, which is why it goes through the same
         * slow tracker rather than writing the baseline directly. */
        if (probe_take_zero_request()) {
            for (int a = 0; a < 3; a++) s_accel_baseline[a] = 0.0f;
            ESP_LOGI(TAG, "accelerometer baseline re-zeroed");
        }
        if (probe_publish_enabled() && probe_mqtt_connected()) {
            float rms = 0.0f, peak = 0.0f;
            accel_window_stats(&rms, &peak);
            size_t idx = (s_wave_index + 127u) & 127u;
            probe_mqtt_publish_measurement(
                s_accel_history[0][idx], s_accel_history[1][idx],
                s_accel_history[2][idx], 0.0f, 0.0f, 0.0f,
                rms, 0.0f, peak, 0.0f);
        }
        vTaskDelayUntil(&next, pdMS_TO_TICKS(probe_publish_period_ms()));
    }
}

/* Joystick to menu-event translator.
 *
 * Direction is committed on the RELEASE edge, so holding the stick over is one
 * move rather than a repeat storm, and the switch is edge-detected with a
 * one-shot latch so a held button is one click. */
/* Median of five, in place.  Five is enough to reject a single-sample spike
 * (or two, if they are adjacent) and small enough that a real deflection is
 * reported after two sample periods at most. */
static int median5(const int *v)
{
    int a[5];
    memcpy(a, v, sizeof(a));
    for (int i = 1; i < 5; i++) {
        int key = a[i], j = i - 1;
        while (j >= 0 && a[j] > key) { a[j + 1] = a[j]; j--; }
        a[j + 1] = key;
    }
    return a[2];
}

static void menu_task(void *arg)
{
    (void)arg;
    probe_dir_t pending = PROBE_DIR_NONE;
    bool have_pending = false;
    bool sw_unlocked = true;

    int hx[PROBE_JOY_MEDIAN_N], vy[PROBE_JOY_MEDIAN_N];
    for (int i = 0; i < PROBE_JOY_MEDIAN_N; i++) { hx[i] = 2048; vy[i] = 2048; }
    int ring = 0;
    probe_dir_t candidate = PROBE_DIR_NONE;
    int candidate_count = 0;

    for (;;) {
        int jx = s_joy_x_ready ? joystick_read(s_joy_x_unit, s_joy_x_ch) : 2048;
        int jy = s_joy_y_ready ? joystick_read(s_joy_y_unit, s_joy_y_ch) : 2048;

        /* Axes are SWAPPED relative to the wiring: on this module the ADC
         * channel labelled X is the horizontal axis and the one labelled Y is
         * vertical.  The swap lives here, at the single place both channels
         * meet, so no other code has to know about it. */
        hx[ring] = jy;   /* horizontal */
        vy[ring] = jx;   /* vertical   */
        ring = (ring + 1) % PROBE_JOY_MEDIAN_N;
        const int hor = median5(hx);
        const int ver = median5(vy);

        /* Ring-down guard: the accelerometer and the stick are bolted to the
         * same housing, so a tap on it rattles the stick.
         *
         * The window is armed per tap but bounded per burst.  An uncapped
         * window -- the first revision used a flat 400 ms -- is re-armed by
         * every strike of a burst, so a run of hard taps held it asserted
         * continuously and the stick appeared dead.  Now the first tap of a
         * burst opens a PROBE_TAP_MUTE_BUDGET_MS budget, later taps inside the
         * budget may extend the window only up to its end. */
        static uint32_t mute_seen;
        static int64_t mute_until_us;
        static int64_t mute_budget_us;
        if (s_tap_seen != mute_seen) {
            mute_seen = s_tap_seen;
            int64_t now_us = esp_timer_get_time();
            if (now_us >= mute_until_us)
                mute_budget_us = now_us + (int64_t)PROBE_TAP_MUTE_BUDGET_MS * 1000;
            int64_t until = now_us + (int64_t)PROBE_TAP_MUTE_MS * 1000;
            if (until > mute_budget_us) until = mute_budget_us;
            if (until > mute_until_us) mute_until_us = until;
        }
        const bool mute = esp_timer_get_time() < mute_until_us;

        int sw = gpio_get_level(PROBE_PIN_JOYSTICK_SW);
        if (sw == 0 && sw_unlocked && !mute) {
            probe_menu_input(PROBE_DIR_CLICK);
            sw_unlocked = false;
        } else if (sw != 0) {
            sw_unlocked = true;
        }

        probe_dir_t d = PROBE_DIR_NONE;
        /* Vertical is inverted relative to the raw ADC direction on this
         * module: pushing the stick up raises the channel voltage. */
        if (ver > PROBE_JOY_RELEASE_HIGH) d = PROBE_DIR_UP;
        else if (ver < PROBE_JOY_RELEASE_LOW) d = PROBE_DIR_DOWN;
        else if (hor > PROBE_JOY_RELEASE_HIGH) d = PROBE_DIR_RIGHT;
        else if (hor < PROBE_JOY_RELEASE_LOW) d = PROBE_DIR_LEFT;

        if (mute) {
            if (d != PROBE_DIR_NONE) s_joy_muted++;
            candidate = PROBE_DIR_NONE;
            candidate_count = 0;
            pending = PROBE_DIR_NONE;
            have_pending = false;
        } else {
            /* Arm a direction only once it has been the same for
             * PROBE_JOY_CONFIRM_SAMPLES consecutive samples. */
            if (d != PROBE_DIR_NONE && d == candidate) {
                candidate_count++;
            } else {
                candidate = d;
                candidate_count = (d == PROBE_DIR_NONE) ? 0 : 1;
            }
            if (d != PROBE_DIR_NONE &&
                candidate_count >= PROBE_JOY_CONFIRM_SAMPLES) {
                pending = d;
                have_pending = true;
            } else if (d == PROBE_DIR_NONE && have_pending) {
                /* Commit on the release edge: holding the stick over is one
                 * move, not a repeat storm. */
                probe_menu_input(pending);
                have_pending = false;
            }
        }

        vTaskDelay(pdMS_TO_TICKS(PROBE_JOY_SAMPLE_MS));
    }
}

void app_main(void)
{
    i2c_master_bus_config_t bus_cfg = {
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .i2c_port = PROBE_I2C_PORT,
        .scl_io_num = PROBE_PIN_I2C_SCL,
        .sda_io_num = PROBE_PIN_I2C_SDA,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_cfg, &s_i2c));
    gpio_config_t tof_xshut = {
        .pin_bit_mask = 1ULL << PROBE_PIN_TOF_XSHUT,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&tof_xshut));
    gpio_set_level(PROBE_PIN_TOF_XSHUT, 1);
    vTaskDelay(pdMS_TO_TICKS(5));
    esp_err_t rgb_err = onboard_rgb_set_green();
    if (rgb_err != ESP_OK) ESP_LOGW(TAG, "onboard RGB LED setup failed: %s", esp_err_to_name(rgb_err));
    i2c_scan();

    if (imu_init() != ESP_OK) ESP_LOGE(TAG, "LSM6DS3-1 not available");
    if (tof_init() != ESP_OK) ESP_LOGE(TAG, "VL53L1X not available");
    bus_health_check();
    if (display_init() != ESP_OK) ESP_LOGE(TAG, "TFT initialisation failed");
    bus_health_check();
    joystick_init();
    probe_menu_init();
    /* Core assignment.
     *
     * Core 0 already carries the WiFi/lwIP and MQTT client tasks, so the two
     * jobs that talk to the network or drive the I2C sensors stay there and
     * share that core with the protocol stack rather than contending for the
     * one the display needs.
     *
     * Core 1 carries everything the operator can see or touch: the TFT refresh
     * (about 35 ms of blocking SPI per full frame pair) and the joystick poll.
     * A stalled frame therefore cannot delay a publish, and a slow broker
     * cannot leave the screen half-drawn. */
    BaseType_t r1 = xTaskCreatePinnedToCore(imu_capture_task, "imu_capture", 4096, NULL, 6, NULL, 0);
    BaseType_t r2 = xTaskCreatePinnedToCore(publish_task,    "publish",     6144, NULL, 3, NULL, 0);
    BaseType_t r3 = xTaskCreatePinnedToCore(waveform_task,   "waveform",    8192, NULL, 5, NULL, 1);
    BaseType_t r4 = xTaskCreatePinnedToCore(menu_task,       "menu",        4096, NULL, 4, NULL, 1);
    ESP_LOGI(TAG, "tasks: imu=%d pub=%d wf=%d menu=%d free_heap=%u",
             (int)r1, (int)r2, (int)r3, (int)r4, (unsigned)esp_get_free_heap_size());
}
