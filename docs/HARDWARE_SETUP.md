# Hardware-Setup-Guide

Diese Anleitung begleitet dich von "ich habe ein OTE-Modbus-Gateway verbaut" bis zu
"Home Assistant kann Werte auslesen". Alle Werte (IP-Adressen, Modbus-Adresse) in den
Beispielen sind Platzhalter – deine eigenen Werte hängen von deiner DIP-Schalter-Stellung
und deinem Netzwerk ab.

## Was du brauchst

- Ein OCHSNER-Wärmepumpe mit OTE-Regler und bereits verbautem **OTE-Modbus-Gateway**
  (TEM ZIF180) – siehe [README: Ist dieses Projekt für dich?](../README.md#ist-dieses-projekt-für-dich)
- Einen RS485-Adapter (USB für den Test, RS485-zu-Ethernet für den Dauerbetrieb – siehe
  [README: Benötigte Hardware](../README.md#benötigte-hardware))
- Etwas Zeit und (idealerweise) Monteurs-/Installateurszugang, um im Schaltschrank
  nachzusehen und DIP-Schalter einzustellen

## Schritt 1: Gateway lokalisieren und DIP-Schalter ablesen

Das Gateway sitzt meist im Schaltschrank/Innenteil der Anlage, auf einer Hutschiene, mit
der Aufschrift "TEM ZIF180" bzw. "eBus-Modbus IF". Es hat einen 10-poligen DIP-Schalter mit
folgender Belegung (steht auch direkt auf dem Gerätelabel):

| Pins | Funktion |
|---|---|
| 1–3 | Baudrate |
| 4–5 | Parität |
| 6–9 | Modbus-Slave-Adresse (4-Bit) |
| 10 | Busabschluss (120Ω) |

**Wichtig:** Fotografiere die DIP-Schalter-Stellung **frontal und scharf** (nicht schräg/
seitlich) – die Stellung ist auf schlecht fokussierten oder schrägen Fotos erstaunlich
leicht falsch abzulesen. Im Zweifel: Foto mehrfach aus leicht unterschiedlichen Winkeln.

### Baudrate (Pins 3, 2, 1)

| Pin 3 | Pin 2 | Pin 1 | Baudrate |
|---|---|---|---|
| 0 | 0 | 0 | 1200 |
| 0 | 0 | 1 | 2400 |
| 0 | 1 | 0 | 4800 |
| 0 | 1 | 1 | 9600 |
| 1 | 0 | 0 | 19200 (Werkseinstellung) |
| 1 | 0 | 1 | 38400 |
| 1 | 1 | 0 | 57600 |
| 1 | 1 | 1 | 115200 |

### Parität (Pins 5, 4)

| Pin 5 | Pin 4 | Parität |
|---|---|---|
| 0 | 0 | keine |
| 0 | 1 | gleiche (even) – Werkseinstellung |
| 1 | 1 | ungleiche (odd) |

Stopp-Bits ergeben sich daraus: **1 Stopp-Bit bei aktiver Parität, 2 Stopp-Bits ohne
Parität.**

### Modbus-Adresse (Pins 9, 8, 7, 6)

| Pins 9,8,7,6 | Adresse |
|---|---|
| 0,0,0,0 | **ungültig** – laut Hersteller-Handbuch keine gültige Adresse! |
| 0,0,0,1 | 11 |
| 0,0,1,0 | 12 |
| ... | ... (fortlaufend) |
| 1,1,1,1 | 25 |

⚠️ **Wenn alle vier Adress-Pins auf OFF stehen, hat das Gateway keine gültige Adresse.**
Das ist der Werkszustand ab Erstinbetriebnahme des Gateways – du musst mindestens einen
der Pins 6–9 aktiv setzen (z. B. Pin 6 → Adresse 11), sonst antwortet das Gateway auf
keine Modbus-Anfrage, unabhängig davon ob Verkabelung/Software korrekt sind.

### Busabschluss (Pin 10)

Nur relevant, falls das Gateway das letzte/einzige Gerät am RS485-Bus ist (typisch bei
einer Punkt-zu-Punkt-Verbindung zu einem einzelnen RS485-Master). 1 = Abschlusswiderstand
aktiv.

## ⚠️ Wichtiger Sicherheitshinweis zu DIP-Schalter-Änderungen

Wenn du DIP-Schalter ändern musst: Nach der Änderung muss das Gateway ggf. stromlos
gemacht werden (eBus-Klemme kurz abziehen/wieder anstecken), damit die neue Einstellung
sicher übernommen wird.

**Das ist nicht folgenlos:** In der Praxis hat das Abziehen/Wiederanstecken der eBus-
Verbindung am Gateway bei einer Testinstallation einen Fehler ausgelöst und die
Wärmepumpe in den Notbetrieb versetzt (nach Wiederverbinden lief sie normal weiter). Die
Ochsner-Dokumentation beschreibt nur den Fall "Gateway war nie am Bus", nicht "ein bereits
erkanntes Gerät verschwindet plötzlich". Plane DIP-Schalter-Änderungen daher bewusst ein
(nicht bei kritischen Außentemperaturen, nicht routinemäßig) und nicht als
"risikofreien Nebeneffekt".

## Schritt 2: Verkabelung

Das Gateway hat zwei Klemmenblöcke:
- **ModBus:** Beschriftet `A ⊥ B` (A, Masse/Schirm, B)
- **eBus:** bereits mit der Wärmepumpe verbunden – hier nichts ändern

Verbinde dein RS485-Adapter mit **A→A, B→B**, und wenn dein Adapter eine dritte Klemme für
Masse/Schirm hat, diese mit der mittleren Klemme (⊥) des Gateways verbinden. Die
Modbus-Leitung sollte laut Handbuch verdrillt und geschirmt sein (Cat5/6-Kabel eignet sich).

Bei Verwendung eines **Waveshare RS232/485/422 TO POE ETH (B)** (oder ähnlichem Gerät mit
RA/RB/TA/TB-Klemmen): Nutze **TA und TB**, nicht RA/RB – letztere sind nur für echten
4-Draht-RS422-Betrieb relevant. Die genaue Pin-Zuordnung steht im
[Waveshare-Wiki, Abschnitt "Hardware Description"](https://www.waveshare.com/wiki/RS232/485/422_TO_POE_ETH_(B)).

## Schritt 3: Erster Verbindungstest (USB-RS485)

Bevor du irgendetwas in Home Assistant konfigurierst, empfiehlt sich ein reiner
CLI-Verbindungstest, um Verkabelung/DIP-Konfiguration unabhängig von HA zu verifizieren:

```bash
pip3 install pymodbus pyserial
```

```python
from pymodbus.client import ModbusSerialClient

client = ModbusSerialClient(
    port="/dev/cu.usbserial-XXXX",   # via `ls /dev/cu.*` ermitteln
    baudrate=19200,                   # deine abgelesene Baudrate
    parity="E",                       # "N"/"E"/"O" je nach DIP-Schalter
    stopbits=1,                       # 1 bei Paritaet, 2 ohne
    bytesize=8,
    timeout=2,
)
client.connect()
# Objekt 100 "Verbindungs-Info": Modbus-Adresse 257 (dezimal, 1-basiert lt. Ochsner-PDF)
# -> pymodbus erwartet 0-basiert: 256
result = client.read_holding_registers(address=256, count=1, slave=11)  # deine Adresse
print(result.registers[0])  # 1 = eBus-Verbindung ok, 0 = keine Verbindung
client.close()
```

Wenn das `1` liefert: Glückwunsch, die Grundkonfiguration stimmt.

## Schritt 4: Produktiv-Anbindung über RS485-zu-Ethernet-Gateway

Am Beispiel des Waveshare RS232/485/422 TO POE ETH (B):

1. **Werks-IP beachten:** Das Gerät hat werksseitig **keine DHCP-Anfrage aktiv**, sondern
   eine feste Werks-IP (typischerweise `192.168.1.200`, Subnetz `255.255.255.0`). Liegt
   dein Netz in einem anderen Adressbereich, ist das Gerät zunächst nicht erreichbar – das
   ist kein Defekt. Lege temporär eine zweite IP im selben Subnetz auf deinem Rechner an
   (z. B. macOS: `sudo ifconfig en0 alias 192.168.1.50 255.255.255.0`), rufe
   `http://192.168.1.200` im Browser auf (kein Passwort ab Werk) und stelle "IP mode" auf
   "Dynamic", falls du eine feste IP lieber per DHCP-Reservierung an deinem Router vergeben
   willst. Danach den Alias wieder entfernen (`sudo ifconfig en0 -alias 192.168.1.50`).
2. **Serial Settings anpassen:** Baud Rate, Parity, Stopbits müssen exakt zur
   DIP-Schalter-Konfiguration des Ochsner-Gateways passen (siehe Schritt 1). Der Werksdefault
   des Waveshare-Geräts (oft 115200/None) passt in aller Regel **nicht** zum
   Ochsner-Gateway-Default (19200/Even) – das ist eine der häufigsten Fehlerquellen.
3. **Modbus-Gatewaymodus aktivieren:** Unter "Multi-Host Settings" das Feld "Protocol" auf
   "Modbus TCP to RTU" stellen.
4. ⚠️ **Bekannter Fallstrick:** Die Waveshare-Dokumentation beschreibt, dass sich der
   "Device Port" bei dieser Auswahl automatisch auf `502` umstellt – das gilt aber nur für
   das Windows-Tool VirCom, **nicht zuverlässig für die Web-Oberfläche**. Prüfe nach dem
   Speichern, ob der Port wirklich auf `502` steht, und setze ihn sonst manuell.
5. Nach jeder Änderung: mit einem Verbindungstest verifizieren (siehe unten), nicht blind
   auf die gespeicherten Einstellungen vertrauen – dies ist eine bekannte Einschränkung
   dieses Geräts, wenn man die Web-Oberfläche statt VirCom nutzt.

```python
from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient(host="192.168.x.x", port=502, timeout=3)
client.connect()
result = client.read_holding_registers(address=256, count=1, slave=11)
print(result.registers[0])
client.close()
```

## Firmware-Hinweis

Aktuelle Waveshare-Geräte dieser Baureihe werden mit der neuesten Firmware ausgeliefert
(z. B. V1.523 zum Zeitpunkt dieser Doku). Der Hersteller warnt ausdrücklich, dass ab dieser
Version **kein Downgrade auf ältere Firmware mehr möglich ist** (Brick-Risiko) – ein
Firmware-Update ist für den hier beschriebenen Anwendungsfall nicht nötig.

## Nächste Schritte

Sobald der Verbindungstest zuverlässig funktioniert, kann die eigentliche Home-Assistant-
Integration eingerichtet werden (siehe Hauptprojekt-README, Abschnitt "Installation").
