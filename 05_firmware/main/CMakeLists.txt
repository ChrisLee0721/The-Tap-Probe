# CMakeLists.txt -- main component of the tap-test probe firmware
#
# Hardware bring-up image: joystick menu on TFT1, live traces on TFT2,
# inertial sensing from the two LSM6DS3 modules, JSON over MQTT.

idf_component_register(
    SRCS
        "hardware_bringup.c"
        "probe_menu.c"
    INCLUDE_DIRS
        "."
    REQUIRES
        driver
        vl53l1x
        esp_wifi
        esp_netif
        esp_event
        nvs_flash
        mqtt
)

# Keep -O2: the DSP and the FFT for the sizing channel are the heaviest part of
# the measurement task, and -Og measurably perturbs the capture timing.
target_compile_options(${COMPONENT_LIB} PRIVATE -O2 -Wall -Wextra)
