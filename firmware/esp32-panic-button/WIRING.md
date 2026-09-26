# Wall panic button: wiring and build

One unit per bedroom. Mounted on the wall beside the bed at a height the parent can hit from lying down, plus a second pull-cord or a Zigbee button in the bathroom (falls happen there).

## Parts (per unit, Indian prices approximate, Sept 2026)

| Part | Why | Approx. |
|---|---|---|
| ESP32 DevKitC (WROOM-32) | Wi-Fi, cheap, well supported | Rs 300-400 |
| 60 mm red mushroom push button, **1 NC contact** (Schneider XB4/XB5 style, or arcade dome button) | Big, tactile, obvious. NC = broken wire is an alarm, not silence | Rs 250-500 |
| 5 V 2 A USB adapter + cable | Mains power | Rs 200 |
| Mini DC UPS for router (Resonate RouterUPS / Oakter) | Power cuts. One for the router, one shared by buttons | Rs 1,500-2,500 |
| Piezo buzzer 5 V active | Confirms the press was sent | Rs 30 |
| 5 mm LEDs green + red, 220 ohm resistors | Status | Rs 20 |
| ABS junction box 100 x 100 mm | Enclosure | Rs 100 |
| Optional: LilyGO T-A7670X (ESP32 + 4G Cat-1 modem, voice + SMS) instead of the plain ESP32, with a prepaid SIM | Works when Wi-Fi / broadband is down | Rs 2,500-3,500 + Rs 200/month SIM |

Do **not** use SIM800L (2G). Jio has no 2G and Airtel/Vi are switching it off.

## Connections

```
Mushroom button (NC)   ---- GPIO14 ---- (internal pull-up)
                       ---- GND
Green LED  anode -> 220R -> GPIO25, cathode -> GND
Red LED    anode -> 220R -> GPIO26, cathode -> GND
Buzzer     + -> GPIO27, - -> GND
Optional supply sense: UPS 5V -> 10k -> GPIO34 -> 10k -> GND  (2:1 divider)
5V in from USB adapter (behind the mini UPS)
```

Rest state: contact closed, GPIO14 reads LOW. Press (or cable cut): GPIO14 reads HIGH, alert sent.

If you use the T-A7670X, its modem is on UART1 (default TX 26 / RX 27 / PWRKEY 4 on that board), so move the LEDs and buzzer to free pins (e.g. 32, 33, 25) and update the constants in the sketch.

## LED language (teach this to the parents and the helper)

| LED | Meaning |
|---|---|
| Green steady | Everything fine. Button will work. |
| Green fast blink | No Wi-Fi. Check the router / router UPS. Modem fallback still works if fitted. |
| Green slow blink | Wi-Fi ok but the hub is unreachable (internet or server down). Modem fallback if fitted. |
| Red steady | Alert has been sent and is still open. Help has been told. |
| 3 short beeps then 1 long beep | Press received and the family has been told. |
| Frantic short beeps | Could NOT send anything. Call 112 by phone. |

## Build steps

1. Arduino IDE 2.x: Boards Manager -> "esp32" by Espressif. Library Manager -> ArduinoJson (7.x). For the modem: TinyGSM (use the LilyGO fork for A7670).
2. Copy `secrets.example.h` to `secrets.h`, fill in the SSID, hub URL and device token. Use a different `DEVICE_ID` for each room.
3. Flash. Open Serial Monitor at 115200 and confirm `panic button mom-room-button fw 0.1.0 booted` and a heartbeat `200`.
4. Check the hub: `GET /api/v1/status?t=<responder_token>` shows the device online.
5. Press the button with the hub in test mode (or with `kind: test` from the kiosk) before wiring it to the wall.
6. Mount so the button is reachable from the bed with the parent lying down. Cable-tie the USB cable so it cannot be tugged out; a pulled plug shows up as "offline" within 5 minutes anyway.

## Things to get right

- **Every button needs its own `DEVICE_ID`** or the hub will think Mom's press came from Dad's room.
- Set `client.setCACert` with the hub's CA once you have a fixed domain; `setInsecure()` is for bring-up only.
- Keep the mini UPS's output on the router AND the button. The button without the router is only useful if the modem is fitted.
- The hub's weekly test (`docs/RUNBOOK.md`) is the only proof the whole chain still works. Put it in the calendar.
