# OREI HDMI Switch (RS-232) for Home Assistant

Control an OREI HDMI switch from Home Assistant over its RS-232 port, through an
Ethernet-to-RS-232 adapter or a serial port on the Home Assistant host. Built for the
**UKM-401** 4x1 4K HDMI KVM; other OREI switches with the same one-line protocol can be
added in `protocol.py`.

## What you get

| Entity | What it does |
|---|---|
| `select.<switch>_input` | The live input, named after what is plugged in (Wii, Xbox, …). Choosing an option switches. `unknown` when no input has a signal. |
| `binary_sensor.<switch>_signal` | On while any input has a live source. |
| `binary_sensor.<switch>_link` | On while the switch answers the status poll (every 30 s by default), which proves the whole path: network, adapter, RS-232 cable, switch. Stays available when the path is down, with the last reply, the last error and the time of the last answer as attributes. |
| `button.<switch>_restart` | Restarts the switch (its `Reset` command). |
| Action `orei_ukm.send_command` | Sends any raw command line and returns the reply, e.g. `Status`. |

The switch refuses to select an input with nothing powered on it; the select then raises an
error ("Xbox: Input 2 has no signal; turn on the device connected to it first") instead of
pretending it switched.

## Setup

1. Install through HACS (custom repository `davidcoulson/ha-orei-ukm`, type Integration), or
   copy `custom_components/orei_ukm` into `/config/custom_components/`. Restart Home Assistant.
2. Settings > Devices & services > Add integration > **OREI HDMI Switch (RS-232)**.
3. Choose **Ethernet-to-RS-232 adapter** and enter its address and TCP port, or **Serial port**
   and the device path (e.g. `/dev/ttyUSB0`).
4. Open the integration's **Configure** to name each input and set the status check interval
   (default 30 s).

### The adapter

Put the Ethernet-to-RS-232 adapter in **TCP server** (raw socket) mode with the switch's serial
settings: **9600 baud, 8 data bits, no parity, 1 stop bit** for the UKM-401. The integration
opens a connection per command and closes it again, because these adapters usually accept one
TCP client at a time.

## Icon

`custom_components/orei_ukm/brand/` carries the integration's icon and logo (light and dark),
made from OREI's own logo, so Home Assistant shows them without a home-assistant/brands entry.
OREI is a trademark of its owner; the artwork is used only to identify the hardware.

## UKM-401 protocol

From the OREI manual (commands end with a newline):

| Command | Reply |
|---|---|
| `PS11R` … `PS14R` | switches to input 1–4; `please insert HDMI` if nothing is live on it |
| `Status` | `Status:` / `Baud 9600` / `PS12R OK`, or `NA` when no input is live |
| `Reset` | restarts the switch |
| `Recover` | factory reset (not exposed as an entity) |
| `Baud XX` | changes the baud rate (not exposed) |

## Development

```bash
uv venv -p 3.14 .venv && uv pip install -p .venv/bin/python -r requirements_test.txt
.venv/bin/python -m pytest -q
```

The tests run the integration inside a real Home Assistant core against a fake UKM-401 on a
local TCP port that answers exactly like the real switch (including `NA` and
`please insert HDMI`).
