#include "nadi_led.h"

#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "led_strip.h"

#define LEVEL 24  // of 255: bright enough to see across a room, not blinding on a desk

static const char *TAG = "nadi_led";
static led_strip_handle_t s_strip;
static SemaphoreHandle_t s_lock;
static esp_timer_handle_t s_timer;
static nadi_color_t s_steady = NADI_LED_OFF;
static volatile bool s_blinking;

static void show(nadi_color_t c)
{
    static const uint8_t rgb[][3] = {
        [NADI_LED_OFF] = {0, 0, 0},
        [NADI_LED_RED] = {LEVEL, 0, 0},
        [NADI_LED_YELLOW] = {LEVEL, LEVEL * 2 / 3, 0},
        [NADI_LED_PURPLE] = {LEVEL, 0, LEVEL},
        [NADI_LED_GREEN] = {0, LEVEL, 0},
        [NADI_LED_BLUE] = {0, 0, LEVEL},
        [NADI_LED_WHITE] = {LEVEL, LEVEL, LEVEL},
    };
    if (!s_strip) {
        return;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    led_strip_set_pixel(s_strip, 0, rgb[c][0], rgb[c][1], rgb[c][2]);
    led_strip_refresh(s_strip);
    xSemaphoreGive(s_lock);
}

static void blink_done(void *arg)
{
    s_blinking = false;
    show(s_steady);
}

void nadi_led_init(int gpio)
{
    if (gpio < 0) {
        ESP_LOGI(TAG, "Status LED is turned off in the settings.");
        return;
    }
    led_strip_config_t strip = {
        .strip_gpio_num = gpio,
        .max_leds = 1,
        .led_pixel_format = LED_PIXEL_FORMAT_GRB,
        .led_model = LED_MODEL_WS2812,
    };
    led_strip_rmt_config_t rmt = {
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = 10 * 1000 * 1000,
    };
    if (led_strip_new_rmt_device(&strip, &rmt, &s_strip) != ESP_OK) {
        ESP_LOGW(TAG, "No status LED on GPIO %d. The board works without it.", gpio);
        s_strip = NULL;
        return;
    }
    s_lock = xSemaphoreCreateMutex();
    const esp_timer_create_args_t args = {.callback = blink_done, .name = "led_blink"};
    esp_timer_create(&args, &s_timer);
    led_strip_clear(s_strip);
}

void nadi_led_set(nadi_color_t c)
{
    s_steady = c;
    if (!s_blinking) {
        show(c);
    }
}

void nadi_led_blink(nadi_color_t c, int ms)
{
    if (!s_strip) {
        return;
    }
    s_blinking = true;
    show(c);
    esp_timer_stop(s_timer);
    esp_timer_start_once(s_timer, (uint64_t)ms * 1000);
}
