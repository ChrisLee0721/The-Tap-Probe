/* probe_menu.h -- operator menu, WiFi station, MQTT client.
 *
 * The menu owns three things and nothing else: the screen state, the network
 * state (WiFi station + MQTT client) and the publish switches the operator can
 * flip.  The sensor side feeds it through probe_mqtt_publish_*(), which keeps
 * the sensor task free of any menu or network knowledge.
 */

#ifndef PROBE_MENU_H
#define PROBE_MENU_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* One physical action from the joystick handler. */
typedef enum {
    PROBE_DIR_NONE = 0,
    PROBE_DIR_UP,
    PROBE_DIR_DOWN,
    PROBE_DIR_LEFT,
    PROBE_DIR_RIGHT,
    PROBE_DIR_CLICK,
} probe_dir_t;

/* ---- lifecycle ------------------------------------------------------- */

/* Bring up NVS, the WiFi station and the boot scan, then start connecting with
 * the compiled-in credentials.  Call once, before the display task starts. */
void probe_menu_init(void);

/* Feed one operator action.  Safe to call from any task. */
void probe_menu_input(probe_dir_t d);

/* Render the current page into a 128x160 RGB565 big-endian frame buffer. */
void probe_menu_render(uint8_t *frame);

/* Bumped on every state change; the display task redraws only when it moves. */
uint32_t probe_menu_generation(void);

/* ---- uplink ---------------------------------------------------------- */

/* Periodic summary frame.  `t1`/`rms1`/`pk1` are in g.  The body channel is
 * omitted from the payload when peak2 is ~0, i.e. when no second sensor is
 * fitted -- a row of zeros would otherwise read as a measured quiet channel. */
void probe_mqtt_publish_measurement(float ax1, float ay1, float az1,
                                    float ax2, float ay2, float az2,
                                    float rms1, float rms2,
                                    float peak1, float peak2);

/* One triggered tap window.  \p xyz holds \p frames consecutive x,y,z
 * samples as int16 in units of PROBE_IMU_LSB_PER_G.  \p pre is how many of
 * those frames precede the trigger.  Silently dropped when the tap stream
 * switch is off, the link is down, or the payload will not fit. */
void probe_mqtt_publish_waveform(const int16_t *xyz, int frames, int pre, int trig,
                                  int fs);

/* Encode and publish whatever tap window is waiting.  Called from the display
 * task so the sensor task never blocks on the socket. */
void probe_mqtt_pump(void);

/* Continuous 6.66 kHz sample batches (one message per FIFO drain).  Only sends
 * while the wave-stream switch is on; see cmd "wave_stream". */
void probe_mqtt_publish_stream(const int16_t *xyz, int frames, int fs);

/* ---- state queries the display and the summary publisher need -------- */

bool        probe_wifi_connected(void);
int         probe_wifi_rssi(void);
const char *probe_wifi_state_text(void);
bool        probe_mqtt_connected(void);
uint32_t    probe_mqtt_published(void);
uint32_t    probe_tap_count(void);
float       probe_tap_thresh_g(void);              /* trigger level, g   */
bool        probe_take_publish_request(void);      /* one-shot "send now" */
bool        probe_take_zero_request(void);         /* one-shot re-zero     */
bool        probe_publish_enabled(void);
bool        probe_tap_stream_enabled(void);
uint32_t    probe_publish_period_ms(void);
/* Flat index of the grid cell the operator is standing on (row * cols + col).
 * The web owns the grid and sends this index; without it a tap cannot be
 * attributed to a position. */
int         probe_menu_point(void);
/* Shape of the planned grid, so the device can draw the same map the browser
 * is showing.  3x3 until the browser says otherwise. */
void        probe_menu_grid(int *rows, int *cols);

/* ---- sensor-side status, shown on the SENSOR page -------------------- */

void probe_menu_note_sensor(bool imu_ok, bool tof_ok, uint16_t tof_mm);
void probe_menu_note_tap(void);

#ifdef __cplusplus
}
#endif

#endif /* PROBE_MENU_H */
