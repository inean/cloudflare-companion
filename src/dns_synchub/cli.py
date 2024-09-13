import argparse
import asyncio
from logging import Logger
from typing import Any

import dotenv

from dns_synchub.__about__ import __version__ as VERSION
from dns_synchub.mappers.cloudflare import CloudFlareMapper
from dns_synchub.pollers import Poller
from dns_synchub.pollers.docker import DockerPoller
from dns_synchub.pollers.traefik import TraefikPoller
from dns_synchub.settings import Settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Cloudflare Companion')
    parser.add_argument('--env-file', type=str, help='Path to the .env file')
    parser.add_argument('--version', action='version', version=f'%(prog)s {VERSION}')

    args = parser.parse_args()
    dotenv.load_dotenv(args.env_file)
    return args


async def main(log: Logger, *, settings: Settings) -> None:
    # Add Cloudflarte mapper
    dns = CloudFlareMapper(log, settings=settings)

    # Add Pollers
    pollers: list[Poller[Any]] = []
    if settings.enable_traefik_poll:
        pollers.append(TraefikPoller(log, settings=settings))
    if settings.enable_docker_poll:
        pollers.append(DockerPoller(log, settings=settings))

    # Start Pollers
    try:
        async with asyncio.TaskGroup() as tg:
            for poller in pollers:
                await poller.events.subscribe(dns)
                tg.create_task(poller.start())
    except asyncio.CancelledError:
        for poller in pollers:
            await poller.stop()
