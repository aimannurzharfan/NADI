/*
 * NADI CSI receiver: joins the Wi-Fi network, measures CSI from the sender's packets, and every
 * report window publishes one IoTDA property report (motion features, never raw CSI or MAC addresses).
 *
 * Local mode: Mosquitto on the laptop (mqtt://, username = device ID).
 * Huawei mode: IoTDA over MQTTS with the device ID and secret.
 *
 * Serial commands (115200 baud, press Enter): setup, show, reset, restart, help. "setup" changes the Wi-Fi network,
 * broker and room without reflashing; menuconfig values are only the defaults.
 * Status LED: red = no Wi-Fi, yellow = no MQTT, purple = no CSI from the sender, green = working, blue blink = report.
 *
 * CSI set-up based on espressif/esp-csi examples/get-started/csi_recv (Apache-2.0 / CC0).
 * The receiver stays on the network's channel for MQTT, so the sender must send on that channel too.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include <time.h>

#include "esp_crt_bundle.h"
#include "esp_system.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "freertos/timers.h"
#include "mbedtls/md.h"
#include "mqtt_client.h"

#include "csi_features.h"
#include "nadi_cfg.h"
#include "nadi_console.h"
#include "nadi_led.h"
#include "report.h"

#define NADI_FW_VERSION "1.1.0"
#define RESTART_AFTER_S 300            // Wi-Fi or MQTT down this long: restart the board
#define CSI_QUIET_US (3 * 1000000LL)   // no CSI from the sender for this long: LED purple

#if CONFIG_NADI_MOTION_SOURCE_RSSI
#define MOTION_SOURCE NADI_MOTION_RSSI
#define MOTION_NAME "RSSI"
#else
#define MOTION_SOURCE NADI_MOTION_CSI
#define MOTION_NAME "CSI amplitude"
#endif

#define MIN_PACKETS 20  // fewer than this in a window: no report, so the room shows offline, not empty
#define WIFI_UP BIT0
#define MQTT_UP BIT1

static const char *TAG = "nadi_recv";

typedef struct {
    int8_t buf[2 * NADI_SUBCARRIERS];
    int8_t rssi;
} csi_packet_t;

static uint8_t s_sender_mac[6];
static QueueHandle_t s_csi_queue;
static SemaphoreHandle_t s_window_lock;
static nadi_window_t s_window;
static volatile uint32_t s_dropped;
static EventGroupHandle_t s_events;
static TimerHandle_t s_reconnect_timer;
static esp_mqtt_client_handle_t s_mqtt;
static char s_topic[160];
static char s_broker[160];
static bool s_time_ok;
static volatile int64_t s_last_csi_us;

/* Settings: saved with "setup" (NVS), otherwise the menuconfig values. */
static struct {
    char ssid[33];
    char pass[65];
    char host[128];   // local: laptop IP; huawei: IoTDA host name
    int32_t port;
    char secret[65];  // local: this device's MQTT password; huawei: IoTDA device secret
    char room[33];
} s_cfg;

#if CONFIG_NADI_TARGET_LOCAL
#define DEFAULT_HOST CONFIG_NADI_MQTT_HOST
#define DEFAULT_PORT CONFIG_NADI_MQTT_PORT
#define DEFAULT_SECRET CONFIG_NADI_MQTT_PASSWORD
#define SECRET_NAME "MQTT password"
#define NADI_LOCAL 1
#else
#define DEFAULT_HOST CONFIG_NADI_IOTDA_HOST
#define DEFAULT_PORT CONFIG_NADI_IOTDA_PORT
#define DEFAULT_SECRET CONFIG_NADI_IOTDA_DEVICE_SECRET
#define SECRET_NAME "IoTDA device secret"
#define NADI_LOCAL 0
#endif

static void load_settings(void)
{
    nadi_cfg_str("ssid", CONFIG_NADI_WIFI_SSID, s_cfg.ssid, sizeof(s_cfg.ssid));
    nadi_cfg_str("pass", CONFIG_NADI_WIFI_PASSWORD, s_cfg.pass, sizeof(s_cfg.pass));
    nadi_cfg_str("host", DEFAULT_HOST, s_cfg.host, sizeof(s_cfg.host));
    s_cfg.port = nadi_cfg_int("port", DEFAULT_PORT);
    nadi_cfg_str("secret", DEFAULT_SECRET, s_cfg.secret, sizeof(s_cfg.secret));
    nadi_cfg_str("room", CONFIG_NADI_ROOM_ID, s_cfg.room, sizeof(s_cfg.room));
}

static bool parse_mac(const char *text, uint8_t mac[6])
{
    unsigned int b[6];
    if (sscanf(text, "%x:%x:%x:%x:%x:%x", &b[0], &b[1], &b[2], &b[3], &b[4], &b[5]) != 6) {
        return false;
    }
    for (int i = 0; i < 6; i++) {
        if (b[i] > 0xff) {
            return false;
        }
        mac[i] = (uint8_t)b[i];
    }
    return true;
}

/* Letters, digits, - and _ only: the value goes into a topic and into JSON unescaped. */
static bool safe_id(const char *s, size_t max_len)
{
    size_t n = strlen(s);
    if (n == 0 || n > max_len) {
        return false;
    }
    for (size_t i = 0; i < n; i++) {
        char c = s[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_')) {
            return false;
        }
    }
    return true;
}

/* ---------- CSI ---------- */

static void csi_cb(void *ctx, wifi_csi_info_t *info)
{
    if (!info || !info->buf || memcmp(info->mac, s_sender_mac, 6) != 0 || info->len < (int)sizeof(((csi_packet_t *)0)->buf)) {
        return;
    }
    csi_packet_t p;
    memcpy(p.buf, info->buf, sizeof(p.buf));
    p.rssi = info->rx_ctrl.rssi;
    if (xQueueSend(s_csi_queue, &p, 0) != pdTRUE) {
        s_dropped++;
    }
    s_last_csi_us = esp_timer_get_time();
}

static void csi_task(void *arg)
{
    csi_packet_t p;
    for (;;) {
        if (xQueueReceive(s_csi_queue, &p, portMAX_DELAY) == pdTRUE) {
            xSemaphoreTake(s_window_lock, portMAX_DELAY);
            nadi_window_add(&s_window, p.buf, sizeof(p.buf), p.rssi);
            xSemaphoreGive(s_window_lock);
        }
    }
}

static void csi_start(void)
{
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));
    wifi_csi_config_t cfg = {
        .lltf_en = true,
        .htltf_en = false,
        .stbc_htltf2_en = false,
        .ltf_merge_en = true,
        .channel_filter_en = true,
        .manu_scale = false,
        .shift = 0,
    };
    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(csi_cb, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));
}

/* ---------- Wi-Fi ---------- */

static void reconnect_cb(TimerHandle_t t)
{
    esp_wifi_connect();
}

static void explain_disconnect(uint8_t reason)
{
    switch (reason) {
    case WIFI_REASON_NO_AP_FOUND:
    case WIFI_REASON_NO_AP_FOUND_W_COMPATIBLE_SECURITY:
    case WIFI_REASON_NO_AP_FOUND_IN_AUTHMODE_THRESHOLD:
    case WIFI_REASON_NO_AP_FOUND_IN_RSSI_THRESHOLD:
        ESP_LOGW(TAG, "The Wi-Fi network \"%s\" was not found. Check the name, and that it is a 2.4 GHz network "
                 "(the ESP32-S3 cannot use 5 GHz).", s_cfg.ssid);
        break;
    case WIFI_REASON_AUTH_FAIL:
    case WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT:
    case WIFI_REASON_HANDSHAKE_TIMEOUT:
    case WIFI_REASON_CONNECTION_FAIL:
        ESP_LOGW(TAG, "The Wi-Fi network \"%s\" refused the connection. Check the Wi-Fi password.", s_cfg.ssid);
        break;
    default:
        ESP_LOGW(TAG, "Wi-Fi disconnected (reason %d).", reason);
    }
}

static void wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        ESP_LOGI(TAG, "Connecting to the Wi-Fi network \"%s\".", s_cfg.ssid);
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(s_events, WIFI_UP);
        explain_disconnect(((wifi_event_sta_disconnected_t *)data)->reason);
        ESP_LOGI(TAG, "Trying again in 5 s.");
        xTimerStart(s_reconnect_timer, 0);
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *ev = (ip_event_got_ip_t *)data;
        uint8_t ch = 0;
        wifi_second_chan_t second;
        esp_wifi_get_channel(&ch, &second);
        ESP_LOGI(TAG, "Connected to \"%s\" on channel %d. IP address: " IPSTR ".", s_cfg.ssid, ch,
                 IP2STR(&ev->ip_info.ip));
        ESP_LOGI(TAG, "The sender must also use channel %d. It finds it by itself when its network name is set.", ch);
        xEventGroupSetBits(s_events, WIFI_UP);
    }
}

static void wifi_start(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event, NULL));

    wifi_config_t wc = {0};
    strlcpy((char *)wc.sta.ssid, s_cfg.ssid, sizeof(wc.sta.ssid));
    strlcpy((char *)wc.sta.password, s_cfg.pass, sizeof(wc.sta.password));
    wc.sta.scan_method = WIFI_ALL_CHANNEL_SCAN;
    wc.sta.sort_method = WIFI_CONNECT_AP_BY_SIGNAL;
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wc));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));  // power saving would miss packets
}

/* ---------- time ---------- */

static void time_start(void)
{
    esp_sntp_config_t cfg = ESP_NETIF_SNTP_DEFAULT_CONFIG(CONFIG_NADI_NTP_SERVER);
    esp_netif_sntp_init(&cfg);
    if (esp_netif_sntp_sync_wait(pdMS_TO_TICKS(15000)) == ESP_OK) {
        s_time_ok = true;
        ESP_LOGI(TAG, "Clock set from %s.", CONFIG_NADI_NTP_SERVER);
    } else {
        ESP_LOGW(TAG, "Could not set the clock from %s (no internet?). Reports go out with ts 0 and the server "
                 "uses its own clock. It keeps trying in the background.", CONFIG_NADI_NTP_SERVER);
    }
}

static long long now_ts(void)
{
    time_t t = time(NULL);
    if (t > 1700000000) {  // after Nov 2023: the clock has been set
        s_time_ok = true;
        return (long long)t;
    }
    return 0;
}

/* ---------- MQTT ---------- */

static void mqtt_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    esp_mqtt_event_handle_t ev = data;
    switch ((esp_mqtt_event_id_t)id) {
    case MQTT_EVENT_CONNECTED:
        ESP_LOGI(TAG, "Connected to the MQTT broker at %s.", s_broker);
        xEventGroupSetBits(s_events, MQTT_UP);
        break;
    case MQTT_EVENT_DISCONNECTED:
        if (xEventGroupGetBits(s_events) & MQTT_UP) {
            ESP_LOGW(TAG, "Disconnected from the MQTT broker. Reconnecting.");
        }
        xEventGroupClearBits(s_events, MQTT_UP);
        break;
    case MQTT_EVENT_ERROR:
        if (ev->error_handle->error_type == MQTT_ERROR_TYPE_CONNECTION_REFUSED) {
#if CONFIG_NADI_TARGET_LOCAL
            ESP_LOGE(TAG, "The broker refused the login (code %d). Check that the device ID \"%s\" is in "
                     "MQTT_DEVICE_IDS and the password is this device's MQTT_PASSWORD_<ID> from .env (type setup to "
                     "change it), then run python scripts/mqtt_users.py and restart Mosquitto.",
                     ev->error_handle->connect_return_code, CONFIG_NADI_DEVICE_ID);
#else
            ESP_LOGE(TAG, "IoTDA refused the login (code %d). Check the device ID and device secret.",
                     ev->error_handle->connect_return_code);
#endif
        } else if (ev->error_handle->error_type == MQTT_ERROR_TYPE_TCP_TRANSPORT) {
#if CONFIG_NADI_TARGET_LOCAL
            ESP_LOGE(TAG, "Could not reach the broker at %s. Check the laptop IP address (type setup to change it), "
                     "that Mosquitto is running, and that Windows Firewall allows port 1883.", s_broker);
#else
            ESP_LOGE(TAG, "Could not reach IoTDA at %s. Check the host name and that the network allows port %ld.",
                     s_broker, (long)s_cfg.port);
#endif
        }
        break;
    default:
        break;
    }
}

#if CONFIG_NADI_TARGET_HUAWEI
/* IoTDA login: password = HMAC-SHA256(key = timestamp YYYYMMDDHH, message = device secret), hex. */
static void iotda_password(const char *stamp, char out[65])
{
    uint8_t mac[32];
    mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), (const unsigned char *)stamp, strlen(stamp),
                    (const unsigned char *)s_cfg.secret, strlen(s_cfg.secret), mac);
    for (int i = 0; i < 32; i++) {
        sprintf(out + 2 * i, "%02x", mac[i]);
    }
}
#endif

#if CONFIG_NADI_MQTT_TLS
extern const char mqtt_ca_pem_start[] asm("_binary_mqtt_ca_pem_start");
#endif

static void mqtt_start(void)
{
    static char uri[200], client_id[200], password[80];
    esp_mqtt_client_config_t cfg = {0};
#if CONFIG_NADI_TARGET_LOCAL
    snprintf(s_broker, sizeof(s_broker), "%s:%ld", s_cfg.host, (long)s_cfg.port);
#if CONFIG_NADI_MQTT_TLS
    snprintf(uri, sizeof(uri), "mqtts://%s", s_broker);
    cfg.broker.verification.certificate = mqtt_ca_pem_start;
#ifdef CONFIG_NADI_MQTT_TLS_SKIP_CN
    cfg.broker.verification.skip_cert_common_name_check = true;
#endif
#else
    snprintf(uri, sizeof(uri), "mqtt://%s", s_broker);
#endif
    strlcpy(client_id, CONFIG_NADI_DEVICE_ID, sizeof(client_id));
    strlcpy(password, s_cfg.secret, sizeof(password));
#else
    snprintf(s_broker, sizeof(s_broker), "%s:%ld", s_cfg.host, (long)s_cfg.port);
    snprintf(uri, sizeof(uri), "mqtts://%s", s_broker);
    char stamp[16];
    time_t t = time(NULL);
    struct tm utc;
    gmtime_r(&t, &utc);
    strftime(stamp, sizeof(stamp), "%Y%m%d%H", &utc);
    // {device_id}_0_0_{stamp}: device ID type 0, signature type 0 (timestamp not checked, so reconnects work)
    snprintf(client_id, sizeof(client_id), "%s_0_0_%s", CONFIG_NADI_DEVICE_ID, stamp);
    iotda_password(stamp, password);
    cfg.broker.verification.crt_bundle_attach = esp_crt_bundle_attach;
#endif
    cfg.broker.address.uri = uri;
    cfg.credentials.client_id = client_id;
    cfg.credentials.username = CONFIG_NADI_DEVICE_ID;
    cfg.credentials.authentication.password = password;
    cfg.session.keepalive = 60;
    cfg.network.reconnect_timeout_ms = 5000;
    s_mqtt = esp_mqtt_client_init(&cfg);
    esp_mqtt_client_register_event(s_mqtt, ESP_EVENT_ANY_ID, mqtt_event, NULL);
    ESP_LOGI(TAG, "Connecting to the MQTT broker at %s.", s_broker);
    esp_mqtt_client_start(s_mqtt);
}

/* ---------- reports ---------- */

static int wifi_rssi(void)
{
    wifi_ap_record_t ap;
    return esp_wifi_sta_get_ap_info(&ap) == ESP_OK ? ap.rssi : 0;
}

static void report_task(void *arg)
{
    static char json[512];
    TickType_t last = xTaskGetTickCount();
    esp_task_wdt_add(NULL);
    for (;;) {
        vTaskDelayUntil(&last, pdMS_TO_TICKS(CONFIG_NADI_REPORT_INTERVAL_S * 1000));
        esp_task_wdt_reset();
        nadi_features_t f;
        xSemaphoreTake(s_window_lock, portMAX_DELAY);
        nadi_window_result(&s_window, MOTION_SOURCE, &f);
        nadi_window_reset(&s_window);
        uint32_t dropped = s_dropped;
        s_dropped = 0;
        xSemaphoreGive(s_window_lock);

        if (dropped) {
            ESP_LOGW(TAG, "%lu CSI packets were dropped because the receiver was busy.", (unsigned long)dropped);
        }
        if (f.n_packets < MIN_PACKETS) {
            ESP_LOGW(TAG, "Only %lu CSI packets from the sender (%s) in the last %d s. No report was sent, so the "
                     "dashboard shows the room as offline, not empty. Check that the sender is powered and on "
                     "this receiver's channel.", (unsigned long)f.n_packets, CONFIG_NADI_SENDER_MAC,
                     CONFIG_NADI_REPORT_INTERVAL_S);
            continue;
        }
        nadi_health_t health = {
            .fw_version = NADI_FW_VERSION,
            .uptime_s = (unsigned long)(esp_timer_get_time() / 1000000),
            .wifi_rssi = wifi_rssi(),
            .free_heap = (unsigned long)esp_get_free_heap_size(),
            .dropped = (unsigned long)dropped,
        };
        int len = nadi_csi_json(json, sizeof(json), s_cfg.room, now_ts(), &f, &health);
        if (len < 0) {
            ESP_LOGE(TAG, "The report did not fit in its buffer and was not sent.");
            continue;
        }
        if (!(xEventGroupGetBits(s_events) & MQTT_UP)) {
            ESP_LOGW(TAG, "Not connected to the MQTT broker, so this report was not sent: %lu packets, "
                     "motion_std %.4f.", (unsigned long)f.n_packets, f.motion_std);
            continue;
        }
        esp_mqtt_client_publish(s_mqtt, s_topic, json, len, 1, 0);
        nadi_led_blink(NADI_LED_BLUE, 150);
        ESP_LOGI(TAG, "Report sent: %lu packets, motion_mean %.4f, motion_std %.4f, amp_var %.6f, RSSI %.1f dBm.",
                 (unsigned long)f.n_packets, f.motion_mean, f.motion_std, f.amp_var, f.rssi_mean);
    }
}

/* ---------- start-up ---------- */

static bool settings_ok(void)
{
    bool ok = true;
    if (strlen(s_cfg.ssid) == 0) {
        ESP_LOGE(TAG, "No Wi-Fi network is set. Type setup and press Enter.");
        ok = false;
    }
    if (!safe_id(CONFIG_NADI_DEVICE_ID, 128) || !safe_id(s_cfg.room, 32)) {
        ESP_LOGE(TAG, "The device ID and room ID may use only letters, digits, - and _.");
        ok = false;
    }
    if (!parse_mac(CONFIG_NADI_SENDER_MAC, s_sender_mac)) {
        ESP_LOGE(TAG, "The sender MAC address \"%s\" is not valid, for example 1a:00:00:00:00:00.", CONFIG_NADI_SENDER_MAC);
        ok = false;
    }
#if CONFIG_NADI_TARGET_LOCAL
    if (strlen(s_cfg.host) == 0 || strlen(s_cfg.secret) == 0) {
        ESP_LOGE(TAG, "Local mode needs the laptop IP address and the MQTT password. Type setup and press Enter.");
        ok = false;
    }
#else
    if (strlen(s_cfg.host) == 0 || strlen(s_cfg.secret) == 0) {
        ESP_LOGE(TAG, "Huawei mode needs the IoTDA host name and device secret. Type setup and press Enter.");
        ok = false;
    }
#endif
    return ok;
}

/* ---------- serial commands ---------- */

static void show_settings(void)
{
    printf("Device %s, firmware %s, %s.\n", CONFIG_NADI_DEVICE_ID, NADI_FW_VERSION,
           NADI_LOCAL ? "local mode" : "huawei mode");
    printf("  Wi-Fi name:     %s\n", s_cfg.ssid[0] ? s_cfg.ssid : "(not set)");
    printf("  Wi-Fi password: %s\n", nadi_cfg_mask(s_cfg.pass));
    printf("  Broker:         %s port %ld\n", s_cfg.host[0] ? s_cfg.host : "(not set)", (long)s_cfg.port);
    printf("  " SECRET_NAME ": %s\n", nadi_cfg_mask(s_cfg.secret));
    printf("  Room ID:        %s\n", s_cfg.room);
    printf("  Sender MAC:     %s (menuconfig)\n", CONFIG_NADI_SENDER_MAC);
    EventBits_t bits = s_events ? xEventGroupGetBits(s_events) : 0;
    printf("  Now: Wi-Fi %s, MQTT %s.\n", (bits & WIFI_UP) ? "connected" : "not connected",
           (bits & MQTT_UP) ? "connected" : "not connected");
}

/* One "setup" question: Enter alone keeps the current value. Returns false if nobody answered in time. */
static bool ask(const char *question, char *value, size_t len, bool secret)
{
    char line[128];
    if (secret) {
        printf("%s [%s, Enter keeps it]: ", question, nadi_cfg_mask(value));
    } else {
        printf("%s [%s]: ", question, value[0] ? value : "not set");
    }
    fflush(stdout);
    int n = nadi_console_read(line, sizeof(line), secret, 120);
    if (n < 0) {
        printf("\nNo answer for 2 minutes: setup cancelled, nothing saved.\n");
        return false;
    }
    if (n > 0) {
        strlcpy(value, line, len);
    }
    return true;
}

static void run_setup(void)
{
    esp_log_level_set("*", ESP_LOG_WARN);  // keep the questions readable
    printf("\nSetup: type a new value and press Enter, or press Enter to keep the value in brackets.\n");
    char port[8];
    snprintf(port, sizeof(port), "%ld", (long)s_cfg.port);
    bool ok = ask("Wi-Fi name (2.4 GHz)", s_cfg.ssid, sizeof(s_cfg.ssid), false) &&
              ask("Wi-Fi password", s_cfg.pass, sizeof(s_cfg.pass), true) &&
              ask(NADI_LOCAL ? "Broker address (the laptop IP shown on the dashboard)" : "IoTDA host name",
                  s_cfg.host, sizeof(s_cfg.host), false) &&
              ask("Broker port", port, sizeof(port), false) &&
              ask(SECRET_NAME, s_cfg.secret, sizeof(s_cfg.secret), true) &&
              ask("Room ID (for example room1)", s_cfg.room, sizeof(s_cfg.room), false);
    esp_log_level_set("*", ESP_LOG_INFO);
    if (!ok) {
        load_settings();
        return;
    }
    int p = atoi(port);
    if (p < 1 || p > 65535 || !safe_id(s_cfg.room, 32)) {
        printf("The port must be 1 to 65535 and the room ID only letters, digits, - and _. Nothing saved.\n");
        load_settings();
        return;
    }
    s_cfg.port = p;
    if (nadi_cfg_set_str("ssid", s_cfg.ssid) || nadi_cfg_set_str("pass", s_cfg.pass) ||
        nadi_cfg_set_str("host", s_cfg.host) || nadi_cfg_set_int("port", s_cfg.port) ||
        nadi_cfg_set_str("secret", s_cfg.secret) || nadi_cfg_set_str("room", s_cfg.room)) {
        printf("Could not save the settings to flash.\n");
        return;
    }
    printf("Saved. Restarting in 2 s to use them.\n");
    vTaskDelay(pdMS_TO_TICKS(2000));
    esp_restart();
}

static void on_command(const char *cmd)
{
    if (strcmp(cmd, "setup") == 0) {
        run_setup();
    } else if (strcmp(cmd, "show") == 0) {
        show_settings();
    } else if (strcmp(cmd, "reset") == 0) {
        nadi_cfg_reset();
        printf("Saved settings cleared; the menuconfig values apply. Restarting in 2 s.\n");
        vTaskDelay(pdMS_TO_TICKS(2000));
        esp_restart();
    } else if (strcmp(cmd, "restart") == 0) {
        esp_restart();
    } else {
        printf("Commands: setup (change Wi-Fi, broker, room), show, reset (back to the compiled settings), restart.\n");
    }
}

/* ---------- status LED and self-recovery ---------- */

static void monitor_task(void *arg)
{
    int64_t wifi_down_since = esp_timer_get_time(), mqtt_down_since = wifi_down_since;
    esp_task_wdt_add(NULL);
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        esp_task_wdt_reset();
        int64_t now = esp_timer_get_time();
        EventBits_t bits = xEventGroupGetBits(s_events);
        bool wifi = bits & WIFI_UP, mqtt = bits & MQTT_UP;
        if (wifi) {
            wifi_down_since = now;
        }
        if (mqtt) {
            mqtt_down_since = now;
        }
        nadi_led_set(!wifi ? NADI_LED_RED : !mqtt ? NADI_LED_YELLOW
                     : now - s_last_csi_us > CSI_QUIET_US ? NADI_LED_PURPLE : NADI_LED_GREEN);
        if (nadi_console_busy()) {
            continue;  // never restart while someone is typing in setup
        }
        if (now - wifi_down_since > RESTART_AFTER_S * 1000000LL) {
            ESP_LOGE(TAG, "No Wi-Fi connection for 5 minutes. Restarting the board to try again from the start.");
            vTaskDelay(pdMS_TO_TICKS(500));
            esp_restart();
        }
        if (now - mqtt_down_since > RESTART_AFTER_S * 1000000LL) {
            ESP_LOGE(TAG, "No connection to the MQTT broker for 5 minutes. Restarting the board to try again.");
            vTaskDelay(pdMS_TO_TICKS(500));
            esp_restart();
        }
    }
}

/* ---------- start-up ---------- */

void app_main(void)
{
    nadi_cfg_init();
    load_settings();
    nadi_led_init(CONFIG_NADI_LED_GPIO);
    nadi_led_set(NADI_LED_RED);
    nadi_console_start(on_command);

#if CONFIG_NADI_TARGET_LOCAL
    const char *mode = "local mode (Mosquitto on the laptop)";
#else
    const char *mode = "huawei mode (Huawei Cloud IoTDA)";
#endif
    ESP_LOGI(TAG, "NADI CSI receiver %s is starting. Device %s, room %s, one report every %d s, %s.",
             NADI_FW_VERSION, CONFIG_NADI_DEVICE_ID, s_cfg.room, CONFIG_NADI_REPORT_INTERVAL_S, mode);
    ESP_LOGI(TAG, "Type setup and press Enter to change the Wi-Fi network, broker or room; show to see the settings.");
    ESP_LOGI(TAG, "Motion features from %s (menuconfig: Motion features from).", MOTION_NAME);
    while (!settings_ok()) {
        ESP_LOGE(TAG, "Fix the settings above with setup. Checking again in 10 s.");
        vTaskDelay(pdMS_TO_TICKS(10000));
        load_settings();
    }
    snprintf(s_topic, sizeof(s_topic), NADI_REPORT_TOPIC_FMT, CONFIG_NADI_DEVICE_ID);

    s_events = xEventGroupCreate();
    s_window_lock = xSemaphoreCreateMutex();
    s_csi_queue = xQueueCreate(128, sizeof(csi_packet_t));
    s_reconnect_timer = xTimerCreate("wifi_retry", pdMS_TO_TICKS(5000), pdFALSE, NULL, reconnect_cb);
    nadi_window_init(&s_window);

    wifi_start();
    csi_start();
    xTaskCreate(csi_task, "csi", 4096, NULL, 5, NULL);
    xTaskCreate(monitor_task, "monitor", 4096, NULL, 2, NULL);
    ESP_LOGI(TAG, "Listening for CSI from the sender " MACSTR ".", MAC2STR(s_sender_mac));

    xEventGroupWaitBits(s_events, WIFI_UP, pdFALSE, pdTRUE, portMAX_DELAY);
    time_start();
    mqtt_start();
    xTaskCreate(report_task, "report", 6144, NULL, 4, NULL);
}
