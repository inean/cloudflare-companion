import importlib
import os
from sys import stderr
from typing import Optional

from opentelemetry import metrics
from opentelemetry.metrics import Meter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource

from dns_synchub.telemetry import (
    TelementryExporters as Exporters,
    TelemetryEnv as Env,
    TelemetryEnvDefaults as Constants,
)
from dns_synchub.utils._once import Once


class _TelemetryMeter:
    _instance: Optional['_TelemetryMeter'] = None
    _set_once = Once()

    def __init__(self, service_name: str | None = None, exporters: set[str] | None = None):
        if service_name is None:
            service_name = os.environ.get(
                Env.OTEL_SERVICE_NAME,
                Constants.OTEL_SERVICE_NAME,
            )
        if exporters is None:
            exporters = set(
                os.environ.get(
                    Env.OTEL_METRICS_EXPORTER,
                    Constants.OTEL_METRICS_EXPORTER,
                ).split(',')
            )

        self.service_name = service_name
        self.exporters = exporters
        self._meter_provider = self._init_meter()

    def _init_meter(self) -> MeterProvider:
        # Define metric readers
        metric_readers = []

        # Console metrics exporter
        if Exporters.CONSOLE in self.exporters:
            console_exporter = ConsoleMetricExporter(out=stderr)
            metric_readers.append(PeriodicExportingMetricReader(console_exporter))

        # OTLP metrics exporter
        if Exporters.OTLP in self.exporters:
            otlp_modname = 'opentelemetry.exporter.otlp.proto.grpc.metric_exporter'
            if Env.OTEL_EXPORTER_OTLP_ENDPOINT not in os.environ:
                raise ValueError(f'{Env.OTEL_EXPORTER_OTLP_ENDPOINT} environment variable not set')
            try:
                otlp_exporter = importlib.import_module(otlp_modname)
            except ImportError as err:
                raise ImportError(
                    f'Missing "opentelemetry-exporter-otlp-proto-grpc" package. '
                    f'Use [otlp] optional feature or remove "{Exporters.OTLP}" '
                    f'from "{Env.OTEL_METRICS_EXPORTER}"'
                ) from err

            periodic_reader = PeriodicExportingMetricReader(
                otlp_exporter.OTLPMetricExporter(insecure=True)
            )
            metric_readers.append(periodic_reader)

        return MeterProvider(
            resource=Resource.create({'service.name': self.service_name}),
            metric_readers=metric_readers,
        )

    def get_meter(self, name: str = __name__) -> Meter:
        return metrics.get_meter_provider().get_meter(name)

    @property
    def meter_provider(self) -> MeterProvider:
        assert self._meter_provider is not None
        return self._meter_provider


def telemetry_meter(
    service_name: str | None = None, exporters: set[str] | None = None
) -> _TelemetryMeter:
    def set_tm() -> None:
        _TelemetryMeter._instance = _TelemetryMeter(service_name, exporters)
        metrics.set_meter_provider(_TelemetryMeter._instance.meter_provider)

    executed = _TelemetryMeter._set_once.do_once(set_tm)
    if service_name is not None and executed is False:
        raise RuntimeError('Overriding of current TracerProvider is not allowed')

    assert _TelemetryMeter._instance is not None
    return _TelemetryMeter._instance
