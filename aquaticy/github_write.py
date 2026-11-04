"""Aendern bei GitHub wie Codex oder Claude Code: holen, Branch, Commit und Push, Pull Request.

Seit 14.4.4. Der GitHub-Schluessel bleibt auf diesem Rechner: Die VM bekommt nur die Dateien
(ein Archiv des Repos), nie den Schluessel. Committen und pushen macht dieser Code ueber die
GitHub-API (Git-Daten: Blobs, Baum, Commit, Ref) -- immer ohne force, ein Push auf einen
Branch mit neueren Commits wird abgelehnt wie bei git. Jeder Schritt, der etwas bei GitHub
aendert, braucht das Ja des Nutzers (aquaticy/tools.py). Dateien mit Schluesseln oder
Passwoertern werden nicht uebertragen.
"""

from __future__ import annotations

import base64
import json
import re
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

API = "https://api.github.com"
MAX_FILES = 100
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024
MAX_TARBALL = 20 * 1024 * 1024
MAX_TEXT = 60_000
WORKFLOWS = ".github/workflows/"
ACTIONS = ("checkout", "branch", "commit", "push", "pull_request", "comment")
_BRANCH = re.compile(r"[A-Za-z0-9._/-]{1,200}")


class WriteError(ValueError):
    """Ein Schreibschritt bei GitHub ging nicht."""


def valid_branch(name: str) -> bool:
    """Ein Branch-Name nach den Regeln von git (die wichtigsten davon)."""
    return bool(_BRANCH.fullmatch(name)) and not (
        name.startswith(("-", "/", ".")) or name.endswith(("/", ".", ".lock"))
        or ".." in name or "//" in name or "/." in name or name == "HEAD")


def default_branch_name() -> str:
    return time.strftime("aquaticy/aenderung-%Y%m%d-%H%M%S")


def valid_repo_path(path: str) -> bool:
    teile = path.split("/")
    return (0 < len(path) <= 400 and all(c.isprintable() for c in path)
            and "\\" not in path and not path.startswith("/")
            and all(t not in ("", ".", "..", ".git") for t in teile))


def secret_problem(path: str, data: bytes) -> str:
    """Steht ein Schluessel oder Passwort in der Datei? Dann wird sie nicht uebertragen."""
    from aquaticy.review_scan import mask_secrets

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return ""
    if re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", text) or any(
            mask_secrets(zeile) != zeile for zeile in text.splitlines()):
        return (f"{path} enthält wohl einen Schlüssel, ein Token oder ein Passwort. Entferne "
                "es und übertrage danach erneut.")
    return ""


class Api:
    """Ein GitHub-Zugang fuer einen Schritt: begrenzte Zahl Aufrufe, je Sekunde einer."""

    def __init__(self, client: httpx.Client, headers: dict[str, str],
                 throttle: Callable[[str], None], limit: int = 300) -> None:
        self.client = client
        self.headers = headers
        self.throttle = throttle
        self.limit = limit
        self.calls = 0

    def _count(self) -> None:
        if self.calls >= self.limit:
            raise WriteError("Zu viele GitHub-Aufrufe für einen Schritt. Übertrage weniger "
                             "Dateien auf einmal.")
        self.calls += 1
        self.throttle("api.github.com")

    def get(self, route: str, **params: Any) -> Any:
        from aquaticy import github_repo

        self._count()
        try:
            return github_repo.request(self.client, route, self.headers,
                                       {k: v for k, v in params.items() if v not in ("", None)})
        except github_repo.Missing as exc:
            raise Missing(str(exc)) from exc
        except github_repo.GitHubError as exc:
            raise WriteError(str(exc)) from exc

    def send(self, method: str, route: str, payload: dict[str, Any]) -> Any:
        self._count()
        antwort = self.client.request(method, API + route, headers=self.headers, json=payload,
                                      follow_redirects=False)
        status = antwort.status_code
        if status in (200, 201):
            if len(antwort.content) > 2 * 1024 * 1024:
                raise WriteError("GitHub-Antwort zu groß.")
            return antwort.json()
        if status == 204:
            return {}
        meldung = ""
        try:
            daten = antwort.json()
            meldung = " ".join(str(daten.get("message") or "").split())[:200]
        except ValueError:
            pass
        klein = meldung.lower()
        if status in (401, 403):
            if "rate limit" in klein:
                raise WriteError("Das GitHub-Limit ist erreicht. Versuche es später erneut.")
            raise WriteError(
                f"GitHub verweigert das Schreiben ({status}). Dein Token braucht für dieses "
                "Repo Contents: Read and write, für Pull Requests auch Pull requests: Read "
                "and write. Änderungen an GitHub Actions brauchen zusätzlich Workflows.")
        if status == 404:
            raise WriteError("Nicht gefunden oder ohne Schreibrecht. Prüfe Repo, Branch und "
                             "die Rechte deines Tokens.")
        if status == 409 or "fast forward" in klein or "fast-forward" in klein:
            raise WriteError("Der Branch hat inzwischen neue Commits. Hole den Stand neu "
                             "(checkout) und übertrage deine Änderung danach. Aquaticy pusht "
                             "nie mit force.")
        if "reference already exists" in klein:
            raise WriteError("Diesen Branch gibt es schon.")
        if status == 422:
            raise WriteError("GitHub lehnt das ab" + (f": {meldung}" if meldung else ".")
                             + " Prüfe Branch, Titel und ob es schon einen Pull Request gibt.")
        raise WriteError(f"GitHub antwortet mit {status}.")


class Missing(WriteError):
    """Ein Branch oder Commit existiert nicht."""


def resolve(api: Api, repo: str, ref: str) -> str:
    """Der volle Commit-SHA zu Branch, Tag oder SHA."""
    commit = api.get(f"/repos/{repo}/commits/{quote(ref, safe='')}")
    sha = str(commit.get("sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise WriteError("GitHub hat keinen gültigen Commit geliefert.")
    return sha


def branch_head(api: Api, repo: str, branch: str) -> str:
    """Der Kopf eines Branches -- "" wenn es ihn nicht gibt."""
    try:
        daten = api.get(f"/repos/{repo}/git/ref/heads/{quote(branch, safe='/')}")
    except Missing:
        return ""
    sha = str((daten.get("object") or {}).get("sha") or "")
    if daten.get("ref") != f"refs/heads/{branch}" or not re.fullmatch(r"[0-9a-f]{40}", sha):
        return ""
    return sha


def check_changes(changes: list[dict[str, Any]], *, workflows_allowed: bool) -> None:
    """Pruefungen vor jeder Uebertragung. Raises WriteError."""
    if not changes:
        raise WriteError("Es gibt keine Änderungen zu übertragen.")
    if len(changes) > MAX_FILES:
        raise WriteError(f"Höchstens {MAX_FILES} Dateien je Commit.")
    gesamt = 0
    pfade: set[str] = set()
    for change in changes:
        pfad = str(change.get("path") or "")
        if not valid_repo_path(pfad) or pfad in pfade:
            raise WriteError(f"Ungültiger oder doppelter Pfad: {pfad[:120]}")
        pfade.add(pfad)
        if pfad.startswith(WORKFLOWS) and not workflows_allowed:
            raise WriteError("Änderungen an GitHub Actions (.github/workflows) macht Aquaticy "
                             "nicht. Sie könnten Geheimnisse des Repos auslesen. Ändere sie "
                             "selbst auf GitHub.")
        daten = change.get("data")
        if daten is None:
            continue
        if not isinstance(daten, bytes) or len(daten) > MAX_FILE_BYTES:
            raise WriteError(f"{pfad} ist größer als 5 MB.")
        gesamt += len(daten)
        problem = secret_problem(pfad, daten)
        if problem:
            raise WriteError(problem)
    if gesamt > MAX_TOTAL_BYTES:
        raise WriteError("Zusammen höchstens 20 MB je Commit.")


def commit(api: Api, repo: str, branch: str, message: str, changes: list[dict[str, Any]], *,
           parent: str) -> dict[str, Any]:
    """Ein Commit mit allen Aenderungen, danach der Push (Ref ohne force).

    Args:
        parent: Der Commit, auf dem die Aenderungen beruhen. Gibt es den Branch schon und
            zeigt er auf etwas anderes, lehnt GitHub den Push ab (kein Vorspulen moeglich).
    """
    vorhanden = branch_head(api, repo, branch)
    eltern = api.get(f"/repos/{repo}/git/commits/{parent}")
    baum = str((eltern.get("tree") or {}).get("sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", baum):
        raise WriteError("GitHub hat keinen gültigen Baum geliefert.")
    eintraege: list[dict[str, Any]] = []
    for change in changes:
        if change.get("data") is None:
            eintraege.append({"path": change["path"], "mode": "100644", "type": "blob",
                              "sha": None})
            continue
        blob = api.send("POST", f"/repos/{repo}/git/blobs", {
            "content": base64.b64encode(change["data"]).decode("ascii"), "encoding": "base64"})
        eintraege.append({"path": change["path"],
                          "mode": "100755" if change.get("mode") == "100755" else "100644",
                          "type": "blob", "sha": blob["sha"]})
    neu_baum = api.send("POST", f"/repos/{repo}/git/trees",
                        {"base_tree": baum, "tree": eintraege})
    neu = api.send("POST", f"/repos/{repo}/git/commits", {
        "message": message, "tree": neu_baum["sha"], "parents": [parent]})
    sha = str(neu.get("sha") or "")
    if vorhanden:
        api.send("PATCH", f"/repos/{repo}/git/refs/heads/{quote(branch, safe='/')}",
                 {"sha": sha, "force": False})
    else:
        api.send("POST", f"/repos/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": sha})
    return {"commit": sha, "branch": branch, "new_branch": not vorhanden,
            "url": f"https://github.com/{repo}/commit/{sha}",
            "files": [{"path": c["path"], "status": c.get("status") or (
                "gelöscht" if c.get("data") is None else "geändert")} for c in changes]}


def download_tarball(client: httpx.Client, headers: dict[str, str], repo: str,
                     sha: str) -> bytes:
    """Das Archiv eines festen Commits. Folgt nur der Weiterleitung zu codeload.github.com."""
    antwort = client.get(f"{API}/repos/{repo}/tarball/{sha}", headers=headers,
                         follow_redirects=False)
    if antwort.status_code in (301, 302, 303, 307, 308):
        ziel = urlsplit(antwort.headers.get("location", ""))
        if ziel.scheme != "https" or ziel.hostname != "codeload.github.com":
            raise WriteError("GitHub leitet an eine unerwartete Adresse weiter.")
        url = ziel.geturl()
        kopf = {"User-Agent": headers.get("User-Agent", "aquaticy")}
    elif antwort.status_code == 200:
        return _begrenzt(antwort.content)
    else:
        raise WriteError(f"Das Archiv ließ sich nicht laden ({antwort.status_code}).")
    daten = bytearray()
    with client.stream("GET", url, headers=kopf, follow_redirects=False) as strom:
        if strom.status_code != 200:
            raise WriteError(f"Das Archiv ließ sich nicht laden ({strom.status_code}).")
        for stueck in strom.iter_bytes(65_536):
            daten.extend(stueck)
            if len(daten) > MAX_TARBALL:
                raise WriteError("Das Repo ist größer als 20 MB. Das geht nicht in die VM.")
    return bytes(daten)


def _begrenzt(daten: bytes) -> bytes:
    if len(daten) > MAX_TARBALL:
        raise WriteError("Das Repo ist größer als 20 MB. Das geht nicht in die VM.")
    return daten


# -- In der VM: auspacken und Aenderungen finden ------------------------------------------------
# Feste Python-Helfer. Sie laufen in der VM (python3 ist im Standardabbild) und lesen nur
# Dateien unter dem Arbeitsordner. Die Zuordnung Ordner -> Repo merkt sich der Rechner selbst
# (aquaticy/tools.py), nicht die VM.
SKIP = ("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules", ".venv",
        ".git", ".tox", ".aquaticy-github.json")

EXTRACT = r'''
import hashlib, json, os, sys, tarfile
archiv, ziel = sys.argv[1], sys.argv[2]
if os.path.lexists(ziel):
    print("EXISTS"); sys.exit(3)
os.makedirs(ziel)
with tarfile.open(archiv) as tar:
    for m in tar.getmembers():
        teile = m.name.split("/", 1)
        if len(teile) < 2 or not teile[1]:
            continue
        m.name = teile[1]
        if m.issym() or m.islnk() or m.isdev() or not (m.isfile() or m.isdir()):
            continue
        teile = m.name.split("/")
        if m.name.startswith("/") or ".." in teile or ".git" in teile:
            continue
        m.mode = (m.mode & 0o755) | 0o600
        try:
            tar.extract(m, ziel, filter="data")
        except TypeError:
            tar.extract(m, ziel)
os.unlink(archiv)
'''

MANIFEST = r'''
import hashlib, json, os, stat, sys
ziel = sys.argv[1]
SKIP = set(json.loads(sys.argv[2]))
mode = sys.argv[3]
def blob(p):
    with open(p, "rb") as f:
        d = f.read()
    return hashlib.sha1(b"blob %d\0" % len(d) + d).hexdigest(), len(d)
dateien = {}
for wurzel, ordner, namen in os.walk(ziel):
    ordner[:] = [o for o in ordner if o not in SKIP and not os.path.islink(os.path.join(wurzel, o))]
    for n in namen:
        if n in SKIP or n.endswith(".pyc"):
            continue
        p = os.path.join(wurzel, n)
        if os.path.islink(p) or not os.path.isfile(p):
            continue
        rel = os.path.relpath(p, ziel).replace(os.sep, "/")
        sha, groesse = blob(p)
        x = "100755" if os.stat(p).st_mode & stat.S_IXUSR else "100644"
        dateien[rel] = [sha, x, groesse]
        if len(dateien) > 20000:
            print(json.dumps({"error": "zu viele Dateien"})); sys.exit(4)
pfad = os.path.join(ziel, ".aquaticy-github.json")
if mode == "write":
    with open(pfad, "w") as f:
        json.dump(dateien, f)
    print(json.dumps({"files": len(dateien)}))
else:
    try:
        with open(pfad) as f:
            alt = json.load(f)
    except (OSError, ValueError):
        print(json.dumps({"error": "manifest"})); sys.exit(5)
    aenderungen = []
    for rel, (sha, x, groesse) in sorted(dateien.items()):
        vorher = alt.get(rel)
        if vorher is None:
            aenderungen.append({"path": rel, "status": "neu", "mode": x, "size": groesse})
        elif vorher[0] != sha or vorher[1] != x:
            aenderungen.append({"path": rel, "status": "geändert", "mode": x, "size": groesse})
    for rel in sorted(set(alt) - set(dateien)):
        aenderungen.append({"path": rel, "status": "gelöscht", "mode": "100644", "size": 0})
    print(json.dumps({"changes": aenderungen[:501]}))
'''


def vm_dir(name: str) -> str:
    """Der Arbeitsordner in der VM fuer ein Repo: /work/<name>, ohne Tricks."""
    sauber = re.sub(r"[^A-Za-z0-9._-]", "-", str(name or "").strip())[:80].strip(".-")
    if not sauber:
        raise WriteError("Ungültiger Ordnername.")
    return f"/work/{sauber}"


def parse_helper(stdout: str) -> dict[str, Any]:
    zeile = (stdout or "").strip().splitlines()[-1:] or ["{}"]
    try:
        daten = json.loads(zeile[0])
    except ValueError as exc:
        raise WriteError("Die VM hat unerwartet geantwortet.") from exc
    if not isinstance(daten, dict):
        raise WriteError("Die VM hat unerwartet geantwortet.")
    return daten
