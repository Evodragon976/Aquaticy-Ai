"""System-DNS mit Frist und einer festen Obergrenze haengender Aufloesungen."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TypeVar

_T = TypeVar("_T")
_SLOTS = threading.BoundedSemaphore(8)
TIMEOUT = 2.0


def call(function: Callable[..., _T], *args: object, timeout: float = TIMEOUT,
         **kwargs: object) -> _T:
    end = time.monotonic() + timeout
    if not _SLOTS.acquire(timeout=max(0, timeout)):
        raise TimeoutError("DNS ist ausgelastet.")
    done = threading.Event()
    values: list[_T] = []
    errors: list[BaseException] = []

    def work() -> None:
        try:
            values.append(function(*args, **kwargs))
        except BaseException as exc:
            errors.append(exc)
        finally:
            _SLOTS.release()
            done.set()

    try:
        threading.Thread(target=work, name="aquaticy-dns", daemon=True).start()
    except BaseException:
        _SLOTS.release()
        raise
    if not done.wait(max(0, end - time.monotonic())):
        raise TimeoutError("Die DNS-Auflösung hat zu lange gedauert.")
    if errors:
        raise errors[0]
    if not values:
        raise TimeoutError("Keine DNS-Antwort erhalten.")
    return values[0]
