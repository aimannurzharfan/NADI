/*
 * NADI climate node (ESP32-S3): room temperature and humidity every 60 s, and switches the
 * air conditioner off by infrared when the server sends the command ac_off.
 *
 * Wiring: DHT22 DATA on GPIO 4, KY-022 IR receiver OUT on GPIO 18, KY-005 IR transmitter SIG on GPIO 17.
 * Settings: copy secrets.example.h to secrets.h and fill it in. Those are only the defaults: "setup" over serial
 * changes the Wi-Fi network, broker and room without uploading again.
 *
 * Serial Monitor (115200 baud, line ending "Newline"), type:
 *   setup   change Wi-Fi name and password, broker address and port, MQTT password, room (kept in flash)
 *   show    show the settings (passwords hidden)
 *   reset   forget the saved settings and use secrets.h again
 *   learn   record the air conditioner remote's "off" button (learn mode); kept in flash
 *   send    send the stored code now, to test it
 *   irtest  flash the IR LED once a second for 10 s: look at it through a phone camera
 *   status  connection state
 *
 * Status LED (onboard RGB): red = no Wi-Fi, yellow = no MQTT, purple = the DHT22 does not answer, green = working,
 * blue blink = report sent, white blink = IR sent.
 *
 * Same topics and JSON as Huawei IoTDA in both modes:
 *   report   $oc/devices/{device_id}/sys/properties/report   service "climate"
 *   command  $oc/devices/{device_id}/sys/commands/request_id={id}   {"command_name":"ac_off", ...}
 *   reply    $oc/devices/{device_id}/sys/commands/response/request_id={id}
 */
#include <ArduinoJson.h>
#include <DHT.h>
#include <IRrecv.h>
#include <IRremoteESP8266.h>
#include <IRsend.h>
#include <IRutils.h>
#include <Preferences.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <esp_task_wdt.h>
#include <time.h>

#include "mbedtls/md.h"
#include "secrets.h"

#ifndef LED_PIN
#define LED_PIN 48  // onboard RGB LED: 48 on most DevKitC-1 boards, 38 on some; -1 turns it off
#endif

#define FW_VERSION "1.1.0"
#define DHT_PIN 4
#define IR_RECV_PIN 18
#define IR_SEND_PIN 17
#define CLIMATE_INTERVAL_MS 60000UL  // IoTDA budget: at most one climate report a minute
#define LEARN_TIMEOUT_MS 30000UL
#define RESTART_AFTER_MS 300000UL    // Wi-Fi or MQTT down this long: restart the board
#define IR_KHZ 38
#define IR_REPEAT_GAP_MS 150         // the code is sent twice, this far apart
#define LED_LEVEL 24
// One line: sim/fake_board.py and the tests read it from here
#define CLIMATE_JSON_FMT "{\"services\":[{\"service_id\":\"climate\",\"properties\":{\"room_id\":\"%s\",\"ts\":%lld,\"temp_c\":%.1f,\"humidity\":%.1f,\"fw_version\":\"%s\",\"uptime_s\":%lu,\"wifi_rssi\":%d,\"free_heap\":%lu,\"dropped\":%lu}}]}"

DHT dht(DHT_PIN, DHT22);
// Long buffer and 50 ms gap: air conditioner remotes send long messages
IRrecv irrecv(IR_RECV_PIN, 1024, 50, true);
IRsend irsend(IR_SEND_PIN);
Preferences prefs;

#ifndef MQTT_TLS
#define MQTT_TLS 0
#endif
#if NADI_TARGET_LOCAL && MQTT_TLS
#include "mqtt_ca.h"  // MQTT_CA_PEM, written by python scripts/mqtt_tls.py
WiFiClientSecure net;
#define SECRET_NAME "MQTT password"
#elif NADI_TARGET_LOCAL
WiFiClient net;
#define SECRET_NAME "MQTT password"
#else
WiFiClientSecure net;
#define SECRET_NAME "IoTDA device secret"
#endif
PubSubClient mqtt(net);

// Settings: saved with "setup", otherwise secrets.h
String cfgSsid, cfgPass, cfgHost, cfgSecret, cfgRoom;
int cfgPort;

String reportTopic, commandTopic, clientId, mqttPassword;
uint16_t *offCode = nullptr;  // raw IR timings, microseconds (always kept, as the fallback)
uint16_t offCodeLen = 0;
int offProto = -1;            // decode_type_t of a recognised remote, -1 = raw only
uint16_t offBits = 0;
uint8_t offState[64];         // air conditioner protocols: the decoded state bytes
uint64_t offValue = 0;        // simple protocols: the decoded value
bool learning = false;
unsigned long learnStarted = 0, lastClimate = 0, lastMqttTry = 0, wifiOkAt = 0, mqttOkAt = 0;
unsigned long irTestNext = 0, dropped = 0;
int irTestLeft = 0;
bool settingsOk = true, dhtOk = true;

// ---------- status LED ----------

enum Color { OFF, RED, YELLOW, PURPLE, GREEN, BLUE, WHITE };
Color steady = OFF;
unsigned long blinkUntil = 0;

void showColor(Color c) {
#if LED_PIN >= 0
  static const uint8_t rgb[][3] = {{0, 0, 0}, {LED_LEVEL, 0, 0}, {LED_LEVEL, LED_LEVEL * 2 / 3, 0}, {LED_LEVEL, 0, LED_LEVEL},
                                   {0, LED_LEVEL, 0}, {0, 0, LED_LEVEL}, {LED_LEVEL, LED_LEVEL, LED_LEVEL}};
  rgbLedWrite(LED_PIN, rgb[c][0], rgb[c][1], rgb[c][2]);
#endif
}

void blink(Color c, unsigned long ms) {
  showColor(c);
  blinkUntil = millis() + ms;
}

void updateLed() {
  Color c = WiFi.status() != WL_CONNECTED ? RED : !mqtt.connected() ? YELLOW : !dhtOk ? PURPLE : GREEN;
  if (blinkUntil && millis() > blinkUntil) {
    blinkUntil = 0;
    showColor(c);
  } else if (!blinkUntil && c != steady) {
    showColor(c);
  }
  steady = c;
}

// ---------- settings ----------

bool safeId(const char *s, size_t maxLen) {
  size_t n = strlen(s);
  if (n == 0 || n > maxLen) return false;
  for (size_t i = 0; i < n; i++) {
    char c = s[i];
    if (!isalnum((unsigned char)c) && c != '-' && c != '_') return false;
  }
  return true;
}

void loadSettings() {
  prefs.begin("cfg", true);
  cfgSsid = prefs.getString("ssid", WIFI_SSID);
  cfgPass = prefs.getString("pass", WIFI_PASSWORD);
#if NADI_TARGET_LOCAL
  cfgHost = prefs.getString("host", MQTT_HOST);
  cfgPort = prefs.getInt("port", MQTT_PORT);
  cfgSecret = prefs.getString("secret", MQTT_PASSWORD);
#else
  cfgHost = prefs.getString("host", IOTDA_HOST);
  cfgPort = prefs.getInt("port", IOTDA_PORT);
  cfgSecret = prefs.getString("secret", IOTDA_DEVICE_SECRET);
#endif
  cfgRoom = prefs.getString("room", ROOM_ID);
  prefs.end();
}

bool checkSettings() {
  bool ok = true;
  if (cfgSsid.length() == 0) {
    Serial.println("No Wi-Fi network is set. Type setup and press Enter.");
    ok = false;
  }
  if (!safeId(DEVICE_ID, 128) || !safeId(cfgRoom.c_str(), 32)) {
    Serial.println("DEVICE_ID and the room ID may use only letters, digits, - and _.");
    ok = false;
  }
  if (cfgHost.length() == 0 || cfgSecret.length() == 0) {
    Serial.println(NADI_TARGET_LOCAL ? "Local mode needs the broker address (the laptop IP) and the MQTT password. Type setup."
                                     : "Huawei mode needs the IoTDA host name and device secret. Type setup.");
    ok = false;
  }
#if !NADI_TARGET_LOCAL
  if (strlen(IOTDA_CA_PEM) == 0) {
    Serial.println("Huawei mode needs IOTDA_CA_PEM in secrets.h.");
    ok = false;
  }
#endif
  return ok;
}

const char *masked(const String &secret) { return secret.length() ? "********" : "(not set)"; }

// Read one answer. Typed characters are echoed, or shown as * for a password. -1 = no answer for 2 minutes.
int readLine(String &out, bool secret) {
  out = "";
  unsigned long deadline = millis() + 120000UL;
  while (millis() < deadline) {
    esp_task_wdt_reset();
    if (!Serial.available()) {
      delay(10);
      continue;
    }
    char c = Serial.read();
    if (c == '\r' || c == '\n') {
      if (out.length() == 0 && Serial.peek() == '\n') Serial.read();
      Serial.println();
      return out.length();
    }
    if ((c == 8 || c == 127) && out.length()) {
      out.remove(out.length() - 1);
      Serial.print("\b \b");
    } else if (c >= 32 && c < 127 && out.length() < 100) {
      out += c;
      Serial.print(secret ? '*' : c);
    }
  }
  return -1;
}

bool ask(const char *question, String &value, bool secret) {
  if (secret) Serial.printf("%s [%s, Enter keeps it]: ", question, masked(value));
  else Serial.printf("%s [%s]: ", question, value.length() ? value.c_str() : "not set");
  String line;
  int n = readLine(line, secret);
  if (n < 0) {
    Serial.println("\nNo answer for 2 minutes: setup cancelled, nothing saved.");
    return false;
  }
  if (n > 0) value = line;
  return true;
}

void runSetup() {
  Serial.println("\nSetup: type a new value and press Enter, or press Enter to keep the value in brackets.");
  String ssid = cfgSsid, pass = cfgPass, host = cfgHost, port = String(cfgPort), secret = cfgSecret, room = cfgRoom;
  bool ok = ask("Wi-Fi name (2.4 GHz)", ssid, false) && ask("Wi-Fi password", pass, true) &&
            ask(NADI_TARGET_LOCAL ? "Broker address (the laptop IP shown on the dashboard)" : "IoTDA host name", host, false) &&
            ask("Broker port", port, false) && ask(SECRET_NAME, secret, true) && ask("Room ID (for example room1)", room, false);
  if (!ok) return;
  int p = port.toInt();
  if (p < 1 || p > 65535 || !safeId(room.c_str(), 32)) {
    Serial.println("The port must be 1 to 65535 and the room ID only letters, digits, - and _. Nothing saved.");
    return;
  }
  prefs.begin("cfg", false);
  prefs.putString("ssid", ssid);
  prefs.putString("pass", pass);
  prefs.putString("host", host);
  prefs.putInt("port", p);
  prefs.putString("secret", secret);
  prefs.putString("room", room);
  prefs.end();
  Serial.println("Saved. Restarting in 2 s to use them.");
  delay(2000);
  ESP.restart();
}

void showSettings() {
  Serial.printf("Device %s, firmware %s, %s.\n", DEVICE_ID, FW_VERSION, NADI_TARGET_LOCAL ? "local mode" : "huawei mode");
  Serial.printf("  Wi-Fi name:     %s\n", cfgSsid.length() ? cfgSsid.c_str() : "(not set)");
  Serial.printf("  Wi-Fi password: %s\n", masked(cfgPass));
  Serial.printf("  Broker:         %s port %d\n", cfgHost.length() ? cfgHost.c_str() : "(not set)", cfgPort);
  Serial.printf("  " SECRET_NAME ": %s\n", masked(cfgSecret));
  Serial.printf("  Room ID:        %s\n", cfgRoom.c_str());
}

// ---------- stored IR code ----------

void loadOffCode() {
  prefs.begin("nadi", true);
  size_t bytes = prefs.getBytesLength("off_raw");
  if (bytes >= 2 * 10 && bytes % 2 == 0) {
    offCode = new uint16_t[bytes / 2];
    prefs.getBytes("off_raw", offCode, bytes);
    offCodeLen = bytes / 2;
  }
  offProto = prefs.getInt("off_proto", -1);
  offBits = prefs.getUShort("off_bits", 0);
  offValue = prefs.getULong64("off_value", 0);
  size_t n = prefs.getBytesLength("off_state");
  if (n > sizeof(offState)) offProto = -1;
  else if (n) prefs.getBytes("off_state", offState, n);
  prefs.end();
}

void saveOffCode(uint16_t *raw, uint16_t len, const decode_results &r) {
  bool known = r.decode_type != decode_type_t::UNKNOWN;
  bool acState = known && hasACState(r.decode_type) && r.bits / 8 <= sizeof(offState);
  prefs.begin("nadi", false);
  prefs.putBytes("off_raw", raw, (size_t)len * 2);
  prefs.putInt("off_proto", known ? (int)r.decode_type : -1);
  prefs.putUShort("off_bits", r.bits);
  prefs.remove("off_state");
  prefs.remove("off_value");
  if (acState) prefs.putBytes("off_state", r.state, r.bits / 8);
  else if (known) prefs.putULong64("off_value", r.value);
  prefs.end();
  delete[] offCode;
  offCode = raw;
  offCodeLen = len;
  offProto = known ? (int)r.decode_type : -1;
  offBits = r.bits;
  if (acState) memcpy(offState, r.state, r.bits / 8);
  else offValue = r.value;
}

// One transmission: the decoded protocol if it was recognised, otherwise the raw timings.
bool sendOnce() {
  if (offProto >= 0) {
    decode_type_t type = (decode_type_t)offProto;
    bool ok = hasACState(type) ? irsend.send(type, offState, offBits / 8) : irsend.send(type, offValue, offBits);
    if (ok) return true;
  }
  if (offCodeLen) {
    irsend.sendRaw(offCode, offCodeLen, IR_KHZ);
    return true;
  }
  return false;
}

bool sendOffCode() {
  if (offCodeLen == 0 && offProto < 0) {
    Serial.println("No air conditioner code is stored. Type learn first.");
    return false;
  }
  sendOnce();
  delay(IR_REPEAT_GAP_MS);
  sendOnce();  // twice: one burst is easily missed across a room
  blink(WHITE, 300);
  if (offProto >= 0) {
    Serial.printf("Sent the stored air conditioner off code twice (%s, %u bits).\n",
                  typeToString((decode_type_t)offProto).c_str(), offBits);
  } else {
    Serial.printf("Sent the stored air conditioner off code twice (raw, %u timings).\n", offCodeLen);
  }
  return true;
}

void irTestStep() {
  if (!irTestLeft || millis() < irTestNext) return;
  irsend.enableIROut(IR_KHZ);
  for (int i = 0; i < 4; i++) irsend.mark(50000);  // 0.2 s of 38 kHz light (mark() takes at most 65 ms)
  irsend.space(0);                                 // a phone camera shows it as a purple-white flash
  blink(WHITE, 200);
  irTestNext = millis() + 1000;
  if (--irTestLeft == 0) Serial.println("IR test finished.");
}

// ---------- learn mode ----------

void startLearning() {
  learning = true;
  learnStarted = millis();
  irrecv.enableIRIn();
  Serial.println("Learn mode: point the air conditioner remote at the IR receiver (GPIO 18), about 5 cm away,");
  Serial.println("and press its OFF button once. Waiting 30 s.");
}

void stopLearning() {
  irrecv.disableIRIn();
  learning = false;
}

void checkLearning() {
  decode_results results;
  if (irrecv.decode(&results)) {
    if (results.overflow) {
      Serial.println("The code was too long to record. Hold the remote closer and type learn again.");
    } else {
      uint16_t len = getCorrectedRawLength(&results);
      if (len < 10) {
        Serial.println("That was too short to be an air conditioner code (interference?). Type learn and try again.");
      } else {
        bool known = results.decode_type != decode_type_t::UNKNOWN;
        Serial.printf("Recorded: protocol %s, %d bits, %u timings.\n", typeToString(results.decode_type).c_str(),
                      results.bits, len);
        Serial.println(known ? "The remote's protocol was recognised: the decoded code will be sent (raw timings kept as backup)."
                             : "Protocol not recognised: the raw timings will be sent.");
        saveOffCode(resultToRawArray(&results), len, results);
        Serial.println("Saved in flash; it stays after a restart. To test: turn the air conditioner on, aim the");
        Serial.println("IR transmitter (GPIO 17) at it from 1 to 2 m, and type send.");
      }
    }
    stopLearning();
  } else if (millis() - learnStarted > LEARN_TIMEOUT_MS) {
    Serial.println("No IR code was received in 30 s. Check the receiver wiring (OUT on GPIO 18) and type learn again.");
    stopLearning();
  }
}

// ---------- Wi-Fi and time ----------

void onWifiEvent(WiFiEvent_t event, WiFiEventInfo_t info) {
  if (event == ARDUINO_EVENT_WIFI_STA_GOT_IP) {
    Serial.printf("Connected to \"%s\". IP address: %s.\n", cfgSsid.c_str(), WiFi.localIP().toString().c_str());
  } else if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
    uint8_t reason = info.wifi_sta_disconnected.reason;
    if (reason == WIFI_REASON_NO_AP_FOUND || reason == WIFI_REASON_NO_AP_FOUND_W_COMPATIBLE_SECURITY ||
        reason == WIFI_REASON_NO_AP_FOUND_IN_AUTHMODE_THRESHOLD || reason == WIFI_REASON_NO_AP_FOUND_IN_RSSI_THRESHOLD) {
      Serial.printf("The Wi-Fi network \"%s\" was not found. Check the name, and that it is a 2.4 GHz network.\n",
                    cfgSsid.c_str());
    } else if (reason == WIFI_REASON_AUTH_FAIL || reason == WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT ||
               reason == WIFI_REASON_HANDSHAKE_TIMEOUT || reason == WIFI_REASON_CONNECTION_FAIL) {
      Serial.printf("The Wi-Fi network \"%s\" refused the connection. Check the Wi-Fi password (type setup).\n",
                    cfgSsid.c_str());
    } else {
      Serial.printf("Wi-Fi disconnected (reason %d). Reconnecting.\n", reason);
    }
  }
}

long long nowTs() {
  time_t t = time(nullptr);
  return t > 1700000000 ? (long long)t : 0;  // 0 until the clock is set; the server then uses its own
}

void waitForClock() {
  for (int i = 0; i < 30 && nowTs() == 0; i++) {
    esp_task_wdt_reset();
    delay(500);
  }
  if (nowTs()) {
    Serial.printf("Clock set from %s.\n", NTP_SERVER);
  } else {
    Serial.printf("Could not set the clock from %s (no internet?). Reports go out with ts 0.\n", NTP_SERVER);
  }
}

// ---------- MQTT ----------

void reply(const String &requestId, int resultCode, const char *result) {
  String topic = "$oc/devices/" DEVICE_ID "/sys/commands/response/request_id=" + requestId;
  char body[160];
  snprintf(body, sizeof(body), "{\"result_code\":%d,\"response_name\":\"ac_off\",\"paras\":{\"result\":\"%s\"}}",
           resultCode, result);
  mqtt.publish(topic.c_str(), body);
}

void onMessage(char *topic, byte *payload, unsigned int len) {
  String t(topic);
  if (t.indexOf("/sys/commands/response/") >= 0) return;  // our own replies
  int at = t.indexOf("request_id=");
  String requestId = at >= 0 ? t.substring(at + 11) : "";
  JsonDocument doc;
  if (deserializeJson(doc, payload, len)) {
    Serial.println("A command arrived that is not valid JSON. Ignored.");
    return;
  }
  const char *name = doc["command_name"] | "";
  if (strcmp(name, "ac_off") != 0) {
    Serial.printf("Unknown command \"%s\". Ignored.\n", name);
    reply(requestId, 1, "unknown_command");
    return;
  }
  Serial.println("Command ac_off received.");
  bool sent = sendOffCode();
  reply(requestId, sent ? 0 : 1, sent ? "sent" : "no_code");
}

#if !NADI_TARGET_LOCAL
// IoTDA login: password = HMAC-SHA256(key = timestamp YYYYMMDDHH, message = device secret), hex
String iotdaPassword(const char *stamp) {
  uint8_t mac[32];
  mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), (const unsigned char *)stamp, strlen(stamp),
                  (const unsigned char *)cfgSecret.c_str(), cfgSecret.length(), mac);
  char hex[65];
  for (int i = 0; i < 32; i++) sprintf(hex + 2 * i, "%02x", mac[i]);
  return String(hex);
}
#endif

void setupMqtt() {
  reportTopic = "$oc/devices/" DEVICE_ID "/sys/properties/report";
  commandTopic = "$oc/devices/" DEVICE_ID "/sys/commands/#";
  mqtt.setServer(cfgHost.c_str(), cfgPort);
#if NADI_TARGET_LOCAL
#if MQTT_TLS
  net.setCACert(MQTT_CA_PEM);
#endif
  clientId = DEVICE_ID;
  mqttPassword = cfgSecret;
#else
  net.setCACert(IOTDA_CA_PEM);
  char stamp[16];
  time_t t = time(nullptr);
  struct tm utc;
  gmtime_r(&t, &utc);
  strftime(stamp, sizeof(stamp), "%Y%m%d%H", &utc);
  // device ID type 0, signature type 0 (timestamp not checked, so reconnects keep working)
  clientId = String(DEVICE_ID) + "_0_0_" + stamp;
  mqttPassword = iotdaPassword(stamp);
#endif
  mqtt.setBufferSize(1024);
  mqtt.setKeepAlive(60);
  mqtt.setSocketTimeout(5);  // a broker that does not answer blocks for at most 5 s, so serial and learn stay usable
  mqtt.setCallback(onMessage);
}

void connectMqtt() {
  if (mqtt.connected() || WiFi.status() != WL_CONNECTED || millis() - lastMqttTry < 5000) return;
  lastMqttTry = millis();
  if (mqtt.connect(clientId.c_str(), DEVICE_ID, mqttPassword.c_str())) {
    mqtt.subscribe(commandTopic.c_str(), 1);
    Serial.printf("Connected to the MQTT broker at %s. Listening for the command ac_off.\n", cfgHost.c_str());
    lastClimate = millis() - CLIMATE_INTERVAL_MS;  // report straight away
    return;
  }
  int state = mqtt.state();
  if (state == MQTT_CONNECT_BAD_CREDENTIALS || state == MQTT_CONNECT_UNAUTHORIZED) {
#if NADI_TARGET_LOCAL
    Serial.println("The broker refused the login. Check that DEVICE_ID is in MQTT_DEVICE_IDS and the MQTT password is this");
    Serial.println("device's MQTT_PASSWORD_<ID> from .env (type setup), then run python scripts/mqtt_users.py.");
#else
    Serial.println("IoTDA refused the login. Check DEVICE_ID and the IoTDA device secret (type setup).");
#endif
  } else {
    Serial.printf("Could not reach the MQTT broker at %s port %d (state %d). Check the address (type setup), that the\n",
                  cfgHost.c_str(), cfgPort, state);
    Serial.println("broker is running, and that Windows Firewall allows port 1883. Trying again in 5 s.");
  }
}

// ---------- climate ----------

void reportClimate() {
  float temp = dht.readTemperature();
  float hum = dht.readHumidity();
  if (isnan(temp) || isnan(hum)) {
    delay(2500);  // the DHT22 needs 2 s between readings
    temp = dht.readTemperature();
    hum = dht.readHumidity();
  }
  dhtOk = !(isnan(temp) || isnan(hum));
  if (!dhtOk) {
    Serial.println("The DHT22 did not answer. Check the wiring: VCC to 3.3 V, GND, DATA to GPIO 4. No report sent.");
    return;
  }
  char body[384];
  snprintf(body, sizeof(body), CLIMATE_JSON_FMT, cfgRoom.c_str(), nowTs(), temp, hum, FW_VERSION,
           (unsigned long)(millis() / 1000), (int)WiFi.RSSI(), (unsigned long)ESP.getFreeHeap(), dropped);
  if (mqtt.connected() && mqtt.publish(reportTopic.c_str(), body)) {
    blink(BLUE, 150);
    Serial.printf("Climate report sent: %.1f C, humidity %.1f%%.\n", temp, hum);
  } else {
    dropped++;  // reports that could not be sent, reported with the next one that is
    Serial.printf("Not connected to the MQTT broker, so this report was not sent: %.1f C, humidity %.1f%%.\n", temp, hum);
  }
}

// ---------- serial commands ----------

void printStatus() {
  Serial.printf("Device %s, room %s, firmware %s, %s.\n", DEVICE_ID, cfgRoom.c_str(), FW_VERSION,
                NADI_TARGET_LOCAL ? "local mode (Mosquitto on the laptop)" : "huawei mode (Huawei Cloud IoTDA)");
  Serial.printf("Wi-Fi: %s. MQTT: %s. Stored air conditioner code: %s.\n",
                WiFi.status() == WL_CONNECTED ? "connected" : "not connected",
                mqtt.connected() ? "connected" : "not connected",
                offProto >= 0 ? typeToString((decode_type_t)offProto).c_str() : offCodeLen ? "raw" : "none (type learn)");
}

void handleSerial() {
  static String line;
  while (Serial.available()) {
    char c = Serial.read();
    if (c != '\n' && c != '\r') {
      if (line.length() < 32) line += c;
      continue;
    }
    line.trim();
    line.toLowerCase();
    if (line == "learn") startLearning();
    else if (line == "send") sendOffCode();
    else if (line == "status") printStatus();
    else if (line == "setup") runSetup();
    else if (line == "show") showSettings();
    else if (line == "irtest") {
      Serial.println("IR test: the IR LED flashes once a second for 10 s. Look at it through a phone camera.");
      irTestLeft = 10;
      irTestNext = 0;
    } else if (line == "reset") {
      prefs.begin("cfg", false);
      prefs.clear();
      prefs.end();
      Serial.println("Saved settings cleared; secrets.h applies. Restarting in 2 s.");
      delay(2000);
      ESP.restart();
    } else if (line.length()) Serial.println("Commands: setup, show, reset, learn, send, irtest, status.");
    line = "";
  }
}

// ---------- self-recovery ----------

void checkRestart() {
  unsigned long now = millis();
  if (WiFi.status() == WL_CONNECTED) wifiOkAt = now;
  if (mqtt.connected()) mqttOkAt = now;
  if (learning) return;  // never restart in the middle of learn mode
  if (now - wifiOkAt > RESTART_AFTER_MS) {
    Serial.println("No Wi-Fi connection for 5 minutes. Restarting the board to try again from the start.");
    delay(500);
    ESP.restart();
  }
  if (now - mqttOkAt > RESTART_AFTER_MS) {
    Serial.println("No connection to the MQTT broker for 5 minutes. Restarting the board to try again from the start.");
    delay(500);
    ESP.restart();
  }
}

// ---------- main ----------

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println();
  Serial.printf("NADI climate node %s is starting. Type setup and press Enter to change the Wi-Fi network or broker.\n",
                FW_VERSION);
  // The core already runs the task watchdog: 30 s, and restart the board if the main loop gets stuck
  esp_task_wdt_config_t wdt = {.timeout_ms = 30000, .idle_core_mask = 0, .trigger_panic = true};
  esp_task_wdt_reconfigure(&wdt);
  esp_task_wdt_add(NULL);
  showColor(RED);
  dht.begin();
  irsend.begin();
  loadSettings();
  loadOffCode();
  settingsOk = checkSettings();
  if (!settingsOk) {
    Serial.println("Type setup to fix the settings. Learn mode and irtest still work.");
    return;
  }
  printStatus();
  WiFi.onEvent(onWifiEvent);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(cfgSsid.c_str(), cfgPass.c_str());
  Serial.printf("Connecting to the Wi-Fi network \"%s\".\n", cfgSsid.c_str());
  configTime(0, 0, NTP_SERVER);  // keeps trying in the background
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) {
    esp_task_wdt_reset();
    delay(500);
  }
  if (WiFi.status() == WL_CONNECTED) waitForClock();
  setupMqtt();
  wifiOkAt = mqttOkAt = millis();
  if (!offCodeLen && offProto < 0) Serial.println("No air conditioner code is stored yet. Type learn to record the remote's OFF button.");
}

void loop() {
  esp_task_wdt_reset();
  handleSerial();
  irTestStep();
  if (learning) checkLearning();
  if (!settingsOk) return;
  connectMqtt();
  mqtt.loop();
  updateLed();
  checkRestart();
  if (!learning && millis() - lastClimate >= CLIMATE_INTERVAL_MS) {  // learn mode: no reports
    lastClimate = millis();
    reportClimate();
  }
}
