"""Checagem curta de protocolo (~5 s por host). Sem dependência pesada; a rede é injetável nos testes.

SFTP: TCP + banner SSH (auth SSH completo não é barato sem cliente). Os demais: TCP + autenticação.
Mensagens de erro são códigos fixos — nunca a senha, o token nem o traceback do socket.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import socket
import ssl
import struct
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from .readonly import ReadOnlyFTP, ReadOnlyPortainerClient, ReadOnlyViolation

HOST_TIMEOUT_SECONDS = 5.0
CONNECTION_TYPES = ("mysql", "postgres", "ftp", "sftp", "portainer")

_PG_PROTOCOL = 196608  # 3.0
_MYSQL_CAP_PROTOCOL_41 = 0x00000200
_MYSQL_CAP_SECURE_CONNECTION = 0x00008000
_MYSQL_CAP_PLUGIN_AUTH = 0x00080000
_MYSQL_CAP_PLUGIN_AUTH_LENENC = 0x00200000


class ProbeError(Exception):
    """Falha de teste. `code` é estável e seguro para a API/auditoria."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _recvn(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ProbeError("protocol")
        buf += chunk
    return buf


def _tcp(host: str, port: int, timeout: float) -> socket.socket:
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except TimeoutError as exc:
        raise ProbeError("timeout") from exc
    except ConnectionRefusedError as exc:
        raise ProbeError("refused") from exc
    except OSError as exc:
        raise ProbeError("unreachable") from exc
    sock.settimeout(timeout)
    return sock


class ConnectionProbes:
    def __init__(self, timeout: float = HOST_TIMEOUT_SECONDS, *, urlopen_fn=urlopen, ftp_cls=None):
        self.timeout = timeout
        self._urlopen = urlopen_fn
        self._ftp_cls = ftp_cls

    def test_one(
        self,
        conn_type: str,
        host: str,
        port: int,
        username: str,
        secret: str,
        database: str | None,
        remote_path: str | None,
    ) -> None:
        if conn_type == "postgres":
            self._postgres(host, port, username, secret, database or "postgres")
        elif conn_type == "mysql":
            self._mysql(host, port, username, secret, database)
        elif conn_type == "ftp":
            self._ftp(host, port, username, secret, remote_path)
        elif conn_type == "sftp":
            self._sftp(host, port)
        elif conn_type == "portainer":
            self._portainer(host, port, secret)
        else:
            raise ProbeError("type_unsupported")

    def _postgres(self, host: str, port: int, user: str, password: str, database: str) -> None:
        sock = _tcp(host, port, self.timeout)
        try:
            payload = b"user\x00" + user.encode("utf-8") + b"\x00database\x00" + database.encode("utf-8") + b"\x00\x00"
            body = struct.pack(">I", _PG_PROTOCOL) + payload
            sock.sendall(struct.pack(">I", 4 + len(body)) + body)
            self._pg_auth(sock, user, password)
        except TimeoutError as exc:
            raise ProbeError("timeout") from exc
        finally:
            sock.close()

    def _pg_auth(self, sock: socket.socket, user: str, password: str) -> None:
        while True:
            tag, payload = self._pg_read(sock)
            if tag == b"E":
                raise ProbeError("auth_failed")
            if tag != b"R":
                if tag == b"Z":
                    return
                continue
            if len(payload) < 4:
                raise ProbeError("protocol")
            method = int.from_bytes(payload[:4], "big")
            if method == 0:
                return
            if method == 3:
                raw = password.encode("utf-8") + b"\x00"
                sock.sendall(b"p" + struct.pack(">I", 4 + len(raw)) + raw)
            elif method == 5:
                salt = payload[4:8]
                inner = hashlib.md5(password.encode("utf-8") + user.encode("utf-8")).hexdigest()
                hashed = "md5" + hashlib.md5(inner.encode("ascii") + salt).hexdigest()
                raw = hashed.encode("ascii") + b"\x00"
                sock.sendall(b"p" + struct.pack(">I", 4 + len(raw)) + raw)
            elif method == 10:
                self._pg_scram(sock, user, password, payload[4:])
            else:
                raise ProbeError("auth_unsupported")

    def _pg_read(self, sock: socket.socket) -> tuple[bytes, bytes]:
        hdr = _recvn(sock, 5)
        length = int.from_bytes(hdr[1:5], "big")
        rest = _recvn(sock, length - 4) if length > 4 else b""
        return hdr[:1], rest

    def _pg_scram(self, sock: socket.socket, user: str, password: str, mechs: bytes) -> None:
        names = [m for m in mechs.split(b"\x00") if m]
        if b"SCRAM-SHA-256" not in names:
            raise ProbeError("auth_unsupported")
        nonce = secrets.token_urlsafe(16)
        client_first_bare = f"n={_scram_escape(user)},r={nonce}"
        client_first = f"n,,{client_first_bare}"
        encoded = client_first.encode("utf-8")
        msg = b"SCRAM-SHA-256\x00" + struct.pack(">I", len(encoded)) + encoded
        sock.sendall(b"p" + struct.pack(">I", 4 + len(msg)) + msg)
        tag, payload = self._pg_read(sock)
        if tag != b"R" or int.from_bytes(payload[:4], "big") != 11:
            raise ProbeError("auth_failed")
        server_first = payload[4:].decode("utf-8")
        attrs = dict(p.split("=", 1) for p in server_first.split(",") if "=" in p)
        salt = __import__("base64").b64decode(attrs["s"])
        iters = int(attrs["i"])
        salted = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters)
        client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
        stored = hashlib.sha256(client_key).digest()
        client_final_wo = f"c=biws,r={attrs['r']}"
        auth_msg = f"{client_first_bare},{server_first},{client_final_wo}".encode()
        signature = hmac.new(stored, auth_msg, hashlib.sha256).digest()
        proof = bytes(a ^ b for a, b in zip(client_key, signature))
        proof_b64 = __import__("base64").b64encode(proof).decode("ascii")
        client_final = f"{client_final_wo},p={proof_b64}".encode()
        sock.sendall(b"p" + struct.pack(">I", 4 + len(client_final)) + client_final)
        tag, payload = self._pg_read(sock)
        if tag == b"E" or (tag == b"R" and int.from_bytes(payload[:4], "big") not in (12, 0)):
            raise ProbeError("auth_failed")

    def _mysql(self, host: str, port: int, user: str, password: str, database: str | None) -> None:
        sock = _tcp(host, port, self.timeout)
        try:
            payload = self._mysql_read(sock)
            if not payload or payload[0] == 0xFF:
                raise ProbeError("protocol")
            plugin, scramble = _mysql_handshake(payload)
            reply, seq = _mysql_login(user, password, database, plugin, scramble)
            sock.sendall(_mysql_packet(reply, seq))
            resp = self._mysql_read(sock)
            if not resp:
                raise ProbeError("protocol")
            if resp[0] == 0x00 or resp[0] == 0xFE:
                return
            if resp[0] == 0xFF:
                raise ProbeError("auth_failed")
            if resp[0] == 0x01:
                raise ProbeError("auth_unsupported")
            raise ProbeError("auth_failed")
        except TimeoutError as exc:
            raise ProbeError("timeout") from exc
        finally:
            sock.close()

    def _mysql_read(self, sock: socket.socket) -> bytes:
        hdr = _recvn(sock, 4)
        length = int.from_bytes(hdr[:3], "little")
        return _recvn(sock, length) if length else b""

    def _ftp(self, host: str, port: int, user: str, password: str, remote_path: str | None) -> None:
        import ftplib

        cls = self._ftp_cls or ReadOnlyFTP
        try:
            ftp = cls()
            ftp.connect(host, port, timeout=self.timeout)
            ftp.login(user, password)
            if remote_path:
                ftp.cwd(remote_path)
            ftp.quit()
        except ftplib.error_perm as exc:
            raise ProbeError("auth_failed") from exc
        except TimeoutError as exc:
            raise ProbeError("timeout") from exc
        except ConnectionRefusedError as exc:
            raise ProbeError("refused") from exc
        except OSError as exc:
            raise ProbeError("unreachable") from exc

    def _sftp(self, host: str, port: int) -> None:
        sock = _tcp(host, port, self.timeout)
        try:
            banner = sock.recv(256)
            if not banner.startswith(b"SSH-"):
                raise ProbeError("protocol")
        except TimeoutError as exc:
            raise ProbeError("timeout") from exc
        finally:
            sock.close()

    def _portainer(self, host: str, port: int, token: str) -> None:
        client = ReadOnlyPortainerClient(
            f"http://{host}:{port}", token, timeout=self.timeout, urlopen_fn=self._urlopen,
        )
        try:
            with client.get("/api/status") as resp:
                if getattr(resp, "status", 200) >= 400:
                    raise ProbeError("auth_failed")
        except ReadOnlyViolation as exc:
            raise ProbeError("protocol") from exc
        except ProbeError:
            raise
        except TimeoutError as exc:
            raise ProbeError("timeout") from exc
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise ProbeError("auth_failed") from exc
            raise ProbeError("protocol") from exc
        except URLError as exc:
            reason = exc.reason
            if isinstance(reason, socket.timeout):
                raise ProbeError("timeout") from exc
            if isinstance(reason, ConnectionRefusedError):
                raise ProbeError("refused") from exc
            raise ProbeError("unreachable") from exc
        except ssl.SSLError as exc:
            raise ProbeError("protocol") from exc
        except TimeoutError as exc:
            raise ProbeError("timeout") from exc


def _scram_escape(value: str) -> str:
    return value.replace("=", "=3D").replace(",", "=2C")


def _mysql_packet(payload: bytes, seq: int) -> bytes:
    return len(payload).to_bytes(3, "little") + bytes([seq]) + payload


def _mysql_handshake(payload: bytes) -> tuple[str, bytes]:
    if payload[0] != 10:
        raise ProbeError("protocol")
    rest = payload[1:]
    nul = rest.find(b"\x00")
    rest = rest[nul + 1 :]
    rest = rest[4:]  # connection id
    scramble = rest[:8]
    rest = rest[8 + 1 :]
    if len(rest) < 5:
        return "mysql_native_password", scramble
    rest = rest[2 + 1 + 2 :]  # caps low, charset, status
    cap_high = int.from_bytes(rest[:2], "little") if len(rest) >= 2 else 0
    rest = rest[2:]
    plugin_len = rest[0] if rest else 0
    rest = rest[1:]
    rest = rest[10:]  # reserved
    take = max(13, plugin_len - 8) if plugin_len else 13
    scramble += rest[:take].split(b"\x00")[0]
    rest = rest[take:]
    if rest.startswith(b"\x00"):
        rest = rest[1:]
    plugin = rest.split(b"\x00")[0].decode("ascii", "replace") or "mysql_native_password"
    if cap_high:
        pass
    return plugin, scramble.rstrip(b"\x00")


def _mysql_login(user: str, password: str, database: str | None, plugin: str, scramble: bytes) -> tuple[bytes, int]:
    caps = _MYSQL_CAP_PROTOCOL_41 | _MYSQL_CAP_SECURE_CONNECTION | _MYSQL_CAP_PLUGIN_AUTH | _MYSQL_CAP_PLUGIN_AUTH_LENENC
    if database:
        caps |= 0x00000008  # CLIENT_CONNECT_WITH_DB
    auth = _mysql_auth_response(plugin, password, scramble)
    parts = [
        caps.to_bytes(4, "little"),
        (16 * 1024 * 1024).to_bytes(4, "little"),
        bytes([33]),  # utf8
        b"\x00" * 23,
        user.encode("utf-8") + b"\x00",
        bytes([len(auth)]) + auth,
    ]
    if database:
        parts.append(database.encode("utf-8") + b"\x00")
    parts.append(plugin.encode("ascii") + b"\x00")
    return b"".join(parts), 1


def _mysql_auth_response(plugin: str, password: str, scramble: bytes) -> bytes:
    pw = password.encode("utf-8")
    if not password:
        return b""
    if plugin == "caching_sha2_password":
        h1 = hashlib.sha256(pw).digest()
        h2 = hashlib.sha256(h1).digest()
        return bytes(a ^ b for a, b in zip(h1, hashlib.sha256(h2 + scramble).digest()))
    # mysql_native_password
    h1 = hashlib.sha1(pw).digest()
    h2 = hashlib.sha1(h1).digest()
    return bytes(a ^ b for a, b in zip(h1, hashlib.sha1(scramble + h2).digest()))
