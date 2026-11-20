#!/usr/bin/env python3
"""preview_screens.py -- render the TFT framebuffers to PNG, offline.

The two ST7735 panels are the one part of this project that cannot be checked
by reading a log: a layout that overflows, a label that gets clipped or a font
that turns to mush all look fine over UART.  This script re-implements the
drawing maths of probe_menu.c and of draw_measure_screen() against the same
generated font header, so the exact pixels can be inspected before flashing.

It is a PREVIEW, not the device: if the two disagree, the C is authoritative and
this file is the bug.  Re-run after any layout change:

    python tools/preview_screens.py

Outputs PNGs next to this script under ../docs/screens/.
"""

import os
import re

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_H = os.path.join(HERE, "..", "main", "probe_font.h")
OUT = os.path.join(HERE, "..", "docs", "screens")

W, H = 128, 160
ZOOM = 4

# --- colours, RGB565 as used in the firmware --------------------------------
C_BG, C_TITLE, C_TEXT = 0x0000, 0x0210, 0xFFFF
C_DIM, C_SELBG, C_SELTX = 0x8410, 0x07FF, 0x0000
C_OK, C_BAD, C_HINT = 0x07E0, 0xF800, 0xFFE0
C_ACCENT, C_BAR = 0xFD20, 0x0841


def rgb565(c):
    r = (c >> 11) & 0x1F
    g = (c >> 5) & 0x3F
    b = c & 0x1F
    return (r * 255 // 31, g * 255 // 63, b * 255 // 31)


def load_font(path):
    src = open(path, encoding="utf-8").read()
    body = src.split("PROBE_FONT[95][5] = {", 1)[1]
    rows = re.findall(r"\{0x([0-9A-F]{2}),0x([0-9A-F]{2}),0x([0-9A-F]{2}),"
                      r"0x([0-9A-F]{2}),0x([0-9A-F]{2})\}", body)
    return [[int(v, 16) for v in row] for row in rows]


FONT = load_font(FONT_H)
FONT_W, FONT_H_, FONT_ADV = 5, 7, 6


class Frame:
    def __init__(self):
        self.img = Image.new("RGB", (W, H), rgb565(C_BG))
        self.px = self.img.load()

    def rect(self, x, y, w, h, color):
        c = rgb565(color)
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                if 0 <= xx < W and 0 <= yy < H:
                    self.px[xx, yy] = c

    def text(self, x, y, s, color, scale=1):
        c = rgb565(color)
        cx = x
        for ch in s:
            if ch.islower():
                ch = ch.upper()
            o = ord(ch)
            g = FONT[o - 0x20] if 0x20 <= o <= 0x7E else FONT[0]
            for col in range(FONT_W):
                for row in range(FONT_H_):
                    if (g[col] >> row) & 1:
                        for sy in range(scale):
                            for sx in range(scale):
                                px, py = cx + col * scale + sx, y + row * scale + sy
                                if 0 <= px < W and 0 <= py < H:
                                    self.px[px, py] = c
            cx += FONT_ADV * scale
            if cx > W:
                break

    def text_w(self, s, scale=1):
        return len(s) * FONT_ADV * scale

    def save(self, name):
        os.makedirs(OUT, exist_ok=True)
        path = os.path.join(OUT, name)
        self.img.resize((W * ZOOM, H * ZOOM), Image.NEAREST).save(path)
        return path


# --- geometry, copied from probe_menu.c ------------------------------------
TITLE_H = 14
LIST_TOP, LIST_PITCH, ROWS = 17, 18, 6
VALUE_Y, VALUE_H = 123, 15
LEGEND_Y, LEGEND_H = 140, 20

MAIN = ["POINT ID", "WIFI LINK", "MQTT LINK", "SENSORS", "TAP DATA", "SYSTEM"]
WIFI = ["LINK", "SCAN AP", "JOIN AP", "PASSCODE", "AUTO JOIN", "BACK"]
MQTT = ["LINK", "BROKER", "PUBLISH", "TAP STREAM", "QOS LEVEL", "BACK"]
DATA = ["TAP LEVEL", "SEND RATE", "SEND NOW", "CLEAR CNT", "BACK"]


def chrome(f, title, shown=None, total=None):
    f.rect(0, 0, 128, TITLE_H, C_TITLE)
    f.text(3, 4, title, C_TEXT, 1)
    if total and total > ROWS:
        pos = "%d/%d" % (shown, total)
        f.text(125 - f.text_w(pos, 1), 4, pos, C_HINT, 1)


def value_line(f, v):
    f.rect(0, VALUE_Y, 128, VALUE_H, C_BAR)
    f.rect(0, VALUE_Y, 3, VALUE_H, C_ACCENT)
    f.text(7, VALUE_Y + 4, ">", C_ACCENT, 1)
    f.text(15, VALUE_Y + 4, v, C_OK, 1)


def legend(f, s):
    f.rect(0, LEGEND_Y, 128, LEGEND_H, C_BG)
    f.text(3, LEGEND_Y + 6, s, C_HINT, 1)


def list_page(name, title, items, sel, value):
    f = Frame()
    chrome(f, title, sel + 1, len(items))
    for i, label in enumerate(items):
        y = LIST_TOP + i * LIST_PITCH
        if i == sel:
            f.rect(0, y - 2, 128, 17, C_SELBG)
            f.rect(0, y - 2, 3, 17, C_ACCENT)
            f.text(6, y, label[:10], C_SELTX, 2)
        else:
            f.text(6, y, label[:10], C_TEXT, 2)
    value_line(f, value)
    legend(f, "UP/DN MOVE  CLICK OK  L BACK")
    return f.save(name)


def scan_page():
    f = Frame()
    chrome(f, "WIFI>SCAN")
    aps = [("MAOJUNPENG", -46, 1), ("CU_5G", -58, 1), ("ChinaNet-7f2", -71, 1),
           ("TPLINK_2G", -74, 1), ("Xiaomi_AX", -79, 1), ("CMCC-HOME", -83, 1)]
    for i, (ssid, rssi, lock) in enumerate(aps):
        y = 18 + i * 12
        if i == 1:
            f.rect(0, y - 2, 128, 12, C_SELBG)
        line = "%-10s %4d%s" % (ssid[:10], rssi, "*" if lock else " ")
        f.text(3, y, line, C_SELTX if i == 1 else C_TEXT, 1)
    value_line(f, "CLICK JOINS")
    legend(f, "UP/DN MOVE  LEFT BACK")
    return f.save("04_scan.png")


def status_page():
    f = Frame()
    chrome(f, "MENU>STATUS")
    rows = [("WIFI ON", True), ("BROKER UP", True),
            ("UPLINK ON", True), ("TAP SEND", True)]
    for i, (label, up) in enumerate(rows):
        y = 20 + i * 22
        f.rect(4, y + 3, 8, 8, C_OK if up else C_BAD)
        f.text(18, y, label, C_OK if up else C_DIM, 2)
    f.text(6, 112, "WIFI>MQTT>TAP>WEB", C_HINT, 1)
    value_line(f, "LIVE DATA PATH")
    legend(f, "LEFT OR CLICK BACK")
    return f.save("05_status.png")


def editor_page():
    f = Frame()
    chrome(f, "MQTT>BROKER")
    buf = "mqtt://192.168"
    pos = len(buf) - 1
    start = max(0, pos - 9)
    view = buf[start:start + 10] or "_"
    f.text(6, 22, view, C_TEXT, 2)
    cx = 6 + (pos - start) * FONT_ADV * 2
    f.rect(min(max(cx, 6), 116), 40, FONT_W * 2, 2, C_ACCENT)
    f.text(6, 52, "CHAR", C_DIM, 1)
    f.text(6, 64, buf[pos], C_OK, 3)
    f.text(6, 100, "BROKER URI", C_DIM, 1)
    value_line(f, "CLICK SAVES")
    legend(f, "UP/DN CHAR  L/R POS")
    return f.save("06_editor.png")


def measure_screen():
    f = Frame()
    f.rect(0, 0, 128, 14, C_TITLE)
    f.text(3, 4, "MEASURE", C_TEXT, 1)
    # measurement point, always visible while striking
    f.text(124 - f.text_w("P2", 2), 0, "P2", C_TEXT, 2)

    f.text(6, 20, "DISTANCE", C_DIM, 1)
    f.text(6, 31, "207", C_ACCENT, 3)
    f.text(6 + f.text_w("207", 3) + 4, 44, "MM", C_DIM, 1)
    f.rect(6, 66, 116, 1, 0x2945)

    f.text(6, 72, "LAST TAP", C_DIM, 1)
    f.text(6, 83, "0.42", C_TEXT, 3)
    f.text(6 + f.text_w("0.42", 3) + 4, 96, "G", C_DIM, 1)

    f.text(6, 116, "TAPS 17", C_TEXT, 1)
    f.rect(6, 130, 7, 7, C_OK)
    f.text(17, 130, "WIFI", C_OK, 1)
    f.rect(62, 130, 7, 7, C_OK)
    f.text(73, 130, "MQTT", C_OK, 1)
    f.rect(6, 143, 7, 7, C_OK)
    f.text(17, 143, "TAP STREAM", C_HINT, 1)
    return f.save("07_measure_panel.png")


if __name__ == "__main__":
    made = [
        list_page("01_main.png", "PROBE MENU", MAIN, 0, "P2 OF 5"),
        list_page("02_wifi.png", "MENU>WIFI", WIFI, 1, "SCAN FOR AP"),
        list_page("03_mqtt.png", "MENU>MQTT", MQTT, 4, "QOS 0"),
        list_page("08_data.png", "MENU>DATA", DATA, 0, "0.25 G"),
        scan_page(),
        status_page(),
        editor_page(),
        measure_screen(),
    ]
    for p in made:
        print(p)
