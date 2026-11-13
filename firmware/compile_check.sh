#!/bin/sh
# Compile csi_send and csi_recv in Docker, csi_recv in both local and huawei mode, without touching anyone's sdkconfig.
# From the repo root (Windows PowerShell):
#   docker run --rm -v ${PWD}/firmware:/fw espressif/idf:v5.4.1 sh /fw/compile_check.sh
# Settings are the menuconfig defaults plus dummy values below, so the build is complete; nothing is flashed.
set -e
. "$IDF_PATH/export.sh" > /dev/null 2>&1 || true

build() {  # project, label, extra defaults lines
  dir=/tmp/nadi_build_$1_$2
  rm -rf "$dir" && mkdir -p "$dir"
  printf '%s\n' "$3" > "$dir/extra.defaults"
  echo "== $1 ($2)"
  cd "/fw/$1"
  idf.py -B "$dir" -D SDKCONFIG="$dir/sdkconfig" -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;$dir/extra.defaults" build > "$dir/log.txt" 2>&1 \
    || { tail -40 "$dir/log.txt"; exit 1; }
  grep -E "warning:" "$dir/log.txt" | grep -v "managed_components" || true
  ls -l "$dir"/*.bin | awk '{print "   " $5 " bytes " $9}'
}

build csi_send local 'CONFIG_NADI_AP_SSID="TestNet"'
build csi_recv local 'CONFIG_NADI_WIFI_SSID="TestNet"
CONFIG_NADI_TARGET_LOCAL=y
CONFIG_NADI_MQTT_HOST="192.168.0.10"'
# local mode over TLS, with a throwaway CA (the real one comes from scripts/mqtt_tls.py)
had_ca=0; [ -f /fw/csi_recv/main/mqtt_ca.pem ] && had_ca=1
if [ $had_ca = 0 ]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=compile-check" -keyout /tmp/ca.key \
    -out /fw/csi_recv/main/mqtt_ca.pem > /dev/null 2>&1
fi
build csi_recv local_tls 'CONFIG_NADI_WIFI_SSID="TestNet"
CONFIG_NADI_TARGET_LOCAL=y
CONFIG_NADI_MQTT_TLS=y
CONFIG_NADI_MQTT_PORT=8883
CONFIG_NADI_MQTT_HOST="192.168.0.10"' || { [ $had_ca = 0 ] && rm -f /fw/csi_recv/main/mqtt_ca.pem; exit 1; }
[ $had_ca = 0 ] && rm -f /fw/csi_recv/main/mqtt_ca.pem
build csi_recv huawei 'CONFIG_NADI_WIFI_SSID="TestNet"
CONFIG_NADI_TARGET_HUAWEI=y
CONFIG_NADI_IOTDA_HOST="example.iotda-device.ap-southeast-1.myhuaweicloud.com"'
echo "ALL BUILT"
