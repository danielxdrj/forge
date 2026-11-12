"""Redação de corpo de issue: tokens, senhas, JWT, connection string e chave privada."""
from forge_core.redaction import redact_secrets

GHP = "ghp_" + ("A" * 36)
GHO = "gho_" + ("B" * 36)
PAT = "github_pat_" + ("C" * 40)
AKIA = "AKIA" + ("D" * 16)
JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.signaturepartxx"
CONN = "postgres://alice:hunter2@db.example.invalid:5432/app"
PKEY = "-----BEGIN RSA PRIVATE KEY-----\nMIIFAKEKEY\n-----END RSA PRIVATE KEY-----"


def test_redacts_github_tokens_and_pat():
    text = f"token {GHP} session {GHO} fine-grained {PAT}"
    out = redact_secrets(text)
    assert GHP not in out
    assert GHO not in out
    assert PAT not in out
    assert "***" in out


def test_redacts_aws_key_jwt_password_and_connection_string():
    text = (
        f"key={AKIA} jwt={JWT} password=hunter2 senha:secreta token=abc123xyz "
        f"url={CONN} aws_secret_access_key=wJalrXUtnFEMI/K7MDENG"
    )
    out = redact_secrets(text)
    assert AKIA not in out
    assert JWT not in out
    assert "hunter2" not in out
    assert "secreta" not in out
    assert "abc123xyz" not in out
    assert "alice:hunter2" not in out
    assert "wJalrXUtnFEMI/K7MDENG" not in out
    assert "postgres://***:***@" in out


def test_redacts_private_key_block_and_keeps_surrounding_text():
    text = f"antes\n{PKEY}\ndepois login ok"
    out = redact_secrets(text)
    assert "MIIFAKEKEY" not in out
    assert "BEGIN PRIVATE KEY" in out
    assert "antes" in out
    assert "depois login ok" in out


def test_empty_and_none_are_safe():
    assert redact_secrets("") == ""
    assert redact_secrets(None) == ""
