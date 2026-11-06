"""15.2.4: nachgestellte Fehler F101 bis F120."""

import base64
import contextlib
import gzip
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from email.utils import formatdate
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, x25519
from cryptography.x509.oid import NameOID

from aquaticy import cluster, llamacpp, website


def _asset(body):
    return {'digest': 'sha256:' + hashlib.sha256(body).hexdigest(), 'size': len(body),
            'browser_download_url': 'https://github.com/example/archive'}


def test_f101_installer_redirect_rules_also_apply_with_a_redirecting_client(tmp_path):
    body, hosts = b'archive', []
    def handle(request):
        hosts.append(request.url.host)
        if request.url.host == 'github.com':
            return httpx.Response(302, headers={'location': 'https://outside.example/archive'})
        return httpx.Response(200, content=body)
    with (httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=True) as http,
          pytest.raises(llamacpp.LlamaError)):
        llamacpp.download(_asset(body), tmp_path / 'archive', http=http)
    assert hosts == ['github.com']


def test_f102_archive_downloads_have_an_overall_deadline(tmp_path, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(llamacpp, 'DOWNLOAD_SECONDS', 10, raising=False)
    monkeypatch.setattr(llamacpp.time, 'monotonic', lambda: clock[0])
    class Body(httpx.SyncByteStream):
        def __iter__(self):
            for part in (b'a', b'b'):
                clock[0] += 7
                yield part
    with (httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(
            200, stream=Body()))) as http, pytest.raises(llamacpp.LlamaError)):
        llamacpp.download(_asset(b'ab'), tmp_path / 'archive', http=http)


def _sqlite(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE items (value TEXT)')
        conn.execute('INSERT INTO items VALUES (?)', ('original' * 100,))


def test_f103_sqlite_snapshot_transfers_survive_live_database_writes(tmp_path, monkeypatch):
    peer = cluster.Cluster(tmp_path)
    user = 'a' * 32
    source = tmp_path / 'users' / user / 'data.db'
    _sqlite(source)
    monkeypatch.setattr(cluster, 'CHUNK', 64)
    signature = cluster.manifest(source.parent)['data.db']
    request = {'user': user, 'rel': 'data.db', 'sig': signature}
    first = peer._serve_file(request)
    assert not first['eof']
    with sqlite3.connect(source) as conn:
        conn.execute('INSERT INTO items VALUES (?)', ('new' * 100,))
    stamp = source.stat().st_mtime_ns
    os.utime(source, ns=(stamp + 1000000, stamp + 1000000))
    assert cluster.manifest(source.parent)['data.db'] != signature
    following = peer._serve_file({**request, 'offset': 64})
    assert 'changed' not in following and following['data']


def test_f104_cluster_rpc_reads_obey_the_whole_request_timeout(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(cluster.time, 'monotonic', lambda: clock[0])
    class Reply:
        status = 200
        def read(self, *a):
            clock[0] += 2
            return b'{}'
        def read1(self, *a):
            return self.read()
    class Connection:
        sock = SimpleNamespace(settimeout=lambda seconds: None)
        def __init__(self, *a, **kw):
            pass
        def connect(self):
            pass
        def request(self, *a, **kw):
            pass
        def getresponse(self):
            return Reply()
        def close(self):
            pass
    monkeypatch.setattr(cluster.http.client, 'HTTPConnection', Connection)
    with pytest.raises((cluster.ClusterError, TimeoutError)):
        cluster._http_post({'address': '127.0.0.1', 'port': 8765}, '/', b'{}', 1)


@pytest.mark.parametrize('value', ['not-a-port', '70000'])
def test_f105_bad_discovery_port_settings_do_not_prevent_startup(value):
    result = subprocess.run([sys.executable, '-c',
        'from aquaticy.cluster import DISCOVERY_PORT; assert 0 < DISCOVERY_PORT < 65536'],
        env=dict(os.environ, AQUATICY_CLUSTER_PORT=value), capture_output=True, timeout=10,
        check=False)
    assert result.returncode == 0, result.stderr.decode()


def test_f106_encrypted_cluster_proxy_responses_reject_http_compression(monkeypatch):
    key, salt = b'k' * 32, b's' * 16
    def handle(request):
        outer = json.loads(request.content)
        inner = json.loads(cluster.unseal(key, base64.b64decode(outer['box']), 'rpc'))
        raw = io.BytesIO()
        writer = cluster.FrameWriter(raw, key, salt, 'stream:' + inner['n'])
        writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n')
        writer.end()
        return httpx.Response(200, content=gzip.compress(raw.getvalue()), headers={
            'Content-Encoding': 'gzip', 'X-Aquaticy-Salt': base64.b64encode(salt).decode()})
    http = httpx.Client(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(cluster, 'read_frames', cluster.read_frames)
    monkeypatch.setattr(httpx, 'Client', lambda **kw: http)
    peer = SimpleNamespace(key=key, node_id='a' * 32)
    handler = SimpleNamespace(headers={}, command='GET', path='/', wfile=io.BytesIO(),
                              responded=False, close_connection=False)
    with pytest.raises(cluster.ClusterError):
        cluster.Cluster._proxy_once(peer, handler, {'address': '127.0.0.1', 'port': 8765},
                                    'user', b'', False, '192.168.1.20')


def _certificate(*, expired=False):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'chat.example.org')])
    now = datetime.now(UTC)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=30))
            .not_valid_after(now + timedelta(days=-1 if expired else 30))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName('chat.example.org')]),
                           critical=False).sign(key, hashes.SHA256()))
    return (key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()),
            cert.public_bytes(serialization.Encoding.PEM))


def test_f107_cloudflared_trust_matches_the_loaded_fallback_when_a_private_key_is_missing(tmp_path):
    _, cert = _certificate()
    cert_path, _ = website.cert_paths(tmp_path)
    cert_path.parent.mkdir(parents=True)
    cert_path.write_bytes(cert)
    _, real = website.tls_context(tmp_path, 'chat.example.org')
    assert real is False
    assert website.ca_pool_for(tmp_path, 'chat.example.org')
    assert website.needs_certificate(tmp_path, 'chat.example.org')


def test_f108_expired_certificates_are_rejected_before_installing_them():
    key, cert = _certificate(expired=True)
    with pytest.raises(website.WebsiteError):
        website._check_chain(cert, key, 'chat.example.org')


def test_f109_self_signed_certificates_are_repaired_when_the_private_key_no_longer_matches(
    tmp_path,
):
    cert_path, key_path = website.self_signed(tmp_path, 'chat.example.org')
    different_key, _ = _certificate()
    key_path.write_bytes(different_key)
    website.self_signed(tmp_path, 'chat.example.org')
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    fmt = (serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    assert cert.public_key().public_bytes(*fmt) == key.public_key().public_bytes(*fmt)


def test_f110_domain_normalization_preserves_sharp_s_with_modern_idna():
    assert website.clean_domain('straße.de') == 'xn--strae-oqa.de'


def test_f111_acme_polling_respects_retry_after_http_dates(monkeypatch):
    clock, origin, delays = [0.0], 1700000000.0, []
    monkeypatch.setattr(website.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(website.time, 'time', lambda: origin + clock[0])
    acme = object.__new__(website.Acme)
    responses = iter([(httpx.Headers({'Retry-After': formatdate(origin + 60, usegmt=True)}),
                       b'{"status":"pending"}'), (httpx.Headers(), b'{"status":"valid"}')])
    acme.post = lambda *a: next(responses)
    def sleep(seconds):
        delays.append(seconds)
        clock[0] += seconds
    acme._sleep = sleep
    assert acme._poll('https://acme.example/order', {'valid'}, {'invalid'})['status'] == 'valid'
    assert delays == [60.0]


def test_f112_dns_txt_propagation_requires_the_complete_record_value(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(website.time, 'monotonic', lambda: clock[0])
    def sleep(seconds):
        clock[0] += seconds
    response = httpx.Response(200, json={'Answer': [{'type': 16, 'data': '"prefix-token-suffix"'}]})
    with httpx.Client(transport=httpx.MockTransport(lambda r: response)) as http:
        assert not website.wait_for_txt('_acme-challenge.example.org', 'token', http=http,
                                        timeout=1, sleep=sleep)


def test_f113_failed_dns_propagation_does_not_trigger_certificate_validation(tmp_path, monkeypatch):
    validated = []
    class FakeAcme:
        def __init__(self, *a, **kw):
            pass
        def register(self, *a):
            pass
        def certificate(self, domain, publish, wait):
            wait('_acme-challenge.example.org', 'token')
            validated.append(True)
            raise AssertionError('DNS validation was triggered despite missing propagation')
    monkeypatch.setattr(website, 'Acme', FakeAcme)
    monkeypatch.setattr(website, 'wait_for_txt', lambda *a, **kw: False)
    config = SimpleNamespace(token='synthetic', staging=False, email='', domain='chat.example.org')
    with (httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200))) as http,
          pytest.raises(website.WebsiteError)):
        website.obtain_certificate(config, tmp_path, 'zone', cloudflare=object(), http=http,
                                   sleep=lambda seconds: None)
    assert not validated


def _join_peer(tmp_path, monkeypatch, files, fetch):
    peer = cluster.Cluster(tmp_path)
    peer.state['cluster'] = {'master': 'master', 'joining': True,
                             'secret': base64.b64encode(b'k' * 32).decode()}
    monkeypatch.setattr(peer, 'call', lambda *a, **kw: {'files': files})
    monkeypatch.setattr(peer, '_fetch', fetch)
    class Database:
        def __init__(self, path):
            pass
        def install(self):
            pass
        def cursors(self):
            return {}
        def last_seq(self):
            return 0
        def set_cursors(self, *a, **kw):
            pass
    monkeypatch.setattr(cluster, 'SharedDb', Database)
    return peer


def test_f114_cluster_join_rejects_drive_relative_root_filenames(tmp_path, monkeypatch):
    fetched = []
    def fetch(node, args, **kw):
        fetched.append(args['name'])
        return b'data'
    peer = _join_peer(tmp_path, monkeypatch, [cluster.SHARED_DB, 'C:outside'], fetch)
    peer.complete_join()
    assert 'C:outside' not in fetched and not (tmp_path / 'C:outside').exists()


def test_f115_joining_a_cluster_aborts_when_the_master_database_is_missing(tmp_path, monkeypatch):
    peer = _join_peer(tmp_path, monkeypatch, [cluster.SHARED_DB], lambda *a, **kw: None)
    original = tmp_path / 'original.txt'
    original.write_text('Original data')
    with pytest.raises(cluster.ClusterError):
        peer.complete_join()
    assert original.read_text() == 'Original data' and peer.info['joining'] is True


def test_f116_a_failed_cluster_join_restores_already_moved_local_files(tmp_path, monkeypatch):
    peer = _join_peer(tmp_path, monkeypatch, [cluster.SHARED_DB], lambda *a, **kw: b'data')
    one, two = tmp_path / 'one.env', tmp_path / 'two.env'
    one.write_text('one')
    two.write_text('two')
    original_move, moved, failed = cluster.shutil.move, [], []
    def move(source, target, *a, **kw):
        path = Path(source)
        if path.parent == tmp_path and path.name in {'one.env', 'two.env'}:
            if moved and not failed:
                failed.append(True)
                raise PermissionError('File is busy')
            moved.append(path)
        return original_move(source, target, *a, **kw)
    monkeypatch.setattr(cluster.shutil, 'move', move)
    with pytest.raises(OSError):
        peer.complete_join()
    assert one.read_text() == 'one' and two.read_text() == 'two'


def test_f117_a_failed_sqlite_file_replacement_preserves_the_existing_wal(tmp_path, monkeypatch):
    target = tmp_path / 'data.db'
    connection = sqlite3.connect(target)
    connection.execute('PRAGMA journal_mode=WAL')
    connection.execute('CREATE TABLE values_ (value TEXT)')
    connection.execute("INSERT INTO values_ VALUES ('old')")
    connection.commit()
    wal = Path(str(target) + '-wal')
    assert wal.exists()
    original_replace = os.replace
    def replace(source, destination):
        if Path(destination) == target:
            raise PermissionError('Replacement blocked')
        original_replace(source, destination)
    monkeypatch.setattr(cluster.os, 'replace', replace)
    try:
        with pytest.raises(PermissionError):
            cluster.write_atomic(target, b'New database')
        assert wal.exists()
        with sqlite3.connect(target) as check:
            assert check.execute('SELECT value FROM values_').fetchone()[0] == 'old'
    finally:
        with contextlib.suppress(sqlite3.Error):
            connection.close()


def test_f118_failed_atomic_replication_writes_remove_their_temporary_files(tmp_path, monkeypatch):
    def fail(*args):
        raise PermissionError('Replacement blocked')
    monkeypatch.setattr(cluster.os, 'replace', fail)
    with pytest.raises(PermissionError):
        cluster.write_atomic(tmp_path / 'settings.json', b'new')
    assert not list(tmp_path.glob('.sync-*'))


def test_f119_abandoned_database_snapshots_are_deleted_after_the_retention_period(
    tmp_path, monkeypatch,
):
    peer = cluster.Cluster(tmp_path)
    source = tmp_path / 'data.db'
    _sqlite(source)
    clock = [1000.0]
    monkeypatch.setattr(cluster, '_now', lambda: clock[0])
    monkeypatch.setattr(cluster, 'CHUNK', 64)
    peer._chunk(source, 'user/data.db', 'generation', 0)
    snapshot = peer._snapshots['user/data.db'][0]
    assert snapshot.exists()
    clock[0] += 86400
    plain = tmp_path / 'plain.txt'
    plain.write_text('plain')
    peer._chunk(plain, 'plain', '', 0)
    assert not snapshot.exists()


def test_f120_parallel_cluster_invitations_cannot_bypass_the_pending_limit(tmp_path, monkeypatch):
    peer = cluster.Cluster(tmp_path)
    peer.state['enabled'] = True
    private = x25519.X25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw,
                                               serialization.PublicFormat.Raw)
    original_generate = x25519.X25519PrivateKey.generate
    barrier = threading.Barrier(4)
    def generate():
        barrier.wait(3)
        return original_generate()
    monkeypatch.setattr(x25519.X25519PrivateKey, 'generate', staticmethod(generate))
    def invite(index):
        return peer.handle_hello({'id': f'{index:032x}', 'node': f'{index + 10:032x}',
                                  'pub': base64.b64encode(public).decode(), 'port': 8765},
                                 '192.168.1.20')
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(invite, range(4)))
    assert len([r for r in results if not r.get('error')]) <= 3
    assert len(peer.invites_in) <= 3


def test_cluster_rpc_keeps_the_response_file_open_until_the_body_is_read():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    payload = b'large body' * 100_000
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.rfile.read(int(self.headers['Content-Length'])) == b'{}'
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert cluster._http_post({'address': '127.0.0.1', 'port': server.server_port},
                                   '/', b'{}', 5) == payload
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
