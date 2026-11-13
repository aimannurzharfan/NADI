/*
 * Settings typed in over serial ("setup") and kept in flash (NVS namespace "nadi_cfg").
 * A setting that was never saved falls back to the value compiled in from menuconfig.
 */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"

/* Opens NVS (erasing it only if its format is unusable). Call once at start-up. */
void nadi_cfg_init(void);

/* The saved string for key, or dflt if none was saved. */
void nadi_cfg_str(const char *key, const char *dflt, char *out, size_t len);
int32_t nadi_cfg_int(const char *key, int32_t dflt);

esp_err_t nadi_cfg_set_str(const char *key, const char *value);
esp_err_t nadi_cfg_set_int(const char *key, int32_t value);

/* Forget every saved setting: the compiled values apply again after a restart. */
esp_err_t nadi_cfg_reset(void);

/* "********" for a non-empty secret, "(not set)" for an empty one: passwords are never printed. */
const char *nadi_cfg_mask(const char *secret);
