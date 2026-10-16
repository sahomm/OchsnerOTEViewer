# Changelog / Änderungsprotokoll

Alle Änderungen je Version, zuerst Deutsch, dann Englisch. / All changes per version, German first, then English.

## 0.15.0

### Deutsch

**Neu**
- Sensor **Betriebsart** in Klartext (Standby, Anlauf, Läuft, Heizen, Warmwasser, Abtauen, Nachlauf, Unbekannt) in der Sprache von Home Assistant; der Rohstatus steht im Attribut `status_code`.
- **COP gesamt, COP Heizen, COP Warmwasser** (kumuliert seit Start oder Reset), **COP letzter Lauf** sowie die Summen **Strom Heizen**, **Strom Warmwasser** und **Wärme Warmwasser (berechnet)**. Der Anteil Warmwasser an Strom und Wärme steht als Attribut am COP gesamt.
- **Warmwasser-Erkennung über den Volumenstrom** (optional, in Einrichtung und Optionen): Schalter und Schwelle in l/min. Ohne Schwelle sind COP Heizen und COP Warmwasser „Unbekannt“, der COP gesamt rechnet dann aus dem Durchfluss.
- Option **„Kumulierte COP-Summen zurücksetzen“** in Einrichtung und Optionen. Die Summen werden gespeichert und bleiben auch beim Entfernen der Integration erhalten.
- Neue Sensoren bekommen einheitliche IDs `sensor.ochsner_heatpump_<schlüssel>`, unabhängig vom Raum des Geräts. Bestehende Entitäten behalten ihre IDs.

**Geändert**
- Voraussetzung: **Home Assistant 2026.10.1 oder neuer** (in der `hacs.json` festgelegt).
- Der Sensor „JAZ“ heißt jetzt „JAZ (Heizzähler ÷ Gesamtstrom)“ (nur der Anzeigename; Schlüssel, ID und Verlauf unverändert).
- Das Ein- oder Ausschalten der Warmwasser-Erkennung lädt die Integration neu; die Schwelle wirkt sofort.
- README überarbeitet (Status, neue Abschnitte, Hinweise).

### English

**New**
- **Operating mode** sensor in plain words (Standby, Starting, Running, Heating, Hot water, Defrost, Run-on, Unknown) in the Home Assistant language; the raw status is in the attribute `status_code`.
- **COP total, COP heating, COP hot water** (cumulative since start or reset), **COP last run**, and the totals **Electricity heating**, **Electricity hot water** and **Heat hot water (calculated)**. The hot-water share of electricity and heat is an attribute of COP total.
- **Hot-water detection by volume flow** (optional, in setup and options): switch and threshold in l/min. Without a threshold COP heating and COP hot water are "Unknown", and COP total is calculated from the flow.
- Option **"Reset the cumulative COP totals"** in setup and options. The totals are saved and survive removing the integration.
- New sensors get uniform IDs `sensor.ochsner_heatpump_<key>`, regardless of the device's area. Existing entities keep their IDs.

**Changed**
- Requirement: **Home Assistant 2026.10.1 or newer** (set in `hacs.json`).
- The "SPF" sensor is now named "SPF (heating meter ÷ total electricity)" (display name only; key, ID and history unchanged).
- Switching hot-water detection on or off reloads the integration; the threshold applies immediately.
- README revised (status, new sections, notes).

## 0.14.1

### Deutsch
- Neuer Sensor **Heizenergie (gesamt, kWh)**, geschützt gegen den Moment, in dem das kWh-Register ins MWh-Register überläuft; die JAZ nutzt dieselbe geschützte Summe.
- Die Dauer des Debug-Modus ist wählbar („72 Stunden“ oder „Unbegrenzt“) und bleibt bei Neustart, Neuladen und Update erhalten.
- Bei den Wärmequellen-Temperaturen gilt der Rohwert 65535 als −0,1 °C statt als „nicht verfügbar“.

### English
- New sensor **Heating energy (total, kWh)**, protected against the moment the kWh register rolls over into the MWh register; the SPF uses the same protected total.
- The debug mode duration is selectable ("72 hours" or "Unlimited") and survives restarts, reloads and updates.
- For the heat source temperatures the raw value 65535 now means −0.1 °C instead of "unavailable".

## 0.14.0

### Deutsch
- Optionaler **Debug-Modus**: schreibt jede Abfrage als JSON-Zeile in eine Datei im Konfigurationsordner.

### English
- Optional **debug mode**: writes every poll as a JSON line to a file in the configuration folder.

## Frühere Versionen / Earlier versions

Siehe die Git-Historie und die Update-Hinweise im README (Umstellung der Sensor-Kennung in v0.11.0). / See the git history and the upgrade notes in the README (change of the sensor identification in v0.11.0).
