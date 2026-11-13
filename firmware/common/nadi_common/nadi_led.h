/*
 * The onboard RGB LED (WS2812): one steady colour for the board's state, plus short blinks.
 * GPIO 48 on most DevKitC-1 boards, 38 on some versions; a negative pin turns the LED off for good.
 */
#pragma once

typedef enum {
    NADI_LED_OFF,
    NADI_LED_RED,
    NADI_LED_YELLOW,
    NADI_LED_PURPLE,
    NADI_LED_GREEN,
    NADI_LED_BLUE,
    NADI_LED_WHITE,
} nadi_color_t;

void nadi_led_init(int gpio);

/* The steady colour. */
void nadi_led_set(nadi_color_t c);

/* Show c for ms milliseconds, then go back to the steady colour. */
void nadi_led_blink(nadi_color_t c, int ms);
