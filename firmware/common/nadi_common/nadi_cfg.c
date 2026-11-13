#include "nadi_cfg.h"

#include <string.h>

#include "nvs.h"
#include "nvs_flash.h"

#define NS "nadi_cfg"

void nadi_cfg_init(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);
}

void nadi_cfg_str(const char *key, const char *dflt, char *out, size_t len)
{
    nvs_handle_t h;
    size_t n = len;
    if (nvs_open(NS, NVS_READONLY, &h) == ESP_OK) {
        esp_err_t err = nvs_get_str(h, key, out, &n);
        nvs_close(h);
        if (err == ESP_OK) {
            return;
        }
    }
    strlcpy(out, dflt, len);
}

int32_t nadi_cfg_int(const char *key, int32_t dflt)
{
    nvs_handle_t h;
    int32_t v = dflt;
    if (nvs_open(NS, NVS_READONLY, &h) == ESP_OK) {
        if (nvs_get_i32(h, key, &v) != ESP_OK) {
            v = dflt;
        }
        nvs_close(h);
    }
    return v;
}

static esp_err_t commit(nvs_handle_t h, esp_err_t err)
{
    if (err == ESP_OK) {
        err = nvs_commit(h);
    }
    nvs_close(h);
    return err;
}

esp_err_t nadi_cfg_set_str(const char *key, const char *value)
{
    nvs_handle_t h;
    esp_err_t err = nvs_open(NS, NVS_READWRITE, &h);
    return err == ESP_OK ? commit(h, nvs_set_str(h, key, value)) : err;
}

esp_err_t nadi_cfg_set_int(const char *key, int32_t value)
{
    nvs_handle_t h;
    esp_err_t err = nvs_open(NS, NVS_READWRITE, &h);
    return err == ESP_OK ? commit(h, nvs_set_i32(h, key, value)) : err;
}

esp_err_t nadi_cfg_reset(void)
{
    nvs_handle_t h;
    esp_err_t err = nvs_open(NS, NVS_READWRITE, &h);
    return err == ESP_OK ? commit(h, nvs_erase_all(h)) : err;
}

const char *nadi_cfg_mask(const char *secret)
{
    return secret[0] ? "********" : "(not set)";
}
