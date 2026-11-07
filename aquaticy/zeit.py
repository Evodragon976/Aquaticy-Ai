"""Deutsche Zeit (Europe/Berlin) mit Sommer- und Winterzeit -- egal, wo der Server laeuft (15.5.5).

Ein Server im Container laeuft meist auf UTC. Bis 15.4.5 rechneten Aquaticy und die Coworker mit
der Uhr des Servers: "jeden Tag um 8 Uhr" lief dann im Winter um 9 und im Sommer um 10 Uhr
deutscher Zeit, und das Modell kannte die Uhrzeit gar nicht. Hier steht die eine Stelle fuer
"jetzt in Deutschland". Die Umstellung (letzter Sonntag im Maerz und im Oktober) kommt aus der
Zeitzonen-Datenbank; fehlt die (manche Windows-Installationen), gilt dieselbe EU-Regel von Hand.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, tzinfo

_MEZ = timedelta(hours=1)
_MESZ = timedelta(hours=2)


def _letzter_sonntag(jahr: int, monat: int) -> date:
    tag = date(jahr, monat, 31)
    return tag - timedelta(days=(tag.weekday() + 1) % 7)


class _EURegel(tzinfo):
    """MEZ/MESZ nach EU-Regel: Umstellung um 01:00 UTC am letzten Sonntag im Maerz/Oktober."""

    def _sommer_utc(self, utc: datetime) -> bool:
        beginn = datetime.combine(_letzter_sonntag(utc.year, 3), datetime.min.time()) + \
            timedelta(hours=1)
        ende = datetime.combine(_letzter_sonntag(utc.year, 10), datetime.min.time()) + \
            timedelta(hours=1)
        return beginn <= utc.replace(tzinfo=None) < ende

    def utcoffset(self, dt: datetime | None) -> timedelta:
        if dt is None:
            return _MEZ
        # Wanduhrzeit -> UTC schaetzen (doppelte Stunde im Oktober: fold waehlt)
        als_sommer = dt.replace(tzinfo=None) - _MESZ
        als_winter = dt.replace(tzinfo=None) - _MEZ
        sommer = self._sommer_utc(als_sommer)
        winter = not self._sommer_utc(als_winter)
        if sommer and winter:
            return _MEZ if dt.fold else _MESZ
        return _MESZ if sommer else _MEZ

    def dst(self, dt: datetime | None) -> timedelta:
        return self.utcoffset(dt) - _MEZ

    def tzname(self, dt: datetime | None) -> str:
        return "CEST" if self.utcoffset(dt) == _MESZ else "CET"

    def fromutc(self, dt: datetime) -> datetime:
        utc = dt.replace(tzinfo=None)
        versatz = _MESZ if self._sommer_utc(utc) else _MEZ
        lokal = (utc + versatz).replace(tzinfo=self)
        if versatz == _MEZ and self._sommer_utc(utc - timedelta(hours=1)):
            lokal = lokal.replace(fold=1)
        return lokal


def _zone() -> tzinfo:
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("Europe/Berlin")
    except Exception:
        return _EURegel()


BERLIN: tzinfo = _zone()


def jetzt() -> datetime:
    """Jetzt in Deutschland, mit Zeitzone."""
    return datetime.now(UTC).astimezone(BERLIN)


def heute() -> date:
    return jetzt().date()


def aus_stempel(stempel: float) -> datetime:
    """Ein Unix-Zeitstempel als deutsche Uhrzeit."""
    return datetime.fromtimestamp(float(stempel), BERLIN)


def text(stempel: float | None = None, muster: str = "%d.%m.%Y %H:%M") -> str:
    """Formatiert einen Zeitstempel (oder jetzt) in deutscher Zeit."""
    return (aus_stempel(stempel) if stempel is not None else jetzt()).strftime(muster)


def sommerzeit(moment: datetime | None = None) -> bool:
    moment = moment or jetzt()
    return bool(moment.dst())


def kurz(moment: datetime | None = None) -> str:
    """"MESZ" im Sommer, "MEZ" im Winter."""
    return "MESZ" if sommerzeit(moment) else "MEZ"


def jahr() -> int:
    return heute().year
