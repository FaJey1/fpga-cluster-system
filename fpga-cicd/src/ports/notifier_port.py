from abc import ABC, abstractmethod


class NotifierPort(ABC):
    @abstractmethod
    async def send_callback(self, url: str, payload: dict, secret: str) -> int:
        """Send signed callback. Returns HTTP status code."""
        ...
