"""Begrenzte Haus-Regeln und freiwilliger Kontext fuer Coworker (12.2.1 Terra)."""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any

NOTE_LIMITS = (6000, 12000, 24000)
AUTO_DOMAINS = frozenset({"light", "switch", "fan", "input_boolean", "media_player"})
AUTO_SERVICES = frozenset({"turn_on", "turn_off"})
MAX_CONTEXT = 8000
_FILLER = frozenset({"bitte", "jeden", "morgen", "meine", "meinen", "meiner", "meinem",
                     "halte", "aufgabe", "coworker", "etwas", "immer", "infos", "neues",
                     "wichtige", "wichtigen", "diese", "dieser", "dieses", "sowie", "wenn",
                     "dann", "kann", "soll", "recherchiere", "fasse", "zusammen", "mich",
                     "thema", "über", "sich", "auch", "with", "this", "that", "from"})


def connection_key(settings: Any) -> str:
    """Freigaben gelten nur fuer diese Verbindung, einschliesslich Tokenwechsel."""
    from aquaticy.homeassistant import normalize_url

    url = normalize_url(str(getattr(settings, "ha_url", "") or ""))
    token = str(getattr(settings, "ha_token", "") or "")
    if not url or not token or not getattr(settings, "ha_control", False):
        return ""
    return hashlib.sha256((url + "\x00" + token).encode()).hexdigest()


def permits(binding: str, arguments: dict[str, Any], settings: Any,
            *, ultra: bool) -> bool:
    """Die Haus-Regel erlaubt nur einzelne, risikoarme Ein-/Ausschaltaktionen.

    Keine Zusatzdaten, Zielgruppen, geschuetzten Bereiche oder anderen Dienste.
    Die unveraenderten HA-Pruefungen laufen danach zusaetzlich im Werkzeug.
    """
    from aquaticy.homeassistant import ENTITY_RE, PROTECTED_DOMAINS

    if not ultra or set(arguments) - {"domain", "service", "entity_id", "data"}:
        return False
    if arguments.get("data") not in (None, {}):
        return False
    entity = arguments.get("entity_id")
    domain, service = arguments.get("domain"), arguments.get("service")
    if (not isinstance(entity, str) or not isinstance(domain, str)
            or not isinstance(service, str) or domain not in AUTO_DOMAINS
            or service not in AUTO_SERVICES):
        return False
    if (not ENTITY_RE.fullmatch(entity) or not entity.startswith(domain + ".")
            or domain in PROTECTED_DOMAINS):
        return False
    current = connection_key(settings)
    return bool(current and binding) and hmac.compare_digest(binding, current)


def relevant_context(cw: Any, store: Any, settings: Any) -> str:
    """Begrenzte relevante Auszuege, ausschliesslich aus der Datenbank dieses Kontos."""
    if not cw.sharing_chats and not cw.sharing_coworkers:
        return ""
    words = {w.casefold() for w in re.findall(r"[^\W\d_]{4,}", cw.goal)} - _FILLER
    if not words:
        return ""
    candidates: list[tuple[int, str, str]] = []

    def consider(source: str, text: str) -> None:

        text = str(text or "")[:12000]
        from aquaticy.keyvault import scrub

        text = scrub(text, [str(getattr(settings, key, "") or "") for key in (
            "ha_token", "api_key", "storage_token", "google_client_secret", "github_token",
            "memory_key", "nvidia_nim_api_key", "mistral_api_key", "search_api_key")])
        text = re.sub(r"(?i)((?:password|passwort|token|api[_ -]?key|secret)\s*[:=]\s*)"
                      r"[^\s,;]+", r"\1[entfernt]", text)
        lower = text.casefold()
        matches = [word for word in words if word in lower]
        if not matches:
            return
        first = min(lower.index(word) for word in matches)
        start = max(0, first - 200)
        candidates.append((len(matches), source, text[start:start + 1200]))

    if cw.sharing_coworkers:
        for other in store.all():
            if other.id != cw.id and other.notes:
                consider(f"Coworker {other.name}", other.notes)
    if cw.sharing_chats:
        from aquaticy.cache import Cache

        cache = Cache(settings.db_path, settings.cache_ttl_hours)
        for entry in cache.recent_history(limit=60):
            if entry.session_id != cw.chat and not entry.meta.get("coworker"):
                consider(f"Chat {entry.session_id}, {entry.created_at:.0f}",
                         entry.question + "\n" + entry.answer)
    candidates.sort(key=lambda item: item[0], reverse=True)
    snippets = []
    known = set()
    for _, source, text in candidates:
        if text in known:
            continue
        known.add(text)

        snippets.append(f"Quelle: {source}\n--- Fremder Inhalt ---\n{text}\n--- Ende ---")
        if len(snippets) >= 6:
            break
    return "\n\n".join(snippets)[:MAX_CONTEXT]
