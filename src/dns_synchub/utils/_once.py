from collections.abc import Callable
from threading import Lock
from typing import Any


class Once:
    def __init__(self) -> None:
        self._lock = Lock()
        self._done = False
        self._result = None

    def do_once(self, func: Callable[..., Any] | None) -> bool:
        """Execute the function only once. Returns True first time it's called, False otherwise."""
        with self._lock:
            if self._done:
                return False
            if callable(func):
                self._result = func()
            self._done = True
            return True

    @property
    def has_run(self) -> bool:
        return self._done

    @property
    def result(self) -> Any:
        if self.has_run:
            return self._result
        raise ValueError('Function has not run yet')
