"""15.7.7: Zertifikatsketten, DNS-Fristen und Prozessuebergreifende Zustandsupdates."""

import contextlib
import os
import socket
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from aquaticy import lan, secure_network, secure_pro, uistate, website


def test_f083_failed_website_certificate_replacement_keeps_the_previous_pair(tmp_path, monkeypatch):
    cert, key = website.self_signed(tmp_path, 'before.example.org')
    previous = cert.read_bytes(), key.read_bytes()
    replace = os.replace

    def fail(source, target):
        if Path(target) == cert:
            raise OSError('certificate write interrupted')
        return replace(source, target)

    monkeypatch.setattr(os, 'replace', fail)
    with pytest.raises(OSError):
        website.self_signed(tmp_path, 'after.example.org')
    assert (cert.read_bytes(), key.read_bytes()) == previous


def test_f084_expired_intermediates_make_a_certificate_chain_invalid(tmp_path):
    root_key = ec.generate_private_key(ec.SECP256R1())
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Intermediate')])
    now = datetime.now(UTC)
    builder = (x509.CertificateBuilder().issuer_name(issuer)
               .serial_number(x509.random_serial_number())
               .not_valid_before(now - timedelta(days=5)))
    root = (builder.subject_name(issuer).public_key(root_key.public_key())
            .not_valid_after(now - timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
            .sign(root_key, hashes.SHA256()))
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'a.example')])
    leaf = (builder.subject_name(subject)
            .public_key(leaf_key.public_key()).not_valid_after(now + timedelta(days=90))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName('a.example')]), False)
            .sign(root_key, hashes.SHA256()))
    cert, key = website.cert_paths(tmp_path)
    cert.parent.mkdir()
    cert.write_bytes(leaf.public_bytes(serialization.Encoding.PEM)
                     + root.public_bytes(serialization.Encoding.PEM))
    key.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    assert not website.certificate_valid(tmp_path, 'a.example')
    assert website.certificate_expiry(tmp_path, 'a.example') <= now


def test_f085_acme_account_keys_use_the_curve_supported_by_the_jws_encoder(tmp_path):
    key = ec.generate_private_key(ec.SECP384R1())
    folder = website.site_dir(tmp_path)
    folder.mkdir()
    (folder / 'acme-account.key').write_bytes(key.private_bytes(serialization.Encoding.PEM,
                         serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    assert isinstance(website._account_key(tmp_path).curve, ec.SECP256R1)


def test_f086_simultaneous_acme_initialization_uses_one_persistent_identity(tmp_path, monkeypatch):
    generate = ec.generate_private_key
    barrier = threading.Barrier(2)

    def slow(*args, **kwargs):
        with contextlib.suppress(threading.BrokenBarrierError):
            barrier.wait(.2)
        return generate(*args, **kwargs)

    monkeypatch.setattr(ec, 'generate_private_key', slow)
    with ThreadPoolExecutor(2) as pool:
        keys = list(pool.map(lambda _: website._account_key(tmp_path), range(2)))
    assert keys[0].private_numbers() == keys[1].private_numbers()


def test_f087_reverse_dns_cannot_hold_a_scan_worker_indefinitely(monkeypatch):
    unblock = threading.Event()
    monkeypatch.setattr(lan, 'DNS_TIMEOUT', .1, raising=False)
    monkeypatch.setattr(socket, 'gethostbyaddr', lambda addr: (
        unblock.wait(5), ('device.example', [], []))[1])
    with ThreadPoolExecutor(1) as pool:
        result = pool.submit(lan.hostname_of, '192.168.1.2')
        try:
            assert result.result(timeout=.6) == ''
        finally:
            unblock.set()


def test_f088_separate_processes_do_not_lose_independent_ui_settings(tmp_path):
    db = tmp_path / 'state.db'
    uistate.UIState(db)
    code = '''import sys,time
from pathlib import Path
from aquaticy.uistate import UIState
state=UIState(sys.argv[1]); original=state.read
def read():
    value=original(); Path(sys.argv[2]+sys.argv[3]).touch()
    end=time.monotonic()+.3
    while time.monotonic()<end and len(list(Path(sys.argv[2]).parent.glob('ready-*')))<2:
        time.sleep(.005)
    return value
state.read=read
state.write({sys.argv[4]:sys.argv[5]})
'''
    processes = [subprocess.Popen([sys.executable, '-c', code, str(db),
                  str(tmp_path / 'ready-'), str(n), field, value],
                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for n, (field, value) in enumerate([('theme', 'dark'), ('lang', 'en')])]
    for process in processes:
        out, err = process.communicate(timeout=10)
        assert process.returncode == 0, (out, err)
    result = uistate.UIState(db).read()
    assert result['theme'] == 'dark' and result['lang'] == 'en'


def test_f089_a_returning_device_is_online_again_instead_of_new(tmp_path, monkeypatch):
    secure_pro.configure(tmp_path, '192.168.1.0/24')
    device = lan.Device('192.168.1.2', ports=[443])
    results = iter([[device], [], [device]])
    monkeypatch.setattr(lan, 'scan', lambda *a, **kw: next(results))
    monkeypatch.setattr(secure_network, 'neighbours', lambda *a: [])
    watcher = secure_pro.Watcher(tmp_path, lambda text: True)
    watcher.tick()
    watcher.tick()
    watcher.tick()
    assert not any(item['kind'] == 'new_device' for item in watcher.events)


def test_changing_the_router_does_not_turn_existing_devices_into_new_ones(tmp_path, monkeypatch):
    secure_pro.configure(tmp_path, '192.168.1.0/24')
    device = lan.Device('192.168.1.2', ports=[443])
    monkeypatch.setattr(lan, 'scan', lambda *a, **kw: [device])
    monkeypatch.setattr(secure_network, 'neighbours', lambda *a: [])
    watcher = secure_pro.Watcher(tmp_path, lambda text: True)
    watcher.tick()
    secure_pro.configure(tmp_path, '192.168.1.0/24', router='192.168.1.1')
    watcher.tick()
    assert not any(item['kind'] == 'new_device' for item in watcher.events)
