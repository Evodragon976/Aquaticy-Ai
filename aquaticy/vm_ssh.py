"""OpenSSH nur in der freigegebenen VM, mit Schluessel und festem Hostschluessel."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shlex
from typing import Any

from aquaticy.network_router import private_address

KEY_FILE = "/work/.ssh/id_ed25519"
KEY_TYPES = {"ssh-ed25519", "ecdsa-sha2-nistp256", "ssh-rsa"}


def host_key(value: str) -> tuple[str, str]:
    parts = value.strip().split()
    if len(parts) != 2 or parts[0] not in KEY_TYPES or len(value) > 4096:
        raise ValueError("Gib den vollständigen öffentlichen SSH-Hostschlüssel an.")
    try:
        blob = base64.b64decode(parts[1], validate=True)
        size = int.from_bytes(blob[:4], "big")
        if len(blob) <= 4 or blob[4:4 + size].decode("ascii") != parts[0]:
            raise ValueError("Schlüsseltyp passt nicht.")
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Ungültiger öffentlicher SSH-Hostschlüssel.") from exc
    fingerprint = base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
    return " ".join(parts), "SHA256:" + fingerprint


def prepare(action: str, host: str = "", user: str = "", command: str = "",
            port: Any = 22, key_file: str = KEY_FILE, server_key: str = "",
            timeout: Any = 30) -> dict[str, Any]:
    from aquaticy.sandbox import safe_path

    if not all(isinstance(value, str) for value in (action, host, user, command,
                                                   key_file, server_key)):
        raise ValueError("SSH-Angaben müssen Text sein.")
    if not isinstance(action, str) or action not in {"key", "inspect", "run"}:
        raise ValueError("SSH-Aktion: key, inspect oder run.")
    if (type(port) not in (int, str) or type(timeout) not in (int, str)):
        raise ValueError("SSH-Port und Zeitlimit müssen Zahlen sein.")
    port, timeout = int(port), int(timeout)
    if not 1 <= port <= 65535 or not 1 <= timeout <= 120:
        raise ValueError("SSH-Port: 1 bis 65535. Zeitlimit: 1 bis 120 Sekunden.")
    data = {"action": action, "port": port, "timeout": timeout,
            "key_file": safe_path(key_file)}
    if data["key_file"] == "/work":
        raise ValueError("Wähle eine Schlüsseldatei unter /work.")
    if action != "key":
        data["host"] = private_address(host)
    if action == "run":
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}", user):
            raise ValueError("Ungültiger SSH-Nutzername.")
        if not command.strip() or len(command) > 2000 or any(
                not c.isprintable() and c not in "\n\t" for c in command):
            raise ValueError("SSH braucht einen sichtbaren Befehl mit höchstens 2000 Zeichen.")
        pinned, fingerprint = host_key(server_key)
        data.update(user=user, command=command, server_key=pinned, fingerprint=fingerprint)
    return data


def inspected_keys(output: str) -> list[dict[str, str]]:
    keys: list[dict[str, str]] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) != 3 or parts[0].startswith("#"):
            continue
        try:
            key, fingerprint = host_key(" ".join(parts[1:]))
        except ValueError:
            continue
        if not any(entry["host_key"] == key for entry in keys):
            keys.append({"host_key": key, "fingerprint": fingerprint})
    return keys[:3]


HELPER = r'''
import json, os, shutil, stat, subprocess, sys, tempfile
d = json.loads(sys.argv[1])
if any(shutil.which(program) is None for program in ('ssh', 'ssh-keygen', 'ssh-keyscan')):
    print('OpenSSH fehlt im VM-Abbild (openssh-client).', file=sys.stderr)
    sys.exit(127)
root = '/work/.ssh'
os.makedirs(root, mode=0o700, exist_ok=True)
if os.path.realpath(root) != root or os.stat(root).st_uid != os.getuid():
    raise ValueError('Das SSH-Verzeichnis wurde ersetzt.')
os.chmod(root, 0o700)
key = d['key_file']
if os.path.realpath(key) != key:
    raise ValueError('Die SSH-Schluesseldatei darf keine Verknuepfung sein.')
if d['action'] == 'key' and not os.path.lexists(key):
    if os.path.dirname(key) != root:
        raise ValueError('Neue Schluessel werden nur unter /work/.ssh erstellt.')
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', key,
                    '-C', 'aquaticy-vm'], stdin=subprocess.DEVNULL, check=True)
info = os.stat(key, follow_symlinks=False)
if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
    raise ValueError('Die private SSH-Datei muss dir gehoeren und nur fuer dich lesbar sein.')
if d['action'] == 'key':
    subprocess.run(['ssh-keygen', '-y', '-P', '', '-f', key],
                   stdin=subprocess.DEVNULL, check=True)
else:
    fd, known = tempfile.mkstemp(prefix='known-', dir=root)
    try:
        host = d['host'] if d['port'] == 22 else '[%s]:%s' % (d['host'], d['port'])
        with os.fdopen(fd, 'w') as output:
            output.write(host + ' ' + d['server_key'] + chr(10))
        options = [
            'BatchMode=yes', 'StrictHostKeyChecking=yes', 'GlobalKnownHostsFile=/dev/null',
            'UserKnownHostsFile=' + known, 'IdentitiesOnly=yes', 'IdentityAgent=none',
            'ForwardAgent=no', 'ForwardX11=no', 'ClearAllForwardings=yes',
            'PermitLocalCommand=no', 'PasswordAuthentication=no',
            'KbdInteractiveAuthentication=no', 'PreferredAuthentications=publickey',
            'NumberOfPasswordPrompts=0', 'ConnectionAttempts=1', 'ConnectTimeout=5',
            'ServerAliveInterval=10', 'ServerAliveCountMax=1', 'ControlMaster=no',
            'ControlPath=none', 'UpdateHostKeys=no', 'VerifyHostKeyDNS=no', 'LogLevel=ERROR',
        ]
        algorithm = d['server_key'].split()[0]
        options.append('HostKeyAlgorithms=' + ('rsa-sha2-512,rsa-sha2-256'
                       if algorithm == 'ssh-rsa' else algorithm))
        args = ['ssh', '-F', '/dev/null', '-n', '-T', '-i', key,
                '-l', d['user'], '-p', str(d['port'])]
        for option in options:
            args += ['-o', option]
        args += [d['host'], d['command']]
        result = subprocess.run(args, stdin=subprocess.DEVNULL, timeout=d['timeout'], check=False)
        sys.exit(result.returncode)
    finally:
        os.unlink(known)
'''


def vm_command(data: dict[str, Any]) -> str:
    if data["action"] == "inspect":
        return shlex.join(["ssh-keyscan", "-T", "5", "-p", str(data["port"]),
                           "-t", "ed25519,ecdsa,rsa", data["host"]])
    return shlex.join(["python3", "-c", HELPER, json.dumps(data)])
