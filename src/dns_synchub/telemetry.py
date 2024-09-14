import atexit
from functools import lru_cache
import logging
import os
from typing import TypedDict

from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter
from opentelemetry.sdk.resources import Resource
from typing_extensions import Unpack


# Define the ConfigType TypedDict with optional parameters
class _ConfigType(TypedDict): ...


class ConfigType(_ConfigType, total=False):
    service_id: str
    use_otlp_console_handler: bool
    use_otlp_handler: bool


@lru_cache
def telemetry_log_handler(service_name: str, **config: Unpack[ConfigType]) -> logging.Handler:
    # Set up a logging provider
    logger_provider = LoggerProvider(
        resource=Resource.create({
            'service.name': service_name,
            'service.instance.id': config.get('service_id', os.uname().nodename),
        }),
    )
    set_logger_provider(logger_provider)
    atexit.register(logger_provider.shutdown)

    # Configure ConsoleLogExporter
    if config.get('use_console_exporter', False):
        term_exporter = ConsoleLogExporter()
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(term_exporter))

    # Configure OTLPLogExporter
    if config.get('use_oltp_exporter', True):
        if 'OTEL_EXPORTER_OTLP_ENDPOINT' not in os.environ:
            raise ValueError('OTEL_EXPORTER_OTLP_ENDPOINT environment variable not set')
        otlp_exporter = OTLPLogExporter(insecure=True)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(otlp_exporter))

    # Set up a logging handler for standard Python logging
    return LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
