"""11.3.2 Terra: Tailscale-Ziele, MagicDNS und echte IPv6-Webverbindungen."""

from __future__ import annotations

import http.client
import json
import socket
import threading
from contextlib import closing, suppress
from http.server import BaseHTTPRequestHandler

import pytest

from aquaticy import cluster, web
from tests.test_cluster import _Handler, _konto, _paar, _store, _warte, verbund  # noqa: F401
from tests.test_sharding import Echo, Rpc, _empfangen, paar  # noqa: F401


def _ipv6_da() -> bool:
    """Kann dieser Rechner ueberhaupt auf ::1 lauschen? (11.3.2 Sol)

    Manche Container und Dienste haben IPv6 ganz abgeschaltet; dort scheitert
    schon das Anlegen des Sockets ("Address family not supported"). Das ist
    eine Bedingung der Umgebung wie Chromium fuer den Rundgang, kein Fehler.
    """
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as probe:
            probe.bind(("::1", 0))
        return True
    except OSError:
        return False


IPV6 = _ipv6_da()
OHNE_IPV6 = "Dieser Rechner hat kein IPv6 (::1 laesst sich nicht binden)."


def _dns(addresses):
    return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM,
             socket.IPPROTO_TCP, "", (ip, 0, 0, 0) if ":" in ip else (ip, 0))
            for ip in addresses]


@pytest.mark.parametrize("address", ["100.81.120.999", "100.81.x.y", "100.81.-1.2",
                                   "100.81.1.2.evil", "100.81.1", "100.081.1.2"])
def test_tailscale_detection_rejects_malformed_addresses(address):
    assert not web.is_tailscale(address)


@pytest.mark.parametrize("address", ["100.64.0.1", "100.127.255.254",
                                   "fd7a:115c:a1e0::1", "::ffff:100.64.0.1"])
def test_tailscale_detection_accepts_both_families(address):
    assert web.is_tailscale(address)
    assert cluster.lan_ip_ok(address)


@pytest.mark.parametrize("addresses, expected", [
    (["100.81.120.100"], "100.81.120.100"),
    (["fd7a:115c:a1e0::1"], "fd7a:115c:a1e0::1"),
    (["fd7a:115c:a1e0::1", "100.81.120.100"], "100.81.120.100"),
])
def test_magicdns_resolves_once_to_a_pinned_tailscale_ip(monkeypatch, addresses, expected):
    calls = []

    def lookup(host, port, **kwargs):
        calls.append((host, port, kwargs))
        return _dns(addresses)

    monkeypatch.setattr(socket, "getaddrinfo", lookup)
    assert cluster.resolve_address(" Server.Tail123.TS.NET. ") == expected
    assert len(calls) == 1 and calls[0][0] == "server.tail123.ts.net."


@pytest.mark.parametrize("addresses", [[], ["8.8.8.8"], ["127.0.0.1"], ["192.168.1.1"],
                                      ["fd00::1"], ["2606:4700:4700::1111"],
                                      ["100.81.120.100", "8.8.8.8"]])
def test_magicdns_rejects_every_non_tailnet_answer(monkeypatch, addresses):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _dns(addresses))
    with pytest.raises(cluster.ClusterError):
        cluster.resolve_address("server.tail123.ts.net")


@pytest.mark.parametrize("address", ["example.com", "server", "server.ts.net.evil",
                                   "http://server.tail.ts.net", "server.tail.ts.net:8765",
                                   "user@server.tail.ts.net", "s\n.tail.ts.net",
                                   "a" * 64 + ".tail.ts.net", "8.8.8.8"])
def test_invalid_targets_never_trigger_dns(monkeypatch, address):
    def forbidden(*a, **k):
        pytest.fail("Ungueltige Ziele duerfen keine DNS-Abfrage ausloesen")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    with pytest.raises(cluster.ClusterError):
        cluster.resolve_address(address)


def test_magicdns_lookup_failure_is_actionable(monkeypatch):
    def offline(*a, **k):
        raise socket.gaierror("not found")

    monkeypatch.setattr(socket, "getaddrinfo", offline)
    with pytest.raises(cluster.ClusterError, match="MagicDNS"):
        cluster.resolve_address("server.tail123.ts.net")


@pytest.mark.parametrize("host, expected", [("0.0.0.0", "100.81.120.2"),
                                         ("fd7a:115c:a1e0::1", "fd7a:115c:a1e0::2")])
def test_invitation_selects_the_address_family_of_its_listener(tmp_path, monkeypatch,
                                                            host, expected):
    targets = []

    def transport(target, *args):
        targets.append(target["address"])
        raise cluster.ClusterError("Testziel erreicht")

    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k:
                        _dns(["100.81.120.2", "fd7a:115c:a1e0::2"]))
    server = cluster.Cluster(tmp_path, host=host, transport=transport)
    server.state["enabled"] = True
    with pytest.raises(cluster.ClusterError, match="Testziel erreicht"):
        server.invite("server.tail123.ts.net", 8765)
    assert targets == [expected]


@pytest.mark.parametrize("host, address", [("0.0.0.0", "fd7a:115c:a1e0::2"),
                                         ("fd7a:115c:a1e0::1", "100.81.120.2")])
def test_incompatible_listener_fails_before_pairing(tmp_path, monkeypatch, host, address):
    def forbidden(*args):
        pytest.fail("Ohne passenden Rueckweg darf keine Einladung beginnen")

    server = cluster.Cluster(tmp_path, host=host, transport=forbidden)
    server.state["enabled"] = True
    with pytest.raises(cluster.ClusterError, match="Art der Adresse"):
        server.invite(address, 8765)


@pytest.mark.parametrize("address, expected", [
    (" 192.168.1.20 ", "192.168.1.20"), ("100.81.120.100", "100.81.120.100"),
    ("[fd7a:115c:a1e0::1]", "fd7a:115c:a1e0::1"), ("::1", "::1"),
    ("fe80::1%eth0", "fe80::1%eth0"),
])
def test_numeric_cluster_targets_do_not_need_dns(monkeypatch, address, expected):
    def forbidden(*a, **k):
        pytest.fail("Numerische Ziele brauchen keine DNS-Abfrage")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    assert cluster.resolve_address(address) == expected


@pytest.mark.skipif(not IPV6, reason=OHNE_IPV6)
def test_ipv6_bind_and_http_request_use_the_same_address_family(monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Aquaticy IPv6")

        def log_message(self, *args):
            pass

    monkeypatch.setattr(web, "Handler", Handler)
    server = web.bind_server("::1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert server.address_family == socket.AF_INET6
        with closing(http.client.HTTPConnection("::1", server.server_address[1], timeout=5)) \
                as conn:
            conn.request("GET", "/")
            response = conn.getresponse()
            assert response.status == 200 and response.read() == b"Aquaticy IPv6"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_bound_urls_are_valid_and_do_not_advertise_unbound_interfaces():
    assert web.urls_for("::1", 8765) == ["http://[::1]:8765/"]
    assert web.urls_for("fd7a:115c:a1e0::1", 8765) == [
        "http://[fd7a:115c:a1e0::1]:8765/",
    ]
    assert web.urls_for("::", 8765)[-1] == "http://[::1]:8765/"
    assert web.urls_for("100.81.120.100", 8765) == ["http://100.81.120.100:8765/"]


@pytest.mark.parametrize("ips", [("100.81.120.1", "100.81.120.2"),
                                ("fd7a:115c:a1e0::1", "fd7a:115c:a1e0::2")])
def test_magicdns_pairing_pins_ips_and_keeps_encryption_and_confirmation(
        verbund, monkeypatch, ips):  # noqa: F811
    a, b, _, account, asked, restarts = verbund
    if ":" in ips[0]:
        a.host, b.host = ips
    requests = []

    def transport(target, path, body, timeout):
        destination = b if target["address"] == ips[1] else a
        assert target["address"] in ips
        source = ips[0] if destination is b else ips[1]
        requests.append((destination, path, body, source))
        if path == "/cluster/rpc":
            return destination.handle_rpc(body, source)
        handler = {"/cluster/hello": destination.handle_hello,
                   "/cluster/hello-status": destination.hello_status,
                   "/cluster/hello-join": destination.hello_join}[path]
        return json.dumps(handler(json.loads(body), source)).encode()

    monkeypatch.setattr(a, "_transport", transport)
    monkeypatch.setattr(b, "_transport", transport)
    monkeypatch.setattr(cluster.Cluster, "start", lambda self: None)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _dns([ips[1]]))
    try:
        invitation = a.invite("server.tail123.ts.net", 1002)
        assert invitation.peer["address"] == ips[1]
        assert asked and not a.joined and not b.joined
        with pytest.raises(cluster.ClusterError):
            a.confirm(invitation.id, invitation.code)

        monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _dns(["8.8.8.8"]))
        b.answer(invitation.id, True)
        _warte(lambda: invitation.status == "accepted")
        wrong = "000000" if invitation.code != "000000" else "111111"
        with pytest.raises(cluster.ClusterError, match="Code stimmt nicht"):
            a.confirm(invitation.id, wrong)
        a.confirm(invitation.id, invitation.code)
        _warte(lambda: "b" in restarts, 20)
        assert b.joined and a.joined
        assert b.member(a.node_id)["address"] == ips[0]
        assert a.member(b.node_id)["address"] == ips[1]
        assert b.db.path.exists() and list(b.dir.glob("backup-*/accounts.sqlite3"))
        assert _store(b.data_dir).account(account.id) is not None
        assert a.call(b.node_id, "ping")["version"] == b.version
        assert b.call(a.node_id, "ping")["version"] == a.version
        for _destination, path, body, _source in requests:
            if path == "/cluster/rpc":
                assert account.email.encode() not in body
        destination, _, body, source = next(
            item for item in reversed(requests) if item[1] == "/cluster/rpc")
        with pytest.raises(cluster.ClusterError):
            destination.handle_rpc(body, source)
        with pytest.raises(cluster.ClusterError):
            destination.handle_rpc(body, "8.8.8.8")
    finally:
        a.stop()
        b.stop()


@pytest.mark.parametrize("address", ["100.81.120.2", "fd7a:115c:a1e0::2"])
def test_model_tunnel_over_tailnet_ip_uses_existing_encrypted_protocol(
        paar, monkeypatch, address):  # noqa: F811
    from aquaticy import sharding

    a, b = paar
    a.set_split(True, "testmodell")
    echo = Echo()
    monkeypatch.setattr(web, "SHARDING", Rpc(echo.port))
    target = a.member(b.node_id)
    port = target["port"]
    target["address"] = address
    connect = socket.create_connection
    calls = []

    def route(endpoint, *args, **kwargs):

        if endpoint == (address, port):
            calls.append(endpoint)
            endpoint = ("127.0.0.1", port)
        return connect(endpoint, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", route)
    tunnel = sharding.Tunnel(a, b.node_id)
    try:
        with socket.create_connection(("127.0.0.1", tunnel.port), timeout=10) as conn:
            conn.settimeout(10)
            conn.sendall(b"Tailnet model")
            assert _empfangen(conn, 13) == b"ledom tenliaT"
        assert calls == [(address, port)]
    finally:
        tunnel.stop()
        with suppress(OSError):
            echo.sock.shutdown(socket.SHUT_RDWR)
        echo.sock.close()
        a.stop()
        b.stop()


@pytest.mark.parametrize("address", ["100.81.120.2", "fd7a:115c:a1e0::2", "::1"])
def test_rpc_and_chat_forward_over_tailnet_ip_with_real_http(tmp_path, monkeypatch, address):
    if address == "::1" and not IPV6:
        pytest.skip(OHNE_IPV6)
    store = _store(tmp_path / "accounts")
    account = _konto(store, "tailnet@example.org")
    monkeypatch.setattr(web, "AUTH", store)
    monkeypatch.setattr(web, "SESSIONS", web.SessionRegistry())
    monkeypatch.setattr(web, "SESSION", web.SessionProxy())
    monkeypatch.setattr(web, "start_user_scheduler", lambda account: None)
    server = web.bind_server("::1" if address == "::1" else "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    home, entrance = _paar(tmp_path, server.server_address[1])
    monkeypatch.setattr(web, "CLUSTER", home)
    home.homes[account.id] = home.node_id
    target = entrance.member(home.node_id)
    target["address"] = address
    connect = socket.create_connection
    calls = []

    def route(endpoint, *args, **kwargs):
        if endpoint == (address, server.server_address[1]):
            calls.append(endpoint)
            if address != "::1":
                endpoint = ("127.0.0.1", endpoint[1])
        return connect(endpoint, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", route)
    try:
        assert entrance.call(home.node_id, "ping")["version"] == home.version
        handler = _Handler("/api/account")
        assert entrance._proxy_once(handler, target, account.id, b"", False, address) == "ok"
        response = handler.wfile.getvalue()
        assert response.startswith(b"HTTP/1.0 200")
        assert account.email.encode() in response
        assert len(calls) == 2

        entrance.state["cluster"]["secret"] = cluster._b64(b"x" * 32)
        with pytest.raises(cluster.ClusterError):
            entrance.call(home.node_id, "ping")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
