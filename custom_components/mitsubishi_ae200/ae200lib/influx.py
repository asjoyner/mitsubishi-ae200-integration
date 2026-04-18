"""InfluxDB writer for AE-200 device states.

Supports both InfluxDB v1.x (line protocol over HTTP) and v2.x (influxdb-client).
Selection is automatic: if `token` and `org` are provided, v2 is used; otherwise v1.
"""

import logging
import time
import urllib.request
import urllib.error
import urllib.parse

_LOGGER = logging.getLogger(__name__)

try:
    from influxdb_client import InfluxDBClient, Point, WritePrecision
    from influxdb_client.client.write_api import SYNCHRONOUS
    HAS_INFLUX_V2 = True
except ImportError:
    HAS_INFLUX_V2 = False


def _escape_tag(s: str) -> str:
    """Escape special characters in a tag key or value for line protocol."""
    return s.replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


def _escape_field_str(s: str) -> str:
    """Escape a string field value (inside double quotes)."""
    return s.replace('"', '\\"').replace("\\", "\\\\")


def _build_line_protocol(controller_name: str, devices) -> str:
    """Build InfluxDB line protocol for all devices."""
    lines = []
    now_ns = int(time.time() * 1e9)

    for device in devices:
        if not device.available:
            continue

        tags = (
            f"controller={_escape_tag(controller_name)},"
            f"group_id={_escape_tag(device.group_id)},"
            f"group_name={_escape_tag(device.name)}"
        )

        if device.inlet_temp is not None:
            lines.append(f"ae200_temperature,{tags},type=inlet value={device.inlet_temp} {now_ns}")
        if device.set_temp is not None:
            lines.append(f"ae200_temperature,{tags},type=setpoint value={device.set_temp} {now_ns}")
        if device.set_temp1 is not None:
            lines.append(f"ae200_temperature,{tags},type=setpoint_cool value={device.set_temp1} {now_ns}")
        if device.set_temp2 is not None:
            lines.append(f"ae200_temperature,{tags},type=setpoint_heat value={device.set_temp2} {now_ns}")
        if device.inlet_temp_hwhp is not None and device.inlet_temp_hwhp != 0.0:
            lines.append(f"ae200_temperature,{tags},type=inlet_hwhp value={device.inlet_temp_hwhp} {now_ns}")
        if device.outlet_temp_hwhp is not None and device.outlet_temp_hwhp != 0.0:
            lines.append(f"ae200_temperature,{tags},type=outlet_hwhp value={device.outlet_temp_hwhp} {now_ns}")
        if device.outdoor_temp is not None and device.outdoor_temp != 0.0:
            lines.append(f"ae200_temperature,{tags},type=outdoor value={device.outdoor_temp} {now_ns}")

        drive = 1 if device.drive == "ON" else 0
        error = 1 if device.error_sign == "ON" else 0
        filter_s = 1 if device.filter_sign == "ON" else 0
        mode = _escape_field_str(device.mode)
        fields = f'drive={drive}i,mode="{mode}",error_sign={error}i,filter_sign={filter_s}i'
        if device.fan_speed_sw != "NONE":
            fan = _escape_field_str(device.fan_speed)
            fields += f',fan_speed="{fan}"'
        lines.append(f"ae200_state,{tags} {fields} {now_ns}")

    return "\n".join(lines)


class InfluxV1Writer:
    """Writes to InfluxDB v1.x using the HTTP /write endpoint."""

    def __init__(self, url: str, database: str, username: str = "", password: str = ""):
        self._url = url.rstrip("/")
        self._database = database
        self._username = username
        self._password = password
        self._create_database()

    def _auth_header(self) -> dict[str, str]:
        if not self._username:
            return {}
        import base64
        credentials = base64.b64encode(f"{self._username}:{self._password}".encode()).decode()
        return {"Authorization": f"Basic {credentials}"}

    def _create_database(self) -> None:
        try:
            query = urllib.parse.urlencode({"q": f'CREATE DATABASE "{self._database}"'})
            url = f"{self._url}/query?{query}"
            req = urllib.request.Request(url, method="POST", data=b"")
            for k, v in self._auth_header().items():
                req.add_header(k, v)
            urllib.request.urlopen(req)
        except Exception as err:
            _LOGGER.warning("Could not create database %s: %s", self._database, err)

    def write_device_states(self, controller_name: str, devices) -> None:
        body = _build_line_protocol(controller_name, devices)
        if not body:
            return
        params = urllib.parse.urlencode({"db": self._database, "precision": "ns"})
        url = f"{self._url}/write?{params}"
        req = urllib.request.Request(url, data=body.encode("utf-8"), method="POST")
        req.add_header("Content-Type", "application/octet-stream")
        for k, v in self._auth_header().items():
            req.add_header(k, v)
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as err:
            _LOGGER.error("InfluxDB v1 write failed: %s %s", err.code, err.read().decode())
        except Exception as err:
            _LOGGER.error("InfluxDB v1 write failed: %s", err)

    def close(self):
        pass


class InfluxV2Writer:
    """Writes to InfluxDB v2.x using the influxdb-client library."""

    def __init__(self, url: str, token: str, org: str, bucket: str):
        if not HAS_INFLUX_V2:
            raise ImportError(
                "influxdb-client is required for InfluxDB v2 support. "
                "Install with: pip install influxdb-client"
            )
        self._client = InfluxDBClient(url=url, token=token, org=org)
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
        self._bucket = bucket
        self._org = org

    def write_device_states(self, controller_name: str, devices) -> None:
        body = _build_line_protocol(controller_name, devices)
        if not body:
            return
        try:
            self._write_api.write(bucket=self._bucket, org=self._org, record=body)
        except Exception as err:
            _LOGGER.error("InfluxDB v2 write failed: %s", err)

    def close(self):
        self._client.close()


def create_writer(
    url: str = "http://localhost:8086",
    # v1 params
    database: str = "",
    username: str = "",
    password: str = "",
    # v2 params
    token: str = "",
    org: str = "",
    bucket: str = "",
):
    """Create the appropriate InfluxDB writer based on provided config.

    If `token` and `org` are provided, uses v2 client.
    Otherwise, falls back to v1 HTTP line protocol.
    """
    if token and org:
        _LOGGER.info("Using InfluxDB v2 writer (bucket=%s)", bucket)
        return InfluxV2Writer(url=url, token=token, org=org, bucket=bucket)
    else:
        db = database or bucket or "ae200"
        _LOGGER.info("Using InfluxDB v1 writer (database=%s)", db)
        return InfluxV1Writer(url=url, database=db, username=username, password=password)
