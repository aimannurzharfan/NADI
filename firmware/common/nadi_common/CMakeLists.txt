# Shared by csi_send and csi_recv: settings kept in flash (NVS), serial command line, onboard RGB LED.
idf_component_register(SRCS "nadi_cfg.c" "nadi_console.c" "nadi_led.c"
                       INCLUDE_DIRS "."
                       REQUIRES nvs_flash
                       PRIV_REQUIRES esp_driver_uart esp_timer)
