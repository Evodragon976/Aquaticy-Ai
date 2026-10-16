"""Systemauslastung und verfuegbare Modelle -- ohne Zusatzpakete.

Zwei Fragen beantwortet dieses Modul:

* **Wie ausgelastet ist der Rechner gerade?** Prozessor, Arbeitsspeicher,
  Platte, Grafikkarte. Alles aus Bordmitteln: unter Linux aus ``/proc``,
  sonst ueber ``os`` und ``shutil``. Was sich nicht ermitteln laesst, fehlt
  einfach -- geraten wird nichts.
* **Welche Modelle stehen zur Auswahl?** Die lokal installierten Ollama-
  Modelle und die Anbieter, fuer die ein Schluessel hinterlegt ist.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

#: Aquaticy ist auf zwei Anbieter spezialisiert: **NVIDIA NIM** und **Mistral**.
#:
#: Das ist eine Entscheidung, keine Sparmassnahme. Eine Liste mit dreizehn
#: Anbietern sieht grosszuegig aus, bedeutet aber dreizehnmal "irgendein
#: Standardmodell, ungetestet, mit unbekannten Grenzen". Zwei Anbieter kann
#: man kennen: welches Modell wofuer, wie schnell es antwortet, wie viele
#: Anfragen pro Minute es vertraegt -- und genau danach richtet sich Aquaticy
#: dann auch (siehe PROVIDER_LIMITS und `aquaticy/pace.py`).
#:
#: Lokale Modelle ueber Ollama bleiben davon unberuehrt: sie sind kein
#: Anbieter, sondern der Weg, ganz ohne einen auszukommen.
#:
#: Diese Texte liest der Nutzer -- hier gehoeren echte Umlaute hin, anders
#: als in Kommentaren und Codenamen.
PROVIDER_NOTES: dict[str, str] = {
    "nvidia_nim": "Offene Modelle bei NVIDIA, großzügiges Freikontingent (40 Anfragen/Minute)",
    "mistral": "Europäischer Anbieter, antwortet schnell, Server in der EU",
    "ollama_chat": "Läuft auf deinem Rechner: keine Kosten, nichts verlässt das Haus",
}

#: Wie ein Anbieter in der Auswahl heisst. "ollama_chat" sagt niemandem etwas.
PROVIDER_LABELS: dict[str, str] = {
    "nvidia_nim": "NVIDIA",
    "mistral": "Mistral",
    "ollama_chat": "lokal",
    "ollama": "lokal",
}

#: Das Arbeitspferd je Anbieter: gut genug fuer alles, was Aquaticy den ganzen
#: Tag tut -- recherchieren, lesen, zusammenfassen.
PROVIDER_MODELS: dict[str, str] = {
    "nvidia_nim": "nvidia_nim/meta/llama-3.3-70b-instruct",
    "mistral": "mistral/mistral-large-latest",
}

#: Das schnelle kleine Modell je Anbieter. Es macht die Arbeit, bei der es
#: auf Tempo ankommt und nicht auf Tiefe: die Vorpruefung vor jeder Frage,
#: die Planung -- und vor allem die Rechercheagenten, von denen es viele
#: gleichzeitig gibt. Ein 70B-Modell fuer "such mir die Oeffnungszeiten"
#: kostet Sekunden, die sich mit jedem Agenten summieren.
FAST_MODELS: dict[str, str] = {
    "nvidia_nim": "nvidia_nim/meta/llama-3.1-8b-instruct",
    "mistral": "mistral/mistral-small-latest",
}

#: Fuers Programmieren das jeweils staerkste Modell eines Anbieters -- dort,
#: wo es ein anderes ist als das Arbeitspferd.
CODING_MODELS: dict[str, str] = {
    "nvidia_nim": "nvidia_nim/qwen/qwen2.5-coder-32b-instruct",
    "mistral": "mistral/codestral-latest",
}

#: Grobe Rangfolge. Sie entscheidet, welcher der eingerichteten Anbieter im
#: Code- und im Pro-Modus zum Zug kommt. Mistral steht vorn, weil es
#: spuerbar schneller antwortet; wer es anders sieht, traegt unter
#: AQUATICY_CODE_MODEL sein Modell selbst ein.
CODING_ORDER: tuple[str, ...] = ("mistral", "nvidia_nim")

PROVIDER_KEYS: dict[str, str] = {
    "nvidia_nim": "NVIDIA_NIM_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}

#: Was der Anbieter vertraegt: (Anfragen je Minute, gleichzeitige Anfragen).
#:
#: Die vierzig Anfragen pro Minute bei NVIDIA sind der Grund, warum Aquaticy
#: dort "sehr sehr lange" gebraucht hat: vierundvierzig Agenten schicken
#: ihre Anfragen auf einmal los, die Haelfte kommt als 429 zurueck, jede
#: davon wird wiederholt -- und aus einer Recherche werden Minuten Wartezeit,
#: in denen nichts passiert. Aquaticy haelt das Mass jetzt selbst ein (siehe
#: `aquaticy/pace.py`): gleichmaessig verteilt statt in Wellen gegen die Wand.
#:
#: Wer einen groesseren Vertrag hat, hebt es mit AQUATICY_RPM und
#: AQUATICY_PARALLEL_CALLS an.
PROVIDER_LIMITS: dict[str, tuple[int, int]] = {
    "nvidia_nim": (40, 4),
    "mistral": (240, 8),
}


def provider_limits(provider: str) -> tuple[int, int]:
    """(Anfragen je Minute, gleichzeitige Anfragen) fuer einen Anbieter.

    Unbekannt heisst unbegrenzt: lokale Modelle und alles, was jemand von
    Hand eintraegt, drosselt Aquaticy nicht.
    """
    return PROVIDER_LIMITS.get(provider or "", (0, 0))


# ---------------------------------------------------------------------------
# Auslastung
# ---------------------------------------------------------------------------
def cpu_load() -> dict[str, Any]:
    """Prozessorlast als Anteil der verfuegbaren Kerne."""
    cores = os.cpu_count() or 1
    try:
        one_minute = os.getloadavg()[0]
    except (OSError, AttributeError):
        return {"cores": cores}  # Windows kennt keine Lastdurchschnitte
    return {
        "cores": cores,
        "load": round(one_minute, 2),
        "percent": min(100, round(one_minute / cores * 100)),
    }


def memory_use() -> dict[str, Any]:
    """Arbeitsspeicher in GB. Leer, wenn er sich nicht ermitteln laesst."""
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        values: dict[str, int] = {}
        for line in meminfo.read_text().splitlines():
            name, _, rest = line.partition(":")
            number = rest.strip().split(" ")[0]
            if number.isdigit():
                values[name] = int(number)
        total = values.get("MemTotal", 0) * 1024
        free = values.get("MemAvailable", values.get("MemFree", 0)) * 1024
        if total:
            return _memory_dict(total, total - free)

    # macOS und alles andere: sysconf kennt Seitenzahl und -groesse.
    try:
        total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return {}
    return {"total_gb": round(total / 1_000_000_000, 1)}


def _memory_dict(total: int, used: int) -> dict[str, Any]:
    return {
        "total_gb": round(total / 1_000_000_000, 1),
        "used_gb": round(used / 1_000_000_000, 1),
        "percent": round(used / total * 100) if total else 0,
    }


def disk_use(path: Path | str = "/") -> dict[str, Any]:
    """Plattenbelegung des Datentraegers, auf dem *path* liegt."""
    try:
        usage = shutil.disk_usage(str(path))
    except OSError:
        return {}
    return {
        "total_gb": round(usage.total / 1_000_000_000, 1),
        "used_gb": round(usage.used / 1_000_000_000, 1),
        "free_gb": round(usage.free / 1_000_000_000, 1),
        "percent": round(usage.used / usage.total * 100) if usage.total else 0,
    }


def gpu_use() -> dict[str, Any]:
    """Grafikkarte ueber nvidia-smi. Leer, wenn keine da ist."""
    if not shutil.which("nvidia-smi"):
        return {}
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    line = (out.stdout or "").strip().splitlines()
    if not line:
        return {}
    parts = [part.strip() for part in line[0].split(",")]
    if len(parts) < 4:
        return {}
    try:
        used, total, load = int(parts[1]), int(parts[2]), int(parts[3])
    except ValueError:
        return {}
    return {
        "name": parts[0],
        "used_gb": round(used / 1024, 1),
        "total_gb": round(total / 1024, 1),
        "percent": load,
        "memory_percent": round(used / total * 100) if total else 0,
    }


def snapshot(data_dir: Path | str | None = None) -> dict[str, Any]:
    """Alles auf einmal -- fuer die Anzeige in den Einstellungen."""
    return {
        "system": f"{platform.system()} {platform.machine()}",
        "python": platform.python_version(),
        "cpu": cpu_load(),
        "memory": memory_use(),
        "disk": disk_use(data_dir or Path.home()),
        "gpu": gpu_use(),
    }


# ---------------------------------------------------------------------------
# Auswahl der Modelle
# ---------------------------------------------------------------------------
#: Wie die Herkunft eines Modells in der Auswahl heisst (seit 9.5.14 Seashell).
SOURCE_LABELS: dict[str, str] = {"own": "Dein Schlüssel", "operator": "Gestellt"}


def key_origin(settings: Any, provider: str) -> str:
    """Wer den Schluessel fuer *provider* stellt: "own", "operator" -- oder "" (keiner).

    "own" heisst: der Schluessel steht im Schluesselbund DIESES Kontos
    (aquaticy/keyvault.py). "operator": der Betreiber hat einen (Umgebung des
    Servers). Ein eigener gewinnt -- damit sieht jedes Konto seine eigenen
    Modelle, und nur seine.
    """
    key_name = PROVIDER_KEYS.get(provider, "")
    if not key_name:
        return ""
    eigene: frozenset[str] = frozenset(getattr(settings, "own_key_names", ()) or ())
    schluessel = getattr(settings, "api_keys", {}) or {}
    if key_name in eigene and str(schluessel.get(key_name, "")).strip():
        return "own"
    if os.environ.get(key_name, "").strip() or str(schluessel.get(key_name, "")).strip():
        return "operator"
    return ""


def model_origin(settings: Any, model_id: str, fallback: str = "operator") -> str:
    """Wer DIESEN Aufruf bezahlt -- ``Settings.key_source``, sonst *fallback*.

    Genauer als :func:`key_origin`: ein Modell, das auf einem Server des
    Betreibers laeuft, ist gestellt, auch wenn das Konto einen Schluessel
    fuer den Anbieter hat.
    """
    quelle = getattr(settings, "key_source", None)
    try:
        return str(quelle(model_id)) if callable(quelle) else fallback
    except Exception:
        return fallback


#: Anbieter, bei denen LiteLLM die Zugangsdaten selbst aus der Umgebung liest --
#: ohne einen Schluessel namens <ANBIETER>_API_KEY.
_ZUGANG_AUS_UMGEBUNG: dict[str, tuple[str, ...]] = {
    "bedrock": ("AWS_ACCESS_KEY_ID", "AWS_PROFILE"),
    "sagemaker": ("AWS_ACCESS_KEY_ID", "AWS_PROFILE"),
    "vertex_ai": ("GOOGLE_APPLICATION_CREDENTIALS", "VERTEXAI_PROJECT"),
    "lm_studio": ("LM_STUDIO_API_BASE",),
}


def _ollama_liste(settings: Any, model_id: str) -> list[str]:
    from aquaticy.local_model import DEFAULT_OLLAMA_URL, installed_models

    basis_von = getattr(settings, "ollama_base", None)
    try:
        basis = (basis_von(model_id) if callable(basis_von)
                 else getattr(settings, "api_base", "") or DEFAULT_OLLAMA_URL)
        return installed_models(basis)
    except Exception:
        return []


def model_usable(settings: Any, model_id: str, installed: list[str] | None = None) -> bool:
    """Antwortet *model_id* gerade wirklich? (11.3.0 Luna)

    Die Modellauswahl zeigt nur noch, was beim Anklicken auch laeuft: ein
    lokales Modell, das in Ollama installiert ist, sonst eines mit Schluessel
    (eigener, gestellter, allgemeiner, der eines verknuepften Kontos) oder mit
    eingetragener Adresse (LM Studio, Proxy). Das voreingestellte Modell eines
    frischen Servers zaehlt nicht von selbst -- bis dahin stand zum Beispiel
    Mistral in der Liste, obwohl es keinen Mistral-Schluessel gab.

    Args:
        installed: die Liste von Ollama, wenn sie schon da ist. Sonst wird
            jetzt gefragt -- ein eben installiertes Modell zaehlt sofort.
    """
    from aquaticy.config import SPLIT_MODEL_ID, provider_of
    from aquaticy.local_model import is_installed, local_name

    model_id = str(model_id or "").strip()
    if not model_id or model_id == SPLIT_MODEL_ID:
        # Den Server-Verbund zeigt web.py selbst -- nur, solange er laeuft.
        return False
    name = local_name(model_id)
    if name:
        return is_installed(name, _ollama_liste(settings, model_id) if installed is None
                            else installed)
    provider = provider_of(model_id)
    if not provider:
        return False
    try:
        verknuepft = getattr(settings, "is_linked", None)
        if callable(verknuepft) and verknuepft(model_id):
            return True
        weg = getattr(settings, "route", None)
        if callable(weg) and weg(model_id)[0]:
            return True
        if PROVIDER_KEYS.get(provider):
            return bool(key_origin(settings, provider))
        schluessel = getattr(settings, "key_for", None)
        if callable(schluessel) and schluessel(model_id):
            return True
    except Exception:
        return False
    namen = _ZUGANG_AUS_UMGEBUNG.get(provider, (f"{provider.upper()}_API_KEY",))
    return any(os.environ.get(n, "").strip() for n in namen)


def _mit_herkunft(eintrag: dict[str, str], herkunft: str) -> dict[str, str]:
    eintrag["source"] = herkunft
    eintrag["source_label"] = SOURCE_LABELS.get(herkunft, "")
    return eintrag


def strongest_models(
    settings: Any, limit: int = 3, purpose: str = "work"
) -> list[dict[str, str]]:
    """Die staerksten erreichbaren Modelle -- das beste zuerst.

    Args:
        purpose: "code" nimmt je Anbieter das Modell fuers Programmieren
            (Codestral, Qwen-Coder), "work" das Arbeitspferd. Der Unterschied
            zaehlt: ein Code-Modell auf eine Recherchefrage anzusetzen ist
            genauso verkehrt wie umgekehrt.

    Die Rangfolge: ein von Hand eingetragenes Code-Modell schlaegt alles, dann
    kommen die eingerichteten Anbieter nach `CODING_ORDER`, danach die lokal
    installierten Modelle, das groesste zuerst -- bei Ollama ist die Groesse
    der beste Anhaltspunkt, den es ohne Messung gibt.

    Gebraucht wird die Liste im Code- und im Pro-Modus: dort soll man nicht
    aus allem waehlen koennen, sondern aus den staerksten. Ein schwaches
    Modell ist genau dort am teuersten.
    """
    from aquaticy.config import provider_of
    from aquaticy.local_model import DEFAULT_OLLAMA_URL, installed_models, model_size_gb

    ranked: list[dict[str, str]] = []

    def dazu(model_id: str, kind: str, note: str, herkunft: str = "operator") -> None:
        model_id = (model_id or "").strip()
        if not model_id or any(eintrag["id"] == model_id for eintrag in ranked):
            return
        access = getattr(settings, "model_access", None)
        if access is not None:
            try:
                access(model_id)
            except ValueError:
                return
        ranked.append(_mit_herkunft(
            {
                "id": model_id,
                "label": model_id.split("/", 1)[-1],
                "kind": kind,
                "note": note,
            },
            herkunft,
        ))

    wanted = str(getattr(settings, "code_model", "") or "").strip()
    # Nur wenn es auch antwortet (11.3.0 Luna): ein eingetragenes Modell ohne
    # Schluessel oder ein geloeschtes Ollama-Modell stand sonst ganz oben.
    if wanted and model_usable(settings, wanted):
        dazu(wanted, PROVIDER_LABELS.get(provider_of(wanted), "eigenes"), "von dir eingetragen",
             model_origin(settings, wanted))

    # Anbieter mit eigenem Schluessel zuerst: wer einen hinterlegt, will ihn
    # benutzen -- und ihn kostet das Modell das Kontingent nicht.
    anbieter = sorted(
        (p for p in CODING_ORDER if key_origin(settings, p)),
        key=lambda p: (key_origin(settings, p) != "own", CODING_ORDER.index(p)),
    )
    for provider in anbieter:
        key_name = PROVIDER_KEYS.get(provider, "")
        if not key_name:
            continue
        stark = (
            CODING_MODELS.get(provider) if purpose == "code" else ""
        ) or PROVIDER_MODELS.get(provider, "")
        dazu(
            stark,
            PROVIDER_LABELS.get(provider, provider),
            "Fürs Programmieren"
            if purpose == "code" and CODING_MODELS.get(provider) == stark
            else PROVIDER_NOTES.get(provider, "Über die Schnittstelle des Anbieters"),
            model_origin(settings, stark, key_origin(settings, provider)),
        )

    base = getattr(settings, "api_base", "") or DEFAULT_OLLAMA_URL
    try:
        local = installed_models(base)
    except Exception:
        local = []
    sized = sorted(
        ((model_size_gb(name, base) or 0.0, name) for name in local), reverse=True
    )
    for groesse, name in sized:
        dazu(
            f"ollama_chat/{name}",
            "lokal",
            f"{groesse:.0f} GB auf deinem Rechner" if groesse else "Läuft auf deinem Rechner",
        )

    return ranked[: max(1, int(limit))]


def strongest_model(settings: Any, purpose: str = "work") -> str:
    """Das staerkste Modell, das gerade erreichbar ist.

    Returns:
        Eine Modell-Kennung, oder "" wenn nichts Besseres zu finden war als
        das ohnehin eingestellte Modell.
    """
    beste = strongest_models(settings, limit=1, purpose=purpose)
    return beste[0]["id"] if beste else ""


def fast_model(settings: Any) -> str:
    """Das schnelle kleine Modell -- fuer Vorpruefung, Planung und Agenten.

    Es richtet sich nach dem HAUPTmodell: wer bei NVIDIA arbeitet, soll seine
    Agenten nicht bei Mistral laufen lassen (zwei Schluessel, zwei Grenzen,
    zwei Rechnungen). Gibt es zum Anbieter kein kleines Modell -- oder laeuft
    das Hauptmodell lokal --, bleibt es beim Hauptmodell.
    """
    from aquaticy.config import provider_of

    eigen = str(getattr(settings, "subagent_model", "") or "").strip()
    if eigen:
        return eigen
    return FAST_MODELS.get(provider_of(str(getattr(settings, "model", "") or "")), "")


def available_models(settings: Any) -> list[dict[str, str]]:
    """Alles, worauf sich gerade umschalten laesst.

    Zuerst die lokal installierten Ollama-Modelle, dann die Anbieter, fuer
    die ein Schluessel hinterlegt ist. Was keinen Schluessel hat, taucht nicht
    auf -- eine Auswahl, die beim Anklicken scheitert, hilft niemandem.
    """
    from aquaticy.config import provider_of
    from aquaticy.local_model import (
        DEFAULT_OLLAMA_URL,
        installed_models,
        is_installed,
        known_model,
        local_name,
    )

    found: list[dict[str, str]] = []
    current = getattr(settings, "model", "")
    base = getattr(settings, "api_base", "") or DEFAULT_OLLAMA_URL
    # Jedes Mal live gefragt: was eben mit `ollama pull` dazukam, steht sofort da.
    lokal = installed_models(base)
    for name in lokal:
        model = known_model(name)
        # `gemma3` eingestellt, `gemma3:latest` installiert: dasselbe Modell --
        # dann gilt die eingestellte Kennung, sonst waere nichts ausgewaehlt.
        gleich = local_name(current) and is_installed(local_name(current), [name])
        found.append(_mit_herkunft(
            {
                "id": current if gleich else f"ollama_chat/{name}",
                "label": name,
                "kind": "lokal",
                "note": model.note if model else "Läuft auf deinem Rechner",
            },
            "operator",
        ))

    # Eigene Schluessel zuerst (seit 9.5.14 Seashell): diese Modelle sieht nur
    # dieses Konto -- gestellte sieht jedes.
    anbieter = sorted(
        (p for p in PROVIDER_KEYS if key_origin(settings, p)),
        key=lambda p: key_origin(settings, p) != "own",
    )
    for provider in anbieter:
        herkunft = key_origin(settings, provider)
        model_id = PROVIDER_MODELS.get(provider, "")
        if not model_id:
            continue
        # Laeuft gerade ein anderes Modell dieses Anbieters, ist das gemeint --
        # ausser es ist das schnelle: dann blieb das grosse nicht mehr waehlbar
        # (bis 9.5.34 ging es nur ueber die Einstellungen zurueck).
        if provider_of(current) == provider and current != FAST_MODELS.get(provider, ""):
            model_id = current
        found.append(_mit_herkunft(
            {
                "id": model_id,
                "label": model_id.split("/", 1)[-1],
                "kind": PROVIDER_LABELS.get(provider, provider),
                "note": PROVIDER_NOTES.get(provider, "Über die Schnittstelle des Anbieters"),
            },
            model_origin(settings, model_id, herkunft),
        ))
        # Dazu das schnelle kleine Modell desselben Anbieters. Nicht jede
        # Frage braucht das Arbeitspferd -- wer vor allem Tempo will, waehlt
        # hier, und niemand muss dafuer eine Modell-ID von Hand eintippen.
        schnell = FAST_MODELS.get(provider, "")
        if schnell and schnell != model_id:
            found.append(_mit_herkunft(
                {
                    "id": schnell,
                    "label": schnell.split("/", 1)[-1],
                    "kind": PROVIDER_LABELS.get(provider, provider),
                    "note": "Klein und schnell: kurze Antworten in Sekunden",
                },
                model_origin(settings, schnell, herkunft),
            ))

    # Das laufende Modell gehoert in die Liste, auch wenn es sonst nirgends
    # auftaucht -- sonst steht die Auswahl auf nichts. Aber nur, wenn es auch
    # antwortet (11.3.0 Luna): das voreingestellte Mistral ohne Schluessel
    # oder ein geloeschtes Ollama-Modell gehoeren nicht zur Wahl.
    if (current and not any(item["id"] == current for item in found)
            and model_usable(settings, current, lokal)):
        provider = provider_of(current)
        herkunft = model_origin(settings, current)
        found.insert(
            0,
            _mit_herkunft(
                {
                    "id": current,
                    "label": current.split("/", 1)[-1],
                    "kind": PROVIDER_LABELS.get(provider, provider or "eigenes"),
                    "note": "Aktuell eingestellt",
                },
                herkunft,
            ),
        )
    return found
