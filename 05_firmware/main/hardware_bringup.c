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

#include "probe_config.h"

static const char *TAG = "BRINGUP";
static i2c_master_bus_handle_t s_i2c;
static i2c_master_dev_handle_t s_imu;
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
static uint32_t s_stream_sequence;


static rmt_channel_handle_t s_rgb_channel;
static rmt_encoder_handle_t s_rgb_encoder;

static void stream_accel_sample(float x, float y, float z)
{
    static uint8_t batch[20 * 16];
    static size_t batch_length;
    uint8_t packet[20] = {0xA5, 0x5A};
    int32_t values[3] = {
        (int32_t)(x * 1000000.0f),
        (int32_t)(y * 1000000.0f),
        (int32_t)(z * 1000000.0f),
    };
    uint16_t distance = s_last_distance_valid ? s_last_distance_mm : 0;
    memcpy(packet + 2, &s_stream_sequence, sizeof(s_stream_sequence));
    memcpy(packet + 6, values, sizeof(values));
    memcpy(packet + 18, &distance, sizeof(distance));
    memcpy(batch + batch_length, packet, sizeof(packet));
    batch_length += sizeof(packet);
    if (batch_length == sizeof(batch)) {
        fwrite(batch, 1, batch_length, stdout);
        fflush(stdout);
        batch_length = 0;
    }
    s_stream_sequence++;
}

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

static esp_err_t imu_init(void)
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

    /* Accelerometer: 1.66 kHz, +/-2 g, high-performance mode. */
    err = i2c_write8(s_imu, 0x10, 0x80);
    if (err != ESP_OK) goto init_failed;
    err = i2c_write8(s_imu, 0x11, 0x00); /* gyro off */
    if (err != ESP_OK) goto init_failed;
    err = i2c_write8(s_imu, 0x12, 0x44); /* BDU + register auto-increment */
    if (err != ESP_OK) goto init_failed;
    vTaskDelay(pdMS_TO_TICKS(100));

    uint8_t ctrl1 = 0, ctrl3 = 0, status = 0;
    esp_err_t read_err = i2c_read(s_imu, 0x10, &ctrl1, 1);
    if (read_err == ESP_OK) read_err = i2c_read(s_imu, 0x12, &ctrl3, 1);
    if (read_err == ESP_OK) read_err = i2c_read(s_imu, 0x1E, &status, 1);
    if (read_err != ESP_OK) {
        err = read_err;
        goto init_failed;
    }
    ESP_LOGI(TAG, "LSM6DS3 config: CTRL1_XL=0x%02X CTRL3_C=0x%02X STATUS=0x%02X",
             ctrl1, ctrl3, status);
    if ((ctrl1 & 0xF0) == 0) {
        ESP_LOGE(TAG, "LSM6DS3 accelerometer is powered down (CTRL1_XL=0x%02X)", ctrl1);
        err = ESP_ERR_INVALID_STATE;
        goto init_failed;
    }
    return ESP_OK;

init_failed:
    ESP_LOGE(TAG, "LSM6DS3 initialisation failed: %s", esp_err_to_name(err));
    i2c_master_bus_rm_device(s_imu);
    s_imu = NULL;
    return err;
}

static esp_err_t imu_read_accel(float *x, float *y, float *z)
{
    uint8_t raw[6];
    for (int attempt = 0; attempt < 3; attempt++) {
        esp_err_t err = ESP_ERR_INVALID_RESPONSE;
        uint8_t reg = 0x28;
        err = i2c_master_transmit(s_imu, &reg, 1, 100);
        if (err == ESP_OK) err = i2c_master_receive(s_imu, raw, sizeof(raw), 100);
        if (err != ESP_OK) {
            if (attempt < 2) {
                taskYIELD();
                continue;
            }
            static uint32_t failures;
            failures++;
            if (failures <= 3 || (failures % 20) == 0) {
                ESP_LOGW(TAG, "LSM6DS3 output read failed: %s (failure %lu)",
                         esp_err_to_name(err), (unsigned long)failures);
            }
            return err;
        }
        break;
    }
    static unsigned sample_count;
    sample_count++;
    if (sample_count <= 5) {
        uint8_t status = 0;
        if (i2c_read(s_imu, 0x1E, &status, 1) == ESP_OK) {
            ESP_LOGI(TAG, "LSM6DS3 raw: %02X %02X %02X %02X %02X %02X status=0x%02X",
                     (unsigned)raw[0], (unsigned)raw[1], (unsigned)raw[2],
                     (unsigned)raw[3], (unsigned)raw[4], (unsigned)raw[5],
                     (unsigned)status);
        }
    }
    int16_t ix = (int16_t)((raw[1] << 8) | raw[0]);
    int16_t iy = (int16_t)((raw[3] << 8) | raw[2]);
    int16_t iz = (int16_t)((raw[5] << 8) | raw[4]);
    *x = ix * 0.000061f;
    *y = iy * 0.000061f;
    *z = iz * 0.000061f;
    return ESP_OK;
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

static void tft_fill(spi_device_handle_t dev, int dc, uint16_t color)
{
    tft_set_window(dev, dc, 0, 0, 127, 159);
    uint8_t line[128 * 2];
    for (size_t i = 0; i < 128; i++) {
        line[i * 2] = (uint8_t)(color >> 8);
        line[i * 2 + 1] = (uint8_t)color;
    }
    for (size_t y = 0; y < 160; y++) tft_data(dev, dc, (uint8_t *)line, sizeof(line));
}

static void tft_plot_point(spi_device_handle_t dev, int dc, uint8_t x, uint8_t y,
                           uint16_t color)
{
    tft_set_window(dev, dc, x, y, x, y);
    uint8_t pixel[2] = {(uint8_t)(color >> 8), (uint8_t)color};
    tft_data(dev, dc, pixel, sizeof(pixel));
}

static uint8_t graph_y(float value, float min_value, float max_value,
                       uint8_t top, uint8_t height)
{
    if (value < min_value) value = min_value;
    if (value > max_value) value = max_value;
    float scaled = (value - min_value) / (max_value - min_value);
    return (uint8_t)(top + height - 1 - scaled * (height - 1));
}

static const uint8_t s_digit_font[10][5] = {
    {0x1F, 0x11, 0x11, 0x11, 0x1F}, {0x00, 0x12, 0x1F, 0x10, 0x00},
    {0x1D, 0x15, 0x15, 0x15, 0x17}, {0x11, 0x15, 0x15, 0x15, 0x1F},
    {0x07, 0x04, 0x04, 0x04, 0x1F}, {0x17, 0x15, 0x15, 0x15, 0x1D},
    {0x1F, 0x15, 0x15, 0x15, 0x1D}, {0x01, 0x01, 0x01, 0x01, 0x1F},
    {0x1F, 0x15, 0x15, 0x15, 0x1F}, {0x17, 0x15, 0x15, 0x15, 0x1F},
};
static void frame_digit(uint8_t *frame, int digit, int x0, int y0,
                        int scale, uint16_t color);

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

static void frame_digit(uint8_t *frame, int digit, int x0, int y0,
                        int scale, uint16_t color)
{
    for (int source_y = 0; source_y < 5; source_y++) {
        uint8_t bits = s_digit_font[digit][source_y];
        for (int source_x = 0; source_x < 5; source_x++) {
            if ((bits & (1U << (4 - source_x))) == 0) continue;
            int x = source_y;
            int y = 4 - source_x;
            for (int sy = 0; sy < scale; sy++)
                for (int sx = 0; sx < scale; sx++)
                    frame_pixel(frame, x0 + x * scale + sx,
                                y0 + y * scale + sy, color);
        }
    }
}

static void frame_present(spi_device_handle_t dev, int dc, uint8_t *frame)
{
    tft_set_window(dev, dc, 0, 0, 127, 159);
    for (int y = 0; y < 160; y += 8) {
        tft_data(dev, dc, frame + y * 128 * 2, 8 * 128 * 2);
    }
}

static void draw_accel_screen(void)
{
    frame_clear(s_tft1_frame);
    const uint16_t colors[3] = {0xF800, 0x07E0, 0x001F};
    const uint8_t tops[3] = {0, 53, 106};
    for (int axis = 0; axis < 3; axis++) {
        for (uint8_t x = 2; x < 128; x += 2) {
            size_t a = (s_wave_index + x - 1) & 127;
            size_t b = (s_wave_index + x) & 127;
            uint8_t ya = graph_y(s_accel_history[axis][a], -0.5f, 0.5f, tops[axis], 52);
            uint8_t yb = graph_y(s_accel_history[axis][b], -0.5f, 0.5f, tops[axis], 52);
            frame_pixel(s_tft1_frame, x, ya, colors[axis]);
            frame_pixel(s_tft1_frame, x, yb, colors[axis]);
        }
    }
    frame_present(s_tft1, PROBE_PIN_TFT1_DC, s_tft1_frame);
}

static void draw_distance_digits(uint8_t *frame)
{
    if (s_last_distance_valid) {
        for (int digit = 0; digit < 6; digit++) {
            int divisor = digit == 0 ? 100000 :
                          digit == 1 ? 10000 :
                          digit == 2 ? 1000 :
                          digit == 3 ? 100 :
                          digit == 4 ? 10 : 1;
            frame_digit(frame, (s_last_distance_mm / divisor) % 10,
                        2 + digit * 21, 2, 4, 0xFFE0);
        }
    }
}

static void draw_accel_digits(uint8_t *frame)
{
    const uint16_t colors[3] = {0xF800, 0x07E0, 0x001F};
    for (int axis = 0; axis < 3; axis++) {
        int value = (int)(s_accel_history[axis][s_wave_index] * 10000.0f);
        if (value < 0) value = -value;
        if (value > 999999) value = 999999;
        for (int digit = 0; digit < 6; digit++) {
            int divisor = digit == 0 ? 100000 :
                          digit == 1 ? 10000 :
                          digit == 2 ? 1000 :
                          digit == 3 ? 100 :
                          digit == 4 ? 10 : 1;
            frame_digit(frame, (value / divisor) % 10,
                        2 + digit * 7, 25 + axis * 16, 1, colors[axis]);
        }
    }
}

static void draw_distance_screen(void)
{
    frame_clear(s_tft2_frame);
    for (uint8_t x = 2; x < 128; x += 2) {
        size_t a = (s_wave_index + x - 1) & 127;
        size_t b = (s_wave_index + x) & 127;
        uint8_t ya = graph_y(s_distance_history[a], 0.0f, 2000.0f, 76, 82);
        uint8_t yb = graph_y(s_distance_history[b], 0.0f, 2000.0f, 76, 82);
        frame_pixel(s_tft2_frame, x, ya, 0xFFE0);
        frame_pixel(s_tft2_frame, x, yb, 0xFFE0);
    }
    draw_distance_digits(s_tft2_frame);
    draw_accel_digits(s_tft2_frame);
    frame_present(s_tft2, PROBE_PIN_TFT2_DC, s_tft2_frame);
}

static void imu_capture_task(void *arg)
{
    (void)arg;
    for (;;) {
        float x = 0, y = 0, z = 0;
        if (s_imu != NULL && imu_read_accel(&x, &y, &z) == ESP_OK) {
            const float accel[3] = {x, y, z};
            for (int axis = 0; axis < 3; axis++) {
                s_accel_baseline[axis] +=
                    0.02f * (accel[axis] - s_accel_baseline[axis]);
                s_accel_history[axis][s_wave_index] =
                    accel[axis] - s_accel_baseline[axis];
            }
            stream_accel_sample(
                s_accel_history[0][s_wave_index],
                s_accel_history[1][s_wave_index],
                s_accel_history[2][s_wave_index]);
            s_wave_index = (s_wave_index + 1) & 127;
        }
        taskYIELD();
    }
}

static void waveform_task(void *arg)
{
    (void)arg;
    unsigned tof_errors = 0;
    TickType_t next_display = xTaskGetTickCount();
    TickType_t next_tof = next_display;
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
        if ((int32_t)(now - next_display) >= 0) {
            draw_accel_screen();
            draw_distance_screen();
            next_display = now + pdMS_TO_TICKS(20);
        }
        vTaskDelayUntil(&next_display, pdMS_TO_TICKS(20));
    }
}

static void bus_health_check(void)
{
    const int rounds = 32;
    if (s_imu != NULL) {
        unsigned who_hits = 0, accel_hits = 0;
        for (int i = 0; i < rounds; i++) {
            uint8_t who = 0;
            if (i2c_read(s_imu, 0x0F, &who, 1) == ESP_OK && who == 0x69) who_hits++;
            uint8_t accel = 0;
            if (i2c_read(s_imu, 0x28, &accel, 1) == ESP_OK) accel_hits++;
            vTaskDelay(pdMS_TO_TICKS(2));
        }
        ESP_LOGI(TAG, "bus health LSM6DS3: WHO_AM_I 0x69 %u/%d, OUTX_L_XL ok %u/%d",
                 who_hits, rounds, accel_hits, rounds);
    }
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

static void bringup_task(void *arg)
{
    (void)arg;
    for (;;) {
        float x = 0, y = 0, z = 0;
        int joy_x = s_joy_x_ready ? joystick_read(s_joy_x_unit, s_joy_x_ch) : -1;
        int joy_y = s_joy_y_ready ? joystick_read(s_joy_y_unit, s_joy_y_ch) : -1;
        esp_err_t accel_err = s_imu ? imu_read_accel(&x, &y, &z) : ESP_ERR_NOT_FOUND;
        if (accel_err == ESP_OK) {
            ESP_LOGI(TAG, "accel[g] x=%+.3f y=%+.3f z=%+.3f joystick x=%d y=%d sw=%d",
                     x, y, z, joy_x, joy_y,
                     gpio_get_level(PROBE_PIN_JOYSTICK_SW) == 0 ? 1 : 0);
        } else {
            ESP_LOGW(TAG, "LSM6DS3 read failed (%s); joystick x=%d y=%d sw=%d",
                     esp_err_to_name(accel_err), joy_x, joy_y,
                     gpio_get_level(PROBE_PIN_JOYSTICK_SW) == 0 ? 1 : 0);
        }
        vTaskDelay(pdMS_TO_TICKS(500));
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
    xTaskCreatePinnedToCore(imu_capture_task, "imu_capture", 4096, NULL, 6, NULL, 1);
    xTaskCreate(waveform_task, "waveform", 8192, NULL, 5, NULL);
    xTaskCreate(bringup_task, "bringup", 4096, NULL, 4, NULL);
}
