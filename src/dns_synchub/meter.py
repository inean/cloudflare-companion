import os
from sys import stderr
from typing import TYPE_CHECKING, Any, Literal, TypeAlias

try:
    from opentelemetry import metrics
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.metrics import Meter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import (
        ConsoleMetricExporter,
        PeriodicExportingMetricReader,
    )
    from opentelemetry.sdk.resources import Resource

    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False

    if not TYPE_CHECKING:
        Meter: TypeAlias = Any

        class NoOpMeter:
            def create_counter(self, *args, **kwargs):
                return self

            def create_histogram(self, *args, **kwargs):
                return self

            # counter methods
            def add(self, amount, attributes=None): ...

            # histogram methods
            def record(self, float): ...


class TelemetryMeter:
    has_run: bool = False

    def __init__(self, service_name: str, exporters: set[Literal['console', 'otlp']]):
        self.service_name = service_name
        self.exporters = exporters

        if OPENTELEMETRY_AVAILABLE and not self.has_run:
            self._init_meter()

    def _init_meter(self) -> None:
        # Define metric readers
        metric_readers = []

        # Console metrics exporter
        if 'console' in self.exporters:
            console_exporter = ConsoleMetricExporter(out=stderr)
            metric_readers.append(PeriodicExportingMetricReader(console_exporter))

        # OTLP metrics exporter
        if 'otlp' in self.exporters:
            if 'OTEL_EXPORTER_OTLP_ENDPOINT' not in os.environ:
                raise ValueError('OTEL_EXPORTER_OTLP_ENDPOINT environment variable not set')

            otlp_exporter = OTLPMetricExporter(insecure=True)
            metric_readers.append(PeriodicExportingMetricReader(otlp_exporter))

        # Set the global meter provider
        metrics.set_meter_provider(
            MeterProvider(
                resource=Resource.create({
                    'service.name': self.service_name,
                }),
                metric_readers=metric_readers,
            )
        )

    def get_meter(self, name: str = __name__) -> Meter:
        if not OPENTELEMETRY_AVAILABLE:
            if not TYPE_CHECKING:
                return NoOpMeter()
        return metrics.get_meter_provider().get_meter(name)


def telemetry_meter(
    service_name: str, exporters: set[Literal['console', 'otlp']]
) -> TelemetryMeter:
    return TelemetryMeter(service_name, exporters)
