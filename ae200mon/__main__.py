"""Entry point for ae200mon: python -m ae200mon"""

import argparse
import asyncio
import logging

from .config import load_config
from .daemon import run


def main():
    parser = argparse.ArgumentParser(
        prog="ae200mon",
        description="Monitoring daemon for Mitsubishi AE-200 controllers.",
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to YAML config file (default: use env vars)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=getattr(logging, args.log_level),
    )

    config = load_config(args.config)
    asyncio.run(run(config))


if __name__ == "__main__":
    main()
