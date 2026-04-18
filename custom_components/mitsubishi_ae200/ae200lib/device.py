"""Device state representation for AE-200 controlled units."""

from dataclasses import dataclass, field
import time


@dataclass
class DeviceState:
    """Represents the current state of a single HVAC/water heater unit."""

    group_id: str
    name: str
    attributes: dict[str, str] = field(default_factory=dict)
    last_updated: float = 0.0
    available: bool = True
    last_error: str | None = None
    last_successful_poll: str | None = None

    def update(self, attrs: dict[str, str]) -> None:
        """Merge non-empty attributes from a poll response.

        Empty strings from the controller indicate missing data, not a
        deliberate clear, so we keep the last known good value.
        """
        for key, value in attrs.items():
            if value != "":
                self.attributes[key] = value
        self.last_updated = time.monotonic()
        self.available = True
        self.last_error = None

    def mark_error(self, reason: str) -> None:
        """Mark this device as unavailable with a reason."""
        self.available = False
        self.last_error = reason

    # -- Convenience properties for common attributes --

    @property
    def drive(self) -> str:
        return self.attributes.get("Drive", "OFF")

    @property
    def mode(self) -> str:
        return self.attributes.get("Mode", "AUTO")

    @property
    def set_temp(self) -> float | None:
        return self._float("SetTemp")

    @property
    def set_temp1(self) -> float | None:
        return self._float("SetTemp1")

    @property
    def set_temp2(self) -> float | None:
        return self._float("SetTemp2")

    @property
    def inlet_temp(self) -> float | None:
        return self._float("InletTemp")

    @property
    def fan_speed(self) -> str:
        return self.attributes.get("FanSpeed", "")

    @property
    def fan_speed_sw(self) -> str:
        return self.attributes.get("FanSpeedSW", "NONE")

    @property
    def air_direction(self) -> str:
        return self.attributes.get("AirDirection", "")

    @property
    def swing_sw(self) -> str:
        return self.attributes.get("SwingSW", "")

    @property
    def air_direction_sw(self) -> str:
        return self.attributes.get("AirDirectionSW", "")

    @property
    def error_sign(self) -> str:
        return self.attributes.get("ErrorSign", "OFF")

    @property
    def filter_sign(self) -> str:
        return self.attributes.get("FilterSign", "OFF")

    @property
    def model(self) -> str:
        return self.attributes.get("Model", "")

    @property
    def is_water_heater(self) -> bool:
        return self.model == "WH"

    @property
    def inlet_temp_hwhp(self) -> float | None:
        return self._float("InletTempHWHP")

    @property
    def outlet_temp_hwhp(self) -> float | None:
        return self._float("OutletTempHWHP")

    @property
    def outdoor_temp(self) -> float | None:
        return self._float("OutdoorTemp")

    def _float(self, key: str) -> float | None:
        val = self.attributes.get(key)
        if val is None or val == "":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None
