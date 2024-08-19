from __future__ import annotations

import argparse
import asyncio
import sys

import dns_synchub.logger as logger
from .__about__ import __version__ as VERSION
from dotenv import load_dotenv
from pydantic import ValidationError
from .settings import Settings


import dns_synchub.cli as cli


def parse_args():
    parser = argparse.ArgumentParser(description="Cloudflare Companion")
    parser.add_argument("--env-file", type=str, help="Path to the .env file")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return parser.parse_args()


def main():
    try:
        # Load settings
        args = parse_args()
        # Load environment variables from the specified env file
        args.env_file and load_dotenv(args.env_file)

        settings = Settings()

        # Check for uppercase docker secrets or env variables
        assert settings.cf_token
        assert settings.target_domain
        assert len(settings.domains) > 0

    except ValidationError as e:
        print(f"Unable to load settings: {e}", file=sys.stderr)
        sys.exit(1)

    # Set up logging and dump runtime settings
    log = logger.report_current_status_and_settings(logger.get_logger(settings), settings)
    try:
        asyncio.run(cli.main(log, settings=settings))
        # asyncio.run(legacy_main(log, settings=settings))
    except KeyboardInterrupt:
        # asyncio.run will cancel any task pending when the main function exits
        log.info("Cancel by user.")
        log.info("Exiting...")
        sys.exit(1)
