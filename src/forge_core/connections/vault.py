"""Cofre Fernet: a chave vem só de arquivo em tmpfs (/run/secrets), nunca de config no Git.

Sem arquivo, chave vazia ou inválida, a área de conexões fica desligada. O valor da chave
não entra em exceção, log nem mensagem.
"""
from __future__ import annotations

import os
from collections.abc import Mapping

from ..storage.secrets import SecretMissingError, read_secret_file

SECRET_FILE_ENV = "FORGE_SECRET_CONNECTIONS_KEY_FILE"
DEFAULT_SECRET_FILE = "/run/secrets/forge_connections_key"

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # pragma: no cover - extra [web]
    Fernet = None  # type: ignore[misc, assignment]
    InvalidToken = Exception  # type: ignore[misc, assignment]


class VaultDisabled(Exception):
    """Cofre indisponível. `reason` é um código fixo, nunca o conteúdo da chave."""

    def __init__(self, reason: str = "vault_disabled"):
        super().__init__(reason)
        self.reason = reason


class ConnectionsVault:
    def __init__(self, fernet: object | None, *, reason: str = "vault_disabled"):
        self._fernet = fernet
        self.reason = reason

    @property
    def enabled(self) -> bool:
        return self._fernet is not None

    def encrypt(self, plaintext: str) -> str:
        if self._fernet is None:
            raise VaultDisabled(self.reason)
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        if self._fernet is None:
            raise VaultDisabled(self.reason)
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise VaultDisabled("vault_invalid") from exc
        except (ValueError, TypeError) as exc:
            raise VaultDisabled("vault_invalid") from exc

    @classmethod
    def disabled(cls, reason: str = "vault_disabled") -> "ConnectionsVault":
        return cls(None, reason=reason)

    @classmethod
    def from_key_file(cls, path: str) -> "ConnectionsVault":
        if Fernet is None:
            return cls.disabled("vault_unavailable")
        try:
            raw = read_secret_file(path)
        except SecretMissingError:
            return cls.disabled("vault_disabled")
        try:
            return cls(Fernet(raw.encode("ascii")))
        except (ValueError, TypeError):
            return cls.disabled("vault_invalid")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ConnectionsVault":
        """Lê só o caminho do arquivo. Não usa variável com o valor da chave."""
        env = os.environ if env is None else env
        path = (env.get(SECRET_FILE_ENV) or "").strip()
        if not path:
            return cls.disabled("vault_disabled")
        return cls.from_key_file(path)
