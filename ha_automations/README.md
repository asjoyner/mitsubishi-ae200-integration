# Unified Climate Control for Mitsubishi AE-200

A single Home Assistant automation package that manages temperature, CO2
ventilation, and humidity control across all HVAC zones. Fan speed is
driven by the maximum demand across all subsystems, eliminating conflicts
between separate automations.

## Features

- **Temperature control**: Maintains target +-1F using explicit HEAT/COOL
  mode switching instead of the AE-200's built-in Auto dead band
- **CO2 ventilation**: Boosts fan speed and activates ERVs when CO2 > 800 ppm
- **Humidity control**: Manages whole-house humidifier and per-zone dehumidifiers
- **Graceful degradation**: Zones without CO2 sensors, ERVs, or
  humidifiers/dehumidifiers skip those subsystems automatically

## Prerequisites

- Mitsubishi AE-200 integration installed and configured
- SHT4x temperature/humidity sensors labeled by zone (e.g. `hvac-upstairs`)
- Optional: SCD4x CO2 sensors labeled by same zone labels
- Optional: ERV switches, humidifier switch, dehumidifier switches
- `climate_macros.jinja` in `/config/custom_templates/` (for zone average
  template sensors in `temphum.yaml`)

## Installation

1. Copy `climate_control.yaml` to your HA packages directory:

```bash
mkdir -p /var/lib/hass/config/packages/climate_control
cp climate_control.yaml /var/lib/hass/config/packages/climate_control/
```

2. Ensure your `configuration.yaml` loads packages:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

3. Remove the old automation entries from `temphum.yaml` (the 7 automations
   for humidifier, dehumidifiers, and CO2 ventilation). Keep all template
   sensors -- they are used by this automation and dashboards.

4. Restart Home Assistant.

5. Toggle `input_boolean.hvac_climate_control` ON to start.

## User Controls

| Entity | Default | Purpose |
|---|---|---|
| `input_boolean.hvac_climate_control` | OFF | Master enable/disable |
| `input_boolean.hvac_temp_control` | ON | Temperature control (requires master ON) |
| `input_number.hvac_target_temp` | 72 F | Target temperature |

### Behavior

- **Master OFF**: Nothing runs. Units stay at last-set state.
- **Master ON + Temp ON**: Full control. Temp + CO2 + humidity drive mode,
  setpoint, and fan speed.
- **Master ON + Temp OFF**: CO2 and humidity still run. Temperature falls
  back to AE-200 native Auto mode with target +-2F dead band.

## Zone Configuration

Edit the `zones` list in `climate_control.yaml` to match your setup. Each
zone needs:

- `name`: Display name
- `label`: HA device label for sensor discovery
- `climate`: Climate entity ID
- `avg_temp`: Template sensor for zone average temperature
- `fan_stages`: 3 or 4 (matches the unit's FanSpeedSW capability)
- `erv`: ERV switch entity or null
- `humidifier`: Humidifier switch entity or null
- `dehumidifier`: Dehumidifier switch entity or null
- `dehum_on_threshold`: Humidity % to turn dehumidifier ON (or null)
- `dehum_off_threshold`: Humidity % to turn dehumidifier OFF (or null)

## Fan Speed Logic

Fan speed = max(temperature_demand, co2_demand, humidity_demand)

Ordering: Auto < Low < High < Max

| Subsystem | Condition | Fan Level |
|---|---|---|
| Temperature (4-stage) | score < 1F | Auto |
| Temperature (4-stage) | 1-2F | Low |
| Temperature (4-stage) | 2-3F | High |
| Temperature (4-stage) | >= 3F | Max |
| CO2 | > 800 ppm | Max |
| CO2 | > 600 ppm | High |
| Humidity | humidifier/dehumidifier ON | Low |

Temperature score = max(setpoint_delta, intra_zone_spread).

## Verification

1. Enable `hvac_climate_control`, set target to 72F
2. Watch room temps converge to 71-73F within 1-2 hours
3. Check HA logbook: mode/setpoint/fan changes <= 1 per zone per minute
4. CO2 test: fan goes Max and ERV activates when CO2 > 800
5. CO2 recovery: fan returns to temperature-driven speed
6. Humidity: humidifier/dehumidifier activates at configured thresholds
7. Disable: units hold last state
