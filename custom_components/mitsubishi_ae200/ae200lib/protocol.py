"""XML protocol helpers for AE-200 controllers."""

import xml.etree.ElementTree as ET


# All known Mnet device attributes
MNET_ATTRS = (
    "Drive", "Vent24h", "Mode", "VentMode", "ModeStatus",
    "SetTemp", "SetTemp1", "SetTemp2", "SetTemp3", "SetTemp4", "SetTemp5",
    "SetHumidity", "InletTemp", "InletHumidity",
    "AirDirection", "FanSpeed", "RemoCon",
    "DriveItem", "ModeItem", "SetTempItem", "FilterItem",
    "AirDirItem", "FanSpeedItem", "TimerItem", "CheckWaterItem",
    "FilterSign", "Hold", "EnergyControl", "EnergyControlIC",
    "SetbackControl", "Ventilation", "VentiDrive", "VentiFan",
    "Schedule", "ScheduleAvail", "ErrorSign", "CheckWater",
    "TempLimitCool", "TempLimitHeat", "TempLimit",
    "CoolMin", "CoolMax", "HeatMin", "HeatMax", "AutoMin", "AutoMax",
    "TurnOff", "MaxSaveValue",
    "RoomHumidity", "Brightness", "Occupancy",
    "NightPurge", "Humid", "Vent24hMode", "SnowFanMode",
    "InletTempHWHP", "OutletTempHWHP", "HeadTempHWHP",
    "OutdoorTemp", "BrineTemp", "HeadInletTempCH",
    "BACnetTurnOff", "AISmartStart",
    "Model", "GroupType", "AirDirectionSW", "SwingSW", "FanSpeedSW",
)

SYSTEM_ATTRS = (
    "LocationID", "Name", "Number", "Version", "VersionIF", "Model",
    "TempUnit", "PressUnit",
    "FilterSign", "ShortName", "DecimalPoint", "CSVSeparator",
    "DateFormat", "TimeFormat",
    "RoomTemp", "Occupancy", "Brightness", "RoomHumidity",
    "IPAdrsLan", "IPAdrsLan1", "SubnetMaskLan1", "GwLan1", "MacAddress1",
    "IPAdrsLan2", "SubnetMaskLan2", "MacAddress2", "GwLan2",
    "UseMnet", "MnetAdrs", "MnetStatus", "Operation",
    "Prohibit", "External", "ExOutput",
    "Apportion", "OutTempAdrs",
    "TimeMaster", "HoldType", "OldTypeMode",
    "LocalAddress", "PopUser", "SmtpServer", "PortNo", "SmtpAuth",
    "PopServer", "PopInterval", "MailTitle",
    "DNSPri", "DNSSec",
)


def wrap(command: str, body: str) -> str:
    """Wrap an XML body in the AE-200 Packet envelope."""
    return (
        '<?xml version="1.0" encoding="UTF-8" ?>'
        f"<Packet><Command>{command}</Command>"
        f"<DatabaseManager>{body}</DatabaseManager></Packet>"
    )


def get_request(body: str) -> str:
    return wrap("getRequest", body)


def set_request(body: str) -> str:
    return wrap("setRequest", body)


def build_list_groups() -> str:
    """Build a getRequest to enumerate all device groups."""
    return get_request("<ControlGroup><MnetList /></ControlGroup>")


def mnet_query(device_ids: list[str]) -> str:
    """Build a getRequest for Mnet device status (batch query)."""
    attrs = " ".join(f'{a}="*"' for a in MNET_ATTRS)
    mnets = "\n".join(f'<Mnet Group="{gid}" {attrs} />' for gid in device_ids)
    return get_request(mnets)


def build_mnet_set(device_id: str, attrs: dict[str, str]) -> str:
    """Build a setRequest for a single device."""
    attr_str = " ".join(f'{k}="{v}"' for k, v in attrs.items())
    return set_request(f'<Mnet Group="{device_id}" {attr_str} />')


def system_query() -> str:
    """Build a getRequest for SystemData."""
    attrs = " ".join(f'{a}="*"' for a in SYSTEM_ATTRS)
    return get_request(f"<SystemData {attrs} />")


def xml_to_dict(element: ET.Element) -> dict:
    """Convert an XML element to a dict of its attributes plus child elements."""
    d = dict(element.attrib)
    for child in element:
        tag = child.tag
        if len(child) > 0 or len(child.attrib) > 0:
            child_data = xml_to_dict(child)
            if tag in d:
                if not isinstance(d[tag], list):
                    d[tag] = [d[tag]]
                d[tag].append(child_data)
            else:
                d[tag] = child_data
        elif child.attrib:
            d[tag] = dict(child.attrib)
        elif child.text and child.text.strip():
            d[tag] = child.text.strip()
    return d


def parse_response(raw: str) -> dict:
    """Parse an AE-200 XML response into a Python dict."""
    root = ET.fromstring(raw)
    db = root.find("DatabaseManager")
    if db is None:
        return xml_to_dict(root)
    results = {}
    for child in db:
        tag = child.tag
        data = xml_to_dict(child)
        if tag in results:
            if not isinstance(results[tag], list):
                results[tag] = [results[tag]]
            results[tag].append(data)
        else:
            results[tag] = data
    return results


def parse_group_list(raw: str) -> list[dict[str, str]]:
    """Parse an MnetList response into a list of {id, name} dicts."""
    root = ET.fromstring(raw)
    groups = []
    for r in root.findall(".//MnetRecord"):
        groups.append({"id": r.get("Group"), "name": r.get("GroupNameWeb")})
    return groups


def parse_mnet_devices(raw: str) -> list[dict[str, str]]:
    """Parse an Mnet getRequest response into a list of attribute dicts."""
    root = ET.fromstring(raw)
    devices = []
    for mnet in root.findall(".//Mnet"):
        devices.append(dict(mnet.attrib))
    return devices
