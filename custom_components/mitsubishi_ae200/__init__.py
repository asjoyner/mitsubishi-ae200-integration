"""The Mitsubishi AE200 integration."""
import asyncio
import logging
import xml.etree.ElementTree as ET

import voluptuous as vol
import websockets.exceptions

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .ae200lib.controller import AE200Controller

from .const import DOMAIN, CONF_CONTROLLER_ID

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.BINARY_SENSOR]

SERVICE_FILTER_RESET = "filter_reset"
SERVICE_FILTER_RESET_SCHEMA = vol.Schema({
    vol.Required("group_id"): str,
})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Mitsubishi AE200 from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    ip_address = entry.data[CONF_IP_ADDRESS]
    controller = AE200Controller(ip_address)
    # The AE-200 answers ping, HTTP and the WebSocket upgrade for ~10 min
    # after a power cut before it answers XML. Raising ConfigEntryNotReady
    # makes HA retry setup with backoff; any other exception leaves the
    # entry in setup_error and every entity unavailable until a manual reload.
    try:
        devices = await controller.discover_devices()
    except (
        OSError,
        asyncio.TimeoutError,
        websockets.exceptions.WebSocketException,
        ET.ParseError,
    ) as err:
        raise ConfigEntryNotReady(
            f"AE-200 at {ip_address} not answering: {err!r}"
        ) from err
    if not devices:
        raise ConfigEntryNotReady(f"AE-200 at {ip_address} reported no groups")

    hass.data[DOMAIN][entry.entry_id] = {
        "controller": controller,
        "config": entry.data,
    }

    # Register the controller as a device
    device_registry = dr.async_get(hass)
    hub = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"Mitsubishi AE200 Controller ({entry.data[CONF_CONTROLLER_ID]})",
        manufacturer="Mitsubishi Electric",
        model="AE200 Controller",
        configuration_url=f"http://{ip_address}",
    )
    hass.data[DOMAIN][entry.entry_id]["hub_device_id"] = hub.id

    async def handle_filter_reset(call: ServiceCall) -> None:
        """Reset the filter sign for a specific group."""
        group_id = call.data["group_id"]
        for entry_data in hass.data[DOMAIN].values():
            ctrl = entry_data["controller"]
            if group_id in ctrl.devices:
                _LOGGER.info("Resetting filter sign for group %s", group_id)
                await ctrl.send_command(group_id, {"FilterSign": "RESET"})
                return
        _LOGGER.warning("Group %s not found on any AE-200 controller", group_id)

    hass.services.async_register(
        DOMAIN, SERVICE_FILTER_RESET, handle_filter_reset,
        schema=SERVICE_FILTER_RESET_SCHEMA,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    # Only remove service if no more entries remain
    if not hass.data.get(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_FILTER_RESET)

    return unload_ok
