// Copy this file to secrets.h (same folder) and fill it in. secrets.h is git-ignored: never commit it.
// These are only the defaults: type setup in the Serial Monitor to change Wi-Fi, broker and room without uploading again.

// Wi-Fi: a 2.4 GHz network (the ESP32-S3 cannot use 5 GHz)
#define WIFI_SSID ""
#define WIFI_PASSWORD ""

// Local mode: also the MQTT username, so it must be listed in MQTT_DEVICE_IDS in .env.
// Huawei mode: the device ID IoTDA gave this device.
#define DEVICE_ID "nadi-climate-1"
// The room this node is in, as the server knows it (room1, room2, ...)
#define ROOM_ID "room1"

// 1 = local mode: Mosquitto on the laptop. 0 = huawei mode: Huawei Cloud IoTDA (MQTTS).
#define NADI_TARGET_LOCAL 1

// Local mode
#define MQTT_HOST ""      // the laptop's IPv4 address on the Wi-Fi network, same as MQTT_LAN_IP in .env
#define MQTT_PORT 1883
#define MQTT_PASSWORD ""  // this device's own password in .env: MQTT_PASSWORD_NADI_CLIMATE_1 for nadi-climate-1
// MQTT over TLS on the laptop (optional): run python scripts/mqtt_tls.py, which writes mqtt_ca.h next to this file,
// then set MQTT_TLS to 1 and MQTT_PORT to 8883.
#define MQTT_TLS 0

// Huawei mode
#define IOTDA_HOST ""     // IoTDA console > Overview > Access Details, device access, MQTTS host name
#define IOTDA_PORT 8883
#define IOTDA_DEVICE_SECRET ""
// IoTDA CA certificate (download it from the IoTDA console), pasted between the brackets:
// #define IOTDA_CA_PEM R"(-----BEGIN CERTIFICATE-----
// ...
// -----END CERTIFICATE-----)"
#define IOTDA_CA_PEM ""

// Clock for the "ts" field and for IoTDA login. Without internet, reports go out with ts 0
// and the server uses its own clock.
#define NTP_SERVER "pool.ntp.org"

// Onboard RGB status LED: 48 on most DevKitC-1 boards, 38 on some versions, -1 turns it off
#define LED_PIN 48
