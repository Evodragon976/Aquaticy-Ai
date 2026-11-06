"""15.0.0: GitHub wie Codex, Auftraege per Messenger, Klartext-Befehle, Coworker aus dem Chat
und ein besseres Secure Pro (Geraete, Namen, Sicherheitswert, Verlauf, UPnP)."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from aquaticy import (
    addons,
    bridge,
    github_write,
    lan,
    secure_devices,
    secure_pro,
    web,
)
from aquaticy.config import Settings
from aquaticy.messenger_modes import natural_command
from aquaticy.tools import Toolbox
from tests.test_v1401 import owner  # noqa: F401

TOKEN = "ghp_" + "a" * 36
BASE = "1" * 40
TREE = "2" * 40
NETZ = "192.168.1.0/24"


# -- GitHub: ein nachgebautes GitHub --------------------------------------------------------------
class FakeGitHub:
    def __init__(self) -> None:
        self.refs: dict[str, str] = {"main": BASE}
        self.calls: list[tuple[str, str, Any]] = []
        self.private = False
        self.non_ff = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        pfad = request.url.path
        daten = json.loads(request.content or b"null") if request.content else None
        self.calls.append((request.method, pfad, daten))
        if request.url.host == "codeload.github.com":
            assert "authorization" not in request.headers, "der Schluessel geht nicht mit"
            return httpx.Response(200, content=_tarball({"README.md": b"Hallo\n"}))
        assert request.url.host == "api.github.com"
        if request.method == "GET":
            if pfad == "/repos/o/r":
                return httpx.Response(200, json={"private": self.private,
                                                 "default_branch": "main"})
            if pfad.startswith("/repos/o/r/commits/"):
                return httpx.Response(200, json={"sha": BASE})
            if pfad.startswith("/repos/o/r/git/ref/heads/"):
                name = pfad.split("/git/ref/heads/", 1)[1]
                if name in self.refs:
                    return httpx.Response(200, json={"ref": f"refs/heads/{name}",
                                                     "object": {"sha": self.refs[name]}})
                return httpx.Response(404, json={})
            if pfad.startswith("/repos/o/r/git/commits/"):
                return httpx.Response(200, json={"tree": {"sha": TREE}})
            if pfad == f"/repos/o/r/tarball/{BASE}":
                return httpx.Response(302, headers={
                    "location": f"https://codeload.github.com/o/r/legacy.tar.gz/{BASE}"})
            return httpx.Response(404, json={})
        if pfad == "/repos/o/r/git/blobs":
            return httpx.Response(201, json={"sha": "3" * 40})
        if pfad == "/repos/o/r/git/trees":
            return httpx.Response(201, json={"sha": "4" * 40})
        if pfad == "/repos/o/r/git/commits":
            return httpx.Response(201, json={"sha": "5" * 40})
        if pfad == "/repos/o/r/git/refs":
            self.refs[daten["ref"].removeprefix("refs/heads/")] = daten["sha"]
            return httpx.Response(201, json={})
        if pfad.startswith("/repos/o/r/git/refs/heads/") and request.method == "PATCH":
            assert daten["force"] is False, "nie force"
            if self.non_ff:
                return httpx.Response(422, json={"message": "Update is not a fast forward"})
            self.refs[pfad.split("/refs/heads/", 1)[1]] = daten["sha"]
            return httpx.Response(200, json={})
        if pfad == "/repos/o/r/pulls":
            return httpx.Response(201, json={"number": 7, "state": "open",
                                             "html_url": "https://github.com/o/r/pull/7"})
        if pfad == "/repos/o/r/issues/5/comments":
            return httpx.Response(201, json={"id": 9, "html_url": "https://github.com/x"})
        return httpx.Response(404, json={})

    def writes(self) -> list[tuple[str, str, Any]]:
        return [c for c in self.calls if c[0] != "GET"]


def _tarball(dateien: dict[str, bytes]) -> bytes:
    puffer = io.BytesIO()
    with tarfile.open(fileobj=puffer, mode="w:gz") as tar:
        for name, inhalt in dateien.items():
            info = tarfile.TarInfo(f"o-r-123/{name}")
            info.size = len(inhalt)
            tar.addfile(info, io.BytesIO(inhalt))
    return puffer.getvalue()


@pytest.fixture
def github(settings: Settings, monkeypatch: pytest.MonkeyPatch):
    fake = FakeGitHub()
    echt = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda *a, **kw: echt(
        *a, **{"transport": httpx.MockTransport(fake), **kw}))
    monkeypatch.setattr(addons, "_takt", lambda host, abstand=1.05: None)
    addons.install(settings, "github", pro=False)
    settings.github_token = TOKEN
    box = Toolbox(settings)
    fragen: list[str] = []
    antwort = {"text": "ja"}
    box.ask_handler = lambda frage, optionen: fragen.append(frage) or antwort["text"]
    yield box, fake, fragen, antwort
    box.close()


def test_commit_and_push_on_a_new_branch(github) -> None:
    box, fake, fragen, _ = github
    ergebnis = box.call("github_write", {
        "action": "commit", "repo": "o/r", "branch": "aquaticy/fix", "message": "Fix",
        "files": [{"path": "src/a.py", "content": "print('ok')\n"},
                  {"path": "alt.txt", "delete": True}]})
    assert ergebnis["commit"] == "5" * 40 and ergebnis["new_branch"]
    assert "aquaticy/fix" in fragen[0] and "src/a.py" in fragen[0]
    baum = next(c[2] for c in fake.writes() if c[1].endswith("/git/trees"))
    assert baum["base_tree"] == TREE
    assert {"path": "alt.txt", "mode": "100644", "type": "blob", "sha": None} in baum["tree"]
    commit = next(c[2] for c in fake.writes() if c[1].endswith("/git/commits"))
    assert commit["parents"] == [BASE]
    assert fake.refs["aquaticy/fix"] == "5" * 40


@pytest.mark.parametrize("dateien,branch,wort", [
    ([{"path": "a.py", "content": "x"}], "main", "Standard-Branch"),
    ([{"path": ".github/workflows/ci.yml", "content": "on: push"}], "b", "GitHub Actions"),
    ([{"path": "a.py", "content": f"TOKEN = '{TOKEN}'"}], "b", "Schlüssel"),
    ([{"path": "../x", "content": "x"}], "b", "Ungültiger"),
    ([{"path": ".git/config", "content": "x"}], "b", "Ungültiger"),
])
def test_dangerous_commits_are_refused(github, dateien, branch, wort) -> None:
    box, fake, fragen, _ = github
    ergebnis = box.call("github_write", {"action": "commit", "repo": "o/r", "branch": branch,
                                         "message": "x", "files": dateien})
    assert wort in ergebnis["error"] and not fake.writes() and not fragen


def test_every_write_needs_a_yes(github) -> None:
    box, fake, fragen, antwort = github
    antwort["text"] = "nein"
    assert fragen == []
    ergebnis = box.call("github_write", {"action": "comment", "repo": "o/r", "number": 5,
                                         "body": "Danke!"})
    assert "nicht bestaetigt" in ergebnis["error"] and not fake.writes()
    box.ask_handler = None
    assert "niemand bestätigen" in box.call("github_write", {
        "action": "comment", "repo": "o/r", "number": 5, "body": "x"})["error"]


def test_push_is_rejected_like_git_when_the_branch_moved(github) -> None:
    box, fake, _, _ = github
    fake.refs["feature"] = "9" * 40
    fake.non_ff = True
    ergebnis = box.call("github_write", {"action": "commit", "repo": "o/r", "branch": "feature",
                                         "message": "x", "files": [{"path": "a", "content": "1"}]})
    assert ergebnis.get("error", "").startswith("Der Branch hat inzwischen neue Commits")


def test_pull_request_and_comment(github) -> None:
    box, fake, fragen, _ = github
    pr = box.call("github_write", {"action": "pull_request", "repo": "o/r", "branch": "fix",
                                   "title": "Fix", "body": "Beschreibung"})
    assert {k: pr[k] for k in ("number", "url", "state")} == {
        "number": 7, "url": "https://github.com/o/r/pull/7", "state": "open"}
    assert "nur Daten" in pr["_quelle"], "GitHub-Antworten sind fremder Inhalt"
    anfrage = next(c[2] for c in fake.writes() if c[1].endswith("/pulls"))
    assert anfrage["base"] == "main" and anfrage["head"] == "fix"
    kommentar = box.call("github_write", {"action": "comment", "repo": "o/r", "number": 5,
                                          "body": "Sieht gut aus."})
    assert kommentar["comment"] == 9 and len(fragen) == 2
    assert "merge" not in github_write.ACTIONS, "Mergen macht der Mensch auf GitHub"


def test_reading_only_has_no_write_tool(github) -> None:
    box, fake, _, _ = github
    addons.set_rights(box.settings, "github", {"inhalte": "ja"})
    assert "aus" in box.call("github_write", {"action": "branch", "repo": "o/r"})["error"]
    fake.private = True
    addons.set_rights(box.settings, "github", {"inhalte": "aendern", "repos": "oeffentlich"})
    assert "privat" in box.call("github_write", {"action": "branch", "repo": "o/r"})["error"]


class FakeBox:
    """Eine VM, die nur aufzeichnet: Dateien, Befehle, Ausgaben."""

    def __init__(self, diff: list[dict[str, Any]] | None = None) -> None:
        self.gelegt: dict[str, bytes] = {}
        self.befehle: list[str] = []
        self.diff = diff or []
        self.dateien = {"/work/r/src/a.py": b"neu\n"}

    def put_bytes(self, path: str, data: bytes) -> dict[str, Any]:
        self.gelegt[path] = data
        return {"written": path}

    def run(self, command: str, timeout: int = 0) -> Any:
        self.befehle.append(command)
        if command.endswith(" diff"):
            return SimpleNamespace(exit_code=0, stdout=json.dumps({"changes": self.diff}))
        if command.endswith(" write"):
            return SimpleNamespace(exit_code=0, stdout=json.dumps({"files": 3}))
        return SimpleNamespace(exit_code=0, stdout="")

    def get_bytes(self, path: str, max_bytes: int = 0) -> bytes:
        return self.dateien[path]


def test_checkout_and_push_keep_the_token_out_of_the_vm(github, monkeypatch) -> None:
    box, fake, fragen, _ = github
    vm = FakeBox([{"path": "src/a.py", "status": "geändert", "mode": "100644", "size": 4}])
    box.github_vm_ready = lambda: True
    monkeypatch.setattr(box, "_sandbox", lambda: vm)
    holen = box.call("github_write", {"action": "checkout", "repo": "o/r"})
    assert holen["dir"] == "/work/r" and holen["sha"] == BASE
    archiv = next(iter(vm.gelegt.values()))
    assert TOKEN.encode() not in archiv
    with tarfile.open(fileobj=io.BytesIO(archiv)) as tar:
        assert tar.getnames() == ["o-r-123/README.md"]
    assert all(TOKEN not in befehl for befehl in vm.befehle)
    gepusht = box.call("github_write", {"action": "push", "repo": "o/r", "dir": "r",
                                        "message": "Änderung"})
    assert gepusht["commit"] == "5" * 40 and gepusht["branch"].startswith("aquaticy/")
    assert "src/a.py" in fragen[-1]
    commit = next(c[2] for c in fake.writes() if c[1].endswith("/git/commits"))
    assert commit["parents"] == [BASE], "Basis kommt vom Rechner, nicht aus der VM"
    eintrag = json.loads((box.settings.data_dir / "github-checkouts.json").read_text())
    assert eintrag["/work/r"]["sha"] == "5" * 40


def test_push_needs_a_checkout_from_this_repo(github, monkeypatch) -> None:
    box, fake, _, _ = github
    box.github_vm_ready = lambda: True
    monkeypatch.setattr(box, "_sandbox", lambda: FakeBox())
    ergebnis = box.call("github_write", {"action": "push", "repo": "o/r", "dir": "anders",
                                         "message": "x"})
    assert "checkout" in ergebnis["error"] and not fake.writes()
    box.github_vm_ready = lambda: False
    assert "Code-Chat" in box.call("github_write", {"action": "checkout",
                                                    "repo": "o/r"})["error"]


def test_tarball_redirect_only_to_codeload() -> None:
    def boese(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://evil.example/x.tgz"})

    with (httpx.Client(transport=httpx.MockTransport(boese)) as client,
          pytest.raises(github_write.WriteError, match="unerwartete")):
        github_write.download_tarball(client, {}, "o/r", BASE)


def test_vm_helpers_extract_safely_and_find_changes(tmp_path: Path) -> None:
    puffer = io.BytesIO()
    with tarfile.open(fileobj=puffer, mode="w:gz") as tar:
        for name, inhalt in (("top/a.txt", b"eins"), ("top/sub/b.txt", b"zwei"),
                             ("top/../boese.txt", b"x"), ("top/.git/config", b"x")):
            info = tarfile.TarInfo(name)
            info.size = len(inhalt)
            tar.addfile(info, io.BytesIO(inhalt))
        link = tarfile.TarInfo("top/link")
        link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
        tar.addfile(link)
    archiv = tmp_path / "a.tar.gz"
    archiv.write_bytes(puffer.getvalue())
    ziel = tmp_path / "work" / "r"
    subprocess.run([sys.executable, "-c", github_write.EXTRACT, str(archiv), str(ziel)],
                   check=True)
    assert (ziel / "a.txt").read_bytes() == b"eins" and (ziel / "sub/b.txt").exists()
    assert not (tmp_path / "work" / "boese.txt").exists() and not (ziel / "link").exists()
    assert not (ziel / ".git").exists() and not archiv.exists()

    def manifest(art: str) -> dict[str, Any]:
        aus = subprocess.run([sys.executable, "-c", github_write.MANIFEST, str(ziel),
                              json.dumps(list(github_write.SKIP)), art],
                             capture_output=True, text=True, check=True)
        return json.loads(aus.stdout)

    assert manifest("write") == {"files": 2}
    (ziel / "a.txt").write_bytes(b"geaendert")
    (ziel / "neu.txt").write_bytes(b"neu")
    (ziel / "sub/b.txt").unlink()
    (ziel / "__pycache__").mkdir()
    (ziel / "__pycache__/x.pyc").write_bytes(b"x")
    aenderungen = {c["path"]: c["status"] for c in manifest("diff")["changes"]}
    assert aenderungen == {"a.txt": "geändert", "neu.txt": "neu", "sub/b.txt": "gelöscht"}
    again = subprocess.run([sys.executable, "-c", github_write.EXTRACT, str(archiv), str(ziel)],
                           capture_output=True, text=True)
    assert again.returncode != 0


def test_reading_commits_and_comparisons(settings: Settings) -> None:
    routes = {
        f"/repos/o/r/commits/{BASE}": {
            "sha": BASE, "commit": {"message": "Fix", "author": {"name": "Jonas"}},
            "parents": [{"sha": TREE}], "stats": {"additions": 1, "deletions": 0},
            "files": [{"filename": "a.py", "status": "modified", "additions": 1,
                       "deletions": 0, "patch": "+print(1)"}]},
        "/repos/o/r/compare/main...fix": {
            "status": "ahead", "ahead_by": 1, "behind_by": 0,
            "commits": [{"sha": BASE, "commit": {"message": "Fix"}}], "files": []},
        "/repos/o/r/commits": [{"sha": BASE, "commit": {"message": "Fix", "author": {}}}],
        "/repos/o/r": {"private": False},
    }

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        wert = routes.get(request.url.path)
        return httpx.Response(200, json=wert) if wert is not None else httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        commit = addons.github_call(TOKEN, "commit", repo="o/r", ref=BASE, client=client)
        assert commit["sha"] == BASE and commit["dateien"][0]["patch"] == "+print(1)"
        vergleich = addons.github_call(TOKEN, "vergleich", repo="o/r", ref="fix", base="main",
                                       client=client)
        assert vergleich["voraus"] == 1 and vergleich["commits"][0]["sha"] == BASE
        liste = addons.github_call(TOKEN, "commits", repo="o/r", client=client)
        assert liste["commits"][0]["sha"] == BASE, "voller SHA"
        assert "base" in addons.github_call(TOKEN, "vergleich", repo="o/r", ref="fix",
                                            client=client)["error"]


# -- Messenger -----------------------------------------------------------------------------------
@pytest.mark.parametrize("text,eigen", [
    ("[Aquaticy] Hallo", True), ("Aquaticy] Hallo", True),
    ("[Aquaticy Secure Pro]\nStatus", True), ("[Aquaticy Coworker Ava]\nText", True),
    ("Aquaticy, wie wird das Wetter?", False), ("[Aquaticy Hacker] x", False),
])
def test_own_messages_are_recognised(text: str, eigen: bool) -> None:
    assert bridge.is_own_text(text) is eigen


def test_only_known_labels_are_used() -> None:
    assert bridge.to_chat_text("x", signature="[Aquaticy Secure Pro]") == \
        "[Aquaticy Secure Pro]\nx"
    assert bridge.to_chat_text("x", signature="[Bank]") == "[Aquaticy] x"


@pytest.mark.parametrize("text,erwartet", [
    ("wechsel auf das Modell Qwen 2 2b", ("switch", "Qwen 2 2b")),
    ("Kannst du bitte auf das Modell qwen3:8b wechseln", ("switch", "qwen3:8b")),
    ("switch to model gemma3", ("switch", "gemma3")),
    ("wechsel in den Pro-Modus", ("pro", "")),
    ("setz den Ort auf Köln", ("location", "Köln")),
    ("zeig meine Notizen", ("notes", "")),
    ("Wie wechsel ich das Modell bei ChatGPT?", None),
    ("vergiss alles über mich", None),
    ("/model x", None),
])
def test_plain_sentences_become_commands(text: str, erwartet: Any) -> None:
    assert natural_command(text) == erwartet


def test_plain_model_switch_runs_the_switch_command(settings, monkeypatch) -> None:
    gesehen: list[tuple[str, str]] = []
    antworter = bridge.AgentAnswerer(lambda: settings)
    monkeypatch.setattr(antworter, "_command", lambda name, argument, *a: gesehen.append(
        (name, argument)) or "ok")
    config = bridge.load_config(settings)["whatsapp"]
    entscheidung = bridge.Decision(True, trusted=True, selbst=True)
    assert antworter("Wechsel auf das Modell qwen3", entscheidung, config, "k",
                     "whatsapp") == "ok"
    assert gesehen == [("switch", "qwen3")]


def test_secure_pro_orders_by_messenger(owner, monkeypatch) -> None:  # noqa: F811
    session, settings = owner
    secure_pro.configure(settings.data_dir, NETZ)
    aus = web.secure_messenger_order(session, "status", "Secure Pro Status")
    assert aus.startswith("[Aquaticy Secure Pro]\nAuftrag: Secure Pro Status\n")
    assert "aus" in aus
    secure_pro.set_options(settings.data_dir, {"messenger": True})
    assert "Secure Pro ist an." in web.secure_messenger_order(session, "", "Secure Pro")
    angefordert: list[bool] = []
    monkeypatch.setattr(web, "SECURE_WATCHER", SimpleNamespace(
        request=lambda: angefordert.append(True) or True, snapshot=lambda: {}))
    assert "gestartet" in web.secure_messenger_order(session, "prüfen", "Secure Pro prüfen")
    assert angefordert == [True]
    aufgabe = web.secure_messenger_order(session, "Aufgabe: Melde neue Geräte", "x")
    assert "Aufgabe gespeichert" in aufgabe
    assert "kenne ich nicht" in web.secure_messenger_order(session, "tanz", "Secure Pro tanz")
    session.ultra = False
    assert "Besitzer" in web.secure_messenger_order(session, "status", "Secure Pro Status")


def test_coworker_orders_by_messenger(owner, monkeypatch) -> None:  # noqa: F811
    from aquaticy import coworker as cwm

    session, settings = owner
    session.plan = "ultra"
    store = cwm.CoworkerStore(settings.db_path)
    kollege = store.add("Ava", "Fasse meine Mails zusammen.", plan="ultra")
    monkeypatch.setattr(web, "AIGUARD", None)
    geweckt: list[bool] = []
    monkeypatch.setattr(web, "_coworker_scheduler", lambda s: SimpleNamespace(
        wake=lambda: geweckt.append(True)))
    aus = web.coworker_messenger_order(session, None, "ava", "Schau nach Mails", "x")
    assert aus.startswith("[Aquaticy Coworker Ava]\n") and "keine Aufträge" in aus
    store.set_messenger_orders(kollege.id, True)
    an = web.coworker_messenger_order(session, None, "Ava", "Schau nach Mails",
                                      "Coworker Ava: Schau nach Mails")
    assert "Angenommen" in an and "Auftrag: Coworker Ava: Schau nach Mails" in an
    assert store.unread_messages(kollege.id)[0]["text"] == "Schau nach Mails" and geweckt
    assert "gibt es nicht" in web.coworker_messenger_order(session, None, "Bob", "x", "x")
    assert cwm.view(store, store.get(kollege.id))["messenger_orders"] is True


def test_orders_are_routed_by_their_prefix(monkeypatch) -> None:
    gesehen: list[tuple[str, ...]] = []
    monkeypatch.setattr(web, "secure_messenger_order",
                        lambda s, befehl, auftrag: gesehen.append(("secure", befehl)) or "s")
    monkeypatch.setattr(web, "coworker_messenger_order",
                        lambda s, a, name, inhalt, auftrag: gesehen.append(
                            ("cw", name, inhalt)) or "c")
    route = web._messenger_orders(lambda: None, None)
    assert route("Secure Pro prüfen") == "s" and route("/securepro status") == "s"
    assert route("Secure Pro, was ist ARP-Spoofing?") is None, "eine Frage, kein Befehl"
    assert route("Coworker Ava: Schau nach Mails") == "c"
    assert route("coworker Max Mustermann: mach was") == "c"
    assert route("Wie wird das Wetter?") is None
    assert gesehen == [("secure", "prüfen"), ("secure", "status"),
                       ("cw", "Ava", "Schau nach Mails"), ("cw", "Max Mustermann", "mach was")]


def test_orders_only_in_the_own_chat(settings) -> None:
    from aquaticy.bridge_native import NativeResponder

    aufrufe: list[str] = []
    antwort = NativeResponder(lambda: settings, lambda *a: "Modell",
                              orders=lambda text: aufrufe.append(text) or "Auftrag")
    msg = SimpleNamespace(audio=None, messenger="whatsapp")
    eigen = bridge.Decision(True, trusted=True, selbst=True)
    fremd = bridge.Decision(True, trusted=True, selbst=False)
    gruppe = bridge.Decision(True, trusted=True, selbst=True, group=True)
    config = bridge.load_config(settings)["whatsapp"]
    assert antwort._reply("Secure Pro Status", eigen, config, "k", msg) == "Auftrag"
    assert antwort._reply("Secure Pro Status", fremd, config, "k", msg) == "[Aquaticy] Modell"
    assert antwort._reply("Secure Pro Status", gruppe, config, "k", msg) == "[Aquaticy] Modell"
    assert aufrufe == ["Secure Pro Status"]


# -- Coworker und Einstellungen aus dem Chat ------------------------------------------------------
def test_a_recurring_order_becomes_a_coworker_after_yes(settings) -> None:
    box = Toolbox(settings)
    try:
        angelegt: list[dict[str, Any]] = []
        box.coworker_creator = lambda nutzlast: angelegt.append(nutzlast) or {"ok": True}
        fragen: list[str] = []
        box.ask_handler = lambda frage, optionen: fragen.append(frage) or "ja"
        ergebnis = box.call("coworker_create", {
            "name": "Nora", "goal": "Nenne mir jeden Morgen die neusten Nachrichten.",
            "rhythm": "daily", "hour": 7, "minute": 30})
        assert ergebnis["created"] == "Nora" and "07:30" in ergebnis["when"]
        assert angelegt == [{"name": "Nora",
                             "goal": "Nenne mir jeden Morgen die neusten Nachrichten.",
                             "schedule": {"kind": "research", "rhythm": "daily", "hour": 7,
                                          "minute": 30, "weekday": 0}}]
        assert "Nora" in fragen[0] and "täglich um 07:30" in fragen[0]
        box.ask_handler = lambda frage, optionen: "nein"
        assert "error" in box.call("coworker_create", {"name": "X", "goal": "y",
                                                       "rhythm": "daily"})
        assert len(angelegt) == 1
        assert "error" in box.call("coworker_create", {"name": "X", "goal": "y",
                                                       "rhythm": "minuetlich"})
    finally:
        box.close()


def test_settings_for_a_task_are_asked_first(settings) -> None:
    box = Toolbox(settings)
    try:
        fragen: list[str] = []
        box.ask_handler = lambda frage, optionen: fragen.append(frage) or "nein"
        abgelehnt = box.call("change_setting", {"setting": "sprache", "value": "en",
                                                "reason": "auftrag", "why": "englische Quellen"})
        assert "error" in abgelehnt and "englische Quellen" in fragen[0]
        box.ask_handler = lambda frage, optionen: fragen.append(frage) or "ja"
        assert box.call("change_setting", {"setting": "sprache", "value": "en",
                                           "reason": "auftrag"})["changed"]
        anzahl = len(fragen)
        assert box.call("change_setting", {"setting": "sprache", "value": "de"})["changed"]
        assert len(fragen) == anzahl, "ausdruecklich gewuenscht: keine Rueckfrage"
        assert "error" in box.call("change_setting", {"setting": "AQUATICY_LAN_ENABLED",
                                                      "value": "true", "reason": "auftrag"})
    finally:
        box.close()


def test_the_chat_offers_coworker_creation_only_with_a_creator(settings) -> None:
    from aquaticy.agent import Agent

    agent = Agent(settings)
    try:
        namen = {s["function"]["name"] for s in agent.tools}
        assert "coworker_create" not in namen
        agent.toolbox.coworker_creator = lambda nutzlast: {"ok": True}
        assert "coworker_create" in {s["function"]["name"] for s in agent.tools}
    finally:
        agent.close()


# -- Secure Pro -----------------------------------------------------------------------------------
def test_devices_are_recognised() -> None:
    assert secure_devices.mac_info("b8:27:eb:12:34:56")["vendor"] == "Raspberry Pi"
    assert secure_devices.mac_info("3a:11:22:33:44:55")["random_mac"] is True
    assert secure_devices.mac_info("02:42:ac:11:00:02")["vendor"] == "Docker"
    assert secure_devices.mac_info("kaputt") == {}
    router = secure_devices.describe({"address": "192.168.1.1", "mac": ""}, "192.168.1.1")
    assert router["kind"] == "Router"
    drucker = secure_devices.describe({"address": "192.168.1.9", "ports": [9100]})
    assert drucker["kind"] == "Drucker"


def test_known_devices_are_validated() -> None:
    sauber = secure_devices.clean_known({"AA:BB:CC:DD:EE:FF": "Laptop <b>", "8.8.8.8": "x",
                                         "192.168.1.5": "Drucker", "kaputt": "y", "a": ""})
    assert sauber == {"aa:bb:cc:dd:ee:ff": "Laptop b", "192.168.1.5": "Drucker"}


def test_score_counts_findings_and_settings() -> None:
    gut, note = secure_devices.score([], [], {"watch": True, "packets": True, "nmap": True})
    assert (gut, note) == (100, "A")
    schlecht, note = secure_devices.score(
        [{"kind": "malware", "level": "wichtig"}] * 6, [], {"watch": False})
    assert schlecht == 0 and note == "E"


def test_named_devices_are_no_new_device_alarm(tmp_path: Path, monkeypatch) -> None:
    from aquaticy import secure_network

    secure_pro.configure(tmp_path, NETZ)
    geraete = [lan.Device("192.168.1.2", ports=[443])]
    nachbarn = [{"address": "192.168.1.2", "mac": "b8:27:eb:00:00:01", "ports": [],
                 "active": False, "source": "Nachbartabelle"}]
    monkeypatch.setattr(lan, "scan", lambda *a, **kw: list(geraete))
    monkeypatch.setattr(secure_network, "neighbours", lambda subnet: [dict(n) for n in nachbarn])
    watcher = secure_pro.Watcher(tmp_path, lambda text: True)
    watcher.tick()
    assert watcher.snapshot()["devices"][0]["vendor"] == "Raspberry Pi"
    secure_pro.name_device(tmp_path, "192.168.1.3", "b8:27:eb:00:00:02", "Pi im Keller")
    geraete.append(lan.Device("192.168.1.3", ports=[22]))
    nachbarn.append({"address": "192.168.1.3", "mac": "b8:27:eb:00:00:02", "ports": [],
                     "active": False, "source": "Nachbartabelle"})
    watcher.tick()
    assert not any("192.168.1.3" in f for f in watcher.snapshot()["findings"])
    assert watcher.snapshot()["devices"][1]["name"] == "Pi im Keller"
    geraete.append(lan.Device("192.168.1.4", ports=[80]))
    nachbarn.append({"address": "192.168.1.4", "mac": "b8:27:eb:00:00:03", "ports": [],
                     "active": False, "source": "Nachbartabelle"})
    watcher.tick()
    assert "Neues Gerät: 192.168.1.4 (Raspberry Pi)" in watcher.snapshot()["findings"]
    with pytest.raises(ValueError, match="außerhalb"):
        secure_pro.name_device(tmp_path, "10.0.0.1", "", "x")


def test_history_and_score_are_kept(tmp_path: Path, monkeypatch) -> None:
    secure_pro.configure(tmp_path, NETZ)
    geraete = [lan.Device("192.168.1.2", ports=[23])]
    monkeypatch.setattr(lan, "scan", lambda *a, **kw: list(geraete))
    watcher = secure_pro.Watcher(tmp_path, lambda text: True)
    watcher.tick()
    verlauf = secure_pro.read_history(tmp_path)
    assert any("Telnet" in e["text"] for e in verlauf["events"]) and verlauf["scores"]
    erster = watcher.snapshot()["score"]
    geraete[0].ports.remove(23)
    watcher.tick()
    assert watcher.snapshot()["score"] > erster and watcher.snapshot()["trend"] > 0
    if sys.platform != "win32":
        assert secure_pro.history_path(tmp_path).stat().st_mode & 0o777 == 0o600


def test_turning_off_deletes_the_history(owner) -> None:  # noqa: F811
    session, settings = owner
    secure_pro.configure(settings.data_dir, NETZ)
    secure_pro.history_path(settings.data_dir).write_text("{}")
    assert web.feature_action(session, {"action": "configure", "enabled": False})[1] == 200
    assert not secure_pro.history_path(settings.data_dir).exists()


def test_upnp_answers_count_only_from_the_own_net(monkeypatch) -> None:
    antworten = [
        (b"HTTP/1.1 200 OK\r\nST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n",
         ("192.168.1.1", 1900)),
        (b"HTTP/1.1 200 OK\r\nST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n",
         ("10.0.0.1", 1900)),
        (b"HTTP/1.1 200 OK\r\nST: upnp:rootdevice\r\n", ("192.168.1.7", 1900)),
    ]

    class Sock:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def setsockopt(self, *a):
            pass

        def settimeout(self, *a):
            pass

        def sendto(self, data, ziel):
            import ipaddress

            assert ipaddress.IPv4Address(ziel[0]) in ipaddress.IPv4Network(NETZ)
            assert ziel[1] == 1900 and b"M-SEARCH" in data

        def recvfrom(self, n):
            if antworten:
                return antworten.pop(0)
            raise TimeoutError

    monkeypatch.setattr(secure_devices.socket, "socket", lambda *a: Sock())
    assert secure_devices.upnp_gateways(NETZ, "192.168.1.1", 0.5) == ["192.168.1.1"]


def test_settings_show_messenger_switches() -> None:
    html = (Path(web.__file__).parent / "webui.html").read_text(encoding="utf-8")
    assert 'id="secure-messenger"' in html and 'id="secure-history"' in html
    assert 'action: "messenger", id: cw.id' in html


def test_coworkers_never_get_github_write_or_new_coworkers() -> None:
    from aquaticy import coworker as cwm

    assert {"github_write", "coworker_create"} <= cwm.FORBIDDEN


def test_a_sentence_about_coworkers_is_no_order(settings, monkeypatch) -> None:
    from aquaticy import coworker as cwm

    gesehen: list[str] = []
    monkeypatch.setattr(web, "coworker_messenger_order",
                        lambda s, a, name, inhalt, auftrag: gesehen.append(name) or "c")
    sitzung = SimpleNamespace(settings=lambda: settings)
    route = web._messenger_orders(lambda: sitzung, None)
    assert route("Coworker sind toll, oder?") is None
    cwm.CoworkerStore(settings.db_path).add("Ava", "Fasse meine Mails zusammen.", plan="ultra")
    assert route("Coworker Ava schau nach Mails") == "c" and gesehen == ["Ava"]


def test_a_tag_checkout_pushes_to_a_new_branch(github, monkeypatch) -> None:
    box, _, _, _ = github
    vm = FakeBox([{"path": "src/a.py", "status": "geändert", "mode": "100644", "size": 4}])
    box.github_vm_ready = lambda: True
    monkeypatch.setattr(box, "_sandbox", lambda: vm)
    box.call("github_write", {"action": "checkout", "repo": "o/r", "ref": "v1.0"})
    gepusht = box.call("github_write", {"action": "push", "repo": "o/r", "dir": "r",
                                        "message": "x"})
    assert gepusht["branch"].startswith("aquaticy/"), "kein Branch namens v1.0"


# -- Alte Version laeuft noch (Terminal 15.0.0, Browser 14.3.4) ----------------------------------
def test_the_running_version_is_read_from_the_page(monkeypatch) -> None:
    from aquaticy import old_server

    seite = '<script>window.__AQUATICY_VERSION__ = "14.3.4 Luna";</script>'
    echt = httpx.Client
    monkeypatch.setattr(old_server.httpx, "Client", lambda **kw: echt(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=seite)), **kw))
    assert old_server.running_version(8765) == "14.3.4 Luna"
    monkeypatch.setattr(old_server.httpx, "Client", lambda **kw: echt(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text="anderes")), **kw))
    assert old_server.running_version(8765) == ""


@pytest.mark.parametrize("laeuft", ["14.3.4 Luna", "15.0.0"])
def test_web_start_replaces_another_aquaticy(monkeypatch, laeuft) -> None:
    from aquaticy import cli, old_server

    monkeypatch.setattr(old_server, "running_version", lambda port: laeuft)
    monkeypatch.setattr(old_server, "listener_pids", lambda port: [4242])
    monkeypatch.setattr(old_server, "is_aquaticy", lambda pid: True)
    beendet: list[int] = []
    monkeypatch.setattr(old_server, "stop", lambda pid: beendet.append(pid) or True)
    monkeypatch.setattr(cli.typer, "confirm", lambda *a, **kw: pytest.fail("ohne Rückfrage"))
    cli._altes_aquaticy(8765)
    assert beendet == [4242], "der andere Prozess wird beendet, der neue startet"


def test_web_start_leaves_foreign_programs_alone(monkeypatch) -> None:
    from aquaticy import cli, old_server

    monkeypatch.setattr(old_server, "running_version", lambda port: "")
    monkeypatch.setattr(old_server, "listener_pids", lambda port: [4242])
    monkeypatch.setattr(old_server, "stop", lambda pid: pytest.fail("kein Aquaticy"))
    cli._altes_aquaticy(8765)
    monkeypatch.setattr(old_server, "running_version", lambda port: "14.3.4 Luna")
    monkeypatch.setattr(old_server, "is_aquaticy", lambda pid: False)
    cli._altes_aquaticy(8765)


def test_only_aquaticy_processes_are_stopped(monkeypatch) -> None:
    import os

    from aquaticy import old_server

    assert not old_server.is_aquaticy(os.getpid()), "nie sich selbst"
    getoetet: list[int] = []
    monkeypatch.setattr(old_server, "is_aquaticy", lambda pid: False)
    monkeypatch.setattr(old_server.os, "kill", lambda pid, sig: getoetet.append(pid))
    assert old_server.stop(99999) is False and getoetet == []


def test_the_page_says_when_a_newer_version_is_installed(monkeypatch) -> None:
    from aquaticy import old_server

    monkeypatch.setattr(old_server, "installed_label", lambda: "99.0.0")
    assert web.installed_version() == "99.0.0"
    monkeypatch.setattr(old_server, "installed_label", lambda: web.VERSION_LABEL)
    assert web.installed_version() == ""
    html = (Path(web.__file__).parent / "webui.html").read_text(encoding="utf-8")
    assert "window.__AQUATICY_INSTALLED__" in html
