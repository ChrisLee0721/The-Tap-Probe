# CMakeLists.txt -- main component of the tap-test probe firmware
#
# ESP-IDF v5.x. This currently builds the hardware bring-up smoke test.
# app_main.c remains in the tree as the legacy measurement implementation and
# is not compiled by this target.

idf_component_register(
    SRCS
        "hardware_bringup.c"
    INCLUDE_DIRS
        "."
    REQUIRES
        driver          # i2c_master.h, gpio.h, spi_master.h, adc_oneshot.h
        vl53l1x
)

# The DSP stage uses <math.h> (cosf/sinf/sqrtf/log/lroundf) and <time.h>
# (gmtime_r/strftime).  Newlib's libm and libc are linked by default on all
# ESP32 targets; no extra flag is needed, but the math operations are the
# heaviest part of the measurement task, so keep the optimisation level at -O2
# (the IDF default for release builds) rather than -Og.
target_compile_options(${COMPONENT_LIB} PRIVATE -O2 -Wall -Wextra)
