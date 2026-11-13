set(embed "")
if(CONFIG_NADI_MQTT_TLS)
    # the local broker's CA certificate, written by python scripts/mqtt_tls.py (git-ignored)
    if(NOT EXISTS "${CMAKE_CURRENT_LIST_DIR}/mqtt_ca.pem")
        message(FATAL_ERROR "MQTT over TLS is on but main/mqtt_ca.pem is missing. Run python scripts/mqtt_tls.py first.")
    endif()
    set(embed "mqtt_ca.pem")
endif()
idf_component_register(SRCS "main.c" "csi_features.c" "report.c"
                       INCLUDE_DIRS "."
                       EMBED_TXTFILES ${embed}
                       PRIV_REQUIRES esp_wifi esp_netif esp_timer nvs_flash mqtt mbedtls nadi_common)
