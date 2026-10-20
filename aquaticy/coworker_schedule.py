"""Zeitplaene und Beobachtungen der Coworker (12.2.1 Luna).

Manche Fragen stellt man nicht einmal, sondern immer wieder -- "was ist in
meiner Branche passiert?", "gibt es Neues zu diesem Gesetz?". Ein Auftrag ist
genau das: eine gespeicherte Frage mit einem Rhythmus. Aquaticy stellt sie sich
selbst, recherchiert und legt die Antwort als Chat ab. Beim naechsten Oeffnen
steht sie in der Seitenleiste, als haette man sie selbst gestellt.

Zwei Entscheidungen, die den Rest erklaeren:

* **Ein eigener Agent je Lauf.** Ein Auftrag darf das laufende Gespraech nicht
  anfassen -- weder seinen Verlauf noch seine Einstellungen. Er baut sich also
  seinen eigenen Agenten, laesst ihn arbeiten und wirft ihn weg.
* **Verpasste Laeufe werden nicht nachgeholt.** Wer den Rechner eine Woche aus
  hat, will beim Einschalten nicht sieben Recherchen auf einmal. Der naechste
  Termin wird von jetzt an neu berechnet.
"""

from __future__ import annotations

import contextlib
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

LOG = logging.getLogger("aquaticy.coworker.schedule")

#: Recherchen laufen eher taeglich; eine Bild- oder Preisbeobachtung darf in
#: kurzen Abstaenden pruefen, damit ein voruebergehender Zustand nicht entgeht.
#: "always" heisst: beim naechsten Takt wieder, also durchgehend. Ein Lauf
#: dauert ohnehin laenger als ein Takt -- die Beobachtung faengt damit von
#: selbst wieder an, sobald sie fertig ist.
RHYTHMS = (
    "always", "minutes1", "minutes5", "minutes15", "minutes30",
    "hourly", "daily", "weekly",
)

#: Deutsche Namen fuer die Anzeige -- und fuer den Chat-Titel.
RHYTHM_NAMES = {
    "always": "die ganze Zeit",
    "minutes1": "jede Minute",
    "minutes5": "alle 5 Minuten",
    "minutes15": "alle 15 Minuten",
    "minutes30": "alle 30 Minuten",
    "hourly": "stündlich",
    "daily": "täglich",
    "weekly": "wöchentlich",
}

#: Wie oft nachgesehen wird, ob etwas ansteht. Zwanzig Sekunden, damit "die
#: ganze Zeit" auch wirklich durchgehend heisst und "jede Minute" seine Minute
#: trifft. Der Blick in die Datenbank kostet nichts; was Zeit kostet, ist der
#: Auftrag selbst -- und der laeuft nacheinander, nicht nebeneinander.
TICK_SECONDS = 20

#: Mehr Auftraege waeren keine Erleichterung mehr, sondern eine zweite
#: To-do-Liste, die man auch noch pflegen muss.
MAX_JOBS = 20

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    question   TEXT    NOT NULL,
    rhythm     TEXT    NOT NULL DEFAULT 'daily',
    hour       INTEGER NOT NULL DEFAULT 8,
    minute     INTEGER NOT NULL DEFAULT 0,
    weekday    INTEGER NOT NULL DEFAULT 0,
    enabled    INTEGER NOT NULL DEFAULT 1,
    structured INTEGER NOT NULL DEFAULT 1,
    created_at REAL    NOT NULL DEFAULT 0,
    next_run   REAL    NOT NULL DEFAULT 0,
    last_run   REAL    NOT NULL DEFAULT 0,
    last_state TEXT    NOT NULL DEFAULT '',
    last_chat  TEXT    NOT NULL DEFAULT ''
);
"""

MIGRATIONS = {
    "kind": "TEXT NOT NULL DEFAULT 'research'",
    "source_url": "TEXT NOT NULL DEFAULT ''",
    "image_id": "TEXT NOT NULL DEFAULT ''",
    # Was auf dem Bild zu sehen ist -- einmal vom Bildmodell beschrieben und
    # dann behalten. Das Foto aendert sich nicht; es bei jedem Lauf neu
    # anzusehen waere bei "jede Minute" eine Bildanfrage je Minute.
    "image_note": "TEXT NOT NULL DEFAULT ''",
}

#: Was ein Auftrag sein kann. "image" sucht nach dem Gegenstand auf einem
#: hochgeladenen Bild und meldet sich, sobald es dafuer ein Angebot gibt.
KINDS = ("research", "visual", "price", "image")

#: Auftragsarten, die erst dann einen Chat anlegen, wenn ihre Bedingung
#: eingetreten ist. Bis dahin laufen sie still.
MONITORING = ("visual", "price", "image")

#: Takte unter einer Stunde. Sie gibt es nur fuer Beobachtungen, die still
#: laufen, bis ihre Bedingung eintritt. Eine Recherche legt bei JEDEM Lauf
#: einen neuen Chat an -- "jede Minute" hiess bis 9.5.15 1.440 Chats am Tag,
#: bis der Speicher voll war. Recherchen laufen deshalb hoechstens stuendlich.
SHORT_RHYTHMS = frozenset({"always", "minutes1", "minutes5", "minutes15", "minutes30"})


def rhythm_for(kind: str, rhythm: str) -> str:
    """Der Takt, der fuer diese Auftragsart gilt (siehe SHORT_RHYTHMS)."""
    takt = clean_rhythm(rhythm)
    if str(kind or "research") not in MONITORING and takt in SHORT_RHYTHMS:
        return "hourly"
    return takt


#: Welche Auftraege gerade laufen: (Datenbank, Nummer). Planer und "Jetzt"-
#: Knopf fragen hier nach -- bis 9.5.15 konnte derselbe Auftrag doppelt laufen.
def claim_run(db_path: Any, job_id: int) -> bool:
    from aquaticy.coworker import claim

    return claim(db_path, job_id)


def release_run(db_path: Any, job_id: int) -> None:
    from aquaticy.coworker import release

    release(db_path, job_id)


#: Womit der Zustand eines Auftrags beginnt, den der Rechtsrahmen abgelehnt
#: hat. Solche Auftraege schaltet der Planer ab.
GUARD_STATE = "abgelehnt nach Rechtsrahmen"

#: Der Zustand eines Auftrags, dessen Konto sein Kontingent erreicht hat
#: (5-Stunden-Sitzung oder Woche, aquaticy/quota.py). Bis 9.5.13 galt ein
#: Limit fuer immer, und der Planer schaltete den Auftrag ab. Seit 9.5.14
#: setzt sich das Kontingent zurueck: der Auftrag bleibt an, dieser Termin
#: faellt aus, der naechste laeuft wieder.
TOKEN_LIMIT_STATE = "Kontingent erreicht"


def _number(value: str) -> float | None:
    """Eine Zahl aus einem Preis oder einer Preisgrenze.

    Der schwierige Fall ist ein einzelnes Trennzeichen: ``1.500`` heisst in
    Deutschland eintausendfuenfhundert, in England eins Komma fuenf. Hier
    entscheidet die Gruppengroesse -- genau drei Ziffern dahinter sind eine
    Tausendergruppe, alles andere sind Nachkommastellen. Preise haben nie
    drei Nachkommastellen, also ist das eindeutig genug. Eine fuehrende
    Null (``0.500``) bleibt ein Komma: Tausendergruppen fangen nicht mit
    einer allein stehenden Null an.
    """
    raw = re.sub(r"[^0-9,.]", "", str(value or ""))
    if not raw:
        return None
    if "," in raw and "." in raw:
        # Beide Zeichen da: das hintere trennt die Nachkommastellen.
        decimal = "," if raw.rfind(",") > raw.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        raw = raw.replace(thousands, "").replace(decimal, ".")
    elif "," in raw or "." in raw:
        trenner = "," if "," in raw else "."
        teile = raw.split(trenner)
        if len(teile[-1]) == 3 and teile[0] not in ("", "0"):
            raw = raw.replace(trenner, "")
        else:
            raw = "".join(teile[:-1]) + "." + teile[-1]
    try:
        return float(raw)
    except ValueError:
        return None


def price_condition_met(question: str, products: list[Any]) -> bool | None:
    """Evaluate common price limits from structured, page-derived product data."""
    # Seit 9.5.34: nur ganze Woerter ("Hunter 2" ist kein "unter 2"), und
    # keine Zahl mit Einheit ("bis 17 Zoll", "maximal 1 ms"). Steht irgendwo
    # ein Betrag mit Euro, gilt der; sonst der letzte.
    kandidaten = [
        m for m in re.finditer(
            r"\b(?:unter|weniger als|höchstens|maximal|bis)\s*(?:zu\s*)?([0-9][0-9.,]*)"
            r"(?:\s*(€|eur\b|euro\b|zoll\b|ms\b|hz\b|gb\b|tb\b|mb\b|kg\b|g\b|cm\b|mm\b|m\b|km\b|"
            r"l\b|w\b|kw\b|v\b|mah\b|jahre?\b|monate?\b|tage?\b|stunden?\b|minuten?\b|"
            r"personen\b|%|\"|''))?",
            question.lower())
    ]
    mit_euro = [m for m in kandidaten if m.group(2) in ("€", "eur", "euro")]
    ohne_einheit = [m for m in kandidaten if not m.group(2)]
    auswahl = mit_euro or ohne_einheit
    if not auswahl:
        return None
    match = auswahl[-1]
    limit = _number(match.group(1))
    prices = [_number(str(getattr(product, "price", "") or "")) for product in products]
    known = [price for price in prices if price is not None]
    if limit is None or not known:
        return None
    strict = "unter" in match.group(0) or "weniger als" in match.group(0)
    return any(price < limit if strict else price <= limit for price in known)


@dataclass(slots=True)
class Job:
    """Ein Auftrag, so wie er in der Datenbank steht."""

    id: int
    question: str
    rhythm: str
    hour: int
    minute: int
    weekday: int
    enabled: bool
    structured: bool
    created_at: float
    next_run: float
    last_run: float
    last_state: str
    last_chat: str
    kind: str = "research"
    source_url: str = ""
    image_id: str = ""
    image_note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "rhythm": self.rhythm,
            "rhythm_name": RHYTHM_NAMES.get(self.rhythm, self.rhythm),
            "hour": self.hour,
            "minute": self.minute,
            "weekday": self.weekday,
            "enabled": self.enabled,
            "structured": self.structured,
            "created_at": self.created_at,
            "next_run": self.next_run,
            "last_run": self.last_run,
            "last_state": self.last_state,
            "last_chat": self.last_chat,
            "kind": self.kind,
            "source_url": self.source_url,
            "image_id": self.image_id,
            "image_note": self.image_note,
        }


def clean_rhythm(value: str) -> str:
    wanted = (value or "").strip().lower()
    return wanted if wanted in RHYTHMS else "daily"


def next_time(rhythm: str, hour: int, minute: int, weekday: int, now: float = 0.0) -> float:
    """Wann der Auftrag das naechste Mal faellig ist.

    Gerechnet wird in Ortszeit: wer "jeden Morgen um acht" sagt, meint acht
    Uhr bei sich, nicht in UTC.
    """
    stempel = now or time.time()
    jetzt = datetime.fromtimestamp(stempel)
    rhythm = clean_rhythm(rhythm)
    hour = max(0, min(23, int(hour)))
    minute = max(0, min(59, int(minute)))

    # Durchgehend: schon der naechste Takt ist wieder faellig. Weil ein Lauf
    # laenger dauert als ein Takt, folgt der naechste erst, wenn der vorige
    # fertig ist -- die Beobachtung laeuft also am Stueck, ohne sich zu stapeln.
    if rhythm == "always":
        # Der Rohstempel, nicht der Umweg ueber datetime: der rundet auf
        # Mikrosekunden und kann dabei aufrunden -- dann waere "sofort" um
        # ein Haar in der Zukunft und der Auftrag bliebe einen Takt liegen.
        return stempel

    intervals = {"minutes1": 1, "minutes5": 5, "minutes15": 15, "minutes30": 30}
    if rhythm in intervals:
        return (jetzt + timedelta(minutes=intervals[rhythm])).replace(
            second=0, microsecond=0
        ).timestamp()

    if rhythm == "hourly":
        ziel = jetzt.replace(minute=minute, second=0, microsecond=0)
        if ziel <= jetzt:
            ziel += timedelta(hours=1)
        return ziel.timestamp()

    ziel = jetzt.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if rhythm == "daily":
        if ziel <= jetzt:
            ziel += timedelta(days=1)
        return ziel.timestamp()

    # wöchentlich: 0 = Montag, wie datetime.weekday()
    wunsch = max(0, min(6, int(weekday)))
    vorlauf = (wunsch - ziel.weekday()) % 7
    ziel += timedelta(days=vorlauf)
    if ziel <= jetzt:
        ziel += timedelta(days=7)
    return ziel.timestamp()


class JobStore:
    """Zeitplan-Ansicht auf den gemeinsamen Coworker-Speicher.

    Job bezeichnet hier einen einzelnen geplanten Arbeitsschritt. Es gibt
    weder eine zweite Tabelle noch einen eigenen Auftragsdienst.
    """

    def __init__(self, db_path: Path | str) -> None:
        from aquaticy.coworker import CoworkerStore

        self._store = CoworkerStore(db_path)
        self.db_path = self._store.db_path
        self._lock = self._store._lock

    def _connect(self) -> Any:
        return self._store._connect()

    @staticmethod
    def _row(cw: Any) -> Job:
        data = cw.schedule
        return Job(id=cw.id, question=cw.goal, rhythm=data["rhythm"],
                   hour=data["hour"], minute=data["minute"], weekday=data["weekday"],
                   enabled=cw.enabled, structured=data["structured"], created_at=cw.created_at,
                   next_run=cw.next_wake, last_run=cw.last_run, last_state=cw.last_state,
                   last_chat=cw.chat, kind=data["kind"], source_url=data["source_url"],
                   image_id=data["image_id"], image_note=data.get("image_note", ""))

    def all_jobs(self) -> list[Job]:
        return sorted((self._row(cw) for cw in self._store.all() if cw.schedule),
                      key=lambda job: job.next_run)

    def get(self, job_id: int) -> Job | None:
        cw = self._store.get(job_id)
        return self._row(cw) if cw is not None and cw.schedule else None

    def add(self, question: str, *, rhythm: str = "daily", hour: int = 8,
            minute: int = 0, weekday: int = 0, structured: bool = True,
            kind: str = "research", source_url: str = "", image_id: str = "") -> Job:
        schedule = clean_schedule(dict(rhythm=rhythm, hour=hour, minute=minute,
                                       weekday=weekday, structured=structured, kind=kind,
                                       source_url=source_url, image_id=image_id))
        cw = self._store.add(str(question)[:40], question, plan="normal", schedule=schedule)
        return self._row(cw)

    def set_enabled(self, job_id: int, enabled: bool) -> bool:
        return self._store.set_enabled(job_id, enabled) if self.get(job_id) else False

    def set_image_note(self, job_id: int, note: str) -> None:
        self._store.set_image_note(job_id, note)

    def delete(self, job_id: int) -> bool:
        return self._store.delete(job_id) if self.get(job_id) else False

    def due(self, now: float = 0.0) -> list[Job]:
        return [self._row(cw) for cw in self._store.due(now) if cw.schedule]

    def note_run(self, job_id: int, state: str, chat: str = "") -> None:
        cw = self._store.get(job_id)
        if cw is None or not cw.schedule:
            return
        data = cw.schedule
        self._store.note_run(job_id, state=state, notes=None,
                             next_wake=next_time(data["rhythm"], data["hour"],
                                                 data["minute"], data["weekday"]),
                             reason="Zeitplan", chat=chat)


def clean_schedule(raw: Any) -> dict[str, Any]:
    """Ein vollstaendiger, validierter Zeitplan; leeres Dict heisst selbststaendig."""
    if not isinstance(raw, dict):
        raise ValueError("Der Zeitplan muss ein Objekt sein.")
    if not raw:
        return {}
    kind = str(raw.get("kind") or "research").strip().lower()
    if kind not in KINDS:
        raise ValueError("Diese Art Beobachtung gibt es nicht.")
    source = str(raw.get("source_url") or "").strip()[:2000]
    image = str(raw.get("image_id") or "").strip()[:80]
    if kind == "image" and not image:
        raise ValueError("Für die Bildsuche fehlt das hochgeladene Bild.")
    if kind in ("visual", "price") and not source:
        raise ValueError("Eine Beobachtung braucht die öffentliche Quelladresse.")
    if source:
        try:
            parsed = urlsplit(source)
            if (parsed.scheme not in ("http", "https") or not parsed.hostname
                    or parsed.username or parsed.password or any(ord(c) < 33 for c in source)):
                raise ValueError
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("Die Quelladresse muss eine vollständige http(s)-Adresse sein.") \
                from exc
    return {"kind": kind, "rhythm": rhythm_for(kind, str(raw.get("rhythm") or "daily")),
            "hour": max(0, min(23, int(raw.get("hour", 8)))),
            "minute": max(0, min(59, int(raw.get("minute", 0)))),
            "weekday": max(0, min(6, int(raw.get("weekday", 0)))),
            "structured": raw.get("structured", True) is True, "source_url": source,
            "image_id": image, "image_note": str(raw.get("image_note") or "")[:6000]}


#: Woran ein gefundenes Angebot erkennbar ist: eine vollstaendige Adresse.
#: Ohne sie waere die Meldung "gefunden" ohne Nutzen -- und ohne Beleg.
OFFER_URL_RE = re.compile(r"https?://[^\s<>\]\)\"']{6,}")


#: Parameter, die nur sagen, WOHER jemand kam -- nie, WAS die Seite zeigt.
#: Sie stehen mal in der gelesenen Adresse und mal in der genannten; sie
#: deshalb fuer zwei verschiedene Seiten zu halten, verwirft echte Treffer.
TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "gclid", "gbraid", "wbraid", "fbclid", "msclkid", "igshid",
    "mc_cid", "mc_eid", "yclid", "dclid",
})


def _offer_identity(url: str) -> tuple[str, str, int, str, str] | None:
    """Vergleicht Webadressen inklusive Port; Fragmente sind keine andere Seite.

    Drei Dinge werden bewusst weggeraeumt, weil sie dieselbe Seite bezeichnen:
    das fuehrende ``www.`` (Shops leiten staendig zwischen beiden Formen um,
    und gespeichert wird die Adresse NACH der Umleitung), die Gross- und
    Kleinschreibung im Pfad, und Parameter, die nur die Herkunft zaehlen.
    Alles andere bleibt Unterschied: ``?id=1`` und ``?id=2`` sind zwei
    Produkte, nicht zwei Wege zu einem.
    """
    try:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https") or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        port = parsed.port
        host = parsed.hostname.lower().removeprefix("www.")
        felder = [
            (name, wert)
            for name, wert in parse_qsl(parsed.query, keep_blank_values=True)
            if name.lower() not in TRACKING_PARAMS
        ]
        return (
            scheme, host,
            port if port is not None else (443 if scheme == "https" else 80),
            parsed.path.rstrip("/").lower() or "/", urlencode(sorted(felder)),
        )
    except ValueError:
        return None


def verified_offer_url(text: str, sources: list[Any]) -> str:
    """Die genannte Angebotsadresse -- aber nur, wenn sie gelesen wurde.

    Geprueft wird die LETZTE Adresse im Text, nicht irgendeine. Das Modell
    wird angewiesen, Produktname, Haendler, Preis und dann die Adresse der
    Seite zu nennen; das Angebot steht also am Ende. Wer stattdessen die
    erste passende nimmt, laesst sich von einer nebenbei zitierten -- und
    tatsaechlich gelesenen -- Nachrichtenseite einen Fund vortaeuschen und
    schickt dem Nutzer einen Artikel statt eines Ladens.
    """
    read = set()
    for source in sources:
        url = source.get("url", "") if isinstance(source, dict) else getattr(source, "url", "")
        identity = _offer_identity(str(url or ""))
        if identity is not None:
            read.add(identity)
    genannt = [match.group(0).rstrip(".,;:") for match in OFFER_URL_RE.finditer(text or "")]
    if not genannt:
        return ""
    angebot = genannt[-1]
    return angebot if _offer_identity(angebot) in read else ""


def describe_job_image(agent: Any, job: Job, settings: Any) -> str:
    """Laesst das Vision-Modell beschreiben, was auf dem Auftragsbild liegt.

    Das Bild gehoert dem Konto und liegt in dessen Datenordner. Ohne
    ausdruecklich bildfaehiges Modell wird gar nicht erst gefragt: ein
    Textmodell wuerde die Datei nicht sehen, sondern raten.
    """
    from aquaticy.config import selected_vision_model
    from aquaticy.media import snapshot_path

    if not selected_vision_model(settings):
        return ""
    pfad = snapshot_path(settings.data_dir, job.image_id)
    if pfad is None:
        return ""
    try:
        return str(agent.describe_image(pfad) or "").strip()
    except Exception:
        return ""


def run_job(job: Job, settings: Any, on_abuse: Any = None, *,
            agent_factory: Any = None, context: str = "", active: Any = None,
            chat_id: str = "") -> tuple[str, str]:
    """Fuehrt einen Auftrag aus. Returns: (Zustand, Chat-Kennung).

    Der Agent ist ein eigener: das laufende Gespraech des Nutzers bleibt
    unberuehrt, und die Antwort landet als eigener Chat im Verlauf.

    Rueckfragen kann ein Auftrag nicht stellen -- es sitzt ja niemand davor.
    Der Agent bekommt deshalb keinen Rueckfrage-Empfaenger und muss mit dem
    auskommen, was in der Frage steht.
    """
    from aquaticy import metering
    from aquaticy.agent import Agent
    from aquaticy.cache import Cache
    from aquaticy.guardrails import UNAVAILABLE

    try:
        # Das Kontingent des Kontos (settings.quota) -- vor dem ersten Aufruf.
        metering.check(settings)
    except metering.QuotaExceeded:
        return (TOKEN_LIMIT_STATE, "")

    cache = Cache(settings.db_path, settings.cache_ttl_hours)
    monitoring = job.kind in MONITORING
    # Fehlversuche einer Beobachtung werden nicht als neue Chats gespeichert.
    def ereignis(name: str, payload: dict[str, Any]) -> None:
        # Missbrauch in einem Auftrag zaehlt bei Ai-guard wie im Chat (9.5.26) --
        # vorher lehnte der Rechtsrahmen ab, aber niemand vermerkte es.
        if name == "abuse" and on_abuse is not None:
            try:
                on_abuse(job, payload)
            except Exception:
                LOG.exception("Aufträge: Ai-guard-Meldung zu %s fehlgeschlagen", job.id)

    factory = agent_factory or Agent
    agent = factory(settings, cache=None if monitoring else cache)
    if chat_id:
        agent.session_id = chat_id
    if on_abuse is not None:
        agent.on_event = ereignis
    try:
        frage = job.question
        if job.kind == "image":
            # Einmal ansehen reicht: das Foto aendert sich nicht, und bei
            # "jede Minute" waere jede Minute eine Bildanfrage faellig.
            gesehen = job.image_note.strip()
            if not gesehen:
                gesehen = describe_job_image(agent, job, settings)
                if active is not None and not active():
                    return ("angehalten", "")
                if gesehen:
                    with contextlib.suppress(Exception):
                        JobStore(settings.db_path).set_image_note(job.id, gesehen)
            if not gesehen:
                return ("Bild nicht lesbar", "")
            wo = (
                f"\nSuche zuerst auf dieser Seite: {job.source_url}"
                if job.source_url
                else "\nSuche im offenen Web, bevorzugt bei bekannten Händlern und "
                     "Marktplaetzen."
            )
            frage = (
                "Dies ist eine automatische Suche nach einem Gegenstand, den der Nutzer "
                "fotografiert hat. Auf dem Bild ist zu sehen:\n" + gesehen
                + "\n\nFinde heraus, um welches Modell es sich handelt, und suche ein "
                  "aktuelles Angebot dafür." + wo
                + "\nZusaetzliche Bedingung des Nutzers: " + job.question
                + "\nDie erste Zeile muss exakt BEDINGUNG ERFÜLLT oder BEDINGUNG NICHT "
                  "ERFÜLLT lauten. Erfüllt ist sie nur, wenn du eine konkrete Angebots- "
                  "oder Produktseite wirklich geöffnet und gelesen hast. Nenne danach "
                  "Produktname, Händler, Preis und die vollständige Adresse der Seite. "
                  "Die Adresse der Angebotsseite steht als Letztes in deiner Antwort – "
                  "daran wird geprüft, ob du sie wirklich gelesen hast. "
                  "Rate nicht und erfinde keine Adresse."
            )
        if job.kind == "visual":
            frage = (
                "Dies ist eine automatische Beobachtung. Öffne zuerst mit "
                "inspect_public_visual genau diese öffentliche Quelle: " + job.source_url
                + "\nPrüfe nur diese Bedingung: " + job.question
                + "\nDie erste Zeile muss exakt BEDINGUNG ERFÜLLT oder BEDINGUNG NICHT ERFÜLLT "
                  "lauten. Danach beschreibe knapp das sichtbare Bild, die Quelle und das "
                  "Aufnahmedatum. Rate nicht."
            )
        elif job.kind == "price":
            frage = (
                "Dies ist eine automatische Preisbeobachtung. Öffne mit fetch_page genau "
                "diese öffentliche Produkt- oder Marktseite: " + job.source_url
                + "\nPrüfe diese Bedingung: " + job.question
                + "\nDie erste Zeile muss exakt BEDINGUNG ERFÜLLT oder BEDINGUNG NICHT ERFÜLLT "
                  "lauten. Verwende nur einen aktuell sichtbaren Preis, nenne Produkt, Preis, "
                  "Quelle und Prüfzeit. Rate nicht."
            )
        result = agent.ask(
            (context + "\n\n## Zeitplan: aktuelle Prüfung\n" if context else "") + frage,
            stream=False,
            mode="normal",
            structured=False if monitoring else job.structured,
            recheck=False,
            online=True if monitoring else None,
            visual_sources=True if job.kind == "visual" else None,
        )
        if active is not None and not active():
            return ("angehalten", "")
        antwort = str(getattr(result, "answer", "") or "").strip()
        chat = str(getattr(agent, "session_id", ""))
        if str(getattr(result, "error", "") or "") == UNAVAILABLE:
            # Nicht geprueft ist nicht abgelehnt: der Auftrag bleibt an und
            # versucht es beim naechsten Takt wieder.
            return (UNAVAILABLE, "")
        regel = str(getattr(result, "guarded", "") or "")
        if regel:
            # Dieselbe Frage wird beim naechsten Takt wieder abgelehnt. Der
            # Planer schaltet den Auftrag deshalb ab (siehe Scheduler) --
            # sonst liefe er ewig ins selbe Nein.
            return (f"{GUARD_STATE}: {regel}", "")
        if not antwort:
            return ("ohne Antwort", chat)
        if monitoring:
            first = antwort.splitlines()[0].strip(" *#`:\t").upper()
            matched = first.startswith("BEDINGUNG ERFÜLLT")
            if job.kind == "visual" and not getattr(result, "visuals", []):
                return ("kein Bild gefunden", "")
            if job.kind == "price":
                verified = price_condition_met(
                    job.question, list(getattr(result, "products", []) or [])
                )
                if verified is None:
                    return ("kein prüfbarer Preis gefunden", "")
                matched = verified
            # Gefunden heisst beim Bildauftrag: eine Seite gelesen UND eine
            # Adresse genannt. Ein Modell, das "ja, gibt es" schreibt, hat noch
            # nichts gefunden -- der Nutzer will den Laden, nicht die Zuversicht.
            if job.kind == "image" and not verified_offer_url(
                antwort, list(getattr(result, "sources", []) or [])
            ):
                return ("kein Angebot gefunden", "")
            if not matched:
                return ("noch nicht erfüllt", "")
            meta = result.meta() if hasattr(result, "meta") else {}
            checked = datetime.now().astimezone().isoformat(timespec="seconds")
            meta["monitor_checked_at"] = checked
            if agent_factory is not None:
                meta["coworker"] = job.id
            cache.add_history(chat, job.question, antwort, meta)
            with contextlib.suppress(Exception):
                cache.mark_unread(chat, reason="beobachtung")
            return ("erfüllt", chat)
        if agent_factory is not None:
            meta = result.meta() if hasattr(result, "meta") else {}
            meta["coworker"] = job.id
            cache.add_history(chat, job.question, antwort, meta)
        # Der Auftrag hat sich selbst gestellt -- oft nachts, jedenfalls ohne
        # dass jemand davorsitzt. Damit die Antwort nicht in der Liste
        # untergeht, leuchtet der Chat, bis ihn jemand geoeffnet hat.
        with contextlib.suppress(Exception):
            cache.mark_unread(chat, reason="auftrag")
        return ("fertig", chat)
    except Exception as exc:  # pragma: no cover - haengt am Modell
        return (f"Fehler: {type(exc).__name__}", "")
    finally:
        with contextlib.suppress(Exception):
            agent.close()


class Scheduler:
    """Interne Zeitplan-Ansicht desselben Coworker-Taktgebers."""

    def __init__(self, settings_getter: Any, on_run: Any = None, paused: Any = None,
                 on_abuse: Any = None) -> None:
        from aquaticy.coworker import Scheduler as CoworkerScheduler

        self._scheduler = CoworkerScheduler(settings_getter, plan=lambda: "normal",
                                           paused=paused, on_abuse=on_abuse,
                                           on_run=on_run, scheduled_only=True)

    def start(self) -> None:
        self._scheduler.start()

    def stop(self) -> None:
        self._scheduler.stop()

    def tick(self) -> int:
        return self._scheduler.tick()
