"""Verknuepfte KI-Konten und AI Council (seit 9.6.1).

**Verknuepfen.** Seit 12.0.0 Luna sind es Mistral und NVIDIA NIM -- und nur
bei ihren Add-ons (aquaticy/addons.py) laesst sich ueberhaupt ein
API-Schluessel hinterlegen, nachdem das Add-on installiert ist. Andere
Anbieter in der Cloud ruft Aquaticy gar nicht auf (``config.model_allowed``).
Der Schluessel liegt verschluesselt im
Schluesselbund des Aquaticy-Kontos (aquaticy/keyvault.py) und geht nur an den
Anbieter selbst. Danach liest Aquaticy aus, was das Konto kann:

* **Modelle:** die Liste, die der Anbieter fuer diesen Schluessel nennt. Sie
  stehen danach in der Modellauswahl -- im Normal-, Pro- und Code-Modus.
* **Tokens:** Schickt der Anbieter bei einer Antwort seine Grenzen mit, steht
  hier, was davon im laufenden Zeitfenster noch frei ist. Dafuer geht eine
  winzige Anfrage mit einem einzigen Token raus. Nennt er sie nicht, steht das
  so da.

**Warum kein Passwort?** Sich bei Mistral oder NVIDIA maschinell mit E-Mail
und Passwort anzumelden, scheitert an Zwei-Faktor und Captchas, und Aquaticy
haette das Passwort des ganzen Kontos. Die Knoepfe "Mit Google", "Mit Apple",
"Mit E-Mail" oeffnen deshalb nur die Anmeldeseite des Anbieters; dort meldet
man sich selbst an, erstellt einen Schluessel und fuegt ihn hier ein. Der
Schluessel laesst sich jederzeit beim Anbieter widerrufen und kann nichts
ausser Modelle aufrufen.

**AI Council.** Statt eines Modells arbeiten mehrere: die verknuepften Modelle
bearbeiten die Frage, eines prueft auf Fehler, und das Hauptmodell von
Aquaticy ist der Richter. Er entscheidet, ob die Loesung traegt -- wenn nicht,
gehen seine Einwaende und die Antworten der anderen zurueck an die
Bearbeiter, die sich daran abarbeiten (bis zu drei Runden). Am Ende schreibt
der Richter die Antwort. Agenten laufen in diesem Modus nicht.
"""

from __future__ import annotations

import contextlib
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx

from aquaticy.jsonutil import loads

PROVIDERS: dict[str, dict[str, str]] = {
    "mistral": {"label": "Mistral", "company": "Mistral AI", "key": "MISTRAL_API_KEY",
                "prefix": "mistral/", "get_key": "https://console.mistral.ai/api-keys",
                "form": ""},
    "nvidia_nim": {"label": "NVIDIA NIM", "company": "NVIDIA", "key": "NVIDIA_NIM_API_KEY",
                   "prefix": "nvidia_nim/",
                   "get_key": "https://build.nvidia.com/settings/api-keys", "form": "nvapi-…"},
}
KEY_NAMES = frozenset(p["key"] for p in PROVIDERS.values())




SIGN_IN: dict[str, tuple[str, ...]] = {
    "mistral": ("google", "apple", "microsoft", "email"),
    "nvidia_nim": ("google", "email"),
}
SIGN_IN_LABELS = {"google": "Mit Google", "apple": "Mit Apple", "microsoft": "Mit Microsoft",
                  "email": "Mit E-Mail"}


_MISTRAL_FORM = re.compile(r"[A-Za-z0-9]{32}")


def detect_provider(key: str) -> str:
    """Zu welchem Anbieter gehoert dieser Schluessel? "" = nicht zu erkennen."""
    wert = str(key or "").strip()
    if wert.startswith("nvapi-"):
        return "nvidia_nim"
    if _MISTRAL_FORM.fullmatch(wert):
        return "mistral"
    return ""


STATE_FILE = "linked.json"
TIMEOUT = 15.0

MAX_MODELS = 12

COUNCIL_ROUNDS = 3

MISTRAL_API = "https://api.mistral.ai/v1"
NVIDIA_API = "https://integrate.api.nvidia.com/v1"

_LOCK = threading.Lock()


class LinkError(RuntimeError):
    """Der Anbieter hat abgelehnt oder war nicht erreichbar."""



def _http(client: httpx.Client | None) -> httpx.Client:
    return client or httpx.Client(timeout=TIMEOUT, follow_redirects=False)


def _fehler(antwort: httpx.Response, anbieter: str) -> LinkError:
    if antwort.status_code in (401, 403):
        return LinkError(f"{anbieter} lehnt den Schlüssel ab — bitte prüfen.")
    if antwort.status_code == 429:
        return LinkError(f"{anbieter}: Limit gerade erreicht oder kein Guthaben.")
    return LinkError(f"{anbieter} antwortet mit Fehler {antwort.status_code}.")


def _int(wert: Any) -> int | None:
    try:
        return int(str(wert).strip())
    except (TypeError, ValueError):
        return None



_TOKEN_HEADERS: tuple[tuple[str, str, str], ...] = (
    ("x-ratelimit-limit-tokens-minute", "x-ratelimit-remaining-tokens-minute", "Minute"),
    ("ratelimitbysize-limit", "ratelimitbysize-remaining", "Minute"),
    ("x-ratelimit-limit-tokens", "x-ratelimit-remaining-tokens", "Minute"),
    ("x-ratelimit-limit-tokens-month", "x-ratelimit-remaining-tokens-month", "Monat"),
)


def _tokens(headers: httpx.Headers) -> dict[str, Any] | None:
    """Die Token-Grenze aus den Kopfzeilen -- None, wenn der Anbieter keine nennt."""
    for grenze, rest, zeitraum in _TOKEN_HEADERS:
        limit, frei = _int(headers.get(grenze)), _int(headers.get(rest))
        if limit is not None or frei is not None:
            return {"limit": limit, "remaining": frei, "per": zeitraum, "reset": ""}
    return None


def _probe(http: httpx.Client, url: str, key: str, model: str) -> httpx.Response:
    """Eine Antwort mit genau einem Token -- sie bringt die Grenzen mit."""
    return http.post(url, headers={"Authorization": f"Bearer {key}"}, json={
        "model": model, "max_tokens": 1, "messages": [{"role": "user", "content": "."}]})


_MISTRAL_SKIP = re.compile(r"embed|moderation|ocr|transcri", re.IGNORECASE)


def _sort_models(models: list[dict[str, str]]) -> list[dict[str, str]]:
    """Die "-latest"-Namen zuerst, dann der Rest -- grob, aber ohne Netz."""
    return sorted(models, key=lambda m: (not m["id"].endswith("-latest"), m["id"]))[:MAX_MODELS]


def inspect(provider: str, key: str, client: httpx.Client | None = None) -> dict[str, Any]:
    """Prueft den Schluessel beim Anbieter und liest Modelle und freie Tokens aus.

    Raises:
        LinkError: Schluessel abgelehnt, Anbieter nicht erreichbar.
    """
    if provider not in PROVIDERS:
        raise LinkError("Diesen Anbieter gibt es hier nicht.")
    http = _http(client)
    try:
        if provider == "mistral":
            return _inspect_mistral(http, key)
        return _inspect_nvidia(http, key)
    except httpx.HTTPError as exc:
        raise LinkError(f"{PROVIDERS[provider]['label']} ist nicht erreichbar "
                        f"({type(exc).__name__}).") from exc
    finally:
        if client is None:
            http.close()


def _inspect_mistral(http: httpx.Client, key: str) -> dict[str, Any]:
    antwort = http.get(f"{MISTRAL_API}/models", headers={"Authorization": f"Bearer {key}"})
    if antwort.status_code != 200:
        raise _fehler(antwort, "Mistral")
    gesehen: set[str] = set()
    modelle: list[dict[str, str]] = []
    for m in antwort.json().get("data", []) or []:
        mid = str(m.get("id") or "")
        faehig = m.get("capabilities") or {}
        if (not mid or mid in gesehen or _MISTRAL_SKIP.search(mid)
                or faehig.get("completion_chat") is False or m.get("deprecation")):
            continue
        gesehen.add(mid)
        modelle.append({"id": "mistral/" + mid, "label": str(m.get("name") or mid)})
    modelle = _sort_models(modelle)
    info: dict[str, Any] = {"models": modelle, "tier": "", "tokens": None}
    klein = next((m["id"] for m in modelle if "small" in m["id"]),
                 modelle[-1]["id"] if modelle else "")
    if klein:
        probe = _probe(http, f"{MISTRAL_API}/chat/completions", key, klein.split("/", 1)[1])
        info["tokens"] = _tokens(probe.headers)
        if probe.status_code in (402, 429) and any(
                wort in probe.text.lower() for wort in ("quota", "credit", "payment")):
            info["warning"] = "Kein Guthaben mehr auf dem Mistral-Konto."
    if info["tokens"] is None:
        info["note"] = ("Wie viel du noch hast, sagt Mistral hier nicht. Du siehst es bei Mistral "
                        "unter „Limits“.")
    return info




_NVIDIA_CHAT = re.compile(r"instruct|chat|nemotron|deepseek|qwen|kimi|glm|gpt-oss|mixtral",
                          re.IGNORECASE)
_NVIDIA_SKIP = re.compile(
    r"embed|rerank|retriev|guard|safety|reward|clip|vila|neva|vision|-vl|vl-|parakeet|"
    r"whisper|flux|diffusion|ocr|deplot|kosmos|fuyu|detect|pii|riva|audio|tts|asr|"
    r"translate|cosmos|-base\b", re.IGNORECASE)


_NVIDIA_FIRST = ("nvidia/llama-3.3-nemotron-super-49b-v1.5", "nvidia/nvidia-nemotron-nano-9b-v2",
                 "qwen/qwen3-coder-480b-a35b-instruct")


def _inspect_nvidia(http: httpx.Client, key: str) -> dict[str, Any]:


    probe = _probe(http, f"{NVIDIA_API}/chat/completions", key, _NVIDIA_FIRST[1])
    if probe.status_code in (401, 403):
        raise _fehler(probe, "NVIDIA NIM")
    info: dict[str, Any] = {"models": [], "tier": "", "tokens": _tokens(probe.headers)}
    if probe.status_code == 429:
        info["warning"] = "Grenze erreicht. In einer Minute geht es weiter."
    elif probe.status_code >= 500:
        raise _fehler(probe, "NVIDIA NIM")

    ids: list[str] = []
    antwort = http.get(f"{NVIDIA_API}/models", headers={"Authorization": f"Bearer {key}"})
    if antwort.status_code == 200:
        ids = [str(m.get("id") or "") for m in antwort.json().get("data", []) or []]
    ids = [i for i in dict.fromkeys(ids) if i and _NVIDIA_CHAT.search(i)
           and not _NVIDIA_SKIP.search(i)]
    vorne = [i for i in _NVIDIA_FIRST if i in ids or not ids]

    rest = sorted((i for i in ids if i not in vorne), key=lambda i: ("nemotron" not in i, i))
    info["models"] = [{"id": "nvidia_nim/" + i, "label": i.split("/", 1)[-1]}
                      for i in (vorne + rest)[:MAX_MODELS]]
    if info["tokens"] is None:
        info["note"] = ("Wie viel du noch hast, sagt NVIDIA hier nicht. Kostenlos gehen 40 Fragen "
                        "pro Minute.")
    return info



def _path(data_dir: Path | str) -> Path:
    return Path(data_dir) / STATE_FILE


def load(data_dir: Path | str) -> dict[str, Any]:
    with contextlib.suppress(OSError, ValueError):
        daten = json.loads(_path(data_dir).read_text(encoding="utf-8"))
        if isinstance(daten, dict):
            return daten
    return {}


def save(data_dir: Path | str, provider: str, info: dict[str, Any] | None) -> None:
    with _LOCK:
        daten = load(data_dir)
        if info is None:
            daten.pop(provider, None)
        else:
            daten[provider] = dict(info, checked=time.time())
        ziel = _path(data_dir)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        tmp = ziel.with_suffix(".tmp")
        tmp.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
        tmp.replace(ziel)


def linked_providers(settings: Any) -> list[str]:
    """Verknuepfte Anbieter: der Schluessel ist da.

    Mit Konto zaehlt nur der EIGENE Schluessel -- einer, den der Betreiber in
    seiner Umgebung hat, macht noch kein verknuepftes Konto. Ein Schluessel aus
    der Zeit vor 12.0.0 (damals in den Einstellungen) zaehlt auch ohne
    Auslesen; seine Modelle kommen mit "Aktualisieren".
    """
    import os

    eigene: frozenset[str] = getattr(settings, "own_key_names", frozenset()) or frozenset()
    keys = getattr(settings, "api_keys", {}) or {}
    mit_konto = bool(getattr(settings, "account_email", ""))
    out = []
    for p, d in PROVIDERS.items():
        if mit_konto:
            da = d["key"] in eigene and bool(keys.get(d["key"]))
        else:
            da = bool(keys.get(d["key"]) or os.environ.get(d["key"], "").strip())
        if da:
            out.append(p)
    return out


def picker_models(settings: Any) -> list[dict[str, str]]:
    """Die verknuepften Modelle fuer die Modellauswahl."""
    from aquaticy.system import provider_models

    stand = load(settings.data_dir)
    out: list[dict[str, str]] = []
    for provider in linked_providers(settings):
        d = PROVIDERS[provider]
        info = stand.get(provider)
        models = info.get("models") if isinstance(info, dict) else None
        if not isinstance(models, list):
            continue
        labels = {str(m.get("id") or ""): m.get("label") for m in models if isinstance(m, dict)}
        for mid in provider_models(settings, provider):
            out.append({"id": mid, "label": str(labels.get(mid) or mid.split("/", 1)[1]),
                        "kind": f"{d['label']} (verknüpft)",
                        "note": f"Dein {d['company']}-Konto", "source": "own"})
    return out


_BEST = {
    "mistral": (r"large", r"medium", r"magistral", r"small"),
    "nvidia_nim": (r"nemotron-ultra", r"405b", r"deepseek", r"llama-3\.3-70b", r"70b", r"qwen"),
}


def best_model(settings: Any, provider: str) -> str:
    """Das staerkste verknuepfte Modell eines Anbieters (fuer den Council)."""
    from aquaticy.system import live_models

    modelle = live_models(settings, provider) or []
    for muster in _BEST.get(provider, ()):
        treffer = [m for m in modelle if re.search(muster, m)]
        if treffer:
            return sorted(treffer, reverse=True)[0]
    return modelle[0] if modelle else ""



def council_roles(settings: Any) -> tuple[list[tuple[str, str]], tuple[str, str] | None]:
    """(Bearbeiter, Pruefer) als (Anbieter, Modell). Der letzte verknuepfte prueft."""
    dabei = [(p, best_model(settings, p)) for p in linked_providers(settings)]
    dabei = [(p, m) for p, m in dabei if m]
    if len(dabei) < 2:
        return dabei, None
    return dabei[:-1], dabei[-1]


WORKER_PROMPT = (
    "Du bist Mitglied in einem Rat aus mehreren KI-Modellen. Löse die Aufgabe so gut "
    "du kannst: vollständig, korrekt, auf Deutsch, wenn die Frage deutsch ist. Kennzeichne "
    "Unsicheres als unsicher. Rate keine Fakten.")
CHECK_PROMPT = (
    "Du bist der Prüfer im Rat. Prüfe die folgenden Lösungen auf sachliche Fehler, Lücken, "
    "Widersprüche und Rechenfehler. Nenne jeden Fehler konkret (wer, was, warum falsch). "
    "Findest du nichts, schreib „Keine Fehler gefunden.“")
JUDGE_PROMPT = (
    "Du bist Aquaticy, der Richter im Rat. Vor dir liegen die Lösungen der Bearbeiter und "
    "der Prüfbericht. Entscheide: Ist eine Lösung (oder ihre Kombination) korrekt und "
    "vollständig? Antworte NUR mit JSON: {\"ok\": true|false, \"feedback\": \"was die "
    "Bearbeiter noch klären oder korrigieren müssen (leer, wenn ok)\"}.")
FINAL_PROMPT = (
    "Du bist Aquaticy, der Richter im Rat. Schreibe jetzt die endgültige Antwort an den "
    "Nutzer aus den geprüften Lösungen: korrekt, klar, ohne den Rat zu erwähnen, außer es "
    "bleibt ein Punkt strittig — dann sag das offen.")


def _ask(settings: Any, model: str, system: str, user: str, *, json_mode: bool = False) -> str:
    from aquaticy import metering
    from aquaticy.system import is_gone_error, mark_retired, replacement

    model = replacement(settings, model)
    versucht: set[str] = set()
    while True:
        versucht.add(model)
        kwargs = dict(settings.llm_kwargs_for(model))
        kwargs.setdefault("timeout", 120.0)
        kwargs.setdefault("drop_params", True)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            antwort = metering.completion(settings, model=model, messages=[
                {"role": "system", "content": system}, {"role": "user", "content": user}],
                **kwargs)
        except Exception as exc:
            if not is_gone_error(exc):
                raise
            mark_retired(model, settings)
            nachfolger = replacement(settings, model)
            if nachfolger in versucht:
                raise
            model = nachfolger
        else:
            break
    return str(antwort.choices[0].message.content or "").strip()


def _judge(text: str) -> tuple[bool, str]:
    roh = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    start, ende = roh.find("{"), roh.rfind("}")
    with contextlib.suppress(ValueError):
        daten = loads(roh[start:ende + 1])
        if isinstance(daten, dict) and isinstance(daten.get("ok"), bool):
            return daten["ok"], str(daten.get("feedback") or "").strip()
    return False, "Das Urteil war kein gültiges JSON mit einem booleschen 'ok'-Wert."


def run_council(settings: Any, question: str, context: str = "", judge_model: str = "",
                emit: Any = None, stop: threading.Event | None = None) -> str:
    """Der Rat: Bearbeiter arbeiten, der Pruefer prueft, der Richter entscheidet.

    Returns: die endgueltige Antwort (vom Richter geschrieben).
    """
    bearbeiter, pruefer = council_roles(settings)
    richter = judge_model or settings.model
    melden = emit or (lambda *a, **k: None)
    if not bearbeiter:
        raise LinkError("Für den AI Council braucht es mindestens zwei verknüpfte Konten.")
    aufgabe = f"{context}\n\nAufgabe:\n{question}".strip() if context else question
    loesungen: dict[str, str] = {}
    pruefbericht = ""
    rueckmeldung = ""
    ok = False
    melden("council", phase="start", workers=[m for _, m in bearbeiter],
           checker=pruefer[1] if pruefer else "", judge=richter)
    for runde in range(1, COUNCIL_ROUNDS + 1):
        if stop is not None and stop.is_set():
            return ""
        melden("council", phase="work", round=runde)

        def arbeite(eintrag: tuple[str, str], runde: int = runde,
                    pruefbericht: str = pruefbericht,
                    rueckmeldung: str = rueckmeldung) -> tuple[str, str]:
            _, modell = eintrag
            if runde == 1:
                text = aufgabe
            else:
                andere = "\n\n".join(f"--- {m} ---\n{t}" for m, t in loesungen.items()
                                     if m != modell)
                text = (f"{aufgabe}\n\nDeine bisherige Lösung:\n{loesungen.get(modell, '')}\n\n"
                        f"Lösungen der anderen:\n{andere}\n\nPrüfbericht:\n{pruefbericht}\n\n"
                        f"Einwände des Richters:\n{rueckmeldung}\n\nDiskutiere die Punkte, "
                        "übernimm, was die anderen besser haben, und gib deine verbesserte "
                        "Lösung.")
            try:
                return modell, _ask(settings, modell, WORKER_PROMPT, text)
            except Exception as exc:
                return modell, f"(nicht erreichbar: {type(exc).__name__})"

        with ThreadPoolExecutor(max_workers=len(bearbeiter)) as pool:
            for modell, text in pool.map(arbeite, bearbeiter):
                loesungen[modell] = text
        alle = "\n\n".join(f"--- Lösung von {m} ---\n{t}" for m, t in loesungen.items())
        if pruefer is not None:
            melden("council", phase="check", round=runde, model=pruefer[1])
            try:
                pruefbericht = _ask(settings, pruefer[1], CHECK_PROMPT,
                                    f"Aufgabe:\n{aufgabe}\n\n{alle}")
            except Exception as exc:
                pruefbericht = f"(Prüfer nicht erreichbar: {type(exc).__name__})"
        melden("council", phase="judge", round=runde, model=richter)
        try:
            urteil = _ask(settings, richter, JUDGE_PROMPT,
                          f"Aufgabe:\n{aufgabe}\n\n{alle}\n\nPrüfbericht:\n{pruefbericht}",
                          json_mode=True)
        except Exception:
            urteil = '{"ok": false, "feedback": "Der Prüfer war nicht erreichbar."}'
        ok, rueckmeldung = _judge(urteil)
        melden("council", phase="verdict", round=runde, ok=ok, feedback=rueckmeldung[:500])
        if ok:
            break
    if stop is not None and stop.is_set():
        return ""
    melden("council", phase="final", model=richter)
    alle = "\n\n".join(f"--- Lösung von {m} ---\n{t}" for m, t in loesungen.items())
    pruefstatus = ("Die Prüfung wurde bestätigt." if ok else
                   f"Die Prüfung wurde nicht bestätigt: {rueckmeldung or 'Punkte bleiben offen'}. "
                   "Kennzeichne ungeklärte Punkte in der Antwort ausdrücklich.")
    return _ask(settings, richter, FINAL_PROMPT,
                f"Frage des Nutzers:\n{aufgabe}\n\n{alle}\n\nPrüfbericht:\n{pruefbericht}"
                f"\n\nPrüfstatus:\n{pruefstatus}")
