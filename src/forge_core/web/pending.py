"""Estado in-memory do device flow, atado a um id opaco no cookie do navegador."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import time

from ..auth.github import DeviceCode


@dataclass
class PendingLogin:
    device: DeviceCode
    started: float
    last_poll: float
    interval: float


class PendingStore:
    def __init__(self, clock: Callable[[], float] | None = None):
        self._clock = clock or time.monotonic
        self._items: dict[str, PendingLogin] = {}

    def put(self, browser_id: str, pending: PendingLogin) -> None:
        self.purge()
        self._items[browser_id] = pending

    def get(self, browser_id: str) -> PendingLogin | None:
        return self._items.get(browser_id)

    def pop(self, browser_id: str) -> PendingLogin | None:
        return self._items.pop(browser_id, None)

    def purge(self) -> None:
        now = self._clock()
        dead = [
            key for key, item in self._items.items()
            if now >= item.started + item.device.expires_in
        ]
        for key in dead:
            self._items.pop(key, None)
