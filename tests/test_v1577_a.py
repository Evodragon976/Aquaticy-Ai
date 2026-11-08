"""15.7.7: Zertifikate, lokale Schluessel und HTTPS bleiben konsistent."""

import contextlib
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from aquaticy import homename


def _pair(folder, name='node.tail.ts.net', *, days=90, ca=False):
    folder.mkdir(parents=True, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(UTC)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=2))
            .not_valid_after(now + timedelta(days=days))
            .add_extension(x509.BasicConstraints(ca=ca, path_length=0 if ca else None), True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), False)
            .sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM), key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())


def _tail_pair(root, **kwargs):
    directory = homename.folder(root)
    cert, key = _pair(directory, **kwargs)
    (directory / 'tailscale.crt').write_bytes(cert)
    (directory / 'tailscale.key').write_bytes(key)
    return directory, cert, key


def test_f001_private_key_writes_never_follow_a_predictable_temporary_symlink(tmp_path):
    outside = tmp_path / 'outside'
    outside.write_bytes(b'Original private data')
    target = tmp_path / 'ca.key'
    target.with_suffix('.key.tmp').symlink_to(outside)
    homename._write_private(target, b'New key')
    assert outside.read_bytes() == b'Original private data'
    assert target.read_bytes() == b'New key'


@pytest.mark.parametrize('payload', [[], None, {'Self': []}, {'Self': 'bad'},
                                     {'Self': {}, 'CertDomains': 7}])
def test_f002_unexpected_tailscale_status_shapes_do_not_crash_https_setup(monkeypatch, payload):
    monkeypatch.setattr(homename, '_tailscale', lambda *a, **k:
                        subprocess.CompletedProcess([], 0, json.dumps(payload), ''))
    assert homename.tailscale_state().https is False


def test_f003_a_broken_cached_server_key_is_repaired_before_reuse(tmp_path):
    cert, key = homename.ensure_server_certificate(tmp_path, ['192.168.1.5'])
    key.write_bytes(b'Broken key')
    cert, key = homename.ensure_server_certificate(tmp_path, ['192.168.1.5'])
    assert homename.HomeTLS._context(cert, key)


def test_f004_cached_server_certificates_follow_the_current_root_ca(tmp_path):
    cert, _ = homename.ensure_server_certificate(tmp_path, ['192.168.1.5'])
    other = tmp_path / 'replacement'
    root_cert, root_key = homename.ensure_ca(other)
    folder = homename.folder(tmp_path)
    (folder / 'ca.crt').write_bytes(root_cert.read_bytes())
    (folder / 'ca.key').write_bytes(root_key.read_bytes())
    cert, _ = homename.ensure_server_certificate(tmp_path, ['192.168.1.5'])
    leaf = x509.load_pem_x509_certificate(cert.read_bytes())
    root = x509.load_pem_x509_certificate(root_cert.read_bytes())
    leaf.verify_directly_issued_by(root)


def test_f005_server_certificate_lifetime_never_exceeds_its_issuer(tmp_path):
    folder = homename.folder(tmp_path)
    cert, key = _pair(folder, days=25, ca=True)
    (folder / 'ca.crt').write_bytes(cert)
    (folder / 'ca.key').write_bytes(key)
    leaf, _ = homename.ensure_server_certificate(tmp_path, ['192.168.1.5'])
    assert x509.load_pem_x509_certificate(leaf.read_bytes()).not_valid_after_utc \
        <= x509.load_pem_x509_certificate(cert).not_valid_after_utc


def test_f006_failed_local_certificate_replacement_keeps_the_previous_pair(tmp_path, monkeypatch):
    cert, key = homename.ensure_server_certificate(tmp_path, ['192.168.1.5'])
    previous = cert.read_bytes(), key.read_bytes()
    write = Path.write_bytes
    replace = os.replace

    def fail_replace(source, destination):
        if Path(destination) == cert:
            raise OSError('disk full')
        return replace(source, destination)

    def failure(self, data):
        if self == cert:
            raise OSError('disk full')
        return write(self, data)

    monkeypatch.setattr(Path, 'write_bytes', failure)
    monkeypatch.setattr(os, 'replace', fail_replace)
    with pytest.raises(OSError):
        homename.ensure_server_certificate(tmp_path, ['192.168.1.6'])
    assert (cert.read_bytes(), key.read_bytes()) == previous


def test_f007_concurrent_initialization_issues_only_one_root_ca(tmp_path, monkeypatch):
    original = ec.generate_private_key
    calls = []
    barrier = threading.Barrier(2)

    def generate(*args, **kwargs):
        calls.append(True)
        with contextlib.suppress(threading.BrokenBarrierError):
            barrier.wait(0.2)
        return original(*args, **kwargs)

    monkeypatch.setattr(ec, 'generate_private_key', generate)
    with ThreadPoolExecutor(2) as pool:
        tasks = [pool.submit(homename.ensure_ca, tmp_path) for _ in range(2)]
        for task in tasks:
            task.result(3)
    assert len(calls) == 1
    cert, key = homename.ensure_ca(tmp_path)
    private = serialization.load_pem_private_key(key.read_bytes(), password=None)
    assert x509.load_pem_x509_certificate(cert.read_bytes()).public_key().public_numbers() == \
        private.public_key().public_numbers()


def test_f008_a_tailscale_hostname_change_does_not_reuse_the_old_certificate(tmp_path, monkeypatch):
    _tail_pair(tmp_path, name='old.tail.ts.net')
    calls = []
    monkeypatch.setattr(homename, '_tailscale', lambda *a, **k: calls.append(a) or None)
    result = homename.tailscale_certificate(tmp_path, homename.TailscaleState(
        name='new.tail.ts.net', https=True))
    assert calls and result is None


def test_f009_failed_external_renewal_preserves_the_previous_tailscale_pair(tmp_path, monkeypatch):
    folder, cert, key = _tail_pair(tmp_path, days=10)

    def failed(*args, **kwargs):
        Path(args[args.index('--cert-file') + 1]).write_bytes(b'Partial certificate')
        Path(args[args.index('--key-file') + 1]).write_bytes(b'Partial key')
        return subprocess.CompletedProcess([], 1, '', 'renewal failed')

    monkeypatch.setattr(homename, '_tailscale', failed)
    homename.tailscale_certificate(tmp_path, homename.TailscaleState(
        name='node.tail.ts.net', https=True))
    assert (folder / 'tailscale.crt').read_bytes() == cert
    assert (folder / 'tailscale.key').read_bytes() == key


def test_f010_expired_tailscale_certificates_are_not_offered_as_ready(tmp_path, monkeypatch):
    _tail_pair(tmp_path, days=-1)
    monkeypatch.setattr(homename, '_tailscale', lambda *a, **k: None)
    assert homename.tailscale_certificate(tmp_path, homename.TailscaleState(
        name='node.tail.ts.net', https=True)) is None


def test_f011_certificate_renewal_cannot_block_a_tls_handshake(tmp_path, monkeypatch):
    tls = homename.HomeTLS(tmp_path, [])
    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def renew():
        started.set()
        release.wait(2)

    monkeypatch.setattr(tls, 'refresh', renew)
    worker = threading.Thread(target=lambda: (tls._choose(SimpleNamespace(), None, None),
                                              finished.set()))
    worker.start()
    try:
        assert started.wait(1)
        assert finished.wait(0.2)
    finally:
        release.set()
        worker.join(2)


def test_f012_refresh_discards_disconnected_tailscale_contexts(tmp_path, monkeypatch):
    tls = homename.HomeTLS(tmp_path, [])
    tls._ts = object()
    monkeypatch.setattr(homename, 'ensure_server_certificate', lambda *a: ('cert', 'key'))
    monkeypatch.setattr(tls, '_context', lambda *a: SimpleNamespace())
    monkeypatch.setattr(homename, 'tailscale_state', lambda: homename.TailscaleState())
    tls.refresh()
    assert tls._ts is None


def test_f013_failed_mdns_registration_closes_its_allocated_socket_owner(monkeypatch):
    closed = []

    class Zeroconf:
        def register_service(self, info):
            raise OSError('multicast unavailable')

        def close(self):
            closed.append(True)

    monkeypatch.setitem(sys.modules, 'zeroconf', SimpleNamespace(
        Zeroconf=Zeroconf, ServiceInfo=lambda *a, **k: object()))
    monkeypatch.setattr(homename.shutil, 'which', lambda name: None)
    announcer = homename.Announcer()
    assert announcer.start('192.168.1.5') is False
    assert closed == [True]
    assert announcer._zeroconf is None


def test_f014_mdns_child_processes_are_reaped_on_stop():
    calls = []
    process = SimpleNamespace(terminate=lambda: calls.append('terminate'),
                              wait=lambda **kw: calls.append('wait'),
                              kill=lambda: calls.append('kill'))
    announcer = homename.Announcer()
    announcer._process = process
    announcer.stop()
    assert calls == ['terminate', 'wait']
