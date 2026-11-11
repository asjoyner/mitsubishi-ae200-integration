import logging

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    HVACMode,
    ClimateEntityFeature,
)
from homeassistant.const import (
    CONF_IP_ADDRESS,
    UnitOfTemperature,
    ATTR_TEMPERATURE,
)
from homeassistant.helpers.entity import generate_entity_id, DeviceInfo

from .device import via_controller
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .ae200lib.controller import AE200Controller
from .ae200lib.device import DeviceState

from .const import DOMAIN, CONF_CONTROLLER_ID

_LOGGER = logging.getLogger(__name__)

MIN_TEMP = 16
MAX_TEMP = 30
MAX_TEMP_WATER_HEATER = 80

# Fan menus by the unit's FanSpeedSW capability flag. A flag we do not know
# means no fan menu, so FAN_MODE and fan_modes can never disagree.
FAN_MODE_MAPS = {
    "4STAGES": {
        "AUTO": "Auto",
        "LOW": "Min",
        "MID2": "Low",
        "MID1": "High",
        "HIGH": "Max",
    },
    "3STAGES": {
        "AUTO": "Auto",
        "MID2": "Low",
        "MID1": "High",
        "HIGH": "Max",
    },
}

# Every unit has these; FAN_MODE and SWING_MODE depend on the capability
# flags in the last poll and are added in supported_features.
BASE_FEATURES = (
    ClimateEntityFeature.TARGET_TEMPERATURE |
    ClimateEntityFeature.TARGET_TEMPERATURE_RANGE |
    ClimateEntityFeature.TURN_ON |
    ClimateEntityFeature.TURN_OFF
)

class Mode:
    Heat = "HEAT"
    Heating = "HEATING"
    Dry = "DRY"
    Drying = "DRYING"
    Cool = "COOL"
    Cooling = "COOLING"
    Fan = "FAN"
    Auto = "AUTO"
    AutoCool = "AUTOCOOL"
    AutoHeat = "AUTOHEAT"

def _round_temp(temperature):
    """Round temperature to nearest 0.5°C, as required by the AE200 controller."""
    return round(temperature * 2) / 2


class AE200Climate(ClimateEntity):
    def __init__(self, hass, controller: AE200Controller, device: DeviceState,
                 controllerid: str, entry_id: str):
        self._controller = controller
        self._device = device
        self._entry_id = entry_id
        self.entity_id = generate_entity_id(
            "climate.{}", f"mitsubishi_ae_200_{controllerid}_{device.name}", None, hass
        )
        self._attr_hvac_modes = [
            HVACMode.OFF,
            HVACMode.HEAT,
            HVACMode.COOL,
            HVACMode.DRY,
            HVACMode.FAN_ONLY,
            HVACMode.HEAT_COOL,
        ]
        self._swing_mode_map = {
            "AUTO": "Auto",
            "SWING": "Swing",
            "VERTICAL": "Vertical",
            "MID2": "Mid 2",
            "MID1": "Mid 1",
            "MID0": "Mid 0",
            "HORIZONTAL": "Horizontal",
        }
        self._reverse_swing_mode_map = {v: k for k, v in self._swing_mode_map.items()}
        self._attr_swing_modes = list(self._swing_mode_map.values())

        self._model_code = device.model
        self._is_water_heater = device.is_water_heater

        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._current_temperature = None
        self._target_temperature = None
        self._target_temperature_high = None
        self._target_temperature_low = None
        self._swing_mode = None
        self._fan_mode = None
        self._hvac_mode = HVACMode.OFF
        self._last_hvac_mode = HVACMode.COOL

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
    def _fan_mode_map(self) -> dict[str, str]:
        """Device fan speed -> HA fan mode, per the last poll's capabilities."""
        return FAN_MODE_MAPS.get(self._device.fan_speed_sw, {})

    @property
    def _reverse_fan_mode_map(self) -> dict[str, str]:
        return {v: k for k, v in self._fan_mode_map.items()}

    @property
    def fan_modes(self):
        return list(self._fan_mode_map.values()) or None

    @property
    def supported_features(self):
        """Features from the capability flags in the latest poll.

        Derived on every read, not frozen in __init__: the capability flags
        arrive with the first successful poll, and if that poll returned
        nothing the flags would otherwise stay wrong until HA restarts.
        """
        features = BASE_FEATURES
        if self._fan_mode_map:
            features |= ClimateEntityFeature.FAN_MODE
        if self._device.swing_sw == "ENABLE":
            features |= ClimateEntityFeature.SWING_MODE
        return features

    @property
    def should_poll(self):
        return True

    @property
    def name(self):
        return self._device.name

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_{self._device.group_id}"

    @property
    def device_info(self) -> DeviceInfo:
        MODEL_NAMES = {"IC": "Air Conditioner", "WH": "Air to Water"}
        model = MODEL_NAMES.get(self._model_code, f"Unknown ({self._model_code})")
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry_id}_{self._device.group_id}")},
            name=self._device.name,
            manufacturer="Mitsubishi Electric",
            model=model,
            **via_controller(self.hass, self._entry_id),
        )

    @property
    def temperature_unit(self):
        return self._attr_temperature_unit

    @property
    def current_temperature(self):
        return self._current_temperature

    @property
    def target_temperature(self):
        if self._hvac_mode == HVACMode.HEAT_COOL:
            return None
        else:
            return self._target_temperature

    @property
    def target_temperature_high(self):
        if self._hvac_mode == HVACMode.HEAT_COOL:
            return self._target_temperature_high
        else:
            return None

    @property
    def target_temperature_low(self):
        if self._hvac_mode == HVACMode.HEAT_COOL:
            return self._target_temperature_low
        else:
            return None

    @property
    def min_temp(self):
        return MIN_TEMP

    @property
    def max_temp(self):
        if self._is_water_heater:
            return MAX_TEMP_WATER_HEATER
        return MAX_TEMP

    @property
    def target_temperature_step(self):
        return 0.5

    @property
    def fan_mode(self):
        if self._fan_mode and self._fan_mode in self._fan_mode_map:
            return self._fan_mode_map[self._fan_mode]
        # Return first valid fan mode as fallback; HA rejects None when
        # FAN_MODE feature is supported.
        fan_modes = self.fan_modes
        if fan_modes:
            return fan_modes[0]
        return None

    @property
    def swing_mode(self):
        if self._swing_mode and self._swing_mode in self._swing_mode_map:
            return self._swing_mode_map[self._swing_mode]
        if self._attr_swing_modes:
            return self._attr_swing_modes[0]
        return None

    @property
    def hvac_mode(self):
        return self._hvac_mode

    async def async_turn_on(self):
        _LOGGER.info(f"Turning on HVAC mode: {self._last_hvac_mode} for {self.entity_id}")
        await self._controller.send_command(self._device.group_id, {"Drive": "ON"})
        self._hvac_mode = self._last_hvac_mode
        self.async_write_ha_state()

    async def async_turn_off(self):
        _LOGGER.info(f"Turning off HVAC for {self.entity_id}")
        await self._controller.send_command(self._device.group_id, {"Drive": "OFF"})
        self._hvac_mode = HVACMode.OFF
        self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode):
        device_swing_mode = self._reverse_swing_mode_map.get(swing_mode, swing_mode)
        _LOGGER.info(f"Setting swing mode: {device_swing_mode} for {self.entity_id}")
        await self._controller.send_command(self._device.group_id, {"AirDirection": device_swing_mode})
        self._swing_mode = device_swing_mode
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode):
        device_fan_mode = self._reverse_fan_mode_map.get(fan_mode, fan_mode)
        _LOGGER.info(f"Setting fan mode: {device_fan_mode} for {self.entity_id}")
        await self._controller.send_command(self._device.group_id, {"FanSpeed": device_fan_mode})
        self._fan_mode = device_fan_mode
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs):
        _LOGGER.info(f"Setting temperature: {kwargs.get(ATTR_TEMPERATURE)} for {self.entity_id}")
        _LOGGER.info(kwargs)
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            temperature = _round_temp(temperature)
            params = {"SetTemp": str(temperature)}
            mode = self._device.mode
            if mode in (Mode.Heat, Mode.Heating, Mode.AutoHeat):
                params["SetTemp2"] = str(temperature)
            elif mode in (Mode.Cool, Mode.Cooling, Mode.Dry, Mode.Drying, Mode.AutoCool):
                params["SetTemp1"] = str(temperature)
            await self._controller.send_command(self._device.group_id, params)
            self._target_temperature = temperature
            self.async_write_ha_state()

        temp_low = kwargs.get("target_temp_low")
        temp_high = kwargs.get("target_temp_high")
        if temp_low is not None and temp_high is not None:
            temp_high = _round_temp(temp_high)
            temp_low = _round_temp(temp_low)
            await self._controller.send_command(self._device.group_id, {
                "SetTemp1": str(temp_high),
                "SetTemp2": str(temp_low),
            })
            self._target_temperature_low = temp_low
            self._target_temperature_high = temp_high
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode):
        _LOGGER.info(f"Setting HVAC mode: {hvac_mode} for {self.entity_id}")
        if hvac_mode == HVACMode.OFF:
            await self._controller.send_command(self._device.group_id, {"Drive": "OFF"})
            self._hvac_mode = HVACMode.OFF
        else:
            await self._controller.send_command(self._device.group_id, {"Drive": "ON"})
            mode_map = {
                HVACMode.HEAT: Mode.Heat,
                HVACMode.COOL: Mode.Cool,
                HVACMode.DRY: Mode.Dry,
                HVACMode.FAN_ONLY: Mode.Fan,
                HVACMode.HEAT_COOL: Mode.Auto,
            }
            await self._controller.send_command(
                self._device.group_id, {"Mode": mode_map.get(hvac_mode, Mode.Auto)}
            )
            self._hvac_mode = hvac_mode
        self.async_write_ha_state()

    async def async_update(self):
        _LOGGER.info(f"Updating climate entity: {self.entity_id}")
        await self._controller.poll_device(self._device.group_id)

        model = self._device.model
        if model != self._model_code:
            self._model_code = model
            self._is_water_heater = self._device.is_water_heater
            if model not in ("IC", "WH"):
                _LOGGER.warning(
                    f"Unrecognized unit model '{model}' for {self.entity_id}; "
                    f"using HVAC defaults. See "
                    f"https://github.com/sftgunner/mitsubishi-ae200-integration/blob/main/ADDING_DEVICE_TYPES.md"
                )
        self._current_temperature = self._device.inlet_temp
        self._fan_mode = self._device.fan_speed
        self._swing_mode = self._device.air_direction

        if self._device.drive == "ON":
            # Target temperature: read back the slot the unit actually runs
            # on, the same one async_set_temperature writes for this mode.
            # SetTemp is only the fallback: it accepts and echoes a write
            # that the unit does not control on, so preferring it reports a
            # setpoint the equipment is not keeping and hides a stale slot.
            mode = self._device.mode
            if mode in (Mode.Heat, Mode.Heating, Mode.AutoHeat):
                temp = self._device.set_temp2
            elif mode in (Mode.Cool, Mode.Cooling, Mode.Dry,
                          Mode.Drying, Mode.AutoCool):
                temp = self._device.set_temp1
            else:
                temp = None
            if temp is None:
                temp = self._device.set_temp
            self._target_temperature = temp
            self._target_temperature_high = self._device.set_temp1
            self._target_temperature_low = self._device.set_temp2

            mode = self._device.mode
            if mode in (Mode.Heat, Mode.Heating):
                self._hvac_mode = HVACMode.HEAT
            elif mode in (Mode.Cool, Mode.Cooling):
                self._hvac_mode = HVACMode.COOL
            elif mode in (Mode.Dry, Mode.Drying):
                self._hvac_mode = HVACMode.DRY
            elif mode == Mode.Fan:
                self._hvac_mode = HVACMode.FAN_ONLY
                self._target_temperature = None
            elif mode in (Mode.Auto, Mode.AutoCool, Mode.AutoHeat):
                self._hvac_mode = HVACMode.HEAT_COOL
            else:
                _LOGGER.warning(f"Unknown HVAC mode '{mode}' for {self.entity_id}, defaulting to HEAT_COOL")
                self._hvac_mode = HVACMode.HEAT_COOL
        else:
            self._target_temperature = None
            self._target_temperature_high = None
            self._target_temperature_low = None
            self._hvac_mode = HVACMode.OFF


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mitsubishi AE200 climate entities from a config entry."""
    _LOGGER.info("Setting up Mitsubishi AE200 climate platform from config entry...")

    data = hass.data[DOMAIN][entry.entry_id]
    controller = data["controller"]
    controllerid = entry.data[CONF_CONTROLLER_ID]

    entities = []
    for device in controller.devices.values():
        entities.append(AE200Climate(hass, controller, device, controllerid, entry.entry_id))

    if entities:
        async_add_entities(entities, update_before_add=True)
        _LOGGER.info(f"Added {len(entities)} Mitsubishi AE200 climate device(s).")
    else:
        _LOGGER.warning("No Mitsubishi AE200 devices found.")
