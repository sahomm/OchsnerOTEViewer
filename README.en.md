# OchsnerOTEViewer

[🇩🇪 Deutsch](README.md) | 🇬🇧 English

Home Assistant integration for reading data from OCHSNER heat pumps with **OTE controller
generation** via the official **OTE Modbus Gateway** (TEM ZIF180, eBUS↔Modbus RTU).

> **Disclaimer:** This is a private community project and is not affiliated with OCHSNER
> Wärmepumpen GmbH in any way. All trademarks belong to their respective owners.

## Status

🚧 **Early development stage (v0.1) – the integration exists and has been verified
against a real gateway, but has not yet been end-to-end tested inside a running Home
Assistant instance.**

**This integration currently provides read-only access** to your OCHSNER heat pump –
temperatures, status, energy counters, operating hours, error codes. No values are written
and no settings on the heat pump are changed.

A later extension with control features is conceivable, but deliberately not part of the
current version: write access via the OTE Modbus Gateway requires changing the controller
configuration in a way that can affect the system's own safety-relevant protection
functions. That would only be pursued after careful, explicit review – not casually added
as a "convenience feature".

## Is this project for you?

OCHSNER offers **several different, each optional** accessories for smart home /
remote-access integration. This project covers exactly one of them:

| Accessory | Interface | Covered by this project? |
|---|---|---|
| **OTE Modbus Gateway** (TEM ZIF180) | Modbus RTU over RS485 | ✅ Yes, exactly this one |
| web2com module (TEM RC7000/RC7020) or OTE room terminal with touch display | SOAP/HTTP over Ethernet | ❌ No – see [derbernhard/Ochsner_W2C_HACS](https://github.com/derbernhard/Ochsner_W2C_HACS) or [ahackl/HA_cc_web2com](https://github.com/ahackl/HA_cc_web2com) |
| OTS controller (Siemens Climatix, newer generation) | JSON API over network | ❌ No – see [permissionBRICK/OTS-HomeAssistant](https://github.com/permissionBRICK/OTS-HomeAssistant) |

### How do I find out which hardware I have?

**The heat pump's own nameplate does not tell you this** – it only lists electrical
ratings, refrigerant data, and performance figures (mandatory information for CE marking
and the Pressure Equipment Directive), never optional communication accessories fitted
afterwards.

Instead, check one of these:
1. **Look inside the electrical cabinet:** Search for a small DIN-rail module labeled
   **"TEM ZIF180"** or **"eBus-Modbus IF"**, usually near the rest of the control
   electronics.
2. **In your installation documentation:** Look for a line item such as "OTE Modbus
   interface" or "ZIF180" on your heating installer's order confirmation/invoice.

If you find a web2com module or touch-display room terminal instead of the ZIF180, one of
the alternative projects linked above is probably the better fit for you.

## Required hardware

The OTE Modbus Gateway speaks **Modbus RTU over RS485** – no Ethernet out of the box. You
therefore need an additional RS485 adapter:

- **For permanent production use (recommended):** An RS485-to-Ethernet gateway, e.g. the
  [Waveshare RS232/485/422 TO POE ETH (B)](https://www.waveshare.com/rs232-485-422-to-poe-eth-b.htm).
  Benefit: no USB passthrough needed if Home Assistant runs in a VM/Proxmox; a single cable
  for power (PoE) and data.
- **For an initial connectivity test (optional, cheaper):** A simple USB-to-RS485 adapter
  (e.g. Waveshare USB TO RS485), connected directly to the machine running Home Assistant.

See [docs/HARDWARE_SETUP.en.md](docs/HARDWARE_SETUP.en.md) for exact configuration details
(DIP switches, wiring, network setup).

## Installation

1. In Home Assistant: **HACS → Integrations → ⋮ (menu, top right) → Custom repositories**
2. Add `https://github.com/sahomm/OchsnerOTEViewer`, category **Integration**
3. Search for "Ochsner OTE Viewer" in HACS and install it, then restart Home Assistant
4. **Settings → Devices & Services → Add Integration → "Ochsner OTE Viewer"**
5. Enter the host/IP and port of your RS485-to-Ethernet gateway, and the Modbus address of
   your OTE Modbus Gateway (see [docs/HARDWARE_SETUP.en.md](docs/HARDWARE_SETUP.en.md))

## Contributing

Issues and pull requests are welcome – especially feedback from owners of other OCHSNER
heat pump models with an OTE controller (e.g. brine/water heat pumps), to help extend the
register list and compatibility.

## License

[MIT](LICENSE)
