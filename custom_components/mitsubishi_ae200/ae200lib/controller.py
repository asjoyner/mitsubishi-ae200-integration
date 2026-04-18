"""High-level async client for AE-200 controllers."""

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import websockets.exceptions

from .transport import ws_request
from .protocol import build_list_groups, mnet_query, build_mnet_set, parse_group_list, parse_mnet_devices
from .device import DeviceState

_LOGGER = logging.getLogger(__name__)


class AE200Controller:
    """One instance per physical AE-200 controller.

    Manages device discovery, batch polling, and command dispatch.
    """

    def __init__(self, host: str, timeout: float = 10.0):
        self.host = host
        self.timeout = timeout
        self._devices: dict[str, DeviceState] = {}

    @property
    def devices(self) -> dict[str, DeviceState]:
        """Current cached device states, keyed by group_id."""
        return self._devices

    async def discover_devices(self) -> list[DeviceState]:
        """Query MnetList, create DeviceState objects, and do initial poll."""
        raw = await ws_request(self.host, build_list_groups(), timeout=self.timeout)
        groups = parse_group_list(raw)
        for g in groups:
            gid = g["id"]
            if gid not in self._devices:
                self._devices[gid] = DeviceState(group_id=gid, name=g["name"])
        await self.poll_all()
        return list(self._devices.values())

    async def poll_all(self) -> None:
        """Single WebSocket call to fetch all devices at once."""
        if not self._devices:
            return
        ids = list(self._devices.keys())
        try:
            raw = await ws_request(self.host, mnet_query(ids), timeout=self.timeout)
            device_attrs = parse_mnet_devices(raw)
            now = datetime.now(timezone.utc).isoformat()
            for attrs in device_attrs:
                gid = attrs.get("Group")
                if gid and gid in self._devices:
                    self._devices[gid].update(attrs)
                    self._devices[gid].last_successful_poll = now
        except (ConnectionRefusedError, OSError) as err:
            _LOGGER.warning("Connection refused to %s: %s", self.host, err)
            self._mark_all_error("connection_refused")
        except (asyncio.TimeoutError, websockets.exceptions.WebSocketException) as err:
            _LOGGER.warning("Connection timeout to %s: %s", self.host, err)
            self._mark_all_error("connection_timeout")
        except (ET.ParseError, AttributeError) as err:
            _LOGGER.warning("Invalid response from %s: %s", self.host, err)
            self._mark_all_error("invalid_response")
        except Exception as err:
            _LOGGER.warning("Unexpected error polling %s: %s", self.host, err)
            self._mark_all_error(str(err))

    async def poll_device(self, group_id: str) -> DeviceState | None:
        """Single-device refresh."""
        device = self._devices.get(group_id)
        if device is None:
            return None
        try:
            raw = await ws_request(self.host, mnet_query([group_id]), timeout=self.timeout)
            device_attrs = parse_mnet_devices(raw)
            if device_attrs:
                device.update(device_attrs[0])
                device.last_successful_poll = datetime.now(timezone.utc).isoformat()
        except (ConnectionRefusedError, OSError) as err:
            device.mark_error("connection_refused")
            _LOGGER.warning("Connection refused for %s (%s): %s", device.name, group_id, err)
        except (asyncio.TimeoutError, websockets.exceptions.WebSocketException) as err:
            device.mark_error("connection_timeout")
            _LOGGER.warning("Connection timeout for %s (%s): %s", device.name, group_id, err)
        except (ET.ParseError, AttributeError) as err:
            device.mark_error("invalid_response")
            _LOGGER.warning("Invalid response for %s (%s): %s", device.name, group_id, err)
        except Exception as err:
            device.mark_error(str(err))
            _LOGGER.warning("Unexpected error for %s (%s): %s", device.name, group_id, err)
        return device

    async def send_command(self, group_id: str, attrs: dict[str, str]) -> None:
        """Send a setRequest to a device."""
        payload = build_mnet_set(group_id, attrs)
        try:
            response = await ws_request(self.host, payload, timeout=self.timeout)
            if "ErrorResponse" in response or "errorResponse" in response:
                _LOGGER.error("AE200 setRequest failed for group %s: %s", group_id, response)
            else:
                _LOGGER.debug("AE200 setRequest OK for group %s: %s", group_id, response)
        except asyncio.TimeoutError:
            _LOGGER.warning("AE200 setRequest: no response within %.1fs for group %s", self.timeout, group_id)

    def _mark_all_error(self, reason: str) -> None:
        for device in self._devices.values():
            device.mark_error(reason)
