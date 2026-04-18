"""Configuration loader for ae200mon (YAML file or env vars)."""

import os
from dataclasses import dataclass, field

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


@dataclass
class ControllerConfig:
    host: str
    name: str
    poll_interval: float = 10.0


@dataclass
class InfluxConfig:
    enabled: bool = False
    url: str = "http://localhost:8086"
    # v1 params
    database: str = "ae200"
    username: str = ""
    password: str = ""
    # v2 params
    token: str = ""
    org: str = ""
    bucket: str = ""


@dataclass
class MonitorConfig:
    metrics_port: int = 9200
    controllers: list[ControllerConfig] = field(default_factory=list)
    influx: InfluxConfig = field(default_factory=InfluxConfig)


def load_from_yaml(path: str) -> MonitorConfig:
    """Load config from a YAML file."""
    if not HAS_YAML:
        raise ImportError("PyYAML is required for config files. Install with: pip install pyyaml")
    with open(path) as f:
        data = yaml.safe_load(f)

    controllers = []
    for c in data.get("controllers", []):
        controllers.append(ControllerConfig(
            host=c["host"],
            name=c.get("name", c["host"]),
            poll_interval=c.get("poll_interval", 10.0),
        ))

    influx_data = data.get("influx", {})
    influx = InfluxConfig(
        enabled=influx_data.get("enabled", False),
        url=influx_data.get("url", "http://localhost:8086"),
        database=influx_data.get("database", "ae200"),
        username=influx_data.get("username", ""),
        password=influx_data.get("password", ""),
        token=influx_data.get("token", ""),
        org=influx_data.get("org", ""),
        bucket=influx_data.get("bucket", ""),
    )

    return MonitorConfig(
        metrics_port=data.get("metrics_port", 9200),
        controllers=controllers,
        influx=influx,
    )


def load_from_env() -> MonitorConfig:
    """Load single-controller config from environment variables."""
    host = os.environ.get("AE200_HOST")
    if not host:
        raise ValueError("AE200_HOST environment variable is required when not using a config file")

    controller = ControllerConfig(
        host=host,
        name=os.environ.get("AE200_NAME", host),
        poll_interval=float(os.environ.get("AE200_POLL_INTERVAL", "10")),
    )

    influx = InfluxConfig(
        enabled=bool(os.environ.get("AE200_INFLUX_URL")),
        url=os.environ.get("AE200_INFLUX_URL", "http://localhost:8086"),
        database=os.environ.get("AE200_INFLUX_DATABASE", "ae200"),
        username=os.environ.get("AE200_INFLUX_USERNAME", ""),
        password=os.environ.get("AE200_INFLUX_PASSWORD", ""),
        token=os.environ.get("AE200_INFLUX_TOKEN", ""),
        org=os.environ.get("AE200_INFLUX_ORG", ""),
        bucket=os.environ.get("AE200_INFLUX_BUCKET", ""),
    )

    return MonitorConfig(
        metrics_port=int(os.environ.get("AE200_METRICS_PORT", "9200")),
        controllers=[controller],
        influx=influx,
    )


def load_config(config_path: str | None = None) -> MonitorConfig:
    """Load config from YAML file if given, otherwise from env vars."""
    if config_path:
        return load_from_yaml(config_path)
    return load_from_env()
