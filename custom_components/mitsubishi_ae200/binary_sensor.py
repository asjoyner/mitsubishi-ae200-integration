"""Binary sensors for Mitsubishi AE200 integration."""
import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from .mitsubishi_ae200 import MitsubishiAE200Functions
from .const import DOMAIN, CONF_CONTROLLER_ID

_LOGGER = logging.getLogger(__name__)


class AE200FilterSignSensor(BinarySensorEntity):
    """Binary sensor for AE200 filter sign status."""

    def __init__(self, hass, device, controllerid: str, entry_id: str):
        """Initialize the filter sign sensor."""
        self._device = device
        self._entry_id = entry_id
        self.entity_id = generate_entity_id(
            "binary_sensor.{}",
            f"mitsubishi_ae_200_{controllerid}_{device.getName()}_filter",
            None,
            hass,
        )
        self._attr_is_on = False

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this binary sensor."""
        return f"{self._entry_id}_{self._device.getID()}_filter"

    @property
    def name(self) -> str:
        """Return the name of the binary sensor."""
        return f"{self._device.getName()} Filter Sign"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this sensor."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry_id}_{self._device.getID()}")},
            name=self._device.getName(),
            manufacturer="Mitsubishi Electric",
            model="HVAC Unit",
            via_device=(DOMAIN, self._entry_id),
        )

    @property
    def is_on(self) -> bool:
        """Return True if filter sign is ON."""
        return self._attr_is_on

    async def async_update(self):
        """Update the filter sign status."""
        await self._device._refresh_device_info_async()
        filter_sign = await self._device.getFilterSign()
        self._attr_is_on = filter_sign == "ON"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors from a config entry."""
    _LOGGER.info("Setting up Mitsubishi AE200 binary sensors from config entry...")

    controllerid = entry.data[CONF_CONTROLLER_ID]
    ipaddress = entry.data[CONF_IP_ADDRESS]

    mitsubishi_ae200_functions = MitsubishiAE200Functions()
    sensors = []

    try:
        # Get device list from controller
        group_list = await mitsubishi_ae200_functions.getDevicesAsync(ipaddress)
        for group in group_list:
            from .climate import AE200Device

            device = AE200Device(
                ipaddress, group["id"], group["name"], mitsubishi_ae200_functions
            )
            sensors.append(
                AE200FilterSignSensor(hass, device, controllerid, entry.entry_id)
            )

        if sensors:
            async_add_entities(sensors, update_before_add=True)
            _LOGGER.info(f"Added {len(sensors)} Mitsubishi AE200 binary sensor(s).")
        else:
            _LOGGER.warning("No Mitsubishi AE200 devices found.")
    except Exception as err:
        _LOGGER.error(f"Error setting up Mitsubishi AE200 binary sensors: {err}")
