/*
 * NADI CSI sender: broadcasts small ESP-NOW packets non-stop so the receiver can measure
 * Wi-Fi channel state information (CSI) in the room.
 *
 * Based on espressif/esp-csi examples/get-started/csi_send (Apache-2.0 / CC0).
 * Changes: sends on the Wi-Fi network's channel (found by scanning for its name), 20 MHz,
 * settings from menuconfig, plain English serial messages.
 *
 * Serial commands (115200 baud, press Enter): setup (Wi-Fi name and fallback channel, kept in flash), show, reset.
 * Status LED: green blink = sending, red = cannot start (see the serial log).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "esp_err.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_now.h"
#include "esp_system.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nadi_cfg.h"
#include "nadi_console.h"
#include "nadi_led.h"

static const char *TAG = "nadi_send";
static const uint8_t BROADCAST[ESP_NOW_ETH_ALEN] = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff};

#define NADI_FW_VERSION "1.1.0"

/* Saved with "setup" (NVS), otherwise the menuconfig values. */
static char s_ssid[33];
static int32_t s_fixed_channel;

static void load_settings(void)
{
    nadi_cfg_str("ssid", CONFIG_NADI_AP_SSID, s_ssid, sizeof(s_ssid));
    s_fixed_channel = nadi_cfg_int("channel", CONFIG_NADI_FIXED_CHANNEL);
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
    return (mac[0] & 0x01) == 0;  // a unicast address
}

/* Channel of the strongest access point with the configured name, or 0 if none is found. */
static uint8_t find_network_channel(void)
{
    if (strlen(s_ssid) == 0) {
        return 0;
    }
    wifi_scan_config_t scan = {.ssid = (uint8_t *)s_ssid, .show_hidden = true};
    if (esp_wifi_scan_start(&scan, true) != ESP_OK) {
        return 0;
    }
    uint16_t n = 1;
    wifi_ap_record_t best = {0};
    esp_err_t err = esp_wifi_scan_get_ap_records(&n, &best);  // sorted by signal strength
    if (err != ESP_OK || n == 0) {
        esp_wifi_clear_ap_list();
        return 0;
    }
    return best.primary;
}

static uint8_t pick_channel(void)
{
    uint8_t ch = find_network_channel();
    if (ch) {
        ESP_LOGI(TAG, "Found the Wi-Fi network \"%s\" on channel %d.", s_ssid, ch);
        return ch;
    }
    if (strlen(s_ssid) > 0) {
        ESP_LOGW(TAG, "The Wi-Fi network \"%s\" was not found. Using the fixed channel %d. "
                 "Check the name, and that it is a 2.4 GHz network.", s_ssid, (int)s_fixed_channel);
    } else {
        ESP_LOGW(TAG, "No Wi-Fi network name is set. Using the fixed channel %d.", (int)s_fixed_channel);
    }
    return (uint8_t)s_fixed_channel;
}

static void wifi_start(const uint8_t mac[6])
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();  // needed for scanning
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_mac(WIFI_IF_STA, mac));
    // 20 MHz only: it works whatever width the network uses
    ESP_ERROR_CHECK(esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW_HT20));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
}

static void espnow_start(void)
{
    ESP_ERROR_CHECK(esp_now_init());
    esp_now_peer_info_t peer = {
        .channel = 0,  // 0 = whatever channel the radio is on now
        .ifidx = WIFI_IF_STA,
        .encrypt = false,
    };
    memcpy(peer.peer_addr, BROADCAST, sizeof(BROADCAST));
    ESP_ERROR_CHECK(esp_now_add_peer(&peer));
    // An OFDM rate (802.11n MCS0), because 802.11b packets carry no CSI
    esp_now_rate_config_t rate = {
        .phymode = WIFI_PHY_MODE_HT20,
        .rate = WIFI_PHY_RATE_MCS0_LGI,
        .ersu = false,
        .dcm = false,
    };
    ESP_ERROR_CHECK(esp_now_set_peer_rate_config(BROADCAST, &rate));
}

/* ---------- serial commands ---------- */

static void show_settings(void)
{
    printf("NADI CSI sender, firmware %s.\n", NADI_FW_VERSION);
    printf("  Wi-Fi name:       %s\n", s_ssid[0] ? s_ssid : "(not set: fixed channel only)");
    printf("  Fallback channel: %d\n", (int)s_fixed_channel);
    printf("  Sender MAC:       %s (menuconfig)\n", CONFIG_NADI_SENDER_MAC);
}

static void run_setup(void)
{
    char line[64];
    esp_log_level_set("*", ESP_LOG_WARN);  // keep the questions readable
    printf("\nSetup: type a new value and press Enter, or press Enter to keep the value in brackets.\n");
    printf("Wi-Fi name the receiver uses (2.4 GHz, no password needed) [%s]: ", s_ssid[0] ? s_ssid : "not set");
    fflush(stdout);
    int n = nadi_console_read(line, sizeof(line), false, 120);
    char ssid[33];
    strlcpy(ssid, n > 0 ? line : s_ssid, sizeof(ssid));
    int channel = s_fixed_channel;
    if (n >= 0) {
        printf("Channel to use if that network is not found, 1 to 13 [%d]: ", (int)s_fixed_channel);
        fflush(stdout);
        int m = nadi_console_read(line, sizeof(line), false, 120);
        if (m > 0) {
            channel = atoi(line);
        }
        n = m;
    }
    esp_log_level_set("*", ESP_LOG_INFO);
    if (n < 0) {
        printf("\nNo answer for 2 minutes: setup cancelled, nothing saved.\n");
        return;
    }
    if (channel < 1 || channel > 13) {
        printf("The channel must be 1 to 13. Nothing saved.\n");
        return;
    }
    if (nadi_cfg_set_str("ssid", ssid) || nadi_cfg_set_int("channel", channel)) {
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
        printf("Commands: setup (Wi-Fi name and channel), show, reset (back to the compiled settings), restart.\n");
    }
}

void app_main(void)
{
    nadi_cfg_init();
    load_settings();
    nadi_led_init(CONFIG_NADI_LED_GPIO);
    nadi_console_start(on_command);

    ESP_LOGI(TAG, "NADI CSI sender %s is starting. Type setup and press Enter to change the Wi-Fi name or channel.",
             NADI_FW_VERSION);
    uint8_t mac[6];
    if (!parse_mac(CONFIG_NADI_SENDER_MAC, mac)) {
        ESP_LOGE(TAG, "The sender MAC address \"%s\" is not valid. Set it in menuconfig, for example 1a:00:00:00:00:00.",
                 CONFIG_NADI_SENDER_MAC);
        nadi_led_set(NADI_LED_RED);
        return;
    }

    wifi_start(mac);
    uint8_t channel = pick_channel();
    ESP_ERROR_CHECK(esp_wifi_set_channel(channel, WIFI_SECOND_CHAN_NONE));
    espnow_start();
    ESP_LOGI(TAG, "Sending %d packets per second on channel %d from " MACSTR ".",
             CONFIG_NADI_SEND_HZ, channel, MAC2STR(mac));

    const TickType_t period = pdMS_TO_TICKS(1000 / CONFIG_NADI_SEND_HZ) ? pdMS_TO_TICKS(1000 / CONFIG_NADI_SEND_HZ) : 1;
    TickType_t last_wake = xTaskGetTickCount();
    int64_t last_status_us = esp_timer_get_time();
    int64_t last_scan_us = last_status_us;
    uint32_t sent = 0, failed = 0;
    esp_task_wdt_add(NULL);

    for (uint32_t seq = 0;; seq++) {
        esp_task_wdt_reset();
        if (seq % CONFIG_NADI_SEND_HZ == 0) {
            nadi_led_blink(NADI_LED_GREEN, 100);  // one green blink a second while sending
        }
        if (esp_now_send(BROADCAST, (const uint8_t *)&seq, sizeof(seq)) == ESP_OK) {
            sent++;
        } else {
            failed++;
        }
        int64_t now = esp_timer_get_time();
        if (now - last_status_us >= 10 * 1000000LL) {
            if (failed) {
                ESP_LOGW(TAG, "Sent %lu packets on channel %d in the last 10 s; %lu could not be sent.",
                         (unsigned long)sent, channel, (unsigned long)failed);
            } else {
                ESP_LOGI(TAG, "Sent %lu packets on channel %d in the last 10 s.", (unsigned long)sent, channel);
            }
            sent = failed = 0;
            last_status_us = now;
        }
        if (strlen(s_ssid) > 0 && now - last_scan_us >= CONFIG_NADI_RESCAN_S * 1000000LL) {
            last_scan_us = now;
            uint8_t found = find_network_channel();
            if (found && found != channel) {
                ESP_LOGW(TAG, "The Wi-Fi network moved from channel %d to channel %d. Following it.", channel, found);
                channel = found;
            }
            // Scanning leaves the radio on another channel, so always set it back
            ESP_ERROR_CHECK(esp_wifi_set_channel(channel, WIFI_SECOND_CHAN_NONE));
            last_wake = xTaskGetTickCount();
        }
        vTaskDelayUntil(&last_wake, period);
    }
}
