"""Ein Aufruf an LiteLLM -- mit Ausweg, wenn LiteLLM nach dem Paket `mcp` greift (11.3.2 Sol).

LiteLLM 1.106.0 laedt bei JEDEM Aufruf mit Werkzeugen seine MCP-Gateway-Module
(``litellm.responses.mcp``), und die brauchen das Paket ``mcp``. Das gehoert nicht
zu den Abhaengigkeiten von LiteLLM -- eine frische Installation (``uv tool install``)
hat es nicht. Jede Frage endete dann mit "ModuleNotFoundError: No module named
'mcp'", denn Aquaticy schickt immer Werkzeuge mit.

Aquaticy nutzt kein MCP-Gateway von LiteLLM. Fehlt ``mcp``, wird derselbe Aufruf
deshalb ohne diesen Umweg wiederholt (``_skip_mcp_handler``) und das fuer den
Rest des Laufs gemerkt. Der Fehler kommt vor jeder Anfrage ans Netz: nichts wird
doppelt geschickt oder gezaehlt. ``pyproject.toml`` schliesst 1.106.0 zusaetzlich aus.

Seit 12.0.0 Luna ist das hier auch die Sperre (``config.check_allowed``): Jeder
Modellaufruf von Aquaticy laeuft hier durch, und durch kommen nur Mistral,
NVIDIA NIM und Modelle auf dem Server selbst.
"""

from __future__ import annotations

from typing import Any

_OHNE_MCP = False


def _fehlt_mcp(exc: BaseException) -> bool:
    name = str(getattr(exc, "name", "") or "")
    return isinstance(exc, ModuleNotFoundError) and (name == "mcp" or name.startswith("mcp."))


def close_stream(response: Any) -> None:
    """Schliesst synchrone Streams samt HTTP-Verbindung, auch hinter LiteLLM.

    CustomStreamWrapper hat teils nur aclose(). Bei synchronem Ollama fehlt
    zudem der Verweis http_response im inneren Iterator. Dessen iter_lines-
    Generator haelt noch die echte httpx.Response. Die eng begrenzte
    Kompatibilitaetshilfe schliesst nur Objekte dieses Typs, ohne Daten aus
    dem Generator auszuwerten oder weiterzugeben.
    """
    import inspect

    import httpx

    for stream in (response, getattr(response, "completion_stream", None)):
        if stream is None:
            continue
        raw = getattr(stream, "http_response", None)
        lines = getattr(stream, "streaming_response", None)
        if raw is None and inspect.isgenerator(lines):
            raw = inspect.getgeneratorlocals(lines).get("self")
        if isinstance(raw, httpx.Response):
            raw.close()
        close = getattr(stream, "close", None)
        if callable(close) and not inspect.iscoroutinefunction(close):
            close()
        if inspect.isgenerator(lines):
            lines.close()


def completion(**kwargs: Any) -> Any:
    """Wie ``litellm.completion`` -- nur ohne den MCP-Umweg, wenn `mcp` fehlt."""
    from aquaticy.config import check_allowed
    from aquaticy.local_model import model_use

    check_allowed(str(kwargs.get("model") or ""), str(kwargs.get("api_base") or ""))
    with model_use(str(kwargs.get("model") or ""), str(kwargs.get("api_base") or "")):
        return _call(**kwargs)


def _call(**kwargs: Any) -> Any:
    global _OHNE_MCP
    import litellm

    if _OHNE_MCP and kwargs.get("tools"):
        return litellm.completion(**kwargs, _skip_mcp_handler=True)
    try:
        return litellm.completion(**kwargs)
    except ModuleNotFoundError as exc:
        if not _fehlt_mcp(exc) or not kwargs.get("tools") or "_skip_mcp_handler" in kwargs:
            raise
        _OHNE_MCP = True
        return litellm.completion(**kwargs, _skip_mcp_handler=True)
