"""Link unit devices to the AE200 controller device across HA versions."""
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

# HA 2026.8 added DeviceInfo.via_device_id and deprecated via_device; from
# 2026.10 the deprecated form makes entity setup fail.
_HAS_VIA_DEVICE_ID = "via_device_id" in DeviceInfo.__annotations__


def via_controller(hass: HomeAssistant, entry_id: str) -> dict:
    """DeviceInfo kwargs naming the controller device as the parent."""
    if not _HAS_VIA_DEVICE_ID:
        return {"via_device": (DOMAIN, entry_id)}
    hub_id = hass.data[DOMAIN][entry_id]["hub_device_id"]
    return {"via_device_id": hub_id}
