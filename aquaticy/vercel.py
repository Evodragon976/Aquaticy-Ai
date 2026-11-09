"""Einstieg fuer Vercel: eine schlichte Startseite mit Anleitung (15.8.8).

Vercel baut Python-Projekte als kurzlebige Funktionen. Aquaticy selbst braucht einen Server,
der dauerhaft laeuft: eigene Daten auf der Platte, Hintergrundprozesse (Coworker, Secure Pro,
Messenger), die virtual machine und lange Antworten im Stream. Das geht in einer Funktion
nicht -- und halb laufen lassen hiesse, eine App ohne Anmeldung und ohne Daten ins Internet zu
stellen. Deshalb liefert dieser Einstieg nur eine feste Seite: was Aquaticy ist und wie man es
auf dem eigenen Rechner, im Container oder unter der eigenen Domain startet.

Bewusst nur Standardbibliothek: Der Einstieg importiert nichts von Aquaticy, keine Modelle,
kein Netz, keine Datei. Die Seite ist fest im Code, ohne Skript (strenge Content-Security-Policy).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

REPOSITORY = "https://github.com/Evodragon976/Aquaticy-Ai"

PAGE = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aquaticy AI</title>
<style>
:root{{--bg:#f6f5f0;--fg:#26251f;--muted:#5f5d54;--accent:#2f7a53;--card:#fffefa;--code:#efeee8}}
@media (prefers-color-scheme:dark){{:root{{--bg:#191a17;--fg:#f2f1ea;--muted:#b6b3a8;
  --accent:#5fcf8f;--card:#22231f;--code:#2c2d28}}}}
body{{margin:0;background:var(--bg);color:var(--fg);padding:16px;
  font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:42rem;margin:24px auto;background:var(--card);border-radius:18px;padding:28px}}
h1{{margin:0 0 4px;font-size:26px}}h2{{font-size:18px;margin:26px 0 6px}}
p,li{{color:var(--muted)}}a{{color:var(--accent)}}
pre{{background:var(--code);border-radius:10px;padding:12px;overflow-x:auto;font-size:14px}}
</style></head><body><main>
<h1>Aquaticy AI</h1>
<p>Aquaticy recherchiert für dich: Du fragst, Aquaticy sucht im Web, liest die passenden Seiten
und nennt zu jeder Angabe die Quelle.</p>
<p><b>Hier auf Vercel läuft nur diese Seite.</b> Aquaticy braucht einen Rechner, der dauerhaft
läuft: für deine Daten, die Coworker, Secure Pro, WhatsApp und Signal und die virtual machine.
So startest du es selbst:</p>
<h2>Auf deinem Rechner</h2>
<pre>uv tool install git+{REPOSITORY}
aquaticy</pre>
<h2>Im Container</h2>
<pre>git clone {REPOSITORY}
cd Aquaticy-Ai
docker compose up -d</pre>
<h2>Von unterwegs</h2>
<p>Über Tailscale oder unter deiner eigenen Domain (Cloudflare-Tunnel, eingebaut). Die Anleitung
steht in der <a href="{REPOSITORY}#readme">README</a>.</p>
<hr>
<p lang="en"><b>English:</b> Only this page runs on Vercel. Aquaticy needs a computer that keeps
running (your data, coworkers, Secure Pro, messengers, the virtual machine). Install it with
the commands above; see the <a href="{REPOSITORY}#readme">README</a>.</p>
</main></body></html>""".encode()

HEADERS = [
    ("Content-Type", "text/html; charset=utf-8"),
    ("Cache-Control", "public, max-age=300"),
    ("Content-Security-Policy",
     "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; "
     "frame-ancestors 'none'"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Frame-Options", "DENY"),
]


def app(environ: dict[str, Any],
        start_response: Callable[[str, list[tuple[str, str]]], Any]) -> Iterable[bytes]:
    """WSGI: "/" zeigt die Seite, alles andere gibt es hier nicht."""
    methode = str(environ.get("REQUEST_METHOD", "GET")).upper()
    pfad = str(environ.get("PATH_INFO", "/") or "/")
    if methode not in ("GET", "HEAD"):
        start_response("405 Method Not Allowed", [("Allow", "GET, HEAD"),
                                                  ("Content-Length", "0")])
        return [b""]
    if pfad not in ("/", "/index.html"):
        start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8"),
                                         ("Content-Length", "9"),
                                         ("X-Content-Type-Options", "nosniff")])
        return [b"" if methode == "HEAD" else b"Not found"]
    start_response("200 OK", [*HEADERS, ("Content-Length", str(len(PAGE)))])
    return [b"" if methode == "HEAD" else PAGE]
