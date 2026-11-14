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


async def test_reconfigure_changes_address_and_keeps_identity(hass, setup_switch, fake_switch):
    from pytest_socket import socket_allow_hosts

    socket_allow_hosts(["127.0.0.1", "localhost", "::1"])   # "localhost" tries ::1 first
    from homeassistant.helpers import entity_registry as er

    unique_id = setup_switch.unique_id
    select_id = er.async_get(hass).async_get_entity_id("select", DOMAIN, f"{unique_id}_input")
    result = await setup_switch.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    # Same fake switch, reached by another name for the loopback address.
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "localhost", CONF_PORT: fake_switch.port})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
    assert setup_switch.data[CONF_HOST] == "localhost"
    new_id = f"localhost:{fake_switch.port}"
    assert setup_switch.unique_id == new_id
    assert er.async_get(hass).async_get_entity_id("select", DOMAIN, f"{new_id}_input") == select_id


async def test_reconfigure_rejects_unreachable_address(hass, setup_switch):
    result = await setup_switch.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: 1})
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": "cannot_connect"}
    assert setup_switch.data[CONF_PORT] != 1


async def test_reconfigure_reloads_entry_stuck_in_setup_retry(hass, fake_switch):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from homeassistant.config_entries import ConfigEntryState

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="127.0.0.1:1",
        data={"transport": "tcp", CONF_HOST: "127.0.0.1", CONF_PORT: 1, CONF_MODEL: "UKM-401"},
    )
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: fake_switch.port})
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.state is ConfigEntryState.LOADED


async def test_reconfigure_rejects_address_of_another_entry(hass, setup_switch, fake_switch):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    other = MockConfigEntry(
        domain=DOMAIN, unique_id="10.0.0.9:4196",
        data={"transport": "tcp", CONF_HOST: "10.0.0.9", CONF_PORT: 4196, CONF_MODEL: "UKM-401"},
    )
    other.add_to_hass(hass)
    result = await other.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: fake_switch.port})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"


async def test_reconfigure_frees_old_address_and_keeps_entities(hass, setup_switch, fake_switch):
    from pytest_socket import socket_allow_hosts

    socket_allow_hosts(["127.0.0.1", "localhost", "::1"])
    from homeassistant.helpers import entity_registry as er

    old_id = setup_switch.unique_id
    before = {e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), setup_switch.entry_id)}
    result = await setup_switch.start_reconfigure_flow(hass)
    await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "localhost", CONF_PORT: fake_switch.port})
    await hass.async_block_till_done()
    entities = er.async_entries_for_config_entry(er.async_get(hass), setup_switch.entry_id)
    assert {e.entity_id for e in entities} == before and before
    assert all(e.unique_id.startswith(f"localhost:{fake_switch.port}_") for e in entities)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "tcp"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: fake_switch.port, CONF_MODEL: "UKM-401"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == old_id
