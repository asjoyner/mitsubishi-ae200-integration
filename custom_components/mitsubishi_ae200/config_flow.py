"""Config flow for Mitsubishi AE200 integration."""
import logging
import voluptuous as vol
from typing import Any

from homeassistant import config_entries
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .ae200lib.controller import AE200Controller

from .const import DOMAIN, CONF_CONTROLLER_ID

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CONTROLLER_ID): cv.string,
        vol.Required(CONF_IP_ADDRESS): cv.string,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    controller = AE200Controller(data[CONF_IP_ADDRESS])

    try:
        devices = await controller.discover_devices()

        if not devices:
            raise ValueError("No devices found")

        return {
            "title": f"Mitsubishi AE200 ({data[CONF_CONTROLLER_ID]})",
            "num_devices": len(devices)
        }
    except Exception as err:
        _LOGGER.error(f"Error connecting to Mitsubishi AE200: {err}")
        raise


class MitsubishiAE200ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mitsubishi AE200."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except ValueError:
                errors["base"] = "no_devices"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user_input[CONF_CONTROLLER_ID])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )
