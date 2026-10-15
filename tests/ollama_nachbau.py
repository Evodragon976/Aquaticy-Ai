"""Ein nachgebautes Ollama fuer Tests (11.2.2 Terra).

Verhaelt sich bei ``think`` und ``tools`` wie das echte Ollama 0.9+: Ein Modell,
das etwas nicht kann, bekommt eine Anfrage damit mit HTTP 400 abgelehnt --
'"qwen2.5-coder:14b" does not support thinking'. ``/api/show`` nennt die
Faehigkeiten; mit ``alt=True`` kennt es sie nicht (aelteres Ollama).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

FAEHIGKEITEN = {
    "qwen2.5-coder:14b": ["completion", "tools", "insert"],
    "gemma3:4b": ["completion", "vision"],
    "qwen3:8b": ["completion", "tools", "thinking"],
}


class Ollama:
    """Startet den Nachbau auf einem freien Port; ``url``, ``anfragen``, ``stop()``."""

    def __init__(self, *, alt: bool = False, max_ctx: int = 0) -> None:
        self.alt = alt
        #: Groesseres num_ctx passt "nicht in den Speicher" (0 = alles passt).
        self.max_ctx = max_ctx
        self.anfragen: list[dict[str, Any]] = []
        #: Je Chat-Anfrage: angebotene Werkzeuge und Systemtext.
        self.details: list[dict[str, Any]] = []
        nachbau = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def _json(self, code: int, daten: Any) -> None:
                body = json.dumps(daten).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                if self.path in ("/api/ps", "/api/tags"):
                    self._json(200, {"models": [{"name": n, "size": 1} for n in FAEHIGKEITEN]})
                else:
                    self._json(404, {"error": "not found"})

            def do_POST(self) -> None:
                daten = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0))
                                   or b"{}")
                name = str(daten.get("model") or "")
                if self.path == "/api/show":
                    if nachbau.alt or name not in FAEHIGKEITEN:
                        self._json(200 if nachbau.alt else 404, {"modelfile": ""})
                    else:
                        self._json(200, {"capabilities": FAEHIGKEITEN[name]})
                    return
                if self.path != "/api/chat":
                    self._json(200, {"done": True})
                    return
                optionen = daten.get("options") or {}
                system = next((str(m.get("content") or "") for m in daten.get("messages") or []
                               if m.get("role") == "system"), "")
                nachbau.anfragen.append({"model": name, "think": daten.get("think"),
                                         "tools": bool(daten.get("tools")),
                                         "num_ctx": optionen.get("num_ctx")})
                nachbau.details.append({
                    "werkzeuge": [t["function"]["name"] for t in daten.get("tools") or []],
                    "system": system})
                if nachbau.max_ctx and int(optionen.get("num_ctx") or 0) > nachbau.max_ctx:
                    self._json(500, {"error": "model requires more system memory (12.5 GiB) "
                                              "than is available (8.0 GiB)"})
                    return
                faehig = FAEHIGKEITEN.get(name, [])
                if daten.get("think") is True and "thinking" not in faehig:
                    self._json(400, {"error": f'"{name}" does not support thinking'})
                    return
                if daten.get("tools") and "tools" not in faehig:
                    self._json(400, {"error": f"registry.ollama.ai/library/{name} "
                                              "does not support tools"})
                    return
                antwort = {"model": name, "created_at": "2026-10-15T00:00:00Z",
                           "message": {"role": "assistant", "content": "Fertig."},
                           "done": True, "done_reason": "stop",
                           "prompt_eval_count": 10, "eval_count": 2}
                if daten.get("stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson")
                    self.end_headers()
                    self.wfile.write((json.dumps(antwort) + "\n").encode())
                    return
                self._json(200, antwort)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
