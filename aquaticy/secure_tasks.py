"""Aufgaben fuer Secure Pro: "Melde dich, wenn ein neues Geraet ins Netz kommt".

Der Text wird fest ausgewertet, ohne Modell. So ist klar, was Secure Pro tut: Es meldet
sich, wenn das genannte Ereignis passiert. Eine Aufgabe kann nichts schalten, sperren
oder ausfuehren -- Abwehr braucht immer dein Ja im Secure-Pro-Chat.
"""

from __future__ import annotations

import ipaddress
import re
import secrets
from typing import Any

MAX_TASKS = 20

# Ereignis -> Beschreibung, wie sie in der Oberflaeche steht.
TRIGGERS: dict[str, str] = {
    "new_device": "Ein neues Gerät kommt ins Netz.",
    "device_offline": "Ein Gerät ist nicht mehr erreichbar.",
    "device_online": "Ein Gerät ist wieder erreichbar.",
    "new_port": "Ein Gerät öffnet einen neuen Dienst.",
    "malware": "Ein Malware-Verdacht taucht auf.",
    "vulnerability": "nmap findet eine Schwachstelle.",
    "attack": "Ein Angriff wird erkannt (Portscan, ARP-Spoofing, Passwort-Angriffe).",
    "any": "Es gibt einen neuen Prüfhinweis.",
}

_IP = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
_PORT = re.compile(r"\bport\s*(\d{1,5})\b", re.I)

# Reihenfolge zaehlt: das Genaueste zuerst.
_REGELN: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("malware", re.compile(r"malware|virus|viren|trojaner|schadsoftware|schadprogramm|"
                           r"miner|ransomware|erpress|hintert(?:ü|ue)r|backdoor|botnet",
                           re.I)),
    ("vulnerability", re.compile(r"schwachstelle|sicherheitsl(?:ü|ue)cke|\bl(?:ü|ue)cke|"
                                 r"\bcve\b|vulnerab|nmap", re.I)),
    ("attack", re.compile(r"angriff|attack|attacke|portscan|port-scan|\bscan\w*|spoof|"
                          r"eindring|hack|brute|passwort-?versuch|einbruch|intrusion",
                          re.I)),
    ("device_offline", re.compile(r"offline|nicht (?:mehr )?erreichbar|ausf(?:ä|ae)ll|"
                                  r"f(?:ä|ae)llt aus|ausgeht|verschwind|weg ist|goes down|"
                                  r"unreachable|stops? responding", re.I)),
    ("device_online", re.compile(r"wieder (?:da|online|erreichbar)|online geht|"
                                 r"angeschaltet|comes? (?:back|online)|back online", re.I)),
    ("new_port", re.compile(r"neue[rn]? (?:offene[rn]? )?(?:port|dienst)|port (?:öffnet|"
                            r"oeffnet|aufgeht)|(?:öffnet|oeffnet) .{0,20}port|new (?:open )?"
                            r"(?:port|service)|opens? .{0,20}port|\bport\s*\d{1,5}\b", re.I)),
    ("new_device", re.compile(r"neue[sr]? ger(?:ä|ae)t|neue ger(?:ä|ae)te|unbekannte[sr]? "
                              r"ger(?:ä|ae)t|fremde[sr]? ger(?:ä|ae)t|einlogg|ins (?:w?lan|"
                              r"netz|wlan)|verbindet sich|new device|unknown device|joins?|"
                              r"connects? to (?:the |my )?(?:network|wifi)", re.I)),
    ("any", re.compile(r"(?:jede[nrs]?|alle[n]?|irgendein\w*) (?:pr(?:ü|ue)fhinweis\w*|"
                       r"befund\w*|auff(?:ä|ae)llig\w*|ereignis\w*)|any (?:finding|event)|"
                       r"etwas auff(?:ä|ae)llig", re.I)),
)


def parse(text: str) -> dict[str, Any]:
    """Wertet eine Aufgabe aus.

    Raises:
        ValueError: Wenn der Text leer, zu lang oder nicht verstaendlich ist.
    """
    roh = " ".join(str(text or "").split())
    if not roh or len(roh) > 300 or not all(c.isprintable() for c in roh):
        raise ValueError("Beschreib die Aufgabe in einem Satz mit höchstens 300 Zeichen.")
    trigger = next((name for name, muster in _REGELN if muster.search(roh)), "")
    if not trigger:
        raise ValueError("Das verstehe ich nicht. Beispiele: „Melde dich, wenn ein neues "
                         "Gerät ins Netz kommt.“ „Sag Bescheid, wenn 192.168.1.20 offline "
                         "geht.“ „Melde jeden Malware-Verdacht.“")
    host = ""
    for treffer in _IP.findall(roh):
        try:
            adresse = ipaddress.IPv4Address(treffer)
        except ValueError:
            continue
        if not adresse.is_private:
            raise ValueError("Aufgaben gelten nur für Geräte in deinem Heimnetz.")
        host = str(adresse)
        break
    port = 0
    if (gefunden := _PORT.search(roh)) is not None:
        port = int(gefunden.group(1))
        if not 1 <= port <= 65535:
            raise ValueError("Ein Port liegt zwischen 1 und 65535.")
    if trigger in ("device_offline", "device_online") and not host:
        raise ValueError("Nenne die IP-Adresse des Geräts, zum Beispiel 192.168.1.20.")
    label = TRIGGERS[trigger]
    return {"id": secrets.token_hex(6), "text": roh, "trigger": trigger, "host": host,
            "port": port, "label": label}


def clean(tasks: Any) -> list[dict[str, Any]]:
    """Gespeicherte Aufgaben pruefen. Kaputte Eintraege fallen weg."""
    sauber: list[dict[str, Any]] = []
    if not isinstance(tasks, list):
        return sauber
    for eintrag in tasks[:MAX_TASKS]:
        if not isinstance(eintrag, dict):
            continue
        try:
            neu = parse(str(eintrag.get("text", "")))
        except ValueError:
            continue
        kennung = str(eintrag.get("id", ""))
        if re.fullmatch(r"[0-9a-f]{12}", kennung):
            neu["id"] = kennung
        sauber.append(neu)
    return sauber


def matches(task: dict[str, Any], event: dict[str, Any]) -> bool:
    """Passt ein Ereignis zu einer Aufgabe?"""
    trigger = task.get("trigger")
    art = event.get("kind")
    if task.get("host") and event.get("host") != task["host"]:
        return False
    if task.get("port") and int(event.get("port") or 0) != int(task["port"]):
        return False
    if trigger == "any":
        return True
    if trigger == "attack":
        return art in ("port_scan", "arp_spoof", "brute_force")
    if trigger == "malware":
        return art == "malware"
    if trigger == "new_port":
        return art in ("new_port", "risk_port")
    return bool(trigger == art)
