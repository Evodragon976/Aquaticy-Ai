"""Modell und Arbeitsmodus je Messenger-Chat, unabhaengig von der Website."""

from __future__ import annotations

import re
from typing import Any

SWITCH_RE = re.compile(
    r"(?:wechs(?:le|el)(?:\s+bitte)?\s+(?:dein(?:en|es)?\s+)?(?:llm|modell)"
    r"|bitte\s+wechs(?:le|el)\s+(?:dein(?:en|es)?\s+)?(?:llm|modell))\s*[.!?]?",
    re.I,
)


def switch_request(text: str) -> bool:
    return SWITCH_RE.fullmatch(str(text).strip()) is not None


# Klartext statt Slash-Befehl (14.4.4): "Aquaticy, wechsel auf das Modell Qwen 3" macht dasselbe
# wie "/switch Qwen 3". Nur kurze Saetze, die mit der Bitte anfangen; alles andere beantwortet
# das Modell. Loeschen (/forget) gibt es bewusst nur als ausdruecklichen Befehl.
_BITTE = r"(?:(?:kannst|könntest|koenntest)\s+du\s+|bitte\s+)?"
_NATUERLICH: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(_BITTE + r"(?:wechs(?:le|el)n?|stell[e]?|schalte?|geh[e]?)\s+(?:bitte\s+)?"
                r"(?:auf|zu|zum|in)\s+(?:das\s+|dem\s+|den\s+)?(?:llm|modell|model)\s+"
                r"(?P<arg>.{2,60}?)(?:\s+um)?\s*[.!?]?$", re.I), "switch"),
    (re.compile(_BITTE + r"(?:nimm|nutze|verwende|benutze)\s+(?:bitte\s+)?(?:ab\s+jetzt\s+)?"
                r"(?:das\s+)?(?:llm|modell|model)\s+(?P<arg>.{2,60}?)\s*[.!?]?$", re.I),
     "switch"),
    (re.compile(_BITTE + r"(?:bitte\s+)?(?:auf|zu|zum)\s+(?:das\s+|dem\s+)?(?:llm|modell|model)\s+"
                r"(?P<arg>.{2,60}?)\s+(?:wechseln|umstellen|umschalten|gehen)\s*[.!?]?$", re.I),
     "switch"),
    (re.compile(r"(?:please\s+)?(?:switch|change)\s+(?:to\s+)?(?:the\s+)?model\s+(?:to\s+)?"
                r"(?P<arg>.{2,60}?)\s*[.!?]?$", re.I), "switch"),
    (re.compile(r"(?:please\s+)?use\s+(?:the\s+)?model\s+(?P<arg>.{2,60}?)\s*[.!?]?$", re.I),
     "switch"),
    (re.compile(_BITTE + r"(?:welches|was\s+für\s+ein)\s+(?:llm|modell)\s+(?:nutzt|benutzt|"
                r"verwendest|hast)\s+du(?:\s+gerade)?\s*\??$", re.I), "model"),
    (re.compile(_BITTE + r"(?:wechs(?:le|el)n?|schalte?|geh[e]?)\s+(?:bitte\s+)?(?:in\s+den|"
                r"auf\s+den|zum|auf|in)\s+pro(?:-?modus)?\s*[.!?]?$", re.I), "pro"),
    (re.compile(_BITTE + r"(?:wechs(?:le|el)n?|schalte?|geh[e]?)\s+(?:bitte\s+)?(?:in\s+den|"
                r"auf\s+den|zum|auf|in)\s+(?:normal(?:-?modus)?|normalen\s+modus)\s*[.!?]?$",
                re.I), "normal"),
    (re.compile(_BITTE + r"(?:setz[e]?|stell[e]?)\s+(?:den\s+|meinen\s+)?(?:ort|standort|"
                r"ortsfilter)\s+auf\s+(?P<arg>.{2,60}?)\s*[.!?]?$", re.I), "location"),
    (re.compile(_BITTE + r"(?:ortsfilter|standort|ort)\s+(?:aus|weg|aufheben|löschen)"
                r"\s*[.!?]?$", re.I), "location"),
    (re.compile(_BITTE + r"zeig[e]?\s+(?:mir\s+)?(?:meine\s+)?notizen\s*[.!?]?$", re.I),
     "notes"),
    (re.compile(_BITTE + r"was\s+weißt\s+du\s+(?:alles\s+)?über\s+mich\s*\??$", re.I),
     "memory"),
    (re.compile(_BITTE + r"zeig[e]?\s+(?:mir\s+)?(?:meine\s+)?(?:hochgeladenen\s+)?"
                r"(?:dateien|uploads)\s*[.!?]?$", re.I), "uploads"),
    (re.compile(_BITTE + r"(?:exportier[e]?|schick[e]?\s+mir)\s+(?:den\s+|unseren\s+)?"
                r"(?:verlauf|chat)\s*[.!?]?$", re.I), "export"),
    (re.compile(_BITTE + r"(?:fang\s+neu\s+an|neues\s+gespräch|neuer\s+chat|"
                r"vergiss\s+(?:dieses|unser)\s+gespräch)\s*[.!?]?$", re.I), "clear"),
)


def natural_command(text: str) -> tuple[str, str] | None:
    """Ein Satz, der einen Befehl meint -> ("befehl", "Argument"); sonst None."""
    roh = " ".join(str(text or "").split())
    if not roh or len(roh) > 120 or roh.startswith("/"):
        return None
    for muster, befehl in _NATUERLICH:
        treffer = muster.fullmatch(roh)
        if treffer:
            argument = (treffer.groupdict().get("arg") or "").strip(" \"'„“")
            return befehl, argument
    return None


def _name(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def command(name: str, argument: str, decision: Any, settings: Any,
            state: dict[str, Any], agent: Any) -> Any:
    from aquaticy.bridge import Expanded

    if name in {"quit", "exit", "q"}:
        state.clear()
        if agent:
            if hasattr(agent[0], "clear"):
                agent[0].clear()
            else:
                del agent[0].messages[1:]
        return "Gespräch beendet. Die nächste Nachricht startet im Normal-Modus."
    if name == "export":
        if not decision.selbst:
            return "Das geht nur in deinem eigenen Chat."
        messages = agent[0].messages[1:] if agent else []
        rows = [f"{m['role']}: {m['content']}" for m in messages
                if m.get("role") in {"user", "assistant"} and isinstance(m.get("content"), str)]
        text = "\n\n".join(rows)
        if not text:
            return "Noch kein Gespräch zum Exportieren."
        match = re.fullmatch(r"(?:html|md|csv)?\s*(?:seite ([0-9]{1,4}))?",
                             argument.casefold())
        if match is None:
            return "Verlauf als Text: /export oder /export seite 2."
        pages = [text[i:i + 1400] for i in range(0, len(text), 1400)]
        page = min(len(pages) - 1, max(0, int(match.group(1) or 1) - 1))
        return pages[page] + (f"\nSeite {page + 1}/{len(pages)}. Weitere: /export seite "
                              f"{(page + 1) % len(pages) + 1}" if len(pages) > 1 else "")
    if not decision.trusted:
        return "Das geht nur in deinem eigenen Chat oder für freigegebene Nummern."
    if name == "switch":
        from aquaticy.system import available_models

        try:
            models = available_models(settings)
        except Exception:
            return "Die Modelle sind gerade nicht erreichbar. Versuch /switch gleich noch einmal."
        models = [m for m in models if m.get("id") and m.get("label")]
        page_match = re.fullmatch(r"seite ([0-9]{1,4})", argument.casefold())
        if argument and not page_match:
            matches = [m for m in models if m["id"].casefold() == argument.casefold()]
            if not matches:
                matches = [m for m in models if _name(argument) in {
                    _name(m["label"]), _name(m["id"].split("/", 1)[-1])}]
            if not matches:
                matches = [m for m in models if _name(argument) == _name(re.sub(
                    r"(?<=[a-z])\d+(?:\.\d+)*(?=[:\-])", "", m["label"].casefold()))]
            if len(matches) == 1:
                from aquaticy.config import model_problem

                model = matches[0]["id"]
                if model_problem(model, settings.route(model)[0]):
                    return "Dieses Modell kann hier nicht verwendet werden. Wähle /switch erneut."
                state["model"] = matches[0]["id"]
                return f"Modell für diesen Chat: {matches[0]['id']}.\nWechseln: /switch Modell"
            prefix = "Modell nicht eindeutig oder nicht verfügbar.\n"
        else:
            prefix = "Verfügbare Modelle:\n"
        page = max(0, int(page_match.group(1)) - 1) if page_match else 0
        chunks: list[list[str]] = [[]]
        for m in models:
            row = f"• {m['label']}: /switch {m['id']}"
            if len(row) > 450:
                continue
            if sum(len(r) + 1 for r in chunks[-1]) + len(row) > 1050:
                chunks.append([])
            chunks[-1].append(row)
        page = min(page, len(chunks) - 1)
        listing = "\n".join(chunks[page])
        if len(chunks) > 1:
            listing += (f"\nSeite {page + 1}/{len(chunks)}. Weitere: /switch seite "
                        f"{(page + 1) % len(chunks) + 1}")
        return prefix + (listing or "Keine Modelle erreichbar.") + (
            "\nWechseln kannst du mit /switch und dem Modellnamen, z. B. /switch Qwen 7b.")
    if name == "normal" or (name == "pro" and argument.casefold() in {"aus", "off", "0"}):
        state["pro"] = False
        return "Normal-Modus: höchstens vier Rechercheagenten, ohne Strukturieren und Gegenprüfen."
    state["pro"] = True
    if name == "max":
        return Expanded("/max " + argument) if argument else "Schreib die Frage hinter /max."
    return "Pro-Modus für diesen Chat: Mannschaft, Strukturieren und Gegenprüfen sind aktiviert."
