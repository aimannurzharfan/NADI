#!/bin/sh
# Compile the climate node in both modes with arduino-cli, on a copy (no secrets.h is written in the repo).
# Run in Docker from the repo root (Windows PowerShell):
#   docker run --rm -v nadi-arduino:/root -v ${PWD}/firmware:/fw python:3.12-slim sh /fw/climate_node/compile_check.sh
# The nadi-arduino volume caches arduino-cli, the ESP32 core and the libraries (see firmware/README.md).
set -e
CLI=/root/bin/arduino-cli
FQBN="esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB,CDCOnBoot=default,FlashMode=dio"
for target in 1 tls 0; do
  rm -rf /tmp/climate_node && cp -r /fw/climate_node /tmp/climate_node
  if [ $target = tls ]; then
    sed "s/^#define MQTT_TLS 0/#define MQTT_TLS 1/" /fw/climate_node/secrets.example.h > /tmp/climate_node/secrets.h
    printf '#define MQTT_CA_PEM "-----BEGIN CERTIFICATE-----\\n...\\n-----END CERTIFICATE-----\\n"\n' > /tmp/climate_node/mqtt_ca.h
  else
    sed "s/^#define NADI_TARGET_LOCAL 1/#define NADI_TARGET_LOCAL $target/" /fw/climate_node/secrets.example.h > /tmp/climate_node/secrets.h
  fi
  echo "== NADI_TARGET_LOCAL=$target"
  $CLI compile --fqbn "$FQBN" --warnings all --output-dir /tmp/out_$target /tmp/climate_node
done
