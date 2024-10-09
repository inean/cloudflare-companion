import logging
from typing import (
    Annotated,
    Literal,
    cast,
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
