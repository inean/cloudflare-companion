from functools import lru_cache
import logging
import random
import string
import time

from dns_synchub.logger import telemetry_logger
from dns_synchub.meter import telemetry_meter
from dns_synchub.tracer import telemetry_tracer


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

    service_name = 'practice_service'

    # Set up logging
    practice_logger = logging.getLogger('yoda.practice')
    practice_logger.setLevel(logging.INFO)

    log_handler = telemetry_logger(service_name, exporters={'otlp_console', 'stderr'})
    practice_logger.addHandler(log_handler)
    stderr_handler = logging.StreamHandler()
    practice_logger.addHandler(stderr_handler)

    # Set up tracing
    tracer = telemetry_tracer(service_name, exporters={'console'}).get_tracer('practice_scope')
    # Set up metrics
    meter = telemetry_meter(service_name, exporters={'console'}).get_meter('practice_scope')

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
