"""What the services share: settings, the store, the pyright processes, and the lock."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from wayfinder.core.config import Settings
from wayfinder.services.driver_pool import DriverPool
from wayfinder.storage.repository import GraphRepository


@dataclass(frozen=True)
class ServiceContext:
    settings: Settings
    store: GraphRepository
    pool: DriverPool
    # The store and the pyright processes are single-threaded, and the API runs requests
    # on several threads, so every use of either happens while holding this lock. It is
    # never held across a model call (which takes seconds).
    lock: threading.Lock
