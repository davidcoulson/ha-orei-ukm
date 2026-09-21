"""Setting the switch up from the UI, and naming its inputs."""

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType

from custom_components.orei_ukm.const import CONF_INPUT_NAMES, CONF_MODEL, DOMAIN


async def test_tcp_setup(hass, fake_switch):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "tcp"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: fake_switch.port, CONF_MODEL: "UKM-401"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["transport"] == "tcp"
    assert result["title"] == "OREI UKM-401 (127.0.0.1)"


async def test_tcp_setup_unreachable(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "tcp"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: 1, CONF_MODEL: "UKM-401"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_options_names_inputs(hass, setup_switch):
    entry = setup_switch
    result = await hass.config_entries.options.async_init(entry.entry_id)
    names = {"input_1": "Wii", "input_2": "Xbox", "input_3": "RetroPie", "input_4": "Input 4", "scan_interval": 30}
    result = await hass.config_entries.options.async_configure(result["flow_id"], names)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_INPUT_NAMES] == ["Wii", "Xbox", "RetroPie", "Input 4"]


async def test_options_reject_duplicate_names(hass, setup_switch):
    result = await hass.config_entries.options.async_init(setup_switch.entry_id)
    dupes = {"input_1": "Wii", "input_2": "Wii", "input_3": "C", "input_4": "D", "scan_interval": 30}
    result = await hass.config_entries.options.async_configure(result["flow_id"], dupes)
    assert result["errors"] == {"base": "duplicate_names"}
