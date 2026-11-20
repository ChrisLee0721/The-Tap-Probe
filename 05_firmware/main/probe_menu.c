/* probe_menu.c -- operator menu on TFT1, WiFi station, MQTT client.
 *
 * Screen (128x160):
 *   y   0..13   title bar, breadcrumb of the page tree
 *   y  18..127  up to eight items at font scale 2 (8x11 cell, 14 px pitch)
 *   y 132..141  what the highlighted item currently holds / does
 *   y 146..155  the key legend
 *
 * The screen deliberately shows OPERATING LOGIC rather than measurements: the
 * item list says what the probe can be told to do, the band under it says what
 * the highlighted item is set to, and the legend says which stick move does
 * what.  Live numbers belong on TFT2 and in the web dashboard.
 */

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <math.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "mqtt_client.h"
#include "mbedtls/base64.h"

#include "probe_config.h"
#include "probe_menu.h"

static const char *TAG = "MENU";

/* ========================================================================
 * 1. Font
 *
 * A real 5x7 font, generated from readable ASCII art by tools/gen_font.py.
 * The previous version drew a 3x5 font at scale 2 to make the menu "bigger";
 * scaling by 2 turns every stroke into a 2x2 block, adjacent letters touch and
 * the text reads as mush.  Here the glyph itself is bigger: 7 px tall at
 * scale 1, 14 px at scale 2, with a full 1 px gap at every scale.
 * ===================================================================== */

#include "probe_font.h"

/* ========================================================================
 * 2. Frame helpers (128x160, RGB565 big endian)
 * ===================================================================== */

#define C_BG     0x0000
#define C_TITLE  0x0210
#define C_TEXT   0xFFFF
#define C_DIM    0x8410
#define C_SELBG  0x07FF
#define C_SELTX  0x0000
#define C_OK     0x07E0
#define C_BAD    0xF800
#define C_HINT   0xFFE0
#define C_ACCENT 0xFD20
#define C_BAR    0x0841

static void px(uint8_t *f, int x, int y, uint16_t c)
{
    if (x < 0 || x >= 128 || y < 0 || y >= 160) return;
    size_t i = ((size_t)y * 128u + (size_t)x) * 2u;
    f[i] = (uint8_t)(c >> 8);
    f[i + 1] = (uint8_t)c;
}

static void rect(uint8_t *f, int x, int y, int w, int h, uint16_t c)
{
    for (int yy = y; yy < y + h; yy++)
        for (int xx = x; xx < x + w; xx++)
            px(f, xx, yy, c);
}

/* Width of a string in pixels at a given scale. */
static int text_w(const char *s, int scale)
{
    return (int)strlen(s) * PROBE_FONT_ADV * scale;
}

static void text(uint8_t *f, int x, int y, const char *s, uint16_t c, int scale)
{
    int cx = x;
    for (; *s; s++) {
        const uint8_t *g = probe_font_glyph(*s);
        for (int col = 0; col < PROBE_FONT_W; col++)
            for (int row = 0; row < PROBE_FONT_H; row++)
                if ((g[col] >> row) & 1u)
                    rect(f, cx + col * scale, y + row * scale, scale, scale, c);
        cx += PROBE_FONT_ADV * scale;
        if (cx > 128) break;
    }
}

/* Truncating copy: at most \p max_chars glyph cells, so a long SSID or broker
 * URI cannot run off the panel. */
static void copy_trunc(char *dst, size_t n, const char *src, size_t max_chars)
{
    size_t i = 0;
    for (; i < max_chars && src[i] && i + 1 < n; i++) dst[i] = src[i];
    dst[i] = 0;
}

/* ========================================================================
 * 3. Menu state
 * ===================================================================== */

#define TEXT_MAX        40
#define CHARSET_LEN     66
#define NAV_DEPTH       6

static const char CHARSET[] =
    "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-_/:";

typedef enum {
    PG_MAIN = 0,
    PG_WIFI,
    PG_MQTT,
    PG_SENSOR,
    PG_DATA,
    PG_SYSTEM,
    PG_SCAN,
    PG_INFO,
    PG_EDIT_PASS,
    PG_EDIT_BROKER,
    PG_EDIT_DEVID,
} page_t;

typedef enum {
    IK_SUB = 0,   /* arg = page to push                    */
    IK_TOGGLE,    /* arg = setting id                       */
    IK_ACT,       /* arg = action id                        */
    IK_EDIT,      /* arg = editor target                    */
    IK_BACK,      /* pop one level                          */
    IK_INFO,      /* read-only row                          */
    IK_CYC,       /* arg = cycle id, steps through a list    */
} item_kind_t;

enum { SET_PUBLISH = 0, SET_TAPSTREAM, SET_QOS, SET_AUTOJOIN };
enum { ACT_RESCAN = 0, ACT_CONNECT_DEF, ACT_DROP_WIFI, ACT_MQTT_RESTART,
       ACT_ZERO, ACT_CLEAR, ACT_PUB_NOW, ACT_REBOOT };
enum { ED_PASS = 0, ED_BROKER, ED_DEVID };
enum { CYC_TAPTHRESH = 0, CYC_PUBPERIOD, CYC_POINT };

/* Step tables for the cycling items. */
static const float TAP_THRESH_STEPS[] = {0.10f, 0.25f, 0.50f, 1.00f};
#define TAP_THRESH_N 4
static const uint32_t PUB_PERIOD_STEPS[] = {1000u, 2000u, 5000u, 10000u};
#define PUB_PERIOD_N 4

typedef struct { uint8_t kind; uint8_t arg; const char *label; } item_t;

/* POINT ID sits on the top page, not in a submenu.  The grading layer is a
 * differential measurement across points, so switching points is the single
 * most frequent action of a survey -- burying it one level down meant an
 * entire session could be recorded on P0 without anyone noticing.  STATUS
 * moved into SYSTEM, where it already lived. */
static const item_t MAIN_ITEMS[] = {
    { IK_CYC,   CYC_POINT, "POINT ID"    },
    { IK_SUB,   PG_WIFI,   "WIFI LINK"   },
    { IK_SUB,   PG_MQTT,   "MQTT LINK"   },
    { IK_SUB,   PG_SENSOR, "SENSORS"     },
    { IK_SUB,   PG_DATA,   "TAP DATA"    },
    { IK_SUB,   PG_SYSTEM, "SYSTEM"      },
};
static const item_t WIFI_ITEMS[] = {
    { IK_INFO,   0,             "LINK"     },
    { IK_ACT,    ACT_RESCAN,    "SCAN AP"  },
    { IK_ACT,    ACT_CONNECT_DEF, "JOIN AP" },
    { IK_EDIT,   ED_PASS,       "PASSCODE" },
    { IK_TOGGLE, SET_AUTOJOIN,  "AUTO JOIN"},
    { IK_BACK,   0,             "BACK"     },
};
static const item_t MQTT_ITEMS[] = {
    { IK_INFO,   0,              "LINK"     },
    { IK_EDIT,   ED_BROKER,      "BROKER"   },
    { IK_TOGGLE, SET_PUBLISH,    "PUBLISH"  },
    { IK_TOGGLE, SET_TAPSTREAM,  "TAP STREAM" },
    { IK_TOGGLE, SET_QOS,        "QOS LEVEL" },
    { IK_BACK,   0,              "BACK"     },
};
static const item_t SENSOR_ITEMS[] = {
    { IK_INFO,   0,           "ACCEL"     },
    { IK_INFO,   0,           "RANGER"    },
    { IK_ACT,    ACT_ZERO,    "ZERO BASE" },
    { IK_INFO,   0,           "TAP COUNT" },
    { IK_BACK,   0,           "BACK"      },
};
static const item_t DATA_ITEMS[] = {
    { IK_CYC,    CYC_TAPTHRESH, "TAP LEVEL" },
    { IK_CYC,    CYC_PUBPERIOD, "SEND RATE" },
    { IK_ACT,    ACT_PUB_NOW, "SEND NOW"   },
    { IK_ACT,    ACT_CLEAR,   "CLEAR CNT"  },
    { IK_BACK,   0,           "BACK"       },
};
static const item_t SYSTEM_ITEMS[] = {
    { IK_SUB,    PG_INFO,        "STATUS"    },
    { IK_EDIT,   ED_DEVID,       "DEVICE ID" },
    { IK_ACT,    ACT_MQTT_RESTART, "RESTART MQ" },
    { IK_ACT,    ACT_DROP_WIFI,  "DROP WIFI" },
    { IK_ACT,    ACT_REBOOT,     "REBOOT"    },
    { IK_BACK,   0,              "BACK"      },
};

static page_t s_page;
static int    s_sel;
static int    s_editor_pos;
static char   s_editor_buf[TEXT_MAX + 1];
static int    s_edit_target;
static page_t s_stack_page[NAV_DEPTH];
static int    s_stack_sel[NAV_DEPTH];
static int    s_depth;
static volatile uint32_t s_generation;

/* --- scanned access points ------------------------------------------- */
#define AP_MAX 16
struct scan_result { char ssid[33]; int8_t rssi; uint8_t secure; };
static struct scan_result s_aps[AP_MAX];
static int s_ap_count;
static volatile bool s_scan_wanted;
static volatile bool s_scan_busy;

/* --- network state ---------------------------------------------------- */
static volatile bool s_wifi_up;
static volatile bool s_mqtt_up;
static volatile uint32_t s_pub_count;
static volatile bool s_publish_enabled = true;
static volatile bool s_tap_stream = true;
/* Continuous 6.66 kHz batch stream (cmd "wave_stream").  Off by default: it is
 * ~54 kB/s of base64 and would otherwise run the link flat out. */
static volatile bool s_wave_stream_on;
static uint32_t      s_stream_seq;
static volatile bool s_autojoin = true;
static volatile int  s_qos = PROBE_DEFAULT_MQTT_QOS;
static volatile uint32_t s_pub_period_ms = PROBE_DEFAULT_PUB_PERIOD_MS;
static volatile float s_tap_thresh_g = PROBE_TAP_THRESH_G;
/* Which measurement point the operator is standing on.  The grading layer on
 * the PC side is a differential measurement (§7.7.1): every tap is compared
 * against a reference region, so a tap that does not say where it was taken
 * cannot be graded at all.  Six points covers the bench grid. */
static volatile int s_point_idx = 0;
#define POINT_MAX 64
/* The web owns the grid: it decides how many rows and columns the wall is cut
 * into and sends a flat index (row * cols + col).  The device keeps only the
 * shape so the local POINT ID row and the on-screen grid agree with the
 * browser, and so the menu cannot cycle into a cell that does not exist. */
static int s_grid_rows = 3;
static int s_grid_cols = 3;
static int grid_cells(void) { return s_grid_rows * s_grid_cols; }
static int  s_rssi = -127;
static char s_broker_uri[128];
static char s_dev_id[24];
static char s_sta_ssid[33];
static char s_sta_pass[65];
static volatile int s_retry;
static esp_mqtt_client_handle_t s_mqtt;

/* --- sensor status shown on the SENSOR page --------------------------- */
static volatile bool s_imu_ok;
static volatile bool s_tof_ok;
static volatile uint16_t s_tof_mm;
static volatile uint32_t s_tap_count;

/* --- tap waveform hand-off --------------------------------------------
 * The capture task fills one slot and raises the flag; the display-side pump
 * encodes and publishes the other.  Encoding 512 frames is 4 kB of base64 and
 * a blocking socket write, which must never sit between two FIFO drains. */
static int16_t  s_wave_slot[2][PROBE_TAP_WINDOW * 3];
static int      s_wave_len[2];
static int      s_wave_pre[2];
static int      s_wave_trig[2];
static int      s_wave_fs[2];
static volatile int s_wave_wr;
static volatile int s_wave_pending = -1;
static char     s_wave_b64[((PROBE_TAP_WINDOW * 3 * 2) + 2) / 3 * 4 + 8];
static volatile bool s_pub_wanted;

static volatile bool s_zero_wanted;

static void editor_begin(void);
static void pop_page(void);
static void push_page(page_t p);
static void publish_event(const char *ev);

static void bump(void) { s_generation++; }
uint32_t probe_menu_generation(void) { return s_generation; }

/* ========================================================================
 * 3b. Settings that survive a power cycle
 *
 * The broker address is a property of the PC running the broker, so carrying
 * the probe to another machine must not mean re-typing an IP at every boot.
 * Everything the joystick can change lives in one NVS namespace; the
 * compile-time values in probe_config.h stay the factory fallback for a board
 * with an erased flash.
 * ===================================================================== */
#define CFG_NS "probe_cfg"

static bool cfg_load(const char *key, char *out, size_t n)
{
    nvs_handle_t h;
    out[0] = 0;
    if (nvs_open(CFG_NS, NVS_READONLY, &h) != ESP_OK) return false;
    size_t len = n;
    esp_err_t err = nvs_get_str(h, key, out, &len);
    nvs_close(h);
    if (err != ESP_OK) { out[0] = 0; return false; }
    return out[0] != 0;
}

static void cfg_save(const char *key, const char *val)
{
    nvs_handle_t h;
    if (nvs_open(CFG_NS, NVS_READWRITE, &h) != ESP_OK) return;
    esp_err_t err = (val && val[0]) ? nvs_set_str(h, key, val)
                                    : nvs_erase_key(h, key);
    if (err == ESP_OK) err = nvs_commit(h);
    nvs_close(h);
    ESP_LOGI(TAG, "saved %s in NVS (%s)", key, esp_err_to_name(err));
}

static int cfg_load_int(const char *key, int fallback)
{
    nvs_handle_t h;
    int32_t v = 0;
    if (nvs_open(CFG_NS, NVS_READONLY, &h) != ESP_OK) return fallback;
    esp_err_t err = nvs_get_i32(h, key, &v);
    nvs_close(h);
    return err == ESP_OK ? (int)v : fallback;
}

static void cfg_save_int(const char *key, int v)
{
    nvs_handle_t h;
    if (nvs_open(CFG_NS, NVS_READWRITE, &h) != ESP_OK) return;
    esp_err_t err = nvs_set_i32(h, key, (int32_t)v);
    if (err == ESP_OK) err = nvs_commit(h);
    nvs_close(h);
}

/* Topic builder.  Every publish uses this so that changing the device id at
 * run time moves all four topics together. */
static void topic_of(const char *leaf, char *buf, size_t n)
{
    snprintf(buf, n, "%s/%s/%s", PROBE_TOPIC_BASE, s_dev_id, leaf);
}

/* ========================================================================
 * 4. WiFi station
 * ===================================================================== */

static const char *wifi_state_str(void)
{
    if (s_wifi_up) return "ONLINE";
    return s_retry > 0 ? "RETRY" : "OFFLINE";
}

static void wifi_apply_and_connect(const char *ssid, const char *pass)
{
    wifi_config_t cfg;
    memset(&cfg, 0, sizeof(cfg));
    strncpy((char *)cfg.sta.ssid, ssid, sizeof(cfg.sta.ssid) - 1);
    strncpy((char *)cfg.sta.password, pass, sizeof(cfg.sta.password) - 1);
    cfg.sta.threshold.authmode = WIFI_AUTH_OPEN;
    /* Some consumer APs run WPA2/WPA3 transition mode; advertising PMF
     * capability without requiring it avoids AUTH_EXPIRE on those. */
    cfg.sta.pmf_cfg.capable = true;
    cfg.sta.pmf_cfg.required = false;
    strncpy(s_sta_ssid, ssid, sizeof(s_sta_ssid) - 1);
    strncpy(s_sta_pass, pass, sizeof(s_sta_pass) - 1);

    if (s_wifi_up) {
        esp_wifi_disconnect();
        vTaskDelay(pdMS_TO_TICKS(100));
    }
    esp_wifi_set_config(WIFI_IF_STA, &cfg);
    esp_err_t err = esp_wifi_connect();
    ESP_LOGI(TAG, "wifi connect to '%s' -> %s", ssid, esp_err_to_name(err));
    bump();
}

static void mqtt_start(void);
static void mqtt_restart(void);

static void wifi_event_handler(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        wifi_event_sta_disconnected_t *ev = (wifi_event_sta_disconnected_t *)data;
        s_wifi_up = false;
        s_mqtt_up = false;
        ESP_LOGW(TAG, "wifi disconnected, reason=%d", ev ? ev->reason : -1);
        /* The IDF driver does not retry by itself once the station has been
         * started explicitly; without this the probe stays offline after the
         * first failed handshake. */
        if (s_autojoin && s_sta_ssid[0] != 0) {
            s_retry++;
            esp_wifi_connect();
        }
        bump();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        s_wifi_up = true;
        s_retry = 0;
        ESP_LOGI(TAG, "got ip");
        mqtt_start();
        bump();
    }
}

/* ========================================================================
 * 5. Access-point scan
 * ===================================================================== */

/* Log every visible AP once at boot: the SSID list, its length, its bytes and
 * its auth mode are the three facts needed to tell "wrong password" from
 * "network not in range" from "5 GHz only". */
static void log_ap_table(const wifi_ap_record_t *recs, int n)
{
    for (int i = 0; i < n; i++) {
        char hex[3 * 33 + 1];
        int hn = 0;
        int slen = (int)strnlen((const char *)recs[i].ssid, 32);
        for (int k = 0; k < slen && hn < (int)sizeof(hex) - 3; k++)
            hn += snprintf(hex + hn, sizeof(hex) - (size_t)hn, "%02x", recs[i].ssid[k]);
        hex[hn] = 0;
        ESP_LOGI(TAG, "AP[%d] len=%d rssi=%d auth=%d hex=%s",
                 i, slen, recs[i].rssi, (int)recs[i].authmode, hex);
    }
}

static void scan_task(void *arg)
{
    (void)arg;
    bool boot_scanned = false;
    uint8_t reason = WIFI_REASON_NO_AP_FOUND;
    for (;;) {
        if (!boot_scanned && s_wifi_up == false) {
            /* Let the station settle: a scan issued before the driver has
             * associated can legitimately return an empty list. */
            vTaskDelay(pdMS_TO_TICKS(1500));
            if (!s_wifi_up) {
                boot_scanned = true;
                wifi_scan_config_t sc0;
                memset(&sc0, 0, sizeof(sc0));
                if (esp_wifi_scan_start(&sc0, true) == ESP_OK) {
                    uint16_t n0 = 16;
                    wifi_ap_record_t r0[16];
                    if (esp_wifi_scan_get_ap_records(&n0, r0) == ESP_OK) {
                        ESP_LOGI(TAG, "boot scan: %u ap(s)", n0);
                        log_ap_table(r0, n0);
                    }
                }
            }
        }
        if (s_scan_wanted) {
            s_scan_wanted = false;
            s_scan_busy = true;
            const bool was_up = s_wifi_up;
            wifi_scan_config_t sc;
            memset(&sc, 0, sizeof(sc));
            sc.show_hidden = true;
            sc.scan_type = WIFI_SCAN_TYPE_ACTIVE;
            sc.scan_time.active.min = 120;
            sc.scan_time.active.max = 300;

            /* A scan while associated is legal on this driver: the station
             * leaves the channel for the dwell time and the association is
             * restored afterwards, at the cost of a few lost frames.  The
             * previous revision refused outright, which in practice meant the
             * row did nothing at all -- by the time an operator reaches the
             * menu the device is almost always already associated, so the
             * refusal fired every single time and the page just said NO AP. */
            esp_err_t err = esp_wifi_scan_start(&sc, true);
            if (err == ESP_OK) {
                uint16_t n = AP_MAX;
                wifi_ap_record_t recs[AP_MAX];
                if (esp_wifi_scan_get_ap_records(&n, recs) == ESP_OK) {
                    if (n > AP_MAX) n = AP_MAX;
                    s_ap_count = n;
                    s_sel = 0;
                    for (int i = 0; i < n; i++) {
                        memset(&s_aps[i], 0, sizeof(s_aps[i]));
                        strncpy(s_aps[i].ssid, (const char *)recs[i].ssid, 32);
                        s_aps[i].rssi = recs[i].rssi;
                        s_aps[i].secure = recs[i].authmode != WIFI_AUTH_OPEN;
                    }
                    ESP_LOGI(TAG, "scan found %u ap(s)", (unsigned)n);
                } else {
                    ESP_LOGW(TAG, "scan returned no record list");
                }
            } else {
                ESP_LOGW(TAG, "scan failed: %s", esp_err_to_name(err));
            }
            /* If the dwell did cost the association, put it back rather than
             * leaving the probe offline until the next reconnect attempt. */
            if (was_up && !s_wifi_up) {
                ESP_LOGW(TAG, "scan dropped the link, reconnecting");
                esp_wifi_connect();
            }
            s_scan_busy = false;
            bump();
        }
        vTaskDelay(pdMS_TO_TICKS(200));
    }
    (void)reason;
}

/* ========================================================================
 * 6. MQTT
 * ===================================================================== */

/* Minimal field lookup: the command payloads are a handful of flat string and
 * boolean keys, and pulling in a full JSON parser to read six of them would
 * cost more flash than the whole menu. */
static bool json_str(const char *js, const char *key, char *out, size_t n)
{
    char pat[32];
    snprintf(pat, sizeof(pat), "\"%s\"", key);
    const char *p = strstr(js, pat);
    if (!p) return false;
    p = strchr(p + strlen(pat), ':');
    if (!p) return false;
    p++;
    while (*p == ' ') p++;
    if (*p != '"') return false;
    p++;
    size_t i = 0;
    while (*p && *p != '"' && i + 1 < n) out[i++] = *p++;
    out[i] = 0;
    return true;
}

static bool json_bool(const char *js, const char *key, bool *out)
{
    char pat[32];
    snprintf(pat, sizeof(pat), "\"%s\"", key);
    const char *p = strstr(js, pat);
    if (!p) return false;
    p = strchr(p + strlen(pat), ':');
    if (!p) return false;
    p++;
    while (*p == ' ') p++;
    if (strncmp(p, "true", 4) == 0)  { *out = true;  return true; }
    if (strncmp(p, "false", 5) == 0) { *out = false; return true; }
    /* JSON numbers are common from the browser side ({"on": 1}); accept them
     * so a command is not silently ignored just because of the literal form. */
    if (*p == '1') { *out = true;  return true; }
    if (*p == '0') { *out = false; return true; }
    return false;
}

static bool json_float(const char *js, const char *key, float *out)
{
    char pat[32];
    snprintf(pat, sizeof(pat), "\"%s\"", key);
    const char *p = strstr(js, pat);
    if (!p) return false;
    p = strchr(p + strlen(pat), ':');
    if (!p) return false;
    p++;
    while (*p == ' ') p++;
    char *end = NULL;
    float v = strtof(p, &end);
    if (end == p) return false;
    *out = v;
    return true;
}

static void publish_event(const char *ev)
{
    if (s_mqtt == NULL || !s_mqtt_up) return;
    char topic[96];
    char body[96];
    topic_of(PROBE_TOPIC_EVENT, topic, sizeof(topic));
    snprintf(body, sizeof(body), "{\"dev\":\"%s\",\"ev\":\"%s\"}", s_dev_id, ev);
    esp_mqtt_client_publish(s_mqtt, topic, body, 0, 0, 0);
}

static void cmd_handle(const char *js, int len)
{
    char cmd[20] = {0};
    char extra[40] = "";
    if (!json_str(js, "cmd", cmd, sizeof(cmd))) return;
    bool on = false;
    bool have_on = json_bool(js, "on", &on);
    char ack[192];
    const char *ack_ev = "ack";

    if (strcmp(cmd, "publish") == 0) {
        if (have_on) s_publish_enabled = on;
    } else if (strcmp(cmd, "stream") == 0) {
        if (have_on) s_tap_stream = on;
    } else if (strcmp(cmd, "wave_stream") == 0) {
        /* Continuous batch stream for the live waterfall.  Off by default: it
         * is 40 kB/s of sample data and would run the link flat out. */
        if (have_on) s_wave_stream_on = on;
        ack_ev = "wave_stream";
    } else if (strcmp(cmd, "reboot") == 0) {
        ack_ev = "reboot";
        bump();
        vTaskDelay(pdMS_TO_TICKS(200));
        esp_restart();
    } else if (strcmp(cmd, "devid") == 0) {
        char v[24] = {0};
        if (json_str(js, "v", v, sizeof(v)) && v[0]) {
            strncpy(s_dev_id, v, sizeof(s_dev_id) - 1);
            cfg_save("devid", s_dev_id);
            mqtt_restart();
        }
    } else if (strcmp(cmd, "thresh") == 0) {
        float v = 0.0f;
        if (json_float(js, "v", &v) && v >= 0.01f && v <= 8.0f) s_tap_thresh_g = v;
        ack_ev = "thresh";
        bump();
    } else if (strcmp(cmd, "scan") == 0) {
        s_scan_wanted = true;
        ack_ev = "scan";
    } else if (strcmp(cmd, "grid") == 0) {
        /* {"cmd":"grid","rows":3,"cols":3}.  Sent when the browser changes the
         * planned grid, so the device displays the same shape. */
        float r = 0.0f, cc = 0.0f;
        if (json_float(js, "rows", &r) && json_float(js, "cols", &cc)) {
            int rr = (int)r, c2 = (int)cc;
            if (rr >= 2 && rr <= 8) s_grid_rows = rr;
            if (c2 >= 2 && c2 <= 8) s_grid_cols = c2;
            if (s_point_idx >= grid_cells()) s_point_idx = grid_cells() - 1;
            cfg_save_int("rows", s_grid_rows);
            cfg_save_int("cols", s_grid_cols);
        }
        ack_ev = "grid";
        snprintf(extra, sizeof(extra), ",\"rows\":%d,\"cols\":%d",
                 s_grid_rows, s_grid_cols);
        bump();
    } else if (strcmp(cmd, "point") == 0) {
        float v = 0.0f;
        if (json_float(js, "v", &v) && v >= 0.0f && v < (float)POINT_MAX)
            s_point_idx = (int)v;
        ack_ev = "point";
        /* Echo the point back: the PC side follows the operator's point, and
         * the ack is the only frame that arrives when the button is pressed
         * but before the first tap of the new point. */
        snprintf(extra, sizeof(extra), ",\"pt\":\"P%d\"", s_point_idx);
        bump();
    } else if (strcmp(cmd, "zero") == 0) {
        ack_ev = "zero";
    } else {
        ack_ev = "unknown";
    }
    ESP_LOGI(TAG, "cmd '%s' len=%d", cmd, len);
    if (s_mqtt != NULL && s_mqtt_up) {
        char topic[96];
        topic_of(PROBE_TOPIC_EVENT, topic, sizeof(topic));
        snprintf(ack, sizeof(ack),
                 "{\"dev\":\"%s\",\"ev\":\"%s\",\"cmd\":\"%s\",\"ok\":%s%s}",
                 s_dev_id, ack_ev, cmd, strcmp(ack_ev, "unknown") ? "true" : "false",
                 extra);
        esp_mqtt_client_publish(s_mqtt, topic, ack, 0, 0, 0);
    }
    bump();
}

static void mqtt_event_handler(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)base;
    esp_mqtt_event_handle_t ev = (esp_mqtt_event_handle_t)data;
    switch (id) {
    case MQTT_EVENT_CONNECTED: {
        s_mqtt_up = true;
        ESP_LOGI(TAG, "mqtt connected");
        /* Retained online state: until this lands the broker only has the will. */
        char t[96];
        topic_of(PROBE_TOPIC_STATUS, t, sizeof(t));
        esp_mqtt_client_publish(ev->client, t, "online", 0, 1, 1);
        topic_of(PROBE_TOPIC_CMD, t, sizeof(t));
        int mid = esp_mqtt_client_subscribe(ev->client, t, 1);
        ESP_LOGI(TAG, "subscribed %s mid=%d", t, mid);
        bump();
        break;
    }
    case MQTT_EVENT_DISCONNECTED:
        s_mqtt_up = false;
        ESP_LOGW(TAG, "mqtt disconnected");
        bump();
        break;
    case MQTT_EVENT_DATA:
        if (ev->data && ev->data_len > 0 && ev->topic_len > 0) {
            char body[256];
            int n = ev->data_len < (int)sizeof(body) - 1 ? ev->data_len : (int)sizeof(body) - 1;
            memcpy(body, ev->data, (size_t)n);
            body[n] = 0;
            cmd_handle(body, ev->data_len);
        }
        break;
    case MQTT_EVENT_PUBLISHED:
        /* Deliberately NOT counted here.  This event only fires once a QoS 1
         * or QoS 2 message is acknowledged; the measurement frames go out at
         * QoS 0 and would never be counted, so the sequence number in the
         * payload would sit at a small constant.  Each publisher counts its
         * own send instead. */
        break;
    default:
        break;
    }
}

static void mqtt_start(void)
{
    if (s_mqtt != NULL) return;

    esp_mqtt_client_config_t cfg;
    memset(&cfg, 0, sizeof(cfg));
    cfg.broker.address.uri = s_broker_uri;
    cfg.credentials.client_id = s_dev_id;
    cfg.buffer.size = PROBE_MQTT_BUFFER_SIZE;
    /* One 1024-frame tap window is 6144 bytes of sample data, 8192 as base64,
     * plus the JSON head; the default 1 kB transmit buffer would reject it. */
    cfg.buffer.out_size = 16384;

    static char will_topic[96];
    topic_of(PROBE_TOPIC_STATUS, will_topic, sizeof(will_topic));
    cfg.session.last_will.topic = will_topic;
    cfg.session.last_will.msg = "offline";
    cfg.session.last_will.qos = 1;
    cfg.session.last_will.retain = 1;
    cfg.session.keepalive = PROBE_MQTT_KEEPALIVE_S;
    cfg.network.reconnect_timeout_ms = PROBE_MQTT_RECONNECT_MS;

    s_mqtt = esp_mqtt_client_init(&cfg);
    if (s_mqtt == NULL) {
        ESP_LOGE(TAG, "mqtt init failed");
        return;
    }
    esp_mqtt_client_register_event(s_mqtt, ESP_EVENT_ANY_ID, mqtt_event_handler, NULL);
    esp_err_t err = esp_mqtt_client_start(s_mqtt);
    ESP_LOGI(TAG, "mqtt start (%s) -> %s", s_broker_uri, esp_err_to_name(err));
}

static void mqtt_restart(void)
{
    if (s_mqtt == NULL) { mqtt_start(); return; }
    esp_mqtt_client_stop(s_mqtt);
    esp_mqtt_client_destroy(s_mqtt);
    s_mqtt = NULL;
    s_mqtt_up = false;
    vTaskDelay(pdMS_TO_TICKS(100));
    mqtt_start();
}

/* ========================================================================
 * 7. Uplink: summary frame, tap window, pump
 * ===================================================================== */

void probe_mqtt_publish_measurement(float ax1, float ay1, float az1,
                                    float ax2, float ay2, float az2,
                                    float rms1, float rms2,
                                    float peak1, float peak2)
{
    if (s_mqtt == NULL || !s_mqtt_up) return;

    wifi_ap_record_t ap;
    if (esp_wifi_sta_get_ap_info(&ap) == ESP_OK) s_rssi = ap.rssi;

    char topic[96];
    char payload[320];
    topic_of(PROBE_TOPIC_MEASUREMENT, topic, sizeof(topic));
    /* The body module is optional.  Report the second channel only when a
     * sample from it actually carries energy; a row of zeros would read as a
     * measured quiet channel rather than as "not fitted". */
    char ch2[96];
    if (peak2 > 0.0001f) {
        snprintf(ch2, sizeof(ch2),
                 ",\"t2\":[%.3f,%.3f,%.3f],\"rms2\":%.4f,\"pk2\":%.4f",
                 ax2, ay2, az2, rms2, peak2);
    } else {
        ch2[0] = 0;
    }
    s_pub_count++;
    int n = snprintf(payload, sizeof(payload),
        "{\"dev\":\"%s\",\"pt\":\"P%d\",\"n\":%lu,"
        "\"t1\":[%.3f,%.3f,%.3f],"
        "\"rms1\":%.4f,\"pk1\":%.4f,\"rssi\":%d%s}",
        s_dev_id, s_point_idx, (unsigned long)s_pub_count,
        ax1, ay1, az1, rms1, peak1, s_rssi, ch2);
    if (n > 0) esp_mqtt_client_publish(s_mqtt, topic, payload, 0, s_qos, 0);
    bump();
}

/* ---- continuous batch stream -------------------------------------------
 *
 * One message per FIFO drain (about 20 ms, ~133 sample sets).  Base64 keeps the
 * browser side identical to the tap payload, and at 50 messages/s the 33 %
 * expansion is still only ~54 kB/s.  Publishing straight from the capture task
 * is safe because the FIFO buffers 205 ms: a stalled socket delays samples, it
 * does not lose them, as long as the stall stays under that.
 */
void probe_mqtt_publish_stream(const int16_t *xyz, int frames, int fs)
{
    if (!s_wave_stream_on || s_mqtt == NULL || !s_mqtt_up) return;
    if (frames <= 0) return;
    if (frames > 256) frames = 256;

    size_t olen = 0;
    if (mbedtls_base64_encode((unsigned char *)s_wave_b64, sizeof(s_wave_b64) - 1,
                              &olen, (const unsigned char *)xyz,
                              (size_t)frames * 6u) != 0)
        return;

    static char out[1600];
    int n = snprintf(out, sizeof(out),
                     "{\"dev\":\"%s\",\"pt\":\"P%d\",\"seq\":%lu,"
                     "\"fs\":%d,\"n\":%d,\"d\":\"",
                     s_dev_id, s_point_idx,
                     (unsigned long)(++s_stream_seq), fs, frames);
    if (n <= 0 || (size_t)n + olen + 3u > sizeof(out)) return;
    memcpy(&out[n], s_wave_b64, olen);
    n += (int)olen;
    out[n++] = '"';
    out[n++] = '}';
    out[n] = 0;

    char topic[96];
    topic_of(PROBE_TOPIC_STREAM, topic, sizeof(topic));
    esp_mqtt_client_publish(s_mqtt, topic, out, 0, 0, 0);
}

void probe_mqtt_publish_waveform(const int16_t *xyz, int frames, int pre, int trig,
                                  int fs)
{
    if (!s_tap_stream || frames <= 0 || frames > PROBE_TAP_WINDOW) return;
    if (s_wave_pending >= 0) {
        /* The pump has not caught up.  Dropping is the correct response: the
         * alternative is overwriting a window that is half-encoded. */
        static uint32_t dropped;
        dropped++;
        if (dropped == 1 || (dropped % 20) == 0)
            ESP_LOGW(TAG, "waveform dropped, %lu so far", (unsigned long)dropped);
        return;
    }
    int slot = s_wave_wr;
    memcpy(s_wave_slot[slot], xyz, (size_t)frames * 3u * sizeof(int16_t));
    s_wave_len[slot] = frames;
    s_wave_pre[slot] = pre;
    s_wave_trig[slot] = trig;
    s_wave_fs[slot] = fs;
    s_wave_wr = slot ^ 1;
    s_wave_pending = slot;
}

/* Encodes and publishes whatever window is waiting.  Called from the display
 * task, which owns no timing-critical work of its own: a 4 kB base64 encode
 * plus a socket write must never sit between two FIFO drains. */
void probe_mqtt_pump(void)
{
    /* Re-assert the retained "online" periodically.
     *
     * A hard reset (or a reflash) kills the old TCP session, and the broker
     * only then publishes the last will -- which is retained, and therefore
     * lands AFTER the new session has already said "online".  The retained
     * value stays "offline" for the whole of the next boot, which is exactly
     * what a dashboard reads.  Republishing on a timer makes the state
     * self-correcting instead of depending on the order of two events the
     * device cannot control. */
    static int64_t next_status_us;
    if (s_mqtt_up) {
        int64_t now = esp_timer_get_time();
        if (now >= next_status_us) {
            next_status_us = now + (int64_t)PROBE_MQTT_STATUS_PERIOD_MS * 1000;
            char st[96];
            topic_of(PROBE_TOPIC_STATUS, st, sizeof(st));
            esp_mqtt_client_publish(s_mqtt, st, "online", 0, 1, 1);
        }
    }

    int slot = s_wave_pending;
    if (slot < 0) return;
    s_wave_pending = -1;

    if (s_mqtt == NULL || !s_mqtt_up) return;

    const int frames = s_wave_len[slot];
    size_t olen = 0;
    int rc = mbedtls_base64_encode((unsigned char *)s_wave_b64,
                                   sizeof(s_wave_b64) - 1, &olen,
                                   (const unsigned char *)s_wave_slot[slot],
                                   (size_t)frames * 3u * sizeof(int16_t));
    if (rc != 0) {
        ESP_LOGW(TAG, "base64 encode failed rc=%d", rc);
        return;
    }
    s_wave_b64[olen] = 0;

    char topic[96];
    topic_of(PROBE_TOPIC_WAVEFORM, topic, sizeof(topic));

    char head[192];
    snprintf(head, sizeof(head),
        "{\"dev\":\"%s\",\"pt\":\"P%d\",\"seq\":%lu,\"tap\":%lu,\"fs\":%d,"
        "\"n\":%d,\"scale\":%d,\"pre\":%d,\"trig\":%d,\"pkg\":%.3f,\"d\":\"",
        s_dev_id, s_point_idx, (unsigned long)(s_pub_count + 1u),
        (unsigned long)s_tap_count, s_wave_fs[slot], frames,
        (int)PROBE_IMU_LSB_PER_G, s_wave_pre[slot], s_wave_trig[slot],
        (double)((float)s_wave_trig[slot] / PROBE_IMU_LSB_PER_G));

    static char out[256 + sizeof(s_wave_b64) + 8];
    int on = snprintf(out, sizeof(out), "%s%s\"}", head, s_wave_b64);
    if (on > 0 && on < (int)sizeof(out)) {
        esp_mqtt_client_publish(s_mqtt, topic, out, on, 0, 0);
        s_pub_count++;
    } else {
        ESP_LOGW(TAG, "waveform payload too large: %d", on);
    }
    bump();
}

bool probe_take_publish_request(void)
{
    bool v = s_pub_wanted;
    s_pub_wanted = false;
    return v;
}

bool probe_take_zero_request(void)
{
    bool v = s_zero_wanted;
    s_zero_wanted = false;
    return v;
}

/* ========================================================================
 * 8. Public queries
 * ===================================================================== */

bool     probe_wifi_connected(void)      { return s_wifi_up; }
int      probe_wifi_rssi(void)           { return s_rssi; }
const char *probe_wifi_state_text(void)  { return wifi_state_str(); }
bool     probe_mqtt_connected(void)      { return s_mqtt_up; }
uint32_t probe_mqtt_published(void)      { return s_pub_count; }
bool     probe_publish_enabled(void)     { return s_publish_enabled; }
bool     probe_tap_stream_enabled(void)  { return s_tap_stream; }
uint32_t probe_publish_period_ms(void)   { return s_pub_period_ms; }
int      probe_menu_point(void)          { return s_point_idx; }
void     probe_menu_grid(int *rows, int *cols)
{
    if (rows != NULL) *rows = s_grid_rows;
    if (cols != NULL) *cols = s_grid_cols;
}
uint32_t probe_tap_count(void)           { return s_tap_count; }
float    probe_tap_thresh_g(void)         { return s_tap_thresh_g; }

void probe_menu_note_sensor(bool imu_ok, bool tof_ok, uint16_t tof_mm)
{
    static bool last_imu, last_tof;
    if (imu_ok != last_imu || tof_ok != last_tof) {
        last_imu = imu_ok;
        last_tof = tof_ok;
        s_imu_ok = imu_ok;
        s_tof_ok = tof_ok;
        bump();
    }
    s_tof_mm = tof_mm;
}

void probe_menu_note_tap(void) { s_tap_count++; }

/* ========================================================================
 * 9. Page tree
 * ===================================================================== */

static const item_t *page_items(page_t p, int *count)
{
    switch (p) {
    case PG_WIFI:   *count = (int)(sizeof(WIFI_ITEMS)   / sizeof(item_t)); return WIFI_ITEMS;
    case PG_MQTT:   *count = (int)(sizeof(MQTT_ITEMS)   / sizeof(item_t)); return MQTT_ITEMS;
    case PG_SENSOR: *count = (int)(sizeof(SENSOR_ITEMS) / sizeof(item_t)); return SENSOR_ITEMS;
    case PG_DATA:   *count = (int)(sizeof(DATA_ITEMS)   / sizeof(item_t)); return DATA_ITEMS;
    case PG_SYSTEM: *count = (int)(sizeof(SYSTEM_ITEMS) / sizeof(item_t)); return SYSTEM_ITEMS;
    case PG_MAIN:
    default:        *count = (int)(sizeof(MAIN_ITEMS)   / sizeof(item_t)); return MAIN_ITEMS;
    }
}

static const char *page_title(page_t p)
{
    switch (p) {
    case PG_WIFI:   return "MENU>WIFI";
    case PG_MQTT:   return "MENU>MQTT";
    case PG_SENSOR: return "MENU>SENSOR";
    case PG_DATA:   return "MENU>DATA";
    case PG_SYSTEM: return "MENU>SYSTEM";
    case PG_SCAN:   return "WIFI>SCAN";
    case PG_INFO:   return "MENU>STATUS";
    case PG_EDIT_PASS:   return "WIFI>PASS";
    case PG_EDIT_BROKER: return "MQTT>BROKER";
    case PG_EDIT_DEVID:  return "SYS>DEVID";
    case PG_MAIN:
    default:        return "PROBE MENU";
    }
}

static void push_page(page_t p)
{
    if (s_depth < NAV_DEPTH - 1) {
        s_stack_page[s_depth] = s_page;
        s_stack_sel[s_depth] = s_sel;
        s_depth++;
    }
    s_page = p;
    s_sel = 0;
    publish_event("menu");
    bump();
}

static void pop_page(void)
{
    if (s_depth > 0) {
        s_depth--;
        s_page = s_stack_page[s_depth];
        s_sel = s_stack_sel[s_depth];
    } else {
        s_page = PG_MAIN;
        s_sel = 0;
    }
    bump();
}

/* The one line under the list: what the highlighted item is set to, or what
 * pressing it does.  This is where the screen shows state without turning the
 * whole menu into a table of numbers. */
static void item_value(page_t p, int idx, char *buf, size_t n)
{
    int cnt = 0;
    const item_t *items = page_items(p, &cnt);
    if (idx < 0 || idx >= cnt) { buf[0] = 0; return; }
    const item_t *it = &items[idx];
    switch (it->kind) {
    case IK_BACK: snprintf(buf, n, "RETURN"); return;
    case IK_SUB:  snprintf(buf, n, "ENTER"); return;
    case IK_EDIT:
        if (it->arg == ED_BROKER) { copy_trunc(buf, n, s_broker_uri, 21); }
        else if (it->arg == ED_DEVID) { copy_trunc(buf, n, s_dev_id, 21); }
        else { snprintf(buf, n, "%u CHAR", (unsigned)strlen(s_sta_pass)); }
        return;
    case IK_ACT:
        switch (it->arg) {
        case ACT_RESCAN:       snprintf(buf, n, "SCAN FOR AP"); return;
        case ACT_CONNECT_DEF:  snprintf(buf, n, "JOIN PRESET AP"); return;
        case ACT_DROP_WIFI:    snprintf(buf, n, "DISCONNECT WIFI"); return;
        case ACT_MQTT_RESTART: snprintf(buf, n, "RE-OPEN LINK"); return;
        case ACT_ZERO:         snprintf(buf, n, "ZERO ACCEL"); return;
        case ACT_CLEAR:        snprintf(buf, n, "RESET COUNTER"); return;
        case ACT_PUB_NOW:      snprintf(buf, n, "SEND ONCE"); return;
        case ACT_REBOOT:       snprintf(buf, n, "RESTART BOARD"); return;
        default: buf[0] = 0; return;
        }
    case IK_TOGGLE:
        switch (it->arg) {
        case SET_PUBLISH:   snprintf(buf, n, "%s", s_publish_enabled ? "ON" : "OFF"); return;
        case SET_TAPSTREAM: snprintf(buf, n, "%s", s_tap_stream ? "ON" : "OFF"); return;
        case SET_AUTOJOIN:  snprintf(buf, n, "%s", s_autojoin ? "ON" : "OFF"); return;
        case SET_QOS:       snprintf(buf, n, "QOS %d", s_qos); return;
        default: buf[0] = 0; return;
        }
    case IK_CYC:
        if (it->arg == CYC_POINT) {
            snprintf(buf, n, "R%dC%d", s_point_idx / s_grid_cols + 1,
                     s_point_idx % s_grid_cols + 1);
            return;
        }
        if (it->arg == CYC_TAPTHRESH) { snprintf(buf, n, "%.2f G", (double)s_tap_thresh_g); return; }
        if (it->arg == CYC_PUBPERIOD) { snprintf(buf, n, "EVERY %lu MS", (unsigned long)s_pub_period_ms); return; }
        buf[0] = 0;
        return;
    case IK_INFO:
    default:
        break;
    }
    /* read-only rows report their measurement */
    if (p == PG_WIFI && idx == 0)   { snprintf(buf, n, "%s", wifi_state_str()); return; }
    if (p == PG_MQTT && idx == 0)   { snprintf(buf, n, "%s", s_mqtt_up ? "UP" : "DOWN"); return; }
    if (p == PG_SENSOR && idx == 0) { snprintf(buf, n, "%s", s_imu_ok ? "OK" : "NO"); return; }
    if (p == PG_SENSOR && idx == 1) { snprintf(buf, n, "%s", s_tof_ok ? "OK" : "NO"); return; }
    if (p == PG_SENSOR && idx == 3) { snprintf(buf, n, "%lu TAPS", (unsigned long)s_tap_count); return; }
    buf[0] = 0;
}

static void item_activate(void)
{
    int cnt = 0;
    const item_t *items = page_items(s_page, &cnt);
    if (s_sel < 0 || s_sel >= cnt) return;
    const item_t *it = &items[s_sel];
    switch (it->kind) {
    case IK_SUB:
        push_page((page_t)it->arg);
        return;
    case IK_BACK:
        pop_page();
        return;
    case IK_TOGGLE:
        switch (it->arg) {
        case SET_PUBLISH:   s_publish_enabled = !s_publish_enabled; break;
        case SET_TAPSTREAM: s_tap_stream = !s_tap_stream; break;
        case SET_AUTOJOIN:
            s_autojoin = !s_autojoin;
            if (s_autojoin && !s_wifi_up) esp_wifi_connect();
            break;
        case SET_QOS:       s_qos = s_qos ? 0 : 1; break;
        default: break;
        }
        bump();
        return;
    case IK_CYC:
        if (it->arg == CYC_POINT) {
            s_point_idx = (s_point_idx + 1) % grid_cells();
            bump();
            return;
        }
        if (it->arg == CYC_TAPTHRESH) {
            int i = 0;
            for (; i < TAP_THRESH_N; i++)
                if (fabsf(TAP_THRESH_STEPS[i] - s_tap_thresh_g) < 0.001f) break;
            i = (i + 1) % TAP_THRESH_N;
            s_tap_thresh_g = TAP_THRESH_STEPS[i];
        } else {
            int i = 0;
            for (; i < PUB_PERIOD_N; i++)
                if (PUB_PERIOD_STEPS[i] == s_pub_period_ms) break;
            i = (i + 1) % PUB_PERIOD_N;
            s_pub_period_ms = PUB_PERIOD_STEPS[i];
        }
        bump();
        return;
    case IK_EDIT:
        s_edit_target = it->arg;
        editor_begin();
        return;
    case IK_ACT:
        switch (it->arg) {
        case ACT_RESCAN:
            s_scan_wanted = true;
            s_ap_count = 0;
            push_page(PG_SCAN);
            break;
        case ACT_CONNECT_DEF:
            wifi_apply_and_connect((const char *)PROBE_WIFI_SSID_DEFAULT,
                                   (const char *)PROBE_WIFI_PASS_DEFAULT);
            break;
        case ACT_DROP_WIFI:
            s_autojoin = false;
            esp_wifi_disconnect();
            break;
        case ACT_MQTT_RESTART:
            mqtt_restart();
            break;
        case ACT_ZERO:
            s_zero_wanted = true;
            break;
        case ACT_CLEAR:
            s_tap_count = 0;
            break;
        case ACT_PUB_NOW:
            s_pub_wanted = true;
            break;
        case ACT_REBOOT:
            ESP_LOGW(TAG, "reboot from menu");
            vTaskDelay(pdMS_TO_TICKS(150));
            esp_restart();
            break;
        default:
            break;
        }
        bump();
        return;
    case IK_INFO:
    default:
        /* A read-only row still has one useful action: refresh it. */
        bump();
        return;
    }
}

/* ========================================================================
 * 10. Text editor
 * ===================================================================== */

static void editor_begin(void)
{
    s_editor_pos = 0;
    memset(s_editor_buf, 0, sizeof(s_editor_buf));
    if (s_edit_target == ED_BROKER) {
        strncpy(s_editor_buf, s_broker_uri, TEXT_MAX);
    } else if (s_edit_target == ED_DEVID) {
        strncpy(s_editor_buf, s_dev_id, TEXT_MAX);
    }
    s_page = (s_edit_target == ED_PASS)   ? PG_EDIT_PASS
           : (s_edit_target == ED_BROKER) ? PG_EDIT_BROKER
                                          : PG_EDIT_DEVID;
    bump();
}

static void editor_commit(void)
{
    if (s_edit_target == ED_PASS) {
        strncpy(s_sta_pass, s_editor_buf, sizeof(s_sta_pass) - 1);
        cfg_save("pass", s_sta_pass);
        if (s_sta_ssid[0]) cfg_save("ssid", s_sta_ssid);
        wifi_apply_and_connect(s_sta_ssid[0] ? s_sta_ssid
                                             : (const char *)PROBE_WIFI_SSID_DEFAULT,
                               s_sta_pass);
    } else if (s_edit_target == ED_BROKER) {
        strncpy(s_broker_uri, s_editor_buf, sizeof(s_broker_uri) - 1);
        cfg_save("broker", s_broker_uri);
        ESP_LOGI(TAG, "broker uri set to %s", s_broker_uri);
        mqtt_restart();
    } else {
        if (s_editor_buf[0]) {
            strncpy(s_dev_id, s_editor_buf, sizeof(s_dev_id) - 1);
            cfg_save("devid", s_dev_id);
            ESP_LOGI(TAG, "device id set to %s", s_dev_id);
            mqtt_restart();
        }
    }
    pop_page();
    s_sel = 0;
    bump();
}

/* ========================================================================
 * 11. Input
 * ===================================================================== */

void probe_menu_input(probe_dir_t d)
{
    if (d == PROBE_DIR_NONE) return;
    s_generation++;

    if (s_page >= PG_EDIT_PASS) {
        /* ---- editor pages ---- */
        size_t len = strlen(s_editor_buf);
        if (d == PROBE_DIR_LEFT) {
            if (s_editor_pos > 0) s_editor_pos--;
        } else if (d == PROBE_DIR_RIGHT) {
            if ((size_t)s_editor_pos < len) s_editor_pos++;
        } else if (d == PROBE_DIR_UP || d == PROBE_DIR_DOWN) {
            if ((size_t)s_editor_pos < len) {
                char cur = s_editor_buf[s_editor_pos];
                const char *p = strchr(CHARSET, cur);
                int idx = p ? (int)(p - CHARSET) : 0;
                idx += (d == PROBE_DIR_UP) ? 1 : (CHARSET_LEN - 1);
                idx %= CHARSET_LEN;
                s_editor_buf[s_editor_pos] = CHARSET[idx];
            } else if (len < TEXT_MAX) {
                s_editor_buf[len] = CHARSET[10];
                s_editor_buf[len + 1] = 0;
                s_editor_pos = (int)len + 1;
            }
        } else if (d == PROBE_DIR_CLICK) {
            editor_commit();
        }
        return;
    }

    if (s_page == PG_SCAN) {
        if (d == PROBE_DIR_UP) {
            if (s_sel > 0) s_sel--;
        } else if (d == PROBE_DIR_DOWN) {
            if (s_sel < s_ap_count - 1) s_sel++;
        } else if (d == PROBE_DIR_LEFT) {
            pop_page();
        } else if (d == PROBE_DIR_CLICK) {
            if (s_ap_count > 0 && s_sel < s_ap_count) {
                strncpy(s_sta_ssid, s_aps[s_sel].ssid, sizeof(s_sta_ssid) - 1);
                cfg_save("ssid", s_sta_ssid);
                if (s_aps[s_sel].secure) {
                    s_edit_target = ED_PASS;
                    s_editor_pos = 0;
                    memset(s_editor_buf, 0, sizeof(s_editor_buf));
                    s_page = PG_EDIT_PASS;
                } else {
                    wifi_apply_and_connect(s_sta_ssid, "");
                    pop_page();
                }
            }
        }
        return;
    }

    if (s_page == PG_INFO) {
        if (d == PROBE_DIR_CLICK || d == PROBE_DIR_LEFT) pop_page();
        return;
    }

    /* ---- list pages ---- */
    int cnt = 0;
    page_items(s_page, &cnt);
    if (d == PROBE_DIR_UP) {
        s_sel = (s_sel + cnt - 1) % cnt;
    } else if (d == PROBE_DIR_DOWN) {
        s_sel = (s_sel + 1) % cnt;
    } else if (d == PROBE_DIR_CLICK) {
        item_activate();
    } else if (d == PROBE_DIR_LEFT) {
        pop_page();
    } else if (d == PROBE_DIR_RIGHT) {
        item_activate();
    }
}

/* ========================================================================
 * 12. Rendering
 * ===================================================================== */

/* Geometry, in pixels, for a 128x160 panel and a 5x7 font.
 *
 *   title   0 .. 13     breadcrumb, scale 1
 *   rows   17 .. 121    six rows, 18 px pitch, scale 2 (14 px glyph)
 *   value 123 .. 137    what the highlighted item is set to, scale 1
 *   legend 140 .. 159   key map, scale 1
 */
#define LIST_TOP      17
#define LIST_PITCH    18
#define VALUE_BAR_Y   123
#define VALUE_BAR_H   15
#define LEGEND_BAR_Y  140
#define LEGEND_BAR_H  20

static void draw_title(uint8_t *f, page_t p, int shown, int total)
{
    rect(f, 0, 0, 128, PROBE_MENU_TITLE_H, C_TITLE);
    text(f, 3, 4, page_title(p), C_TEXT, 1);
    if (total > PROBE_MENU_ROWS) {
        char pos[24];
        snprintf(pos, sizeof(pos), "%d/%d", shown, total);
        text(f, 125 - text_w(pos, 1), 4, pos, C_HINT, 1);
    }
}

/* One list row.  The selected row gets an inverted bar plus an accent stripe on
 * the left edge, which is what makes the current position unambiguous at a
 * glance. */
static void draw_row(uint8_t *f, int y, const char *label, bool sel)
{
    char cut[12];
    copy_trunc(cut, sizeof(cut), label, 10);
    if (sel) {
        rect(f, 0, y - 2, 128, 17, C_SELBG);
        rect(f, 0, y - 2, 3, 17, C_ACCENT);
        text(f, 6, y, cut, C_SELTX, 2);
    } else {
        text(f, 6, y, cut, C_TEXT, 2);
    }
}

static void draw_value_line(uint8_t *f, const char *v)
{
    rect(f, 0, VALUE_BAR_Y, 128, VALUE_BAR_H, C_BAR);
    rect(f, 0, VALUE_BAR_Y, 3, VALUE_BAR_H, C_ACCENT);
    text(f, 7, VALUE_BAR_Y + 4, ">", C_ACCENT, 1);
    text(f, 15, VALUE_BAR_Y + 4, v, C_OK, 1);
}

static void draw_legend(uint8_t *f, const char *line)
{
    rect(f, 0, LEGEND_BAR_Y, 128, LEGEND_BAR_H, C_BG);
    text(f, 3, LEGEND_BAR_Y + 6, line, C_HINT, 1);
}

void probe_menu_render(uint8_t *frame)
{
    rect(frame, 0, 0, 128, 160, C_BG);
    char buf[48];

    /* ---- text editors ---- */
    if (s_page >= PG_EDIT_PASS) {
        draw_title(frame, s_page, 0, 0);
        size_t len = strlen(s_editor_buf);
        int start = 0;
        if (s_editor_pos > 9) start = s_editor_pos - 9;
        char view[16];
        int vn = 0;
        for (int i = start; i < (int)len && vn < 10; i++) view[vn++] = s_editor_buf[i];
        if (s_editor_pos >= (int)len && vn < 10) view[vn++] = '_';
        view[vn] = 0;
        text(frame, 6, 22, view, C_TEXT, 2);
        int cx = 6 + (s_editor_pos - start) * PROBE_FONT_ADV * 2;
        if (cx < 6) cx = 6;
        if (cx > 116) cx = 116;
        rect(frame, cx, 40, PROBE_FONT_W * 2, 2, C_ACCENT);

        char cur[2] = { (char)(s_editor_pos < (int)len ? s_editor_buf[s_editor_pos] : ' '), 0 };
        text(frame, 6, 52, "CHAR", C_DIM, 1);
        text(frame, 6, 64, cur, C_OK, 3);
        text(frame, 6, 100, s_edit_target == ED_PASS ? "PASSCODE" :
                           s_edit_target == ED_BROKER ? "BROKER URI" : "DEVICE ID", C_DIM, 1);
        draw_value_line(frame, "CLICK SAVES");
        draw_legend(frame, "UP/DN CHAR  L/R POS");
        return;
    }

    /* ---- access-point list ---- */
    if (s_page == PG_SCAN) {
        draw_title(frame, s_page, 0, 0);
        if (s_scan_busy && s_ap_count == 0) {
            text(frame, 6, 30, "SCANNING", C_DIM, 2);
        } else if (s_ap_count == 0) {
            text(frame, 6, 30, "NO AP", C_BAD, 2);
        } else {
            int top = 0;
            if (s_sel > 7) top = s_sel - 7;
            for (int i = 0; i < 8 && top + i < s_ap_count; i++) {
                int idx = top + i;
                int y = 18 + i * 12;
                bool sel = (idx == s_sel);
                if (sel) rect(frame, 0, y - 3, 128, 13, C_SELBG);
                char ssid[14];
                copy_trunc(ssid, sizeof(ssid), s_aps[idx].ssid, 10);
                snprintf(buf, sizeof(buf), "%d %-10s %4d%s", idx + 1, ssid,
                         s_aps[idx].rssi, s_aps[idx].secure ? "*" : " ");
                text(frame, 3, y, buf, sel ? C_SELTX : C_TEXT, 1);
            }
        }
        draw_value_line(frame, s_ap_count ? "CLICK JOINS" : "BACK AND RETRY");
        draw_legend(frame, "UP/DN MOVE  LEFT BACK");
        return;
    }

    /* ---- status: the data path the probe actually walks ---- */
    if (s_page == PG_INFO) {
        draw_title(frame, s_page, 0, 0);
        /* Every label here is at most ten glyph cells, which is the most that
         * fits across 128 px at font scale 2. */
        struct { const char *on; const char *off; bool up; } rows[4] = {
            {"WIFI ON",    "WIFI OFF",   s_wifi_up},
            {"BROKER UP",  "BROKER DN",  s_mqtt_up},
            {"UPLINK ON",  "UPLINK OFF", s_publish_enabled},
            {"TAP SEND",   "TAP HOLD",   s_tap_stream},
        };
        for (int i = 0; i < 4; i++) {
            int y = 20 + i * 22;
            rect(frame, 4, y + 3, 8, 8, rows[i].up ? C_OK : C_BAD);
            text(frame, 18, y, rows[i].up ? rows[i].on : rows[i].off,
                 rows[i].up ? C_OK : C_DIM, 2);
        }
        text(frame, 6, 112, "WIFI>MQTT>TAP>WEB", C_HINT, 1);
        draw_value_line(frame, "LIVE DATA PATH");
        draw_legend(frame, "LEFT OR CLICK BACK");
        return;
    }

    /* ---- ordinary list pages ---- */
    int cnt = 0;
    const item_t *items = page_items(s_page, &cnt);
    int top = 0;
    if (s_sel >= PROBE_MENU_ROWS) top = s_sel - (PROBE_MENU_ROWS - 1);
    draw_title(frame, s_page, s_sel + 1, cnt);
    for (int i = 0; i < PROBE_MENU_ROWS && top + i < cnt; i++) {
        int idx = top + i;
        int y = LIST_TOP + i * LIST_PITCH;
        draw_row(frame, y, items[idx].label, idx == s_sel);
    }
    item_value(s_page, s_sel, buf, sizeof(buf));
    draw_value_line(frame, buf);
    draw_legend(frame, "UP/DN MOVE  CLICK OK  L BACK");
}


/* ========================================================================
 * 13. Init
 * ===================================================================== */

void probe_menu_init(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }

    if (!cfg_load("broker", s_broker_uri, sizeof(s_broker_uri)))
        strncpy(s_broker_uri, PROBE_MQTT_BROKER_URI_DEFAULT, sizeof(s_broker_uri) - 1);
    if (!cfg_load("devid", s_dev_id, sizeof(s_dev_id)))
        strncpy(s_dev_id, PROBE_DEFAULT_DEV_ID, sizeof(s_dev_id) - 1);
    s_grid_rows = cfg_load_int("rows", 3);
    s_grid_cols = cfg_load_int("cols", 3);
    if (s_grid_rows < 2 || s_grid_rows > 8) s_grid_rows = 3;
    if (s_grid_cols < 2 || s_grid_cols > 8) s_grid_cols = 3;
    ESP_LOGI(TAG, "cfg: broker=%s dev=%s grid=%dx%d",
             s_broker_uri, s_dev_id, s_grid_rows, s_grid_cols);

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t wcfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wcfg));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID,
                                               &wifi_event_handler, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP,
                                               &wifi_event_handler, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());

    xTaskCreate(scan_task, "probe_scan", 4096, NULL, 3, NULL);

    s_page = PG_MAIN;
    s_sel = 0;
    s_depth = 0;
    bump();

    /* Credentials come from NVS once the user picked an AP on the joystick,
     * otherwise the compiled preset, so the probe joins on its own either way. */
    {
        char ssid[33] = {0};
        char pass[65] = {0};
        if (!cfg_load("ssid", ssid, sizeof(ssid)))
            strncpy(ssid, PROBE_WIFI_SSID_DEFAULT, sizeof(ssid) - 1);
        if (!cfg_load("pass", pass, sizeof(pass)))
            strncpy(pass, PROBE_WIFI_PASS_DEFAULT, sizeof(pass) - 1);
        wifi_apply_and_connect(ssid, pass);
    }
}
