# What I need from you to make this real

Everything below is a config entry or a document, not a code change. Send them in any order; partial is fine.

## 1. The house
- [ ] Full postal address, and the "how a driver actually finds it" directions (landmark, lane, gate colour).
- [ ] Google Maps pin (share link) and the Plus Code from Google Maps. I will generate the DIGIPIN.
- [ ] Which room is whose; where the router is; where the concentrator and cylinder are; is there an inverter?
- [ ] Wi-Fi name (not the password here; that goes straight into `secrets.h` on the buttons).
- [ ] Photos of the bedside walls where the buttons will go, and of the two old phones (model + Android version).

## 2. The people (one line each: name, role, mobile, Android or iPhone, WhatsApp yes/no, Telegram yes/no)
- [ ] You
- [ ] Your brother
- [ ] Mom's phone, Dad's phone
- [ ] Driver
- [ ] Neighbour 1, Neighbour 2
- [ ] The society doctor (once found; I can help draft the ask)
- [ ] Anyone else who should be on the list but is not expected to respond (aunt, family friend)

## 3. Hospitals (I will research them once I have the location)
- [ ] Your current preferred hospital and why.
- [ ] Any hospital the parents are already registered at / insurance network.

## 4. Medical (kept OUT of git; put them in a private folder or send them in chat)
- [ ] Mom: diagnosis list, current medicines with doses, last HbA1c, kidney function, any hypoglycaemia history, who her diabetologist is.
- [ ] Dad: diagnosis list, current medicines with doses, last ECG/echo, usual BP, any COPD/smoking history (changes the oxygen target).
- [ ] Allergies, blood groups, any stents/pacemaker, any blood thinners.
- [ ] Health insurance: policy, TPA number; are they 70+ (Ayushman Vay Vandana eligibility)?

## 5. Oxygen
- [ ] Concentrator make and model, and its max flow (L/min).
- [ ] Cylinder size (letters on the shoulder, e.g. "D", "B", or litres water capacity), the regulator type, and the gauge reading now.
- [ ] Do you have a pulse oximeter at the house? Which one?

## 6. Infrastructure decisions (I have defaults; override if you want)
- Hub hosting: default is a small VPS + your own domain. Do you have a domain / VPS / cloud account already?
- Phone siren: default is Pushover (Rs ~420 one-time per person). OK?
- SMS: default is an old Android phone with a prepaid SIM running SMS Gateway. Do you have a third old phone?
- Voice calls: Exotel (needs KYC, a few days) vs starting with the 4G module on the button. Which first?
- Home Assistant: do you already run it, or should lights wait for phase 2?

## 7. Budget check (phase 0 + 1, rough)
| Item | Rs |
|---|---|
| VPS 3 months | 1,500 |
| Pushover x 4 people | 1,700 |
| 2 x ESP32 button kits | 1,800 |
| Mini UPS x 2 | 4,000 |
| Prepaid SIM 3 months | 600 |
| Pulse oximeter, BP monitor, glucometer strips, glucose tabs, aspirin | 3,500 |
| Laminated cards, red folder, gate sticker | 500 |
| **Total** | **~13,600** |
Phase 2 adds ~Rs 3,000 per 4G module, ~Rs 3,000 for Zigbee buttons + dongle, ~Rs 1,000 per WiZ bulb.
