"""10.2.0 Luna: Serverlast aufteilen -- ein Modell, verteilt auf die Server des Verbunds.

Zwei gekoppelte Server in einem Prozess. Statt llama.cpp laufen kleine gestellte
Programme: der "rpc-server" gibt jedes Paket umgedreht zurueck, der
"llama-server" schreibt auf, womit er gestartet wurde, und spricht einmal mit
jedem rpc-server. So laesst sich der ganze Weg pruefen -- Tunnel, Anmeldung,
Verschluesselung, Prozesse und die Zuteilung der Konten.
"""

from __future__ import annotations

import base64
import json
import socket
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from aquaticy import cluster, sharding, web
from aquaticy.config import SPLIT_MODEL_ID, Settings
from tests.test_cluster import _konto, _verbinden, _warte, verbund  # noqa: F401

FAKE_RPC = '''
import socket, sys, threading
args = sys.argv[1:]
if "--help" in args:
    print("  -c,      --cache          enable local file cache")
    sys.exit(0)
host, port = args[args.index("-H") + 1], int(args[args.index("-p") + 1])
srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind((host, port))
srv.listen()
def echo(conn):
    with conn:
        while True:
            daten = conn.recv(65536)
            if not daten:
                return
            conn.sendall(daten[::-1])
while True:
    conn, _ = srv.accept()
    threading.Thread(target=echo, args=(conn,), daemon=True).start()
'''

FAKE_LLAMA = '''
import http.server, json, os, socket, sys
args = sys.argv[1:]
port = int(args[args.index("--port") + 1])
ziele = args[args.index("--rpc") + 1].split(",") if "--rpc" in args else []
antworten = []
for ziel in ziele:
    host, p = ziel.rsplit(":", 1)
    nachricht = ("hallo-" + p).encode()
    with socket.create_connection((host, int(p)), timeout=20) as s:
        s.sendall(nachricht)
        daten = b""
        while len(daten) < len(nachricht):
            stueck = s.recv(65536)
            if not stueck:
                break
            daten += stueck
    antworten.append([ziel, daten.decode()])
with open(os.environ["FAKE_LLAMA_RECORD"], "w") as f:
    json.dump({"args": args, "key": os.environ.get("LLAMA_API_KEY"), "rpc": antworten}, f)
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == "/health" else 404)
        self.end_headers()
        self.wfile.write(b"{}")
    def log_message(self, *a):
        pass
http.server.HTTPServer(("127.0.0.1", port), H).serve_forever()
'''


def _programm(ordner: Path, name: str, code: str) -> Path:
    pfad = ordner / name
    pfad.write_text(f"#!{sys.executable}\n{code}")
    pfad.chmod(0o755)
    return pfad


class Echo:
    """Ein Stellvertreter fuer den rpc-server: gibt alles umgedreht zurueck."""

    def __init__(self) -> None:
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._echo, args=(conn,), daemon=True).start()

    @staticmethod
    def _echo(conn: socket.socket) -> None:
        with conn:
            while True:
                daten = conn.recv(65536)
                if not daten:
                    return
                conn.sendall(daten[::-1])


def _empfangen(sock: socket.socket, anzahl: int) -> bytes:
    daten = b""
    while len(daten) < anzahl:
        stueck = sock.recv(1 << 20)
        if not stueck:
            break
        daten += stueck
    return daten


@pytest.fixture
def paar(verbund, monkeypatch):  # noqa: F811
    """Master A und Mitglied B, gekoppelt; B antwortet ueber echtes HTTP."""
    a, b, _, _, gefragt, neustarts = verbund
    _verbinden(a, b, gefragt, neustarts)
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    http_port = server.server_address[1]
    # A erreicht B unter dem echten Port; die Verbund-Aufrufe laufen weiter im Speicher.
    a._transport.knoten[http_port] = b
    with a._lock:
        for m in a.state["cluster"]["members"]:
            if m["node"] == b.node_id:
                m["address"], m["port"] = "127.0.0.1", http_port
    monkeypatch.setattr(web, "CLUSTER", b)
    try:
        yield a, b
    finally:
        server.shutdown()
        server.server_close()


class Rpc:
    """Was web.SHARDING fuer den Tunnel-Eingang braucht."""

    def __init__(self, port: int) -> None:
        self.port = port

    def rpc_port(self) -> int:
        return self.port


# -- Der Tunnel ---------------------------------------------------------------------------
def test_frames_are_numbered_and_tamper_proof() -> None:
    hin = sharding.Richtung(b"k" * 32)
    zurueck = sharding.Richtung(b"k" * 32)
    eins, zwei = hin.seal(b"eins"), hin.seal(b"zwei")
    # Vertauscht: das zweite Stueck passt nicht an die erste Stelle.
    with pytest.raises(sharding.TunnelError):
        zurueck.open(zwei[4:])
    leser = sharding.Richtung(b"k" * 32)
    assert leser.open(eins[4:]) == b"eins"
    kaputt = bytearray(zwei[4:])
    kaputt[-1] ^= 1
    with pytest.raises(sharding.TunnelError):
        leser.open(bytes(kaputt))
    with pytest.raises(sharding.TunnelError):
        sharding.Richtung(b"x" * 32).open(eins[4:])


def test_oversized_frames_are_refused() -> None:
    import io

    a, b = socket.socketpair()
    with a, b, pytest.raises(sharding.TunnelError):
        sharding.pump_open(io.BytesIO((sharding.FRAME_MAX + 1).to_bytes(4, "big")), a,
                           sharding.Richtung(b"k" * 32))


def test_each_tunnel_gets_its_own_keys() -> None:
    eins = sharding.tunnel_keys(b"l" * 32, b"a" * 16, b"b" * 16)
    zwei = sharding.tunnel_keys(b"l" * 32, b"a" * 16, b"c" * 16)
    assert eins[0] != eins[1] and eins != zwei


def test_the_tunnel_carries_data_both_ways_encrypted(paar, monkeypatch) -> None:
    a, b = paar
    a.set_split(True, "testmodell")
    assert b.split_on, "die Einstellung kommt mit der Mitgliederliste"
    echo = Echo()
    monkeypatch.setattr(web, "SHARDING", Rpc(echo.port))
    tunnel = sharding.Tunnel(a, b.node_id)
    try:
        with socket.create_connection(("127.0.0.1", tunnel.port), timeout=20) as s:
            s.settimeout(20)
            klein = b"hallo verbund"
            s.sendall(klein)
            assert _empfangen(s, len(klein)) == klein[::-1]
        # Mehr als ein Stueck: ein ganzes Megabyte am Stueck.
        with socket.create_connection(("127.0.0.1", tunnel.port), timeout=20) as s:
            s.settimeout(20)
            gross = bytes(range(256)) * 4096
            s.sendall(gross)
            antwort = _empfangen(s, len(gross))
            assert len(antwort) == len(gross)
    finally:
        tunnel.stop()


def test_the_tunnel_answers_only_the_master_with_the_pairing_key(paar, monkeypatch) -> None:
    a, b = paar
    a.set_split(True, "testmodell")
    # Mit dem Gruppenschluessel -- den kennt jedes Mitglied -- geht es nicht.
    gruppe, _ = a._wrap(a.key, "tunnel", {"c": base64.b64encode(b"z" * 16).decode()})
    with pytest.raises(cluster.ClusterError):
        b.open_tunnel(gruppe, "127.0.0.1")
    body, _, _ = a.tunnel_request(b.node_id)
    with pytest.raises(cluster.ClusterError, match=r"Kein Tunnel"):
        b.open_tunnel(body, "8.8.8.8")
    link, zufall = b.open_tunnel(body, "127.0.0.1")
    assert len(zufall) == 16 and link == base64.b64decode(b.state["link"])
    with pytest.raises(cluster.ClusterError, match="wiederholt"):
        b.open_tunnel(body, "127.0.0.1")
    # Ein Mitglied oeffnet keine Tunnel, und ohne Aufteilen gibt es keine.
    with pytest.raises(cluster.ClusterError):
        b.tunnel_request(a.node_id)
    a.set_split(False)
    body, _, _ = a.tunnel_request(b.node_id)
    with pytest.raises(cluster.ClusterError, match="Kein Tunnel"):
        b.open_tunnel(body, "127.0.0.1")


def test_a_refused_tunnel_never_switches_protocols(paar, monkeypatch) -> None:
    """Ohne gueltige Anmeldung bleibt es eine gewoehnliche Absage (403)."""
    a, b = paar
    a.set_split(True, "testmodell")
    monkeypatch.setattr(web, "SHARDING", Rpc(Echo().port))
    ziel = a.member(b.node_id)
    falsch = b'{"from": "x", "box": "AAAA"}'
    with socket.create_connection(("127.0.0.1", ziel["port"]), timeout=10) as s:
        s.sendall(b"POST /cluster/tunnel HTTP/1.1\r\nHost: x\r\nContent-Length: "
                  + str(len(falsch)).encode() + b"\r\n\r\n" + falsch)
        antwort = s.recv(4096)
    assert b" 403 " in antwort.split(b"\r\n", 1)[0] and b" 101 " not in antwort


# -- Wer wohin gehoert --------------------------------------------------------------------
def test_only_the_master_switches_and_only_with_two_servers(verbund) -> None:  # noqa: F811
    a, b, _, _, gefragt, neustarts = verbund
    with pytest.raises(cluster.ClusterError):
        a.set_split(True, "x")  # noch kein Verbund
    _verbinden(a, b, gefragt, neustarts)
    with pytest.raises(cluster.ClusterError, match="Master"):
        b.set_split(True, "x")
    a.set_split(True, "modell")
    assert a.split() == {**a.split(), "on": True, "model": "modell"}
    a.set_split(False)
    assert a.split()["model"] == "modell" and not a.split_on


def test_in_split_mode_every_account_is_served_by_the_master(verbund) -> None:  # noqa: F811
    a, b, _, alt_a, gefragt, neustarts = verbund
    _verbinden(a, b, gefragt, neustarts)
    b.sync_once()
    a.homes[alt_a.id] = b.node_id
    b.homes[alt_a.id] = b.node_id
    a.last_ok[b.node_id] = time.time()
    a.set_split(True, "modell")
    _warte(lambda: a.homes.get(alt_a.id) == a.node_id)
    assert a.assign("neueskonto") == a.node_id
    # Das Mitglied fragt beim Master, statt die alte Zuteilung zu nehmen.
    b.homes["neueskonto"] = b.node_id
    b._local_seen["neueskonto"] = time.time()
    b.last_ok[a.node_id] = time.time()
    assert b.home_for("neueskonto") == a.node_id


# -- Prozesse ------------------------------------------------------------------------------
@pytest.fixture
def programme(tmp_path: Path, monkeypatch) -> Path:
    ordner = tmp_path / "bin"
    ordner.mkdir()
    rpc = _programm(ordner, "rpc-server", FAKE_RPC)
    llama = _programm(ordner, "llama-server", FAKE_LLAMA)
    monkeypatch.setenv(sharding.RPC_ENV, str(rpc))
    monkeypatch.setenv(sharding.SERVER_ENV, str(llama))
    monkeypatch.setenv("FAKE_LLAMA_RECORD", str(tmp_path / "llama.json"))
    monkeypatch.setattr(sharding, "GATHER_SECONDS", 30.0)
    monkeypatch.setattr(sharding, "has_own_accelerator", lambda: False)
    sharding._RPC_CACHE.clear()
    return tmp_path


def test_the_model_runs_split_across_both_servers(paar, programme, monkeypatch) -> None:
    a, b = paar
    modell = programme / "modell.gguf"
    modell.write_bytes(b"GGUF" + bytes(2048))
    monkeypatch.setattr(sharding, "ollama_gguf", lambda name, url: modell)
    mgr_a = sharding.Manager(a, lambda: "http://127.0.0.1:9")
    mgr_b = sharding.Manager(b, lambda: "http://127.0.0.1:9")
    b.hooks.load = lambda: {"split": mgr_b.worker_status()}
    monkeypatch.setattr(web, "SHARDING", mgr_b)
    try:
        a.set_split(True, "testmodell")
        _warte(lambda: (mgr_b.tick(), mgr_b.worker.ready)[1], 20)
        assert mgr_b.rpc_port(), "Mitglied: rpc-server laeuft"

        def bereit() -> bool:
            a.sync_once(full=False)
            mgr_a.tick()
            return mgr_a.ready()

        _warte(bereit, 60)
        aufzeichnung = json.loads((programme / "llama.json").read_text())
        args = aufzeichnung["args"]
        assert args[args.index("--host") + 1] == "127.0.0.1"
        assert "--jinja" in args and args[args.index("-ngl") + 1] == "999"
        ziele = args[args.index("--rpc") + 1].split(",")
        assert len(ziele) == 2 and all(z.startswith("127.0.0.1:") for z in ziele)
        # Der Schluessel steht in der Umgebung, nie auf der Kommandozeile.
        assert aufzeichnung["key"] and aufzeichnung["key"] not in " ".join(args)
        # Beide rpc-server haben geantwortet -- einer davon durch den Tunnel zu B.
        for ziel, antwort in aufzeichnung["rpc"]:
            assert antwort == ("hallo-" + ziel.rsplit(":", 1)[1])[::-1]
        monkeypatch.setattr(sharding, "_AKTIV", mgr_a)  # sonst setzt das Manager.start()
        adresse, schluessel = sharding.endpoint()
        assert adresse.startswith("http://127.0.0.1:") and schluessel == aufzeichnung["key"]
        assert mgr_a.servers() == 2
        ansicht = mgr_a.view()
        assert ansicht["phase"] == "bereit" and ansicht["on"]
        # Ausschalten raeumt auf.
        a.set_split(False)
        mgr_a.tick()
        mgr_b.tick()
        assert not mgr_a.ready() and not mgr_b.worker.running()
    finally:
        mgr_a.stop()
        mgr_b.stop()


def test_rpc_server_only_listens_locally(programme, tmp_path: Path) -> None:
    worker = sharding.RpcWorker(tmp_path)
    try:
        worker.ensure()
        _warte(lambda: (worker.ensure(), worker.ready)[1], 20)
        assert worker._proc is not None
        args = worker._proc.args
        assert args[args.index("-H") + 1] == "127.0.0.1" and "-c" in args
    finally:
        worker.stop()
    assert not worker.running()


def test_a_missing_llama_cpp_is_explained(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(sharding.RPC_ENV, str(tmp_path / "gibt-es-nicht"))
    worker = sharding.RpcWorker(tmp_path)
    worker.ensure()
    assert not worker.ready and "rpc-server" in worker.error


def test_too_little_memory_is_refused(paar, programme, monkeypatch) -> None:
    a, b = paar
    modell = programme / "riesig.gguf"
    modell.write_bytes(b"GGUF")
    monkeypatch.setattr(sharding, "ollama_gguf", lambda name, url: modell)
    monkeypatch.setattr(sharding, "needed_gb", lambda size: 10_000.0)
    monkeypatch.setattr(sharding, "node_memory_gb", lambda: 8.0)
    monkeypatch.setattr(sharding, "GATHER_SECONDS", 0.0)
    a.set_split(True, "riesig")
    a.loads[b.node_id] = {"split": {"ready": True, "mem_gb": 8.0}}
    a.last_ok[b.node_id] = time.time()
    mgr = sharding.Manager(a, lambda: "http://127.0.0.1:9")
    try:
        _warte(lambda: (mgr.tick(), mgr.server.phase == "fehler")[1], 20)
        assert "Zu wenig Speicher" in mgr.server.message and not mgr.ready()
    finally:
        mgr.stop()


def test_ollama_model_file_is_found_from_the_modelfile(tmp_path: Path, monkeypatch) -> None:
    from tests.test_v1003 import compressed_response

    gross = tmp_path / "sha256-gross"
    gross.write_bytes(b"GGUF" + bytes(4096))
    bild = tmp_path / "sha256-bild"
    bild.write_bytes(b"GGUF" + bytes(10))
    kein = tmp_path / "sha256-kein"
    kein.write_bytes(b"nope")

    payload = json.dumps({"modelfile": f"# FROM gemma3:27b\nFROM {gross}\nFROM {bild}\n"
                                      f"FROM {kein}\nFROM relativ/pfad\nTEMPLATE x"}).encode()
    monkeypatch.setattr("httpx.stream", lambda *a, **k: compressed_response(payload, "identity"))
    assert sharding.ollama_gguf("gemma3:27b", "http://127.0.0.1:11434") == gross

    payload = json.dumps({"modelfile": f"FROM {kein}"}).encode()
    with pytest.raises(sharding.ShardError):
        sharding.ollama_gguf("x", "http://127.0.0.1:11434")


# -- Aufrufe und Oberflaeche ----------------------------------------------------------------
def test_calls_go_to_the_local_llama_server_with_its_own_key(monkeypatch) -> None:
    settings = Settings(model=SPLIT_MODEL_ID)
    monkeypatch.setattr(sharding, "endpoint", lambda: ("", ""))
    with pytest.raises(ValueError, match="läuft gerade nicht"):
        settings.llm_kwargs_for(SPLIT_MODEL_ID)
    monkeypatch.setattr(sharding, "endpoint", lambda: ("http://127.0.0.1:5555/v1", "geheim"))
    assert settings.llm_kwargs_for(SPLIT_MODEL_ID) == {
        "api_base": "http://127.0.0.1:5555/v1", "api_key": "geheim"}
    # Auch mit eigenem allgemeinem Schluessel zaehlt es ins Kontingent.
    settings.api_keys["AQUATICY_API_KEY"] = "eigener-schluessel"
    settings.own_key_names = frozenset({"AQUATICY_API_KEY"})
    settings.account_email = "konto@example.org"
    assert settings.key_source(SPLIT_MODEL_ID) == "operator"


def test_only_ultra_on_the_master_switches_split_mode(paar, monkeypatch) -> None:
    a, b = paar

    class Sitzung:
        def __init__(self, ultra: bool) -> None:
            self.ultra = ultra

    monkeypatch.setattr("aquaticy.sharding.ollama_models",
                        lambda url: [{"name": "gemma3:27b", "size_gb": 17.0}])
    monkeypatch.setattr(web, "SHARDING", None)
    assert web.cluster_action(Sitzung(False), {"action": "split", "on": True})[1] == 403
    monkeypatch.setattr(web, "CLUSTER", b)
    antwort, status = web.cluster_action(Sitzung(True), {"action": "split", "on": True,
                                                         "model": "gemma3:27b"})
    assert status == 403 and "Master" in antwort["error"]
    monkeypatch.setattr(web, "CLUSTER", a)
    antwort, status = web.cluster_action(Sitzung(True), {"action": "split", "on": True,
                                                         "model": "gibt-es-nicht"})
    assert status == 400
    antwort, status = web.cluster_action(Sitzung(True), {"action": "split", "on": True,
                                                         "model": "gemma3:27b"})
    assert status == 200 and antwort["split_on"] and a.split()["model"] == "gemma3:27b"


def test_the_ui_has_the_switch_and_explains_it() -> None:
    html = web.UI_FILE.read_text(encoding="utf-8")
    assert 'id="split-on"' in html and 'id="split-model"' in html and 'id="split-restart"' in html
    assert "function splitZeigen(" in html and '{ action: "split", on: an, model: modell }' in html
    assert '"Serverlast aufteilen": "Split server load"' in html
