"""Poll loop and HTTP metrics server for ae200mon."""

import asyncio
import logging
import signal
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from ae200lib.controller import AE200Controller
from ae200lib.metrics import (
    update_metrics,
    ae200_poll_duration_seconds,
    ae200_last_poll_timestamp_seconds,
    ae200_poll_errors_total,
)
from .config import MonitorConfig, ControllerConfig

_LOGGER = logging.getLogger(__name__)


def _make_handler(stop_event: asyncio.Event, loop: asyncio.AbstractEventLoop):
    """Create an HTTP handler class with access to the stop event."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/quitquitquit":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"bye\n")
                loop.call_soon_threadsafe(stop_event.set)
            elif self.path == "/metrics":
                output = generate_latest()
                self.send_response(200)
                self.send_header("Content-Type", CONTENT_TYPE_LATEST)
                self.end_headers()
                self.wfile.write(output)
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path == "/quitquitquit":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"bye\n")
                loop.call_soon_threadsafe(stop_event.set)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # suppress per-request logging

    return Handler


async def poll_loop(
    controller: AE200Controller,
    config: ControllerConfig,
    influx_writer=None,
) -> None:
    """Continuously poll a controller and update metrics."""
    _LOGGER.info("Starting poll loop for %s (%s) every %.0fs",
                 config.name, config.host, config.poll_interval)

    while True:
        start = time.monotonic()
        await controller.poll_all()
        duration = time.monotonic() - start

        devices = list(controller.devices.values())
        update_metrics(config.name, devices)
        ae200_poll_duration_seconds.labels(config.name).set(duration)
        ae200_last_poll_timestamp_seconds.labels(config.name).set(time.time())

        # Track errors
        for device in devices:
            if device.last_error:
                ae200_poll_errors_total.labels(config.name, device.last_error).inc()

        # Write to InfluxDB if configured
        if influx_writer:
            influx_writer.write_device_states(config.name, devices)

        _LOGGER.debug("Polled %s: %d devices in %.2fs", config.name, len(devices), duration)
        await asyncio.sleep(config.poll_interval)


async def run(config: MonitorConfig) -> None:
    """Start metrics server and poll loops for all controllers."""
    # Graceful shutdown event
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    # Start HTTP server (metrics + /quitquitquit)
    handler_class = _make_handler(stop, loop)
    httpd = HTTPServer(("", config.metrics_port), handler_class)
    http_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    http_thread.start()
    _LOGGER.info("HTTP server started on port %d (/metrics, /quitquitquit)", config.metrics_port)

    # Set up InfluxDB writer if configured
    influx_writer = None
    if config.influx.enabled:
        from ae200lib.influx import create_writer
        influx_writer = create_writer(
            url=config.influx.url,
            database=config.influx.database,
            username=config.influx.username,
            password=config.influx.password,
            token=config.influx.token,
            org=config.influx.org,
            bucket=config.influx.bucket,
        )

    # Create controllers and discover devices
    tasks = []
    for cc in config.controllers:
        controller = AE200Controller(cc.host)
        _LOGGER.info("Discovering devices on %s (%s)...", cc.name, cc.host)
        await controller.discover_devices()
        _LOGGER.info("Found %d devices on %s", len(controller.devices), cc.name)
        tasks.append(asyncio.create_task(poll_loop(controller, cc, influx_writer)))

    await stop.wait()
    _LOGGER.info("Shutting down...")
    httpd.shutdown()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    if influx_writer:
        influx_writer.close()
