#!/usr/bin/env python3

import asyncio
from logging import Logger
import pathlib
import re
import sys

from pydantic import ValidationError

import dns_synchub.cli as cli
import dns_synchub.logger as logger
import dns_synchub.settings as settings


def report_state(settings: settings.Settings) -> Logger:
    log = logger.initialize_logger(settings=settings)

    settings.dry_run and log.info(f'Dry Run: {settings.dry_run}')  # type: ignore
    log.debug(f'Default TTL: {settings.default_ttl}')
    log.debug(f'Refresh Entries: {settings.refresh_entries}')

    log.debug(f"Traefik Polling Mode: {'On' if settings.enable_traefik_poll else 'Off'}")
    if settings.enable_traefik_poll:
        if settings.traefik_poll_url and re.match(r'^\w+://[^/?#]+', settings.traefik_poll_url):
            log.debug(f'Traefik Poll Url: {settings.traefik_poll_url}')
            log.debug(f'Traefik Poll Seconds: {settings.traefik_poll_seconds}')
        else:
            settings.enable_traefik_poll = False
            log.error(f'Traefik polling disabled: Bad url: {settings.traefik_poll_url}')

    log.debug(f"Docker Polling Mode: {'On' if settings.enable_docker_poll else 'Off'}")
    log.debug(f'Docker Poll Seconds: {settings.docker_timeout_seconds}')

    for dom in settings.domains:
        log.debug(f'Domain Configuration: {dom.name}')
        log.debug(f'  Target Domain: {dom.target_domain}')
        log.debug(f'  TTL: {dom.ttl}')
        log.debug(f'  Record Type: {dom.rc_type}')
        log.debug(f'  Proxied: {dom.proxied}')
        log.debug(f'  Excluded Subdomains: {dom.excluded_sub_domains}')

    return log


def main() -> int:
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
        print(f'Unable to load settings: {e}', file=sys.stderr)
        return 1

    # Set up logging and dump runtime settings
    log = report_state(options)
    try:
        asyncio.run(cli.main(log, settings=options))
    except KeyboardInterrupt:
        # asyncio.run will cancel any task pending when the main function exits
        log.info('Cancel by user.')
        log.info('Exiting...')

    # Exit grqacefully
    return 0


if __name__ == '__main__':
    # If the script is run as a module, use the directory name as the script name
    script_name = pathlib.Path(sys.argv[0]).stem
    if sys.argv[0] == __file__:
        script_path = pathlib.Path(sys.argv[0])
        script_name = script_path.parent.name.replace('_', '-')
    # Set the script name to the first argument and invoke the main function
    sys.argv[0] = script_name
    sys.exit(main())
