"""Binary sensors for Mitsubishi AE200 integration."""
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from .ae200lib.controller import AE200Controller
from .ae200lib.device import DeviceState

from .const import DOMAIN, CONF_CONTROLLER_ID

_LOGGER = logging.getLogger(__name__)


class AE200FilterSignSensor(BinarySensorEntity):
    """Binary sensor for AE200 filter sign status."""

    def __init__(self, hass, controller: AE200Controller, device: DeviceState,
                 controllerid: str, entry_id: str):
        self._controller = controller
        self._device = device
        self._entry_id = entry_id
        self.entity_id = generate_entity_id(
            "binary_sensor.{}",
            f"mitsubishi_ae_200_{controllerid}_{device.name}_filter",
            None,
            hass,
        )
        self._attr_is_on = False

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_{self._device.group_id}_filter"

    @property
    def name(self) -> str:
        return f"{self._device.name} Filter Sign"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry_id}_{self._device.group_id}")},
            name=self._device.name,
            manufacturer="Mitsubishi Electric",
            model="HVAC Unit",
            via_device=(DOMAIN, self._entry_id),
        )

    @property
    def available(self) -> bool:
        return self._device.available

    @property
    def extra_state_attributes(self) -> dict:
        attrs = {}
        if self._device.last_error is not None:
            attrs["last_error_reason"] = self._device.last_error
        if self._device.last_successful_poll is not None:
            attrs["last_successful_poll"] = self._device.last_successful_poll
        return attrs

    @property
    def is_on(self) -> bool:
        return self._attr_is_on

    async def async_update(self):
        # Device state is already polled by the shared controller via climate.
        # We just read from the shared DeviceState — no duplicate WebSocket call.
        self._attr_is_on = self._device.filter_sign == "ON"


class AE200ErrorSignSensor(BinarySensorEntity):
    """Binary sensor for AE200 error sign status."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, hass, controller: AE200Controller, device: DeviceState,
                 controllerid: str, entry_id: str):
        self._controller = controller
        self._device = device
        self._entry_id = entry_id
        self.entity_id = generate_entity_id(
            "binary_sensor.{}",
            f"mitsubishi_ae_200_{controllerid}_{device.name}_error",
            None,
            hass,
        )
        self._attr_is_on = False

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_{self._device.group_id}_error"

    @property
    def name(self) -> str:
        return f"{self._device.name} Error Sign"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry_id}_{self._device.group_id}")},
            name=self._device.name,
            manufacturer="Mitsubishi Electric",
            model="HVAC Unit",
            via_device=(DOMAIN, self._entry_id),
        )

    @property
    def available(self) -> bool:
        return self._device.available

    @property
    def extra_state_attributes(self) -> dict:
        attrs = {}
        if self._device.last_error is not None:
            attrs["last_error_reason"] = self._device.last_error
        if self._device.last_successful_poll is not None:
            attrs["last_successful_poll"] = self._device.last_successful_poll
        return attrs

    @property
    def is_on(self) -> bool:
        return self._attr_is_on

    async def async_update(self):
        # Read from shared DeviceState — no duplicate polling
        self._attr_is_on = self._device.error_sign == "ON"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors from a config entry."""
    _LOGGER.info("Setting up Mitsubishi AE200 binary sensors from config entry...")

    data = hass.data[DOMAIN][entry.entry_id]
    controller = data["controller"]
    controllerid = entry.data[CONF_CONTROLLER_ID]

    sensors = []
    for device in controller.devices.values():
        sensors.append(
            AE200FilterSignSensor(hass, controller, device, controllerid, entry.entry_id)
        )
        sensors.append(
            AE200ErrorSignSensor(hass, controller, device, controllerid, entry.entry_id)
        )

    if sensors:
        async_add_entities(sensors, update_before_add=True)
        _LOGGER.info(f"Added {len(sensors)} Mitsubishi AE200 binary sensor(s).")
    else:
        _LOGGER.warning("No Mitsubishi AE200 devices found.")
