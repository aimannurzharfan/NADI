/*
 * Serial command line on the COM/UART port (115200 baud): type a word and press Enter.
 * Works with the Arduino Serial Monitor, PuTTY, or python -m serial.tools.miniterm.
 */
#pragma once

#include <stdbool.h>
#include <stddef.h>

typedef void (*nadi_cmd_fn)(const char *line);

/* Start a task that reads lines and passes each non-empty one to handler (lower case, trimmed). */
void nadi_console_start(nadi_cmd_fn handler);

/*
 * Read one line for a "setup" question. Typed characters are echoed, or shown as * when mask is true,
 * so a password never appears on screen. Returns the length, or -1 if nothing was typed for timeout_s.
 * Call only from inside the handler.
 */
int nadi_console_read(char *buf, size_t len, bool mask, int timeout_s);

/* True while a "setup" question is waiting for an answer (so the board does not restart under you). */
bool nadi_console_busy(void);
