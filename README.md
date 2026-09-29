# OchsnerOTEViewer

🇩🇪 Deutsch | [🇬🇧 English](README.en.md)

Home Assistant Integration zum Auslesen von OCHSNER-Wärmepumpen mit **OTE-Reglergeneration**
über das offizielle **OTE-Modbus-Gateway** (TEM ZIF180, eBUS↔Modbus RTU).

Dieses Projekt wurde von [sahomm](https://github.com/sahomm) mit Unterstützung von Claude
(Anthropic) entwickelt.

> **Disclaimer:** Dieses Projekt ist ein privates Community-Projekt und steht in keiner
> Verbindung zu OCHSNER Wärmepumpen GmbH. Alle Markennamen gehören ihren jeweiligen Inhabern.
> Das OCHSNER-Logo (`custom_components/ochsner_ote_viewer/brand/`) wird, wie in der
> Home-Assistant-Community allgemein üblich, ausschließlich zur Identifikation des Produkts
> verwendet, mit dem diese Integration kommuniziert – ohne Billigung oder Zusammenarbeit zu
> unterstellen. Quelle: offizielle Vektor-Grafik von ochsner.com.

## Update-Hinweis (ab v0.11.0)

⚠️ Hattest du bereits eine ältere Version installiert (vor v0.11.0)? Diese Version ändert,
wie Sensoren intern identifiziert werden (stabile Verbindungsdaten statt einer zufälligen
internen ID) – notwendig, damit ein künftiges Entfernen+Neuanlegen der Integration nicht
mehr die komplette Verlaufshistorie verwaist. Als einmaliger Übergang bedeutet das: Nach dem
Update auf v0.11.0 bitte die Integration einmal **entfernen und mit denselben
Verbindungsdaten neu anlegen** (Geräte & Dienste → Ochsner OTE Viewer → Löschen, dann neu
hinzufügen) – sonst entstehen doppelte Entities (alte, verwaiste + neue). Ab diesem Zeitpunkt
bleibt die Historie bei künftigen Entfernen+Neuanlegen-Vorgängen erhalten, solange Host/Port/
Modbus-Adresse gleich bleiben.

## Status

🚧 **Früher Entwicklungsstand (v0.1) – die Integration existiert und wurde gegen ein
reales Gateway verifiziert, aber noch nicht in einer laufenden Home-Assistant-Instanz
End-to-End getestet.**

**Diese Integration bietet aktuell ausschließlich lesenden Zugriff** auf deine
OCHSNER-Wärmepumpe – Temperaturen, Status, Energiezähler, Betriebsstunden, Fehlercodes.
Es werden keine Werte geschrieben und keine Einstellungen an der Wärmepumpe verändert.

Eine spätere Erweiterung um Steuerfunktionen ist denkbar, aber bewusst nicht Teil der
aktuellen Version: Schreibzugriffe über das OTE-Modbus-Gateway setzen eine Umstellung der
Reglerkonfiguration voraus, die sicherheitsrelevante Schutzfunktionen der Anlage betreffen
kann. Das würde nur nach sorgfältiger, expliziter Prüfung angegangen – nicht als einfaches
"Komfortfeature" nebenbei ergänzt.

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
[HARDWARE_SETUP.md](HARDWARE_SETUP.md).

## Installation

1. In Home Assistant: **HACS → Integrationen → ⋮ (Menü oben rechts) → Benutzerdefinierte Repositories**
2. `https://github.com/sahomm/OchsnerOTEViewer` eintragen, Kategorie **Integration**
3. "Ochsner OTE Viewer" in HACS suchen und installieren, danach Home Assistant neu starten
4. **Einstellungen → Geräte & Dienste → Integration hinzufügen → "Ochsner OTE Viewer"**
5. Host/IP und Port deines RS485-zu-Ethernet-Gateways eingeben, sowie die Modbus-Adresse
   deines OTE-Modbus-Gateways (siehe [HARDWARE_SETUP.md](HARDWARE_SETUP.md))

Bei der Einrichtung fragt die Integration zusätzlich, ob deine Anlage eine **Kühlfunktion**
bzw. eine **von Ochsner gesteuerte Zusatzheizung** hat – davon hängt ab, welche Sensoren
angelegt werden (siehe nächster Abschnitt). Eine Checkbox "Externe Stromsensoren einrichten"
führt dich optional zu einer zweiten Seite für die JAZ-/COP-Berechnung (siehe "Nicht
verifizierte Register" unten) – wer das nicht braucht, lässt sie einfach unangehakt.

## Nicht verifizierte Register

Die Anlage, an der dieses Projekt entstanden ist, hat weder eine aktive Kühlfunktion noch
eine von Ochsner gesteuerte Zusatzheizung (die eigenen Heizstäbe hängen direkt am Puffer,
gesteuert über eine separate UVR16x2, nicht über die Ochsner-eigene "Zusatzheizung"-Logik).
Die entsprechenden Register (Kühlpuffer/Kühlenergie, Zusatzheizung-Status/-Zähler) folgen
zwar der Handbuch-Beschreibung, konnten aber **nie gegen eine Anlage mit diesen Funktionen
verifiziert werden**. Sie werden deshalb nur angelegt, wenn du das bei der Einrichtung
explizit aktivierst. Hast du eine dieser Funktionen und kannst die Werte bestätigen (oder
korrigieren) – bitte über ein Issue oder einen PR melden.

**Effizienz-Sensor (JAZ):** Der Sensor "Effizienz seit erster Messung (Jahresarbeitszahl/
JAZ)" berechnet sich aus Heizenergie ÷ elektrischer Energie – **nicht** aus den rohen
Lebenszeit-Zählerständen, sondern aus der **Veränderung seit der ersten erfolgreichen
Messung** (bzw. seit einem erkannten Zähler-Reset). Grund: Ochsners eigener
Heizenergie-Zähler läuft seit Inbetriebnahme der Anlage (oft Jahre), ein frisch
hinzugefügter externer Stromzähler aber erst seit wenigen Tagen – eine Division der
rohen Lebenszeit-Werte ergäbe einen sinnlos hohen Wert (in der Praxis beobachtet: JAZ von
126 statt eines realistischen Werts um 3–5). Das gilt unabhängig davon, ob die
elektrische Seite aus Ochsners eigenem Register oder einem externen Sensor kommt.

⏳ **Das bedeutet: Nach dem Einrichten (oder nach einem erkannten Zähler-Reset) dauert es
etwas, bis ein verlässlicher Wert entsteht** – wie lange, hängt davon ab, wie viel die
Wärmepumpe in der Zwischenzeit heizt. In der ersten Zeit ist der Wert "nicht verfügbar"
oder noch wenig aussagekräftig, das ist normal. Die Kombination der kWh-/MWh-Registerpaare
(angenommen als `MWh × 1000 + kWh`) ist zusätzlich nicht explizit im Handbuch belegt, nur
plausibilisiert.
Zusätzlich braucht dieser Sensor ein Ochsner-seitiges Stromzähler-Zubehör an der OTE, das
viele Anlagen (auch die, an der dieses Projekt entstanden ist) nicht haben – dann bleibt
er dauerhaft "nicht verfügbar", das ist normal.

**Alternative: externer Stromsensor.** Über die Checkbox "Externe Stromsensoren einrichten"
gelangst du zu einer zweiten Einrichtungsseite, auf der du bis zu drei bestehende
Home-Assistant-Energiesensoren angeben kannst (z. B. die drei Phasen-Sensoren eines
Shelly 3EM), die dann statt der Ochsner-eigenen Register für die Effizienzberechnung
genutzt werden – wir summieren die drei Werte selbst. Das umgeht bewusst die "Total"-Entity
vieler 3-Phasen-Zähler: Bei Shelly (Pro) 3EM gibt es dafür einen bekannten, noch offenen
Fehler in Home Assistants eigener Integration, bei dem die "Total"-Energie fälschlich nur
eine einzelne Phase widerspiegelt statt alle drei zu summieren
([home-assistant/core#155155](https://github.com/home-assistant/core/issues/155155)) –
ein falscher Gesamtwert wäre schlimmer als gar keiner.

⚠️ **Sicherheitshinweis:** Unsere Integration liest dabei nur den Wert einer bereits in
Home Assistant vorhandenen Entity aus – sie greift nie selbst in deine Elektroinstallation
ein. Falls du dafür aber **neue Zähler-Hardware nachrüstest** (z. B. einen Shelly 3EM mit
Stromwandlern im Sicherungskasten): Das ist Arbeit an spannungsführenden Leitern mit
**Lebensgefahr** – lass das ausschließlich von einer Elektrofachkraft installieren. Achte
außerdem darauf, dass der gewählte Sensor wirklich nur den Stromkreis der Wärmepumpe misst,
nicht den gesamten Haushalt.

**Kompatible Zähler (Auto-Erkennung):** Auf der zweiten Einrichtungsseite durchsucht die
Integration deine Home-Assistant-Installation selbstständig nach bekannten Zählergeräten.
Wird eines gefunden, erscheint es oben als fertige Auswahl ("Erkanntes Zählergerät") – wählst
du es aus, werden die 6 Felder darunter automatisch befüllt (`meter_profiles.py`). Es gibt
bewusst kein offenes "wähl irgendein Gerät"-Feld: das führte in einer früheren Version schnell
zu falschen Treffern (z. B. wurden einzelne Phasen-Geräte statt des richtigen Hub-Geräts
angeboten). Aktuell unterstützt:

| Gerät | Status |
|---|---|
| Shelly 3EM (Gen1), offizielle `shelly`-Integration | ✅ verifiziert |
| Shelly Pro 3EM (Gen2) und andere Zähler | ❌ noch nicht – Struktur unbekannt, bitte manuell befüllen |

Wird nichts Bekanntes gefunden, entfällt dieses Feld einfach und du füllst die 6 Felder unter
"Manuelle Konfiguration" aus (eingeklappt, wenn ein Gerät gefunden wurde, sonst automatisch
aufgeklappt) – das funktioniert unabhängig davon immer. Unterstützung für weitere Zähler lässt
sich per PR ergänzen: ein neuer `MeterProfile`-Eintrag in `meter_profiles.py` mit einer
`resolve()`-Funktion, die aus dem Geräte-/Entity-Registry die passenden Entities findet.

**COP, berechnet (Durchfluss-Methode):** Zusätzlich zum Ochsner-eigenen (undokumentierten)
"Leistungszahl COP"-Register gibt es einen zweiten, unabhängig berechneten COP-Sensor:

```
Wärmeleistung [kW] = Volumenstrom [L/min] × (Vorlauf − Rücklauf) [K] × 4,186 / 60
COP = Wärmeleistung ÷ elektrische Leistung (aus optionalen externen Leistungssensoren)
```

4,186 kJ/(kg·K) ist die spezifische Wärmekapazität von Wasser – bei einem Wasser-Glykol-
Gemisch im Heizkreis wäre der reale Wert etwas niedriger, das ist hier nicht berücksichtigt.
Dieser Sensor braucht die **Leistungssensoren** (Watt), nicht die Energiesensoren (kWh) von
oben – ein Momentanwert wie COP braucht Momentanleistung, keine Energiezähler. Berechnet wird
nur, während der Statuscode Wärmepumpe "läuft" anzeigt – direkt beim Abschalten fällt die
elektrische Leistung fast augenblicklich auf 0, während Durchfluss und Temperaturspreizung
durch die Trägheit von Wasser/Pumpe noch kurz nachlaufen; ohne diese Absicherung würde die
Division kurzzeitig einen sinnlosen Ausreißer liefern (beobachtet: COP 167 während eines
Abschaltvorgangs). Zusätzlich braucht es eine elektrische Mindestleistung (0,3 kW) – bei einem
zweiten Zyklus zeigte sich, dass der Kompressor elektrisch schon auf Stand-by-Niveau (~9 W)
abschalten kann, während Statuscode und Durchfluss noch für rund 30 Sekunden "läuft" anzeigen
(beobachtet: COP 2328 in genau diesem Fenster) – weder Status noch Durchfluss bilden den
elektrischen Zustand hier zuverlässig ab, deshalb wird die Leistung selbst direkt geprüft. Er
ist bewusst
ein **eigener, zusätzlicher** Sensor, kein Ersatz für das Ochsner-Register – über die
kommende Heizsaison lassen sich beide vergleichen, um herauszufinden, was das undokumentierte
Ochsner-Register tatsächlich abbildet. Das Register "Heizleistung (roh, unverifiziert)" ist
dafür standardmäßig aktiviert (aber ausgeblendet, siehe nächster Abschnitt), damit Home
Assistants Langzeitstatistik seinen Verlauf ab sofort mitschreibt.

## Sensor-Organisation

Bei ~27 Sensoren pro Wärmepumpe lohnt sich eine Sortierung. Home Assistants Geräteseite
erlaubt keine frei benennbaren Themen-Überschriften, aber eine eingebaute Aufteilung in
**Sensoren** (alltagsrelevant, oben) und **Diagnose** (technisch, eigener eingeklappter
Block – Statuscodes, Kältekreis-Drücke, Fehlercodes, Verschleiß-Zähler wie Betriebsstunden/
Schaltzyklen). Alle Sensoren bleiben dabei aktiv und schreiben normal Verlauf/Statistik, sie
sind nur visuell gruppiert.

Zwei Sensoren sind zusätzlich standardmäßig **ausgeblendet** (nicht deaktiviert – sie laufen
im Hintergrund weiter mit, für die geplante Korrelations-Analyse über die Heizsaison), weil
ihr Rohwert für sich genommen eher verwirrt als hilft:

- **"COP (Ochsner-Register, unverifiziert)"** – über **zwei unabhängige, komplette
  Heizzyklen** hinweg bestätigt (nicht vermutet), inklusive der stündlichen Langzeitstatistik
  (min=mean=max=25,5 durchgehend über die komplette Laufstunde des zweiten Zyklus): Das
  Register zeigt konstant denselben Wert (25,5), auch während echten Betriebs mit ~21 kW
  gemessener Wärmeleistung. Es reagiert also – zumindest in dem, was bisher beobachtet wurde –
  nicht live auf den tatsächlichen Betrieb, wie es der Name nahelegt. Warum, ist offen (z. B.
  ein selten aktualisierter interner Parameter oder ein fester Auslegungswert statt einer
  Messung).
- **"Heizleistung (roh, unverifiziert)"** – zeigt Werte wie "-100", die ohne Kontext nicht
  einzuordnen sind. Die minutengenaue Historie eines kompletten Zyklus liefert eine neue,
  begründete Vermutung, was dieses Register eigentlich ist: **wahrscheinlich keine
  Heizleistung in kW**, sondern eher eine Art internes Modulations-/Rampensignal.
  Beobachtetes Muster: konstant -100 im Leerlauf, Anstieg auf +100 innerhalb ~1 Minute beim
  Start, dort konstant für die gesamte Volllastphase (~21 Minuten, während die unabhängig
  gemessene Wärmeleistung stabil bei ~21 kW lag – keine Korrelation zum tatsächlichen,
  variierenden physikalischen Wert), dann beim Abschalten ein fast linearer Abstieg von +100
  auf -100 über ~14 Ein-Minuten-Schritte. Dieses symmetrische ±100-Rampenmuster, gekoppelt an
  Start-/Stopp-Zeitpunkte statt an die tatsächliche Wärmeleistung, passt viel eher zu einem
  Kompressor-Frequenz-/Kapazitäts-Sanftanlauf-/Sanftauslauf-Signal als zu einer kW-Messung –
  weiterhin nur eine Hypothese, weitere Zyklen werden zeigen, ob das Muster stabil bleibt.

Ausgeblendete Sensoren lassen sich jederzeit über die Entity-Einstellungen wieder sichtbar
machen. Bei den beiden berechneten Kern-Sensoren (JAZ, COP berechnet) sowie bei Zähler- und
Statuscode-Namen wird das gängige Kürzel vorangestellt und die ausführliche Beschreibung
dahinter in Klammern ergänzt (z. B. "JAZ (Effizienz seit erster Messung)"). Eine
Hover-Tooltip-Erklärung, wie sie mancher sich vielleicht wünscht, unterstützt Home Assistants
Standardoberfläche für einzelne Entities aktuell nicht – der Name ist das einzige, worüber
eine Integration das direkt beeinflussen kann.

## Mitwirken

Issues und Pull Requests sind willkommen – insbesondere Rückmeldungen von Besitzern anderer
Ochsner-Wärmepumpenmodelle mit OTE-Regler (z. B. Sole-/Wasser-Wärmepumpen, oder mit
Kühlfunktion/Zusatzheizung), um die Registerliste und Kompatibilität zu erweitern. Ebenso
willkommen: neue Einträge in der Zähler-Kompatibilitätsliste oben (`meter_profiles.py`) für
weitere 3-Phasen-Zähler neben dem aktuell unterstützten Shelly 3EM Gen1.

## Lizenz

[MIT](LICENSE)
