# Helpers for built-in RackDash plugins.

from __future__ import annotations
import os
import time
from dataclasses import dataclass, field
from typing import Any


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


@dataclass
class TTLCache:
    seconds: int
    value: Any = None
    timestamp: float = field(default=0.0)

    def fresh(self) -> bool:
        return self.value is not None and (time.time() - self.timestamp) < self.seconds

    def get(self):
        return self.value if self.fresh() else None

    def set(self, value):
        self.value = value
        self.timestamp = time.time()
        return value
