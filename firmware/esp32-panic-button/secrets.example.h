// Copy to secrets.h (git-ignored) and fill in. One file per button.
#pragma once

#define FW_VERSION      "0.1.0"
#define DEVICE_ID       "mom-room-button"        // must match an entry in hub config.yaml -> devices
#define WIFI_SSID       "HomeWiFi"
#define WIFI_PASS       "wifi-password"
#define HUB_URL         "https://alert.example.com"
#define DEVICE_TOKEN    "same-as-hub.device_token"

// Uncomment when an A7670C/T-A7670X modem is fitted. Wi-Fi is tried first; the modem is the fallback.
// #define USE_MODEM
static const char* FALLBACK_NUMBERS[] = { "+91XXXXXXXXXX", "+91XXXXXXXXXX", "+91XXXXXXXXXX", nullptr };
#define SMS_TEXT        "EMERGENCY: Mom pressed the panic button at home (Mom's room). Go now / call the house. Map: https://maps.google.com/?q=LAT,LNG"
