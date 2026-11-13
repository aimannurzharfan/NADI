# NADI CSI sender (ESP32-S3). Based on espressif/esp-csi examples/get-started/csi_send.
cmake_minimum_required(VERSION 3.16)
# Settings over serial, status LED: shared with the other ESP-IDF board
set(EXTRA_COMPONENT_DIRS ../common)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(nadi_csi_send)
