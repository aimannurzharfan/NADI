#!/bin/sh
# Feature and report code from ../main, compiled for the PC. No ESP32 needed.
set -e
cd "$(dirname "$0")"
gcc -std=c11 -O2 -Wall -Wextra -Werror -I../main host_test.c ../main/csi_features.c ../main/report.c -lm -o /tmp/nadi_host_test
/tmp/nadi_host_test
