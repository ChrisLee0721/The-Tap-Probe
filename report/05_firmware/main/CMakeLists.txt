# CMakeLists.txt -- main component of the tap-test probe firmware
#
# ESP-IDF v5.x.  This registers the source file, the include directory and the
# component dependencies.  `idf.py` picks this up automatically; the top-level
# CMakeLists.txt in the project root only needs the project() declaration.

idf_component_register(
    SRCS
        "app_main.c"
    INCLUDE_DIRS
        "."
    REQUIRES
        driver          # i2s_std.h, i2c_master.h, gpio.h
        esp_wifi
        esp_event
        esp_netif
        nvs_flash
        esp_timer
        mqtt            # mqtt_client.h
        esp-tls         # provides esp_crt_bundle.h
        mbedtls
)

# The DSP stage uses <math.h> (cosf/sinf/sqrtf/log/lroundf) and <time.h>
# (gmtime_r/strftime).  Newlib's libm and libc are linked by default on all
# ESP32 targets; no extra flag is needed, but the math operations are the
# heaviest part of the measurement task, so keep the optimisation level at -O2
# (the IDF default for release builds) rather than -Og.
target_compile_options(${COMPONENT_LIB} PRIVATE -O2 -Wall -Wextra)
