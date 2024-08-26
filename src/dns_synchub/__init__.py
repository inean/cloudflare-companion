from __future__ import annotations

import asyncio
import sys

from pydantic import ValidationError

import dns_synchub.cli as cli
import dns_synchub.logger as logger
import dns_synchub.settings as settings


def main():
    try:
        # Load environment variables from the specified env file
        cli.parse_args()

        # Load settings
        options = settings.Settings()

        # Check for uppercase docker secrets or env variables
        assert options.cf_token
        assert options.target_domain
        assert len(options.domains) > 0

    except ValidationError as e:
        print(f"Unable to load settings: {e}", file=sys.stderr)
        sys.exit(1)

    # Set up logging and dump runtime settings
    log = logger.report_current_status_and_settings(logger.get_logger(options), options)
    try:
        asyncio.run(cli.main(log, settings=options))
    except KeyboardInterrupt:
        # asyncio.run will cancel any task pending when the main function exits
        log.info("Cancel by user.")
        log.info("Exiting...")
        sys.exit(1)
