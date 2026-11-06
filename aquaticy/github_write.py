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
MAX_RESPONSE = 2 * 1024 * 1024
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
        or ".." in name or "//" in name or "/." in name or name == "HEAD"
        or any(part.endswith(".lock") for part in name.split("/")))


def default_branch_name() -> str:
    return time.strftime("aquaticy/aenderung-%Y%m%d-%H%M%S")


def valid_repo_path(path: str) -> bool:
    teile = path.split("/")
    return (0 < len(path) <= 400 and all(c.isprintable() for c in path)
            and "\\" not in path and not path.startswith("/")
            and all(t not in ("", ".", "..", ".git") for t in teile))


def secret_problem(path: str, data: bytes) -> str:
    """Steht ein Schluessel oder Passwort in der Datei? Dann wird sie nicht uebertragen."""
    from aquaticy.review_scan import _secret_value_ok, mask_secrets

    text = data.decode("utf-8", "replace").replace("\x00", "")
    env_names = re.compile(
        r"passw(?:or)?d|passwort|pwd|secret|token|api_?key|credential|private_?key|session|"
        r"nonce|salt|otp|(?:^|_)auth(?:_|$)|authorization", re.I)
    env_secrets = any(env_names.search(match[1]) and _secret_value_ok(match[1], match[2])
                      for match in re.finditer(
        r"(?m)^[ \t]*(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*"
        r"([^\s\"'`$(){}\[\]\\]{8,200})(?:[ \t]+#.*)?[ \t]*$", text))
    if env_secrets or re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", text) or any(
            mask_secrets(zeile) != zeile for zeile in text.splitlines()):
        return (f"{path} enthält wohl einen Schlüssel, ein Token oder ein Passwort. Entferne "
                "es und übertrage danach erneut.")
    return ""


def checked_text(value: Any, label: str, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        raise WriteError(f"{label}: höchstens {limit} Zeichen.")
    problem = secret_problem(label, text.encode("utf-8"))
    if problem:
        raise WriteError(problem)
    return text


class Api:
    """Ein GitHub-Zugang fuer einen Schritt: begrenzte Zahl Aufrufe, je Sekunde einer."""

    def __init__(self, client: httpx.Client, headers: dict[str, str],
                 throttle: Callable[[str], None], limit: int = 300,
                 allowed: Callable[[], bool] | None = None) -> None:
        self.client = client
        self.headers = headers
        self.throttle = throttle
        self.limit = limit
        self.calls = 0
        self.allowed = allowed

    def check_allowed(self) -> None:
        if self.allowed is not None and not self.allowed():
            raise WriteError("Die GitHub-Freigabe hat sich geändert. Weitere Schritte wurden "
                             "gestoppt. Bereits ausgeführte Schritte bleiben bestehen.")

    def _count(self) -> None:
        self.check_allowed()
        if self.calls >= self.limit:
            raise WriteError("Zu viele GitHub-Aufrufe für einen Schritt. Übertrage weniger "
                             "Dateien auf einmal.")
        self.calls += 1
        self.throttle("api.github.com")
        self.check_allowed()

    def get(self, route: str, **params: Any) -> Any:
        from aquaticy import github_repo

        self._count()
        try:
            result = github_repo.request(self.client, route, self.headers,
                                        {k: v for k, v in params.items() if v not in ("", None)},
                                        check=self.check_allowed)
            self.check_allowed()
            return result
        except github_repo.Missing as exc:
            raise Missing(str(exc)) from exc
        except github_repo.GitHubError as exc:
            raise WriteError(str(exc)) from exc

    def send(self, method: str, route: str, payload: dict[str, Any]) -> Any:
        self._count()
        with self.client.stream(method, API + route, headers=self.headers, json=payload,
                                follow_redirects=False) as antwort:
            status = antwort.status_code
            content = _read_response(antwort, MAX_RESPONSE, self.check_allowed)
        try:
            daten = json.loads(content) if content else {}
        except ValueError:
            daten = None
        if status in (200, 201):
            if not isinstance(daten, dict):
                raise WriteError("GitHub hat unerwartet geantwortet.")
            return daten
        if status == 204:
            return {}
        meldung = ""
        if isinstance(daten, dict):
            meldung = " ".join(str(daten.get("message") or "").split())[:200]
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
        checked_text(pfad, "Der Dateipfad", 400)
        if (pfad.startswith(WORKFLOWS) or pfad == WORKFLOWS.rstrip("/")
                or pfad == ".github") and not workflows_allowed:
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
    ensure_work_branch(api, repo, branch)
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
    ensure_work_branch(api, repo, branch)
    if vorhanden:
        api.send("PATCH", f"/repos/{repo}/git/refs/heads/{quote(branch, safe='/')}",
                 {"sha": sha, "force": False})
    else:
        api.send("POST", f"/repos/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": sha})
    return {"commit": sha, "branch": branch, "new_branch": not vorhanden,
            "url": f"https://github.com/{repo}/commit/{sha}",
            "files": [{"path": c["path"], "status": c.get("status") or (
                "gelöscht" if c.get("data") is None else "geändert")} for c in changes]}


def ensure_work_branch(api: Api, repo: str, branch: str) -> None:
    info = api.get(f"/repos/{repo}")
    if not isinstance(info, dict) or not info.get("default_branch"):
        raise WriteError("Der aktuelle Standard-Branch ließ sich nicht sicher prüfen.")
    if branch == info["default_branch"]:
        raise WriteError("Der gewählte Branch ist jetzt der Standard-Branch. "
                         "Wähle einen eigenen Branch und bestätige die Änderung erneut.")


def _read_response(response: httpx.Response, limit: int,
                   check: Callable[[], None] | None = None) -> bytes:
    data = bytearray()
    if check:
        check()
    for chunk in response.iter_bytes(65_536):
        if check:
            check()
        if len(data) + len(chunk) > limit:
            raise WriteError("GitHub-Antwort zu groß. Grenze die Anfrage ein.")
        data.extend(chunk)
    if check:
        check()
    return bytes(data)


def download_tarball(client: httpx.Client, headers: dict[str, str], repo: str,
                     sha: str, *, check: Callable[[], None] | None = None) -> bytes:
    """Begrenztes Archiv; Weiterleitungen nur innerhalb der GitHub-API und zu codeload."""
    url = f"{API}/repos/{repo}/tarball/{sha}"
    current_headers = headers
    for _ in range(4):
        if check:
            check()
        with client.stream("GET", url, headers=current_headers,
                           follow_redirects=False) as response:
            if response.status_code == 200:
                return _read_response(response, MAX_TARBALL, check)
            if response.status_code not in (301, 302, 303, 307, 308):
                raise WriteError(f"Das Archiv ließ sich nicht laden ({response.status_code}).")
            target = urlsplit(response.headers.get("location", ""))
            if target.scheme != "https" or target.netloc not in (
                    "api.github.com", "codeload.github.com"):
                raise WriteError("GitHub leitet an eine unerwartete Adresse weiter.")
            if target.netloc == "api.github.com" and urlsplit(url).netloc != "api.github.com":
                raise WriteError("GitHub leitet an eine unerwartete Adresse weiter.")
            url = target.geturl()
            current_headers = (headers if target.netloc == "api.github.com" else
                               {"User-Agent": headers.get("User-Agent", "aquaticy")})
    raise WriteError("GitHub leitet zu oft weiter.")


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
import json, os, shutil, sys, tarfile
archiv, ziel = sys.argv[1], sys.argv[2]
if os.path.lexists(ziel):
    print("EXISTS"); sys.exit(3)
os.makedirs(ziel)
try:
    total, count = 0, 0
    with tarfile.open(archiv) as tar:
        for m in tar:
            count += 1
            if count > 20000:
                raise ValueError("Das Archiv enthält zu viele Einträge.")
            teile = m.name.split("/", 1)
            if len(teile) < 2 or not teile[1]:
                continue
            m.name = teile[1]
            if m.issym() or m.islnk() or m.isdev() or not (m.isfile() or m.isdir()):
                continue
            teile = m.name.split("/")
            if m.name.startswith("/") or ".." in teile or ".git" in teile:
                continue
            if m.size < 0 or m.size > 32 * 1024 * 1024:
                raise ValueError("Eine Archivdatei ist größer als 32 MB.")
            total += m.size
            if total > 128 * 1024 * 1024:
                raise ValueError("Das entpackte Archiv ist größer als 128 MB.")
            m.mode = (m.mode & 0o755) | (0o700 if m.isdir() else 0o600)
            try:
                tar.extract(m, ziel, filter="data")
            except TypeError:
                tar.extract(m, ziel)
except Exception:
    shutil.rmtree(ziel, ignore_errors=True)
    print(json.dumps({"error": "Archiv ungültig oder Entpackgrenze überschritten."}))
    sys.exit(4)
finally:
    try:
        os.unlink(archiv)
    except FileNotFoundError:
        pass
'''

MANIFEST = r'''
import hashlib, json, os, stat, sys, tempfile
ziel = sys.argv[1]
SKIP = set(json.loads(sys.argv[2]))
mode = sys.argv[3]
def blob(p):
    with open(p, "rb") as f:
        size = os.fstat(f.fileno()).st_size
        h = hashlib.sha1(b"blob %d\0" % size, usedforsecurity=False)
        count = 0
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
            count += len(chunk)
    if size != count:
        raise ValueError("Datei während der Prüfung geändert")
    return h.hexdigest(), size
pfad = os.path.join(ziel, ".aquaticy-github.json")
if mode == "ack":
    with open(pfad) as f:
        alt = json.load(f)
    for rel, value in json.loads(sys.argv[4]).items():
        if value is None:
            alt.pop(rel, None)
        else:
            alt[rel] = value
    fd, temporary = tempfile.mkstemp(prefix=".aquaticy-manifest-", dir=ziel)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(alt, f)
        os.replace(temporary, pfad)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)
    print(json.dumps({"files": len(alt)}))
    sys.exit(0)
dateien = {}
for wurzel, ordner, namen in os.walk(ziel):
    ordner[:] = [o for o in ordner if o not in SKIP and not os.path.islink(os.path.join(wurzel, o))]
    for n in namen:
        if n in SKIP or n.endswith(".pyc") or n.startswith(".aquaticy-manifest-"):
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
