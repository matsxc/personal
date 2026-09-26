/*
 * Wall panic button for an elderly parent's room.
 *
 * Hardware (see firmware/esp32-panic-button/WIRING.md):
 *   - ESP32 dev board (or LilyGO T-A7670X for built-in 4G)
 *   - 60 mm red MUSHROOM push button, NORMALLY-CLOSED contact, between BUTTON_PIN and GND
 *       (NC means a broken wire or a pulled plug = alarm, not silence)
 *   - Status LED (green/red) on LED_OK_PIN / LED_ALERT_PIN, piezo buzzer on BUZZER_PIN
 *   - 5 V supply from a USB adapter behind a small DC UPS
 *   - OPTIONAL: SIMCom A7670C on Serial1 for SMS + voice call when Wi-Fi / the hub is unreachable
 *
 * Behaviour:
 *   PRESS            -> POST /api/v1/alert to the hub (retries 5x). Buzzer chirps, red LED on.
 *                       If the hub cannot be reached and a modem is fitted: SMS every fallback
 *                       number + dial the first one.
 *   HOLD 5 s         -> cancel (only works within the hub's 20 s grace window) - for mis-presses.
 *   every 60 s       -> heartbeat with RSSI, uptime, supply voltage. Hub alerts the family when
 *                       heartbeats stop (dead button = no coverage).
 *   Wi-Fi drop       -> yellow blink, keeps reconnecting forever, still works via modem.
 *   Weekly self-test -> the hub side runs it; nothing needed here.
 *
 * Build: Arduino IDE 2.x or PlatformIO, board "ESP32 Dev Module", libraries: ArduinoJson,
 * (optional) TinyGSM. Copy secrets.example.h -> secrets.h.
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "secrets.h"

// ---------------------------------------------------------------- pins
constexpr int BUTTON_PIN     = 14;  // NC contact to GND; internal pull-up
constexpr int LED_OK_PIN     = 25;  // green
constexpr int LED_ALERT_PIN  = 26;  // red
constexpr int BUZZER_PIN     = 27;
constexpr int VSENSE_PIN     = 34;  // optional divider from the UPS output (2:1) to monitor supply

// ---------------------------------------------------------------- timings
constexpr uint32_t DEBOUNCE_MS        = 60;
constexpr uint32_t HOLD_CANCEL_MS     = 5000;
constexpr uint32_t HEARTBEAT_MS       = 60UL * 1000;
constexpr uint32_t HTTP_TIMEOUT_MS    = 8000;
constexpr int      HTTP_RETRIES       = 5;
constexpr uint32_t ALERT_LED_MS       = 15UL * 60 * 1000; // red stays on this long after a press

// ---------------------------------------------------------------- modem (optional)
#ifdef USE_MODEM
  #define TINY_GSM_MODEM_A7670
  #include <TinyGsmClient.h>
  HardwareSerial modemSerial(1);
  TinyGsm modem(modemSerial);
  constexpr int MODEM_TX = 27, MODEM_RX = 26, MODEM_PWRKEY = 4; // T-A7670X defaults; adjust for your board
#endif

// ---------------------------------------------------------------- state
enum class Link { OK, NO_WIFI, NO_HUB };
Link link = Link::NO_WIFI;
uint32_t lastHeartbeat = 0;
uint32_t alertLedUntil = 0;
uint32_t pressStart = 0;
bool pressed = false;
bool cancelSent = false;
String lastIncident;

// ---------------------------------------------------------------- helpers
void chirp(int n, int ms = 80) {
  for (int i = 0; i < n; i++) { digitalWrite(BUZZER_PIN, HIGH); delay(ms); digitalWrite(BUZZER_PIN, LOW); delay(ms); }
}

float supplyVolts() {
  // 12-bit ADC, 3.3 V ref, 2:1 divider. Returns 0 if not wired.
  int raw = analogRead(VSENSE_PIN);
  return raw < 50 ? 0.0f : raw * (3.3f / 4095.0f) * 2.0f;
}

void showLink() {
  static uint32_t t = 0; static bool on = false;
  uint32_t now = millis();
  if (now < alertLedUntil) { digitalWrite(LED_ALERT_PIN, HIGH); digitalWrite(LED_OK_PIN, LOW); return; }
  digitalWrite(LED_ALERT_PIN, LOW);
  switch (link) {
    case Link::OK:      digitalWrite(LED_OK_PIN, HIGH); break;
    case Link::NO_WIFI: if (now - t > 250) { t = now; on = !on; digitalWrite(LED_OK_PIN, on); } break;  // fast blink
    case Link::NO_HUB:  if (now - t > 1000) { t = now; on = !on; digitalWrite(LED_OK_PIN, on); } break; // slow blink
  }
}

void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  static uint32_t lastTry = 0;
  if (millis() - lastTry < 10000) return;
  lastTry = millis();
  link = Link::NO_WIFI;
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASS);
}

// POST JSON to the hub. Returns HTTP status, or -1 on transport failure. Fills `out` with the body.
int postJson(const char* path, const String& body, String& out) {
  if (WiFi.status() != WL_CONNECTED) return -1;
  WiFiClientSecure client;
  client.setInsecure(); // TODO: pin the hub's CA with client.setCACert(HUB_CA) once the domain is fixed
  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);
  if (!http.begin(client, String(HUB_URL) + path)) return -1;
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", String("Bearer ") + DEVICE_TOKEN);
  int code = http.POST(body);
  out = code > 0 ? http.getString() : "";
  http.end();
  return code;
}

String deviceJson(const char* kind) {
  JsonDocument d;
  d["device_id"] = DEVICE_ID;
  if (kind) d["kind"] = kind;
  JsonObject e = d["extra"].to<JsonObject>();
  e["rssi"] = WiFi.RSSI();
  e["uptime_s"] = millis() / 1000;
  e["supply_v"] = supplyVolts();
  e["fw"] = FW_VERSION;
  String s; serializeJson(d, s); return s;
}

// ---------------------------------------------------------------- modem fallback
bool modemAlert() {
#ifdef USE_MODEM
  Serial.println("[modem] hub unreachable, falling back to SMS + call");
  if (!modem.isNetworkConnected()) { modem.restart(); modem.waitForNetwork(30000); }
  bool any = false;
  String text = String(SMS_TEXT) + " Time: " + String(millis() / 1000) + "s uptime. (Wi-Fi/hub down, sent from the button itself)";
  for (const char* num : FALLBACK_NUMBERS) {
    if (!num || !*num) continue;
    if (modem.sendSMS(num, text)) any = true;
    delay(500);
  }
  if (FALLBACK_NUMBERS[0] && *FALLBACK_NUMBERS[0]) {
    modem.callNumber(FALLBACK_NUMBERS[0]);
    delay(25000);             // let it ring; a missed call from the house number IS the message
    modem.callHangup();
  }
  return any;
#else
  return false;
#endif
}

// ---------------------------------------------------------------- actions
void sendAlert() {
  Serial.println("[alert] BUTTON PRESSED");
  alertLedUntil = millis() + ALERT_LED_MS;
  chirp(3);
  String resp; int code = -1;
  for (int i = 0; i < HTTP_RETRIES && !(code >= 200 && code < 300); i++) {
    ensureWifi();
    code = postJson("/api/v1/alert", deviceJson("panic"), resp);
    Serial.printf("[alert] attempt %d -> %d %s\n", i + 1, code, resp.c_str());
    if (code < 0 || code >= 500) delay(1000 * (i + 1));
  }
  if (code >= 200 && code < 300) {
    JsonDocument d; if (!deserializeJson(d, resp)) lastIncident = String((const char*)d["incident_id"]);
    link = Link::OK;
    chirp(1, 400); // long beep = "the family has been told"
  } else {
    link = (WiFi.status() == WL_CONNECTED) ? Link::NO_HUB : Link::NO_WIFI;
    bool ok = modemAlert();
    if (ok) chirp(1, 400); else { for (int i = 0; i < 6; i++) chirp(2, 60); } // frantic = could not send anything
  }
}

void sendCancel() {
  String resp;
  int code = postJson("/api/v1/cancel", deviceJson(nullptr), resp);
  Serial.printf("[cancel] -> %d %s\n", code, resp.c_str());
  if (code >= 200 && code < 300) { alertLedUntil = 0; chirp(2, 150); }
}

void sendHeartbeat() {
  String resp;
  int code = postJson("/api/v1/heartbeat", deviceJson(nullptr), resp);
  if (code >= 200 && code < 300) {
    link = Link::OK;
    JsonDocument d;
    if (!deserializeJson(d, resp)) {
      // Keep the red LED on while the hub still has an open incident for this room.
      if (!d["open_incident"].isNull()) alertLedUntil = millis() + HEARTBEAT_MS * 2;
      else if (alertLedUntil > millis() + HEARTBEAT_MS * 2) alertLedUntil = 0;
    }
  } else {
    link = (WiFi.status() == WL_CONNECTED) ? Link::NO_HUB : Link::NO_WIFI;
    Serial.printf("[heartbeat] failed: %d\n", code);
  }
}

// ---------------------------------------------------------------- setup / loop
void setup() {
  Serial.begin(115200);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(LED_OK_PIN, OUTPUT); pinMode(LED_ALERT_PIN, OUTPUT); pinMode(BUZZER_PIN, OUTPUT);
  analogReadResolution(12);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.setSleep(false); // latency matters more than power here; we are on mains + UPS
  ensureWifi();
#ifdef USE_MODEM
  pinMode(MODEM_PWRKEY, OUTPUT); digitalWrite(MODEM_PWRKEY, HIGH); delay(1000); digitalWrite(MODEM_PWRKEY, LOW);
  modemSerial.begin(115200, SERIAL_8N1, MODEM_RX, MODEM_TX);
  modem.init();
#endif
  chirp(1);
  Serial.printf("panic button %s fw %s booted\n", DEVICE_ID, FW_VERSION);
  lastHeartbeat = millis() - HEARTBEAT_MS; // heartbeat immediately after boot
}

void loop() {
  ensureWifi();
  showLink();

  // NC button: contact closed (LOW) at rest, OPEN (HIGH via pull-up) when pressed or when the wire breaks.
  bool rawPressed = digitalRead(BUTTON_PIN) == HIGH;
  static uint32_t edgeAt = 0; static bool lastRaw = false;
  if (rawPressed != lastRaw) { lastRaw = rawPressed; edgeAt = millis(); }
  bool stable = millis() - edgeAt > DEBOUNCE_MS;

  if (stable && rawPressed && !pressed) {          // press begins
    pressed = true; cancelSent = false; pressStart = millis();
    sendAlert();
  } else if (stable && rawPressed && pressed && !cancelSent && millis() - pressStart > HOLD_CANCEL_MS) {
    cancelSent = true;                              // long hold = "I pressed by mistake"
    sendCancel();
  } else if (stable && !rawPressed && pressed) {   // released (or latching mushroom twisted back out)
    pressed = false;
  }

  if (millis() - lastHeartbeat >= HEARTBEAT_MS) { lastHeartbeat = millis(); sendHeartbeat(); }
  delay(10);
}
