import asyncio
import logging
import time
from typing import Any, Protocol


class BackoffInstance(Protocol):
    logger: logging.Logger
    config: dict[str, Any]


class BackoffError(Exception): ...


def async_backoff(func=None, *, backoff: int | None = None, attempts: int | None = None):
    def decorator(func):
        backoffs = {}

        async def async_wrapper(instance: BackoffInstance, *args, **kwargs):
            max_retries = attempts if attempts is not None else instance.config["max_retries"]
            backoff_time = backoff if backoff is not None else instance.config["backoff_factor"]

            backoffs.setdefault(
                instance,
                {
                    "retries": 0,
                    "max_retries": max_retries,
                    "last_call_time": 0,
                    "backoff_factor": backoff_time,
                },
            )
            state = backoffs[instance]
            try:
                # Fetch timers
                current_time = time.time()
                invoked_time = state["last_call_time"]
                backoff_wait = state["backoff_factor"] * (2 ** state["retries"])

                # If previous attempt was made, wait for backoff
                if invoked_time > 0 and current_time - invoked_time < backoff_wait:
                    backoff_wait = backoff_wait - (current_time - invoked_time)
                    instance.logger.info(f"Retrying in {int(backoff_wait)} seconds...")
                    await asyncio.sleep(backoff_wait)

                # invoke
                state["last_call_time"] = current_time
                response = func(instance, *args, **kwargs)
                state["retries"] = 0
            except BackoffError as err:
                state["retries"] += 1
                response = err.args[0]
            finally:
                return response

        return async_wrapper

    if callable(func):
        return decorator(func)

    return decorator
