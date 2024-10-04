from typing import TypeVar

T = TypeVar('T')


def getd(_optional: T | None, _default: T) -> T:
    return _optional if _optional is not None else _default
