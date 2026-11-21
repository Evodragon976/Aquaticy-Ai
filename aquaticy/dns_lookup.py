"""System-DNS mit Frist und einer festen Obergrenze haengender Aufloesungen."""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from typing import TypeVar

_T = TypeVar("_T")
_SLOTS = threading.BoundedSemaphore(8)
TIMEOUT = 2.0
#: 16.4.7: hoechstens so viele laufende Aufloesungen je Domain (SEC-09 einer externen Pruefung).
JE_DOMAIN = 2
_LAUFEND: dict[str, int] = {}
_DOMAIN_FREI = threading.Condition()
_ZWEITE_EBENE = frozenset({"co", "com", "net", "org", "gov", "edu", "ac", "or", "ne", "go"})


def domain_schluessel(args: tuple[object, ...]) -> str:
    """Die Domain, nach der *args* fragt ("" = keine). Aus "a.b.example.co.uk" wird
    "example.co.uk", aus einer IP-Adresse die Adresse selbst."""
    if not args or not isinstance(args[0], (str, bytes)):
        return ""
    roh = args[0]
    name = (roh.decode("ascii", "replace") if isinstance(roh, bytes) else roh)
    name = name.strip().rstrip(".").lower()
    if not name or ":" in name or re.fullmatch(r"[\d.]+", name):
        return name
    teile = name.split(".")
    if len(teile) >= 3 and len(teile[-1]) == 2 and teile[-2] in _ZWEITE_EBENE:
        return ".".join(teile[-3:])
    return ".".join(teile[-2:])


def _domain_belegen(schluessel: str, end: float) -> bool:
    with _DOMAIN_FREI:
        if not _DOMAIN_FREI.wait_for(lambda: _LAUFEND.get(schluessel, 0) < JE_DOMAIN,
                                     timeout=max(0, end - time.monotonic())):
            return False
        _LAUFEND[schluessel] = _LAUFEND.get(schluessel, 0) + 1
        return True


def _domain_freigeben(schluessel: str) -> None:
    with _DOMAIN_FREI:
        rest = _LAUFEND.get(schluessel, 0) - 1
        if rest > 0:
            _LAUFEND[schluessel] = rest
        else:
            _LAUFEND.pop(schluessel, None)
        _DOMAIN_FREI.notify_all()


def call(function: Callable[..., _T], *args: object, timeout: float = TIMEOUT,
         **kwargs: object) -> _T:
    end = time.monotonic() + timeout
    # 16.4.7: Eine Domain mit langsamem DNS-Server belegt hoechstens JE_DOMAIN Plaetze. Vorher
    # konnte sie alle 8 halten, und fuer alle anderen ging kein DNS mehr.
    schluessel = domain_schluessel(args)
    if schluessel and not _domain_belegen(schluessel, end):
        raise TimeoutError("DNS für diese Domain ist ausgelastet.")
    if not _SLOTS.acquire(timeout=max(0, end - time.monotonic())):
        if schluessel:
            _domain_freigeben(schluessel)
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
            if schluessel:
                _domain_freigeben(schluessel)
            done.set()

    try:
        threading.Thread(target=work, name="aquaticy-dns", daemon=True).start()
    except BaseException:
        _SLOTS.release()
        if schluessel:
            _domain_freigeben(schluessel)
        raise
    if not done.wait(max(0, end - time.monotonic())):
        raise TimeoutError("Die DNS-Auflösung hat zu lange gedauert.")
    if errors:
        raise errors[0]
    if not values:
        raise TimeoutError("Keine DNS-Antwort erhalten.")
    return values[0]
