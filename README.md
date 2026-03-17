# HomeAssistant - Mitsubishi AE200

Add support for Mitsubishi AE-200 air conditioner controller to HomeAssistant

This version forked from @natevoci's original integration (https://github.com/natevoci/ae200), and updated to work with newer HomeAssistant versions

## Installation

### Disclaimer

> :warning: This component is still in the alpha stage of development. It is highly likely that you will need to completely remove and reinstall this component in order to upgrade to the latest version, losing any entities defined in automations.

### Via HACS (preferred)

This component can be easily installed via the Home Assistant Community Store (HACS).

If you have not done so already, [follow the instructions to install HACS](https://hacs.xyz/docs/setup/download/) on your HomeAssistant instance.

Following that, [add this repository to the list of custom repositories in HACS](https://www.hacs.xyz/docs/faq/custom_repositories/), using the following url:

`https://github.com/sftgunner/mitsubishi-ae200-integration`

Then download the repo using HACS using the button below:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=sftgunner&repository=mitsubishi-ae200-integration&category=integration)


Then follow the steps in "Configuration" below.

### Configuration

Edit configuration.yaml and add below lines:

```
climate:
  - platform: mitsubishi_ae200
    controller_id: name_of_controller  # used as part of entity id's
    ip_address: "<ip_address>"
```

## Monitoring with Prometheus

This integration exposes health and error attributes that work well with Home Assistant's [Prometheus integration](https://www.home-assistant.io/integrations/prometheus/).

### Exposed attributes

Each climate and binary sensor entity includes:

- **`last_successful_poll`** — ISO 8601 timestamp of the last successful poll to the AE200 controller. Useful for detecting stale data.
- **`last_error_reason`** — Set when the controller is unreachable: `connection_refused`, `connection_timeout`, `invalid_response`, or a free-form error string. Cleared on successful poll.

The **Error Sign** binary sensor (`binary_sensor.*_error`) reflects the device's built-in `ErrorSign` attribute (`device_class: problem`). When `ON`, the HVAC unit is reporting a fault.

When the controller is unreachable, entities become **unavailable** — HA greys out the card and disables controls automatically.

### Prometheus scrape config

Add Home Assistant as a scrape target in your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: homeassistant
    scrape_interval: 60s
    metrics_path: /api/prometheus
    bearer_token: "<your_long_lived_access_token>"
    static_configs:
      - targets: ["homeassistant.local:8123"]
```

### Example alerting rules

```yaml
groups:
  - name: hvac
    rules:
      - alert: HVACControllerOffline
        expr: homeassistant_entity_available{entity=~"climate.mitsubishi.*"} == 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "AE200 controller offline for {{ $labels.friendly_name }}"

      - alert: HVACUnitFault
        expr: homeassistant_binary_sensor_state{entity=~"binary_sensor.mitsubishi.*error"} == 1
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "HVAC unit fault: {{ $labels.friendly_name }}"
```

- **`homeassistant_entity_available`** — `1` when the entity is available, `0` when the integration marks it unavailable (controller unreachable).
- **`homeassistant_binary_sensor_state`** — `1` when the error sign binary sensor is ON (unit fault), `0` when OFF.
