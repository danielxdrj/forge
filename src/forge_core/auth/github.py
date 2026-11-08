"""Login com GitHub por OAuth device flow (RFC 8628), só para descobrir a identidade numérica.

Fluxo oficial: POST /login/device/code, polling em POST /login/oauth/access_token e GET api.github.com/user
com o token recebido. Sem escopos: o token só serve para ler o id e o login públicos. O token é usado em
memória e descartado; nunca é gravado, logado ou devolvido em erro.

Transporte HTTP é injetado. O real aceita só os hosts fixos abaixo, em HTTPS, sem seguir redirecionamento
(evita vazar o token para outro host). Os testes usam transporte falso.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ..errors import ForgeError

DEVICE_CODE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
ALLOWED_HOSTS = frozenset({"github.com", "api.github.com"})
_LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_SLOW_DOWN_STEP = 5.0
_TERMINAL_CODES = {
    "expired_token": "expired",
    "token_expired": "expired",
    "access_denied": "denied",
    "device_flow_disabled": "device_flow_disabled",
    "incorrect_client_credentials": "client_id_rejected",
    "incorrect_device_code": "device_code_rejected",
}


class DeviceFlowError(ForgeError):
    """Falha do login com código fixo. Nunca carrega token, device code, user code ou corpo de resposta."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class Transport(Protocol):
    def post_form(self, url: str, data: dict[str, str]) -> dict: ...

    def get_json(self, url: str, token: str) -> dict: ...


@dataclass(frozen=True)
class DeviceCode:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


@dataclass(frozen=True)
class GitHubIdentity:
    github_id: int
    login: str


class UrllibTransport:
    """Transporte real: HTTPS, host na allowlist, timeout curto e nenhum redirecionamento."""

    def __init__(self, timeout: float = 10.0):
        self._timeout = timeout
        self._opener = urllib.request.build_opener(_NoRedirect)

    @staticmethod
    def _check(url: str) -> None:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS:
            raise DeviceFlowError("endpoint_not_allowed")

    def _send(self, req: urllib.request.Request) -> dict:
        try:
            with self._opener.open(req, timeout=self._timeout) as resp:
                body = resp.read(65536)
        except urllib.error.HTTPError as exc:
            body = exc.read(65536)
        except (OSError, ValueError):
            raise DeviceFlowError("network") from None
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise DeviceFlowError("malformed_response") from None
        if not isinstance(data, dict):
            raise DeviceFlowError("malformed_response")
        return data

    def post_form(self, url: str, data: dict[str, str]) -> dict:
        self._check(url)
        req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), method="POST",
                                     headers={"Accept": "application/json"})
        return self._send(req)

    def get_json(self, url: str, token: str) -> dict:
        self._check(url)
        req = urllib.request.Request(url, method="GET", headers={
            "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {token}"})
        return self._send(req)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DeviceFlow:
    def __init__(self, client_id: str, transport: Transport,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        if not client_id or not isinstance(client_id, str):
            raise DeviceFlowError("client_id_missing")
        self._client_id = client_id
        self._t = transport
        self._sleep = sleep
        self._clock = clock

    def start(self) -> DeviceCode:
        data = self._t.post_form(DEVICE_CODE_URL, {"client_id": self._client_id, "scope": ""})
        try:
            dc = DeviceCode(str(data["device_code"]), str(data["user_code"]), str(data["verification_uri"]),
                            int(data["expires_in"]), int(data["interval"]))
        except (KeyError, TypeError, ValueError):
            raise DeviceFlowError("malformed_response") from None
        if dc.expires_in <= 0 or dc.interval <= 0 or urllib.parse.urlsplit(dc.verification_uri).hostname \
                not in ALLOWED_HOSTS:
            raise DeviceFlowError("malformed_response")
        return dc

    def poll_token(self, dc: DeviceCode) -> str:
        deadline = self._clock() + dc.expires_in
        interval = float(dc.interval)
        while True:
            if self._clock() >= deadline:
                raise DeviceFlowError("expired")
            data = self._t.post_form(TOKEN_URL, {"client_id": self._client_id, "device_code": dc.device_code,
                                                 "grant_type": GRANT_TYPE})
            token = data.get("access_token")
            if isinstance(token, str) and token:
                return token
            error = data.get("error")
            if error == "authorization_pending":
                self._sleep(interval)
            elif error == "slow_down":
                interval += _SLOW_DOWN_STEP
                self._sleep(interval)
            elif isinstance(error, str) and error in _TERMINAL_CODES:
                raise DeviceFlowError(_TERMINAL_CODES[error])
            else:
                raise DeviceFlowError("device_flow_failed")

    def identity(self, token: str) -> GitHubIdentity:
        data = self._t.get_json(USER_URL, token)
        gid, login = data.get("id"), data.get("login")
        if type(gid) is not int or gid <= 0 or not isinstance(login, str) or not _LOGIN.match(login):
            raise DeviceFlowError("malformed_identity")
        return GitHubIdentity(gid, login)

    def login(self) -> tuple[DeviceCode, GitHubIdentity]:
        dc = self.start()
        token = self.poll_token(dc)
        ident = self.identity(token)
        return dc, ident
