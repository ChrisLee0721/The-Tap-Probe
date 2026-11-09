# CMakeLists.txt -- project root of the tap-test probe firmware
#
# EEE4483 "Internet-of-Things Planning and Deployment" -- embedded appendix.
# Target: ESP-IDF v5.x.
#
# Usage:
#   . $HOME/esp/esp-idf/export.sh      (Windows: %IDF_PATH%\export.bat)
#   cd report/05_firmware
#   idf.py set-target esp32
#   idf.py menuconfig                  (optional: check the probe settings)
#   idf.py -p <PORT> flash monitor
#
# The only thing this file has to do is declare the project and its minimum
# IDF version.  Component discovery, the "main" component and the build rules
# all come from the IDF build system.

cmake_minimum_required(VERSION 3.16)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)

project(tap_probe_rev_c)
