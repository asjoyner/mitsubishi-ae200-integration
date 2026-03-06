# Adding Support for New Device Types

## How Devices Are Identified

The Mitsubishi AE200 controller exposes connected units via a WebSocket API
at `ws://<controller-ip>/b_xmlproc/` using XML payloads.

Each unit belongs to a numbered **Group** (1-N). The unit type is identified
by the `Model` attribute, which can be queried per-group:

```xml
<?xml version="1.0" encoding="UTF-8" ?>
<Packet>
<Command>getRequest</Command>
<DatabaseManager>
<Mnet Group="1" Model="*" />
</DatabaseManager>
</Packet>
```

The controller responds with a short code string in the `Model` field.

## Currently Supported Device Types

| Model Code | Type | Description | Max Temp | Modes Observed |
|---|---|---|---|---|
| `IC` | Air Conditioner | Indoor HVAC unit | 30°C (86°F) | HEAT, COOL, DRY, FAN, AUTO, AUTOHEAT, AUTOCOOL, HEATING, COOLING, DRYING |
| `WH` | Air to Water | Hot water heat pump (e.g. METUS Heat20) | 80°C (176°F) | HEATING, COOLING |

## Key Considerations When Adding a New Device Type

### Temperature Setpoints

The controller uses several temperature attributes. Which ones a device
supports depends on its type:

| Attribute | Purpose | Notes |
|---|---|---|
| `SetTemp` | Generic active setpoint | Used by all devices. **Always send this.** |
| `SetTemp1` | Cooling setpoint | Used by `IC` units in cool/dry/auto modes. Empty on `WH`. |
| `SetTemp2` | Heating setpoint | Used by `IC` units in heat mode. Empty on `WH`. |
| `SetTemp3`-`SetTemp5` | Additional presets | Not currently used by the integration. |

When reading the target temperature, prefer `SetTemp` with a fallback to
`SetTemp1`/`SetTemp2` based on mode. When writing, send `SetTemp` plus the
appropriate mode-specific attribute if the device supports it.

**Important:** The controller only accepts temperature values in **0.5°C
increments** (e.g. 21.0, 21.5, 22.0). Values with more precision (like
21.111 from a Fahrenheit-to-Celsius conversion) are rejected with an
`"Invalid Value"` error response. All temperatures must be rounded to the
nearest 0.5°C before sending.

### Temperature Range

Each device type needs an appropriate `max_temp` ceiling:
- HVAC units cap at 30°C (86°F)
- Water heaters can go up to 80°C (176°F)
- Your new device type may have different limits

Test the acceptable range by sending `setRequest` commands and checking for
`setResponse` (success) vs `setErrorResponse` (failure). The controller's
API may not enforce physical safety limits — defer to the manufacturer's
specifications.

### Modes

Mode strings from the controller can include both base modes and active-state
variants:
- Base: `HEAT`, `COOL`, `DRY`, `FAN`, `AUTO`
- Active-state: `HEATING`, `COOLING`, `DRYING`, `AUTOHEAT`, `AUTOCOOL`

Your device may report modes not listed above. Query the current mode with
`Mode="*"` and test mode transitions to discover what's supported.

### Other Attributes

Some attributes may be empty or unsupported for certain device types. The
`_to_float()` helper handles empty strings gracefully, but be aware that
querying unsupported attributes returns `Unknown Attribute` errors (which
don't prevent valid attributes from being returned in the same request).

Useful attributes to check for a new device type:
- `FanSpeed`, `AirDirection` — may not apply (e.g. water heaters)
- `InletTemp` — current temperature reading
- `InletTempHWHP`, `OutletTempHWHP`, `HeadTempHWHP`, `BrineTemp` — heat pump specific sensors
- `GroupType` — observed values: `NEW`, `OLD`

## How to Add Support

1. Query your device's `Model` attribute to get its code
2. Document the supported modes, temperature attributes, and valid ranges
3. Update these files:
   - `climate.py`: Add the model code to the detection logic in
     `isWaterHeater()` (or add a new method), set appropriate `max_temp`,
     and handle any new modes
   - `mitsubishi_ae200.py`: Add any new attributes to the `getMnetDetails`
     query string if needed
   - `ADDING_DEVICE_TYPES.md`: Add your device to the table above
4. Send a PR to https://github.com/sftgunner/mitsubishi-ae200-integration

## Discovering Attributes

To explore what attributes a device supports, send a `getRequest` with
attributes set to `"*"`. The response will return values for known attributes
and `ERROR` entries for unknown ones:

```xml
<!-- Request -->
<Mnet Group="6" SomeAttr="*" AnotherAttr="*" />

<!-- Response includes both -->
<Mnet Group="6" SomeAttr="value" AnotherAttr="*" />
<ERROR Point="AnotherAttr" Code="0101" Message="Unknown Attribute" />
```
