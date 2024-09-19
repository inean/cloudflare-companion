from functools import lru_cache
import logging
import os
import sys
from sys import stderr

from dns_synchub.settings import Settings
from dns_synchub.types import LogHandlersType

try:
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter
    from opentelemetry.sdk.resources import Resource

    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False


def telemetry_logger(service_name: str, *, exporters: set[LogHandlersType]) -> logging.Handler:
    if not OPENTELEMETRY_AVAILABLE:
        return logging.NullHandler()

    # Set up a logging provider
    logger_provider = LoggerProvider(
        resource=Resource.create({
            'service.name': service_name,
        })
    )
    set_logger_provider(logger_provider)

    # Configure ConsoleLogExporter
    if 'otlp_console' in exporters:
        term_exporter = ConsoleLogExporter(out=stderr)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(term_exporter))

    # Configure OTLPLogExporter
    if 'otlp' in exporters:
        if 'OTEL_EXPORTER_OTLP_ENDPOINT' not in os.environ:
            raise ValueError('OTEL_EXPORTER_OTLP_ENDPOINT environment variable not set')
        otlp_exporter = OTLPLogExporter(insecure=True)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(otlp_exporter))

    # Set up a logging handler for standard Python logging
    return LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)


@lru_cache
def console_log_handler(*, formatter: logging.Formatter) -> logging.Handler:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    return handler


@lru_cache
def file_log_handler(filename: str, *, formatter: logging.Formatter) -> logging.Handler:
    try:
        handler = logging.FileHandler(filename)
        handler.setFormatter(formatter)
    except OSError as err:
        logging.critical(f"Could not open log file '{err.filename}': {err.strerror}")
    return handler


# set up logging
@lru_cache
def initialize_logger(settings: Settings) -> logging.Logger:
    # Set up logging
    logger = logging.getLogger(settings.service_name)

    # remove all existing handlers, if any
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Set the log level
    logger.setLevel(settings.log_level)

    # Set up  console logging
    if 'stderr' in settings.log_handlers:
        handler = console_log_handler(formatter=settings.log_formatter)
        logger.addHandler(handler)

    # Set up file logging
    if 'file' in settings.log_handlers:
        handler = file_log_handler(settings.log_file, formatter=settings.log_formatter)
        logger.addHandler(handler)

    # Set up telemetry
    if OPENTELEMETRY_AVAILABLE:
        handler = telemetry_logger(settings.service_name, exporters=settings.log_handlers)
        logger.addHandler(handler)

    return logger


def get_logger(name: str | Settings) -> logging.Logger:
    if isinstance(name, str):
        return logging.getLogger(name)
    logger = logging.getLogger(name.service_name)
    initialize_logger(name)
    return logger
