from typing import Any

class CloudFlare:
    def __init__(self, token: str, debug: bool = False) -> None: ...

    class zones:
        class dns_records:
            @staticmethod
            def get(zone_id: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]: ...
            @staticmethod
            def post(zone_id: str, data: dict[str, str]) -> dict[str, Any]: ...
            @staticmethod
            def put(zone_id: str, record_id: str, data: dict[str, str]) -> dict[str, Any]: ...

__all__ = ['CloudFlare']
