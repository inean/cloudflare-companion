import argparse
import asyncio
from dataclasses import MISSING, dataclass, field, fields
from logging import Logger
from typing import Any

import dotenv

from dns_synchub.__about__ import __version__ as VERSION
from dns_synchub.mappers.cloudflare import CloudFlareMapper
from dns_synchub.pollers import Poller
from dns_synchub.pollers.docker import DockerPoller
from dns_synchub.pollers.traefik import TraefikPoller
from dns_synchub.settings import Settings


@dataclass
class Args:
    version: str = field(
        metadata={
            'help': 'Show program version',
            'action': 'version',
            'version': f'%(prog)s {VERSION}',
        }
    )
    env_file: str = field(metadata={'help': 'Path to the .env file', 'type': str})
    dry_run: bool = field(default=False, metadata={'help': 'Dry run mode', 'action': 'store_true'})


def parse_args() -> Args:
    parser = argparse.ArgumentParser(description='DNS SyncHub')

    # Iterate over the fields of the Args dataclass to populate the parser
    for field_info in fields(Args):
        name = field_info.name
        metadata = field_info.metadata
        default = field_info.default if field_info.default is not MISSING else None
        # Add the argument to the parser
        parser.add_argument(f'--{name.replace("_", "-")}', default=default, **metadata)

    args = parser.parse_args()
    dotenv.load_dotenv(args.env_file)

    # Return an instance of the custom TypedDict
    return Args(**vars(args))


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
