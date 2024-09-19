from functools import lru_cache
import logging
import os
import random
import string
from sys import stderr
import time
from typing import NotRequired, TypedDict

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from typing_extensions import Unpack


class ConfigType(TypedDict):
    # Telemetry Settings
    service_id: NotRequired[str]

    # Telemetry Log Settings
    log_use_otlp_console_handler: NotRequired[bool]
    log_use_otlp_handler: NotRequired[bool]

    # Metrics Settings
    metrics_use_console_exporter: NotRequired[bool]
    metrics_use_otlp_exporter: NotRequired[bool]

    # Tracing Settings
    tracing_use_console: NotRequired[bool]
    tracing_use_otlp_exporter: NotRequired[bool]


@lru_cache
def _telemetry_resource(service_name: str, **config: Unpack[ConfigType]) -> Resource:
    return Resource.create({
        'service.name': service_name,
        'service.instance.id': config.get('service_id', f'{os.uname().nodename}[{os.getpid()}]'),
    })


@lru_cache
def telemetry_tracer(service_name: str, **config: Unpack[ConfigType]) -> TracerProvider:
    # Create a tracer provider
    tracer_provider = TracerProvider(resource=_telemetry_resource(service_name, **config))

    # Console span exporter
    if config.get('tracing_use_console', False):
        console_exporter = ConsoleSpanExporter(out=stderr)
        span_processor = BatchSpanProcessor(console_exporter)
        tracer_provider.add_span_processor(span_processor)

    # OTLP span exporter
    if config.get('tracing_use_otlp_exporter', True):
        if 'OTEL_EXPORTER_OTLP_ENDPOINT' not in os.environ:
            raise ValueError('OTEL_EXPORTER_OTLP_ENDPOINT environment variable not set')

        otlp_exporter = OTLPSpanExporter(insecure=True)
        span_processor = BatchSpanProcessor(otlp_exporter)
        tracer_provider.add_span_processor(span_processor)

    # Set the global tracer provider
    trace.set_tracer_provider(tracer_provider)
    return tracer_provider


@lru_cache
def telemetry_meter(service_name: str, **config: Unpack[ConfigType]) -> MeterProvider:
    # Define metric readers
    metric_readers = []

    # Console metrics exporter
    if config.get('metrics_use_console_exporter', False):
        console_exporter = ConsoleMetricExporter(out=stderr)
        metric_readers.append(PeriodicExportingMetricReader(console_exporter))

    # OTLP metrics exporter
    if config.get('metrics_use_otlp_exporter', False):
        if 'OTEL_EXPORTER_OTLP_ENDPOINT' not in os.environ:
            raise ValueError('OTEL_EXPORTER_OTLP_ENDPOINT environment variable not set')

        otlp_exporter = OTLPMetricExporter(insecure=True)
        metric_readers.append(PeriodicExportingMetricReader(otlp_exporter))

    meter_provider = MeterProvider(
        resource=_telemetry_resource(service_name, **config), metric_readers=metric_readers
    )

    metrics.set_meter_provider(meter_provider)
    return meter_provider


@lru_cache
def telemetry_log_handler(service_name: str, **config: Unpack[ConfigType]) -> logging.Handler:
    # Set up a logging provider
    logger_provider = LoggerProvider(resource=_telemetry_resource(service_name, **config))
    set_logger_provider(logger_provider)

    # Configure ConsoleLogExporter
    if config.get('log_use_otlp_console_handler', False):
        term_exporter = ConsoleLogExporter(out=stderr)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(term_exporter))

    # Configure OTLPLogExporter
    if config.get('log_use_otlp_handler', False):
        if 'OTEL_EXPORTER_OTLP_ENDPOINT' not in os.environ:
            raise ValueError('OTEL_EXPORTER_OTLP_ENDPOINT environment variable not set')
        otlp_exporter = OTLPLogExporter(insecure=True)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(otlp_exporter))

    # Set up a logging handler for standard Python logging
    return LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)


@lru_cache
def practice(how_long: float) -> bool:
    """
    This is the practice "The Telemetry" function.

    Args:
        how_long (int): Defines how to long to practice (in seconds).

    Returns:
        bool: True for successfully completed practice, False otherwise.
    """
    start_time = time.time()

    # Initialize telemetry components
    config = ConfigType(
        metrics_use_console_exporter=True,
        metrics_use_otlp_exporter=False,
        tracing_use_console=True,
        tracing_use_otlp_exporter=False,
        log_use_otlp_console_handler=True,
        log_use_otlp_handler=False,
    )
    service_name = 'practice_service'

    # Set up logging
    log_handler = telemetry_log_handler(service_name, **config)
    practice_logger = logging.getLogger('yoda.practice')
    practice_logger.setLevel(logging.INFO)
    practice_logger.addHandler(log_handler)

    # Set up tracing and metrics
    tracer = telemetry_tracer(service_name, **config).get_tracer(__name__)
    meter = telemetry_meter(service_name, **config).get_meter(__name__)

    # Define metrics
    practice_counter = meter.create_counter(
        name='practice_counter',
        description='Counts the number of practice attempts',
        unit='1',
    )
    practice_duration_histogram = meter.create_histogram(
        name='practice_duration',
        description='Records the duration of practice sessions',
        unit='s',
    )
    practice_error_counter = meter.create_counter(
        name='practice_errors',
        description='Counts the number of errors during practice',
        unit='1',
    )

    with tracer.start_as_current_span('practice_telemetry'):
        try:
            how_long_int = int(how_long)
            practice_logger.info(
                'Starting to practice The Telemetry for %i second(s)', how_long_int
            )
            practice_counter.add(1)
            while time.time() - start_time < how_long_int:
                next_char = random.choice(string.punctuation)
                print(next_char, end='', flush=True)
                time.sleep(0.5)
            practice_logger.info('Done practicing')
            practice_duration_histogram.record(time.time() - start_time)
        except ValueError as ve:
            practice_logger.error('I need an integer value for the time to practice: %s', ve)
            practice_error_counter.add(1)
            return False
        except Exception as e:
            practice_logger.error('An unexpected error occurred: %s', e)
            practice_error_counter.add(1)
            return False
    return True


if __name__ == '__main__':
    practice(10)
