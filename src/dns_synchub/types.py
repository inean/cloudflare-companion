import asyncio
import logging
from abc import abstractmethod
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import (
    Annotated,
    Generic,
    Literal,
    Protocol,
    TypeVar,
    cast,
    runtime_checkable,
)

from pydantic import BaseModel, BeforeValidator


def validate_log_level(value: str | int) -> int:
    if isinstance(value, str):
        valid_str_levels = {'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'}
        if value.upper() not in valid_str_levels:
            raise ValueError(f'Invalid log level: {value}. Must be one of {valid_str_levels}.')
        return cast(int, getattr(logging, value.upper()))
    else:
        valid_int_levels = {
            logging.CRITICAL,
            logging.ERROR,
            logging.WARNING,
            logging.INFO,
            logging.DEBUG,
        }
        if value not in valid_int_levels:
            raise ValueError(f'Invalid log level: {value}. Must be one of {valid_int_levels}.')
        return value


class LogHandlerType:
    NONE = 'none'
    STDOUT = 'stdout'
    FILE = 'file'


LogLevelType = Annotated[int, BeforeValidator(validate_log_level)]


# Poller Types
PollerSourceType = Literal['manual', 'docker', 'traefik']

# Mapper Types
RecordType = Literal['A', 'AAAA', 'CNAME']


def validate_ttl(value: int | Literal['auto']) -> int | Literal['auto']:
    if isinstance(value, int) and value >= 30:
        return value
    if value == 'auto':
        return value
    raise ValueError("TTL must be at least 30 seconds or 'auto'")


TTLType = Annotated[int | str, BeforeValidator(validate_ttl)]


class Domains(BaseModel):
    name: str
    zone_id: str
    proxied: bool = True
    ttl: TTLType | None = None
    target_domain: str | None = None
    comment: str | None = None
    rc_type: RecordType | None = None
    excluded_sub_domains: list[str] = []

    def match(self, host: str) -> bool:
        return any(f'{sub_dom}.{self.name}' in host for sub_dom in self.excluded_sub_domains)


# Event Types
T = TypeVar('T')


@dataclass
class Event(Generic[T]):
    klass: type[T] = field(init=False)
    data: T

    def __post_init__(self) -> None:
        self.klass = type(self.data)


@runtime_checkable
class EventSubscriber(Protocol[T]):
    @abstractmethod
    async def __call__(self, event: Event[T]) -> None: ...


EventSubscriberType = Coroutine[None, None, None] | EventSubscriber[T]
EventSubscriberDataType = tuple[asyncio.Queue[Event[T]], float, float]
