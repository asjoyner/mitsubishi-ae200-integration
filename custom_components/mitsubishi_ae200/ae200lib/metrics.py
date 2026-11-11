"""Prometheus metric definitions and updater for AE-200 devices."""

from prometheus_client import Gauge, Counter, Info

# -- Temperature gauges --
ae200_inlet_temperature_celsius = Gauge(
    "ae200_inlet_temperature_celsius",
    "Inlet (room) temperature in Celsius",
    ["controller", "group_id", "group_name"],
)
ae200_set_temperature_celsius = Gauge(
    "ae200_set_temperature_celsius",
    "SetTemp register in Celsius. NOT necessarily the setpoint the unit "
    "keeps: it accepts and echoes a write while the unit controls on the "
    "slot for its mode. Use ae200_effective_set_temperature_celsius for "
    "alerting and dashboards.",
    ["controller", "group_id", "group_name"],
)
ae200_effective_set_temperature_celsius = Gauge(
    "ae200_effective_set_temperature_celsius",
    "The setpoint the unit is actually controlling on: SetTemp1 in cooling "
    "modes, SetTemp2 in heating modes, SetTemp where neither applies",
    ["controller", "group_id", "group_name"],
)
ae200_set_temperature_slot_celsius = Gauge(
    "ae200_set_temperature_slot_celsius",
    "Per-mode setpoint slots in Celsius, active or not. The INACTIVE slot "
    "becomes the live setpoint on the next changeover, so a stale one is a "
    "latent fault.",
    ["controller", "group_id", "group_name", "slot"],
)
ae200_set_temperature_slot_active = Gauge(
    "ae200_set_temperature_slot_active",
    "1 for the slot the current mode controls on, 0 for the other",
    ["controller", "group_id", "group_name", "slot"],
)

# -- Water heater temperature gauges --
ae200_inlet_temp_hwhp_celsius = Gauge(
    "ae200_inlet_temp_hwhp_celsius",
    "Water heater inlet temperature in Celsius",
    ["controller", "group_id", "group_name"],
)
ae200_outlet_temp_hwhp_celsius = Gauge(
    "ae200_outlet_temp_hwhp_celsius",
    "Water heater outlet temperature in Celsius",
    ["controller", "group_id", "group_name"],
)
ae200_outdoor_temp_celsius = Gauge(
    "ae200_outdoor_temp_celsius",
    "Outdoor temperature in Celsius",
    ["controller", "group_id", "group_name"],
)

# -- State gauges --
ae200_drive_state = Gauge(
    "ae200_drive_state",
    "Drive state (1=ON, 0=OFF)",
    ["controller", "group_id", "group_name"],
)
ae200_error_sign = Gauge(
    "ae200_error_sign",
    "Error sign (1=error, 0=ok)",
    ["controller", "group_id", "group_name"],
)
ae200_filter_sign = Gauge(
    "ae200_filter_sign",
    "Filter sign (1=needs service, 0=ok)",
    ["controller", "group_id", "group_name"],
)

# -- Unit info --
ae200_unit_info = Info(
    "ae200_unit",
    "Unit metadata",
    ["controller", "group_id", "group_name"],
)

# -- Poll health --
ae200_poll_errors_total = Counter(
    "ae200_poll_errors_total",
    "Total poll errors",
    ["controller", "error_type"],
)
ae200_poll_duration_seconds = Gauge(
    "ae200_poll_duration_seconds",
    "Duration of last poll cycle in seconds",
    ["controller"],
)
ae200_last_poll_timestamp_seconds = Gauge(
    "ae200_last_poll_timestamp_seconds",
    "Unix timestamp of last successful poll",
    ["controller"],
)


def _set_gauge(gauge, labels, value):
    """Set a gauge value, skipping if value is None."""
    if value is not None:
        gauge.labels(*labels).set(value)


def update_metrics(controller_name: str, devices) -> None:
    """Update all Prometheus metrics from current device states."""
    for device in devices:
        labels = (controller_name, device.group_id, device.name)

        _set_gauge(ae200_inlet_temperature_celsius, labels, device.inlet_temp)
        _set_gauge(ae200_set_temperature_celsius, labels, device.set_temp)
        _set_gauge(
            ae200_effective_set_temperature_celsius, labels,
            device.effective_set_temp,
        )

        # Both slots, so a stale inactive one is visible before the mode
        # change that makes it the live setpoint.
        active_slot = device.set_temp_slot
        for slot, attr, value in (
            ("cool", "SetTemp1", device.set_temp1),
            ("heat", "SetTemp2", device.set_temp2),
        ):
            if value is None:
                continue
            slot_labels = labels + (slot,)
            ae200_set_temperature_slot_celsius.labels(*slot_labels).set(value)
            ae200_set_temperature_slot_active.labels(*slot_labels).set(
                1 if attr == active_slot else 0
            )

        # Water heater temps
        _set_gauge(ae200_inlet_temp_hwhp_celsius, labels, device.inlet_temp_hwhp)
        _set_gauge(ae200_outlet_temp_hwhp_celsius, labels, device.outlet_temp_hwhp)
        _set_gauge(ae200_outdoor_temp_celsius, labels, device.outdoor_temp)

        # State
        ae200_drive_state.labels(*labels).set(1 if device.drive == "ON" else 0)
        ae200_error_sign.labels(*labels).set(1 if device.error_sign == "ON" else 0)
        ae200_filter_sign.labels(*labels).set(1 if device.filter_sign == "ON" else 0)

        # Info
        ae200_unit_info.labels(*labels).info({
            "mode": device.mode,
            "model": device.model,
            "fan_speed": device.fan_speed,
            "air_direction": device.air_direction,
        })
