# OchsnerOTEViewer

🇩🇪 Deutsch | [🇬🇧 English](README.en.md)

Home Assistant Integration zum Auslesen von OCHSNER-Wärmepumpen mit **OTE-Reglergeneration**
über das offizielle **OTE-Modbus-Gateway** (TEM ZIF180, eBUS↔Modbus RTU).

> **Disclaimer:** Dieses Projekt ist ein privates Community-Projekt und steht in keiner
> Verbindung zu OCHSNER Wärmepumpen GmbH. Alle Markennamen gehören ihren jeweiligen Inhabern.

## Status

🚧 **Frühe Entwicklungsphase.** Aktuell befindet sich dieses Repository im Aufbau der
Dokumentation. Der eigentliche Integrations-Code folgt als nächster Schritt.

- **Phase 1 (in Arbeit):** Nur lesende Sensoren (Temperaturen, Status, Energiezähler,
  Fehlercodes) – kein Schreibzugriff auf die Wärmepumpe.
- **Phase 2 (zurückgestellt):** Erweiterte Steuerung. Das OTE-Modbus-Gateway erlaubt
  theoretisch auch Schreibzugriffe (Betriebswahl, Sollwerte), das erfordert aber eine
  Umstellung des Applikationstyps am Wärmemanager, die laut Ochsner-Dokumentation die
  eigene Frostschutzfunktion der Anlage aufhebt und die lokale Bedienteil-Umschaltung
  dauerhaft sperrt. Das wird nur mit expliziter Risikoabwägung angegangen, nicht leichtfertig
  als "Komfortfeature" ergänzt.

## Ist dieses Projekt für dich?

OCHSNER bietet **mehrere unterschiedliche, jeweils optionale** Zubehörteile für
Smart-Home-/Fernzugriff an. Dieses Projekt deckt genau eines davon ab:

| Zubehör | Schnittstelle | Für dieses Projekt? |
|---|---|---|
| **OTE-Modbus-Gateway** (TEM ZIF180) | Modbus RTU über RS485 | ✅ Ja, genau dafür |
| web2com-Modul (TEM RC7000/RC7020) oder OTE-Raumterminal mit Touch-Display | SOAP/HTTP über Ethernet | ❌ Nein – siehe [derbernhard/Ochsner_W2C_HACS](https://github.com/derbernhard/Ochsner_W2C_HACS) oder [ahackl/HA_cc_web2com](https://github.com/ahackl/HA_cc_web2com) |
| OTS-Regler (Siemens Climatix, neuere Baureihe) | JSON-API über Netzwerk | ❌ Nein – siehe [permissionBRICK/OTS-HomeAssistant](https://github.com/permissionBRICK/OTS-HomeAssistant) |

### Wie finde ich heraus, welche Hardware ich habe?

Das **Typenschild der Wärmepumpe selbst gibt darüber keine Auskunft** – es enthält nur
elektrische Kenndaten, Kältemittel- und Leistungsangaben (Pflichtangaben für CE/Druckgeräte-
richtlinie), keine Informationen zu optional nachgerüsteten Kommunikationsschnittstellen.

So findest du es stattdessen heraus:
1. **Im Schaltschrank/Innenteil nachsehen:** Suche nach einem kleinen Modul mit der
   Aufschrift **"TEM ZIF180"** bzw. **"eBus-Modbus IF"** (Hutschienenmontage, meist in der
   Nähe der übrigen Regelungs-Elektronik).
2. **In der Installationsdokumentation:** Auf der Auftragsbestätigung/Rechnung deines
   Heizungsbauers nach einer Position wie "OTE-Modbus-Schnittstelle" oder "ZIF180" suchen.

Wenn du dort ein web2com-Modul oder Touch-Display-Raumterminal findest statt des ZIF180,
ist eines der oben verlinkten Alternativ-Projekte vermutlich die bessere Wahl für dich.

## Benötigte Hardware

Das OTE-Modbus-Gateway spricht **Modbus RTU über RS485** – kein Ethernet ab Werk. Du
brauchst also zusätzlich einen RS485-Adapter:

- **Für den produktiven Dauerbetrieb (empfohlen):** Ein RS485-zu-Ethernet-Gateway, z. B.
  [Waveshare RS232/485/422 TO POE ETH (B)](https://www.waveshare.com/rs232-485-422-to-poe-eth-b.htm).
  Vorteil: kein USB-Passthrough nötig, falls Home Assistant in einer VM/Proxmox läuft; ein
  Kabel für Strom (PoE) + Daten.
- **Für den ersten Verbindungstest (optional, günstiger):** Ein einfacher USB-zu-RS485-
  Adapter (z. B. Waveshare USB TO RS485), direkt an den Rechner mit Home Assistant
  angeschlossen.

Details zur genauen Konfiguration (DIP-Schalter, Verkabelung, Netzwerk-Setup) siehe
[docs/HARDWARE_SETUP.md](docs/HARDWARE_SETUP.md).

## Installation

*Folgt, sobald die Integration selbst verfügbar ist (siehe Status oben).*

## Mitwirken

Issues und Pull Requests sind willkommen – insbesondere Rückmeldungen von Besitzern anderer
Ochsner-Wärmepumpenmodelle mit OTE-Regler (z. B. Sole-/Wasser-Wärmepumpen), um die
Registerliste und Kompatibilität zu erweitern.

## Lizenz

[MIT](LICENSE)
