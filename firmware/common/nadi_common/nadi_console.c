#include "nadi_console.h"

#include <ctype.h>
#include <stdio.h>
#include <string.h>

#include "driver/uart.h"
#include "driver/uart_vfs.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define UART_NUM CONFIG_ESP_CONSOLE_UART_NUM

static nadi_cmd_fn s_handler;
static volatile bool s_busy;
static char s_prev;  // last line ending, so "\r\n" counts as one Enter

static void echo(const char *s, size_t n)
{
    uart_write_bytes(UART_NUM, s, n);
}

static int read_line(char *buf, size_t len, bool mask, int timeout_s, bool echo_on)
{
    size_t n = 0;
    int64_t deadline = timeout_s > 0 ? esp_timer_get_time() + (int64_t)timeout_s * 1000000 : 0;
    for (;;) {
        uint8_t c;
        if (uart_read_bytes(UART_NUM, &c, 1, pdMS_TO_TICKS(200)) != 1) {
            if (deadline && esp_timer_get_time() > deadline) {
                buf[n] = 0;
                return -1;
            }
            continue;
        }
        if (c == '\n' && s_prev == '\r' && n == 0) {
            s_prev = 0;
            continue;
        }
        if (c == '\r' || c == '\n') {
            s_prev = (char)c;
            buf[n] = 0;
            if (echo_on) {
                echo("\r\n", 2);
            }
            return (int)n;
        }
        s_prev = 0;
        if ((c == 0x08 || c == 0x7f) && n > 0) {
            n--;
            if (echo_on) {
                echo("\b \b", 3);
            }
        } else if (c >= 0x20 && c < 0x7f && n + 1 < len) {
            buf[n++] = (char)c;
            if (echo_on) {
                echo(mask ? "*" : (const char *)&c, 1);
            }
        }
    }
}

int nadi_console_read(char *buf, size_t len, bool mask, int timeout_s)
{
    s_busy = true;
    int n = read_line(buf, len, mask, timeout_s, true);
    s_busy = false;
    return n;
}

bool nadi_console_busy(void)
{
    return s_busy;
}

static void console_task(void *arg)
{
    char line[64];
    for (;;) {
        if (read_line(line, sizeof(line), false, 0, false) <= 0) {
            continue;
        }
        char *p = line;
        while (*p == ' ') {
            p++;
        }
        for (char *q = p; *q; q++) {
            *q = (char)tolower((unsigned char)*q);
        }
        for (size_t n = strlen(p); n && p[n - 1] == ' '; n--) {
            p[n - 1] = 0;
        }
        if (*p) {
            s_handler(p);
        }
    }
}

void nadi_console_start(nadi_cmd_fn handler)
{
    s_handler = handler;
    if (!uart_is_driver_installed(UART_NUM)) {
        uart_driver_install(UART_NUM, 512, 0, 0, NULL, 0);
    }
    uart_vfs_dev_use_driver(UART_NUM);  // log output and our echo share the driver without mixing bytes
    xTaskCreate(console_task, "console", 6144, NULL, 3, NULL);
}
