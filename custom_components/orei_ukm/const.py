"""Constants for the OREI HDMI switch integration."""

DOMAIN = "orei_ukm"

CONF_TRANSPORT = "transport"
CONF_SERIAL_DEVICE = "serial_device"
CONF_MODEL = "model"
CONF_INPUT_NAMES = "input_names"
CONF_SCAN_INTERVAL = "scan_interval"

TRANSPORT_TCP = "tcp"
TRANSPORT_SERIAL = "serial"

DEFAULT_PORT = 4196  # USR-style serial servers; change to your adapter's port
DEFAULT_SCAN_INTERVAL = 30

SERVICE_SEND_COMMAND = "send_command"
ATTR_COMMAND = "command"
ATTR_CONFIG_ENTRY = "config_entry_id"
