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
import re
import shutil
import subprocess
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

PROVIDER_NOTES: dict[str, str] = {
    "nvidia_nim": "Offene Modelle bei NVIDIA, großzügiges Freikontingent (40 Anfragen/Minute)",
    "mistral": "Europäischer Anbieter, antwortet schnell, Server in der EU",
    "ollama_chat": "Läuft auf deinem Rechner: keine Kosten, nichts verlässt das Haus",
}


PROVIDER_LABELS: dict[str, str] = {
    "nvidia_nim": "NVIDIA",
    "mistral": "Mistral",
    "ollama_chat": "lokal",
    "ollama": "lokal",
}



PROVIDER_MODELS: dict[str, str] = {

    "nvidia_nim": "nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1.5",
    "mistral": "mistral/mistral-large-latest",
}






FAST_MODELS: dict[str, str] = {
    "nvidia_nim": "nvidia_nim/nvidia/nvidia-nemotron-nano-9b-v2",
    "mistral": "mistral/mistral-small-latest",
}


MAX_PICKER_MODELS = 8



RETIRED_MODELS = frozenset({
    "nvidia_nim/meta/llama-3.3-70b-instruct",
    "nvidia_nim/meta/llama-3.1-8b-instruct",
})


MAX_RETIRED_MODELS = 256
MAX_RETIRED_SCOPES = 64
_retired_seen: OrderedDict[str, OrderedDict[str, None]] = OrderedDict()
_retired_lock = threading.Lock()
_retirement_generation = 0



PREFERRED_MODELS: dict[tuple[str, str], tuple[str, ...]] = {
    ("nvidia_nim", "main"): (
        "nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1.5",
        "nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1",
        "nvidia_nim/nvidia/nemotron-3-super-120b-a12b",
        "nvidia_nim/nvidia/llama-3.1-nemotron-ultra-253b-v1",
    ),
    ("nvidia_nim", "fast"): (
        "nvidia_nim/nvidia/nvidia-nemotron-nano-9b-v2",
        "nvidia_nim/nvidia/nemotron-3-nano-30b-a3b",
        "nvidia_nim/nvidia/llama-3.1-nemotron-nano-8b-v1",
    ),
    ("nvidia_nim", "code"): (
        "nvidia_nim/qwen/qwen3-coder-480b-a35b-instruct",
        "nvidia_nim/qwen/qwen2.5-coder-32b-instruct",
    ),
}

_KLEIN = re.compile(r"nano|mini|small|\b(?:[1-9]|1[0-4])b\b|-[1-9]b-", re.IGNORECASE)


def retirement_generation() -> int:
    """Aenderungen auch dann erkennen, wenn begrenzte Beobachtungen wieder verschwinden."""
    with _retired_lock:
        return _retirement_generation


def is_retired(model: str, settings: Any = None) -> bool:
    """Bekannt abgeschaltet oder fuer genau diese Verbindung mit 410 abgelehnt."""
    if model in RETIRED_MODELS:
        return True
    with _retired_lock:
        if model not in _retired_seen or settings is None:
            return False
    from aquaticy.judgecache import scope

    bereich = scope(settings, [model])
    with _retired_lock:
        return bereich is not None and bereich in _retired_seen.get(model, {})


def mark_retired(model: str, settings: Any) -> None:
    """Merkt 410 nur fuer Konto, Schluessel, Endpunkt und aktuelle Modellfreigabe."""
    from aquaticy.judgecache import scope

    global _retirement_generation
    if not model or model in RETIRED_MODELS:
        return
    bereich = scope(settings, [model])
    if bereich is None:
        return
    with _retired_lock:
        _retirement_generation += 1
        verbindungen = _retired_seen.setdefault(model, OrderedDict())
        verbindungen[bereich] = None
        verbindungen.move_to_end(bereich)
        _retired_seen.move_to_end(model)
        while len(verbindungen) > MAX_RETIRED_SCOPES:
            verbindungen.popitem(last=False)
        while len(_retired_seen) > MAX_RETIRED_MODELS:
            _retired_seen.popitem(last=False)


def is_gone_error(exc: BaseException) -> bool:
    """Sagt der Fehler, dass das Modell abgeschaltet ist (410 Gone, end of life)?"""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status == 410
    text = str(exc).lower()
    return bool(re.search(r"\b410\b", text) and re.search(r"\bgone\b", text)) or bool(
        re.search(r"\bmodel\b.{0,160}\b(?:end of life|reached its end)\b", text, re.S))


def live_models(settings: Any, provider: str) -> list[str] | None:
    """Anbieterliste ohne Abgeschaltete; None heisst unbekannt, [] bekannt leer."""
    try:
        from aquaticy import linked

        stand = linked.load(settings.data_dir).get(provider)
    except Exception:
        return None
    if stand is None:
        return None
    if not isinstance(stand, dict):
        return []
    if "models" not in stand:
        return None
    models = stand["models"]
    if not isinstance(models, list):
        return []
    ids = [str(m.get("id") or "") for m in models
           if isinstance(m, dict)]
    return [i for i in dict.fromkeys(ids)
            if i.startswith(provider + "/") and not is_retired(i, settings)]


def provider_choice(settings: Any, provider: str, kind: str = "main") -> str:
    """Das Modell eines Anbieters fuer eine Rolle (main, fast, code) -- nie ein abgeschaltetes.

    Kennt Aquaticy die Liste des Anbieters, gilt nur, was darin steht. Ohne Liste der
    Tabellenwert, solange er nicht abgeschaltet ist.
    """
    tabelle = {"main": PROVIDER_MODELS, "fast": FAST_MODELS, "code": CODING_MODELS}[kind]
    wunsch = tabelle.get(provider, "")
    live = live_models(settings, provider)
    if wunsch and not is_retired(wunsch, settings) and (live is None or wunsch in live):
        return wunsch
    live = live or []
    for kandidat in PREFERRED_MODELS.get((provider, kind), ()):
        if kandidat in live:
            return kandidat
    if kind == "fast":
        return next((i for i in live if _KLEIN.search(i)), "")
    if kind == "main" and live:
        return next((i for i in live if "nemotron" in i), live[0])
    return ""


def replacement(settings: Any, model: str) -> str:
    """Ein abgeschaltetes Modell -> sein Ersatz beim selben Anbieter, sonst unveraendert.

    Getauscht wird nur, wenn der Anbieter einen Ersatz anbietet (seine Liste). Sonst
    bleibt das Modell -- und die Fehlermeldung sagt, dass es abgeschaltet ist.
    """
    if not model or not is_retired(model, settings):
        return model
    from aquaticy.config import provider_of

    anbieter = provider_of(model)
    if not live_models(settings, anbieter):
        return model
    if model in CODING_MODELS.values() or re.search(r"coder|codestral", model, re.IGNORECASE):
        rolle = "code"
    elif model in FAST_MODELS.values() or _KLEIN.search(model):
        rolle = "fast"
    else:
        rolle = "main"
    return provider_choice(settings, anbieter, rolle) or \
        provider_choice(settings, anbieter, "main") or model




CODING_MODELS: dict[str, str] = {
    "nvidia_nim": "nvidia_nim/qwen/qwen2.5-coder-32b-instruct",
    "mistral": "mistral/codestral-latest",
}





CODING_ORDER: tuple[str, ...] = ("mistral", "nvidia_nim")

PROVIDER_KEYS: dict[str, str] = {
    "nvidia_nim": "NVIDIA_NIM_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}












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





def cpu_load() -> dict[str, Any]:
    """Prozessorlast als Anteil der verfuegbaren Kerne."""
    cores = os.cpu_count() or 1
    try:
        one_minute = os.getloadavg()[0]
    except (OSError, AttributeError):
        return {"cores": cores}
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




_ZUGANG_AUS_UMGEBUNG: dict[str, tuple[str, ...]] = {
    "bedrock": ("AWS_ACCESS_KEY_ID", "AWS_PROFILE"),
    "sagemaker": ("AWS_ACCESS_KEY_ID", "AWS_PROFILE"),
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


def ollama_base(settings: Any) -> str:
    """Ollama hat eine eigene Route, auch wenn das Hauptmodell in der Wolke laeuft."""
    from aquaticy.local_model import DEFAULT_OLLAMA_URL, local_name

    basis_von = getattr(settings, "ollama_base", None)
    if callable(basis_von):
        model = str(getattr(settings, "model", "") or "")
        return str(basis_von(model if local_name(model) else "ollama_chat/_discovery"))
    return str(getattr(settings, "api_base", "") or DEFAULT_OLLAMA_URL)


def model_usable(settings: Any, model_id: str, installed: list[str] | None = None) -> bool:
    """Antwortet *model_id* gerade wirklich? (11.3.0 Luna)

    Die Modellauswahl zeigt nur noch, was beim Anklicken auch laeuft: ein
    lokales Modell, das in Ollama installiert ist, sonst eines mit Schluessel
    (eigener, gestellter, allgemeiner) oder mit eingetragener Adresse (LM
    Studio, Proxy). Seit 12.0.0 Luna nur Mistral, NVIDIA NIM oder lokal
    (``config.model_allowed``). Das voreingestellte Modell eines
    frischen Servers zaehlt nicht von selbst -- bis dahin stand zum Beispiel
    Mistral in der Liste, obwohl es keinen Mistral-Schluessel gab.

    Args:
        installed: die Liste von Ollama, wenn sie schon da ist. Sonst wird
            jetzt gefragt -- ein eben installiertes Modell zaehlt sofort.
    """
    from aquaticy.config import SPLIT_MODEL_ID, model_allowed, provider_of
    from aquaticy.local_model import is_installed, local_name

    model_id = str(model_id or "").strip()
    if not model_id or model_id == SPLIT_MODEL_ID:

        return False
    name = local_name(model_id)
    if name:
        return is_installed(name, _ollama_liste(settings, model_id) if installed is None
                            else installed)
    provider = provider_of(model_id)
    if not provider or is_retired(model_id, settings):

        return False
    try:
        weg = getattr(settings, "route", None)
        adresse = weg(model_id)[0] if callable(weg) else ""
        if not model_allowed(model_id, adresse):
            return False
        live = live_models(settings, provider)
        if live is not None and model_id not in live:
            return False
        if adresse:
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
    from aquaticy.local_model import installed_models, model_size_gb

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


    if wanted and model_usable(settings, wanted):
        dazu(wanted, PROVIDER_LABELS.get(provider_of(wanted), "eigenes"), "von dir eingetragen",
             model_origin(settings, wanted))



    anbieter = sorted(
        (p for p in CODING_ORDER if key_origin(settings, p)),
        key=lambda p: (key_origin(settings, p) != "own", CODING_ORDER.index(p)),
    )
    for provider in anbieter:
        key_name = PROVIDER_KEYS.get(provider, "")
        if not key_name:
            continue
        stark = (
            provider_choice(settings, provider, "code") if purpose == "code" else ""
        ) or provider_choice(settings, provider, "main")
        if not stark:
            continue
        dazu(
            stark,
            PROVIDER_LABELS.get(provider, provider),
            "Fürs Programmieren"
            if purpose == "code" and provider_choice(settings, provider, "code") == stark
            else PROVIDER_NOTES.get(provider, "Über die Schnittstelle des Anbieters"),
            model_origin(settings, stark, key_origin(settings, provider)),
        )

    base = ollama_base(settings)
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
        return replacement(settings, eigen)
    anbieter = provider_of(str(getattr(settings, "model", "") or ""))
    return provider_choice(settings, anbieter, "fast") if anbieter in FAST_MODELS else ""


def provider_models(settings: Any, provider: str) -> list[str]:
    """Gemeinsame Auswahl fuer Hauptliste und Add-ons, hoechstens acht je Anbieter."""
    from aquaticy.config import provider_of

    current = str(getattr(settings, "model", "") or "")
    live = live_models(settings, provider)
    if live is not None:
        nemotron = [i for i in live if "nemotron" in i]
        ids = nemotron + [i for i in live if i not in nemotron]
        if current in ids and ids.index(current) >= MAX_PICKER_MODELS:
            ids.remove(current)
            ids.insert(0, current)
        return ids[:MAX_PICKER_MODELS]
    model = provider_choice(settings, provider, "main")
    schnell = provider_choice(settings, provider, "fast")
    if (provider_of(current) == provider and current != schnell
            and not is_retired(current, settings)):
        model = current
    return [m for m in dict.fromkeys((model, schnell)) if m]


def available_models(settings: Any) -> list[dict[str, str]]:
    """Alles, worauf sich gerade umschalten laesst.

    Zuerst die lokal installierten Ollama-Modelle, dann die Anbieter, fuer
    die ein Schluessel hinterlegt ist. Was keinen Schluessel hat, taucht nicht
    auf -- eine Auswahl, die beim Anklicken scheitert, hilft niemandem.
    """
    from aquaticy.config import provider_of
    from aquaticy.local_model import (
        installed_models,
        is_installed,
        known_model,
        local_name,
    )

    found: list[dict[str, str]] = []
    current = getattr(settings, "model", "")
    base = ollama_base(settings)

    lokal = installed_models(base)
    for name in lokal:
        model = known_model(name)


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



    anbieter = sorted(
        (p for p in PROVIDER_KEYS if key_origin(settings, p)),
        key=lambda p: key_origin(settings, p) != "own",
    )
    for provider in anbieter:
        herkunft = key_origin(settings, provider)



        schnell = provider_choice(settings, provider, "fast")
        for model_id in provider_models(settings, provider):
            klein = model_id == schnell
            found.append(_mit_herkunft(
                {
                    "id": model_id,
                    "label": model_id.split("/", 1)[-1],
                    "kind": PROVIDER_LABELS.get(provider, provider),


                    "note": "Klein und schnell: kurze Antworten in Sekunden" if klein
                    else PROVIDER_NOTES.get(provider, "Über die Schnittstelle des Anbieters"),
                },
                model_origin(settings, model_id, herkunft),
            ))





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
