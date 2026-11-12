"""Vault Obsidian: allowlist, realpath, symlink e helper de escrita em Forge/."""
from pathlib import Path

from forge_core.config import load_settings
from forge_core.obsidian.vault import ObsidianVault, VaultRuleError
from forge_core.obsidian.write import prepare_write

SENTINEL = "SENTINELA_VAULT_NAO_LOGAR"


def _vault(tmp_path, allow=("Forge", "Inbox")):
    root = tmp_path / "vault"
    (root / "Forge").mkdir(parents=True)
    (root / "Inbox").mkdir()
    (root / "Secret").mkdir()
    (root / "Forge" / "ok.md").write_text(
        "---\ntitle: Nota ok\ntags: [forge]\n---\nVer [[Inbox/x]] #pista\n" + SENTINEL,
        encoding="utf-8",
    )
    (root / "Inbox" / "x.md").write_text("# Inbox\n", encoding="utf-8")
    (root / "Secret" / "hidden.md").write_text("segredo\n", encoding="utf-8")
    return ObsidianVault(root.resolve(), allow)


def test_disabled_without_path_or_allowlist(tmp_path):
    s = load_settings({"FORGE_CONFIG_DIR": str(tmp_path)})
    v = ObsidianVault.from_settings(s)
    assert not v.enabled
    assert v.status()["error"] == "vault_disabled"
    s2 = load_settings({
        "FORGE_CONFIG_DIR": str(tmp_path),
        "FORGE_OBSIDIAN_VAULT": str(tmp_path / "missing"),
        "FORGE_OBSIDIAN_ALLOW": "Forge",
    })
    assert not ObsidianVault.from_settings(s2).enabled


def test_lists_only_allowlisted_md_and_parses_frontmatter(tmp_path):
    vault = _vault(tmp_path)
    listed = vault.list_notes()
    paths = {n["path"] for n in listed["notes"]}
    assert "Forge/ok.md" in paths
    assert "Inbox/x.md" in paths
    assert not any("Secret" in p for p in paths)
    note = [n for n in listed["notes"] if n["path"] == "Forge/ok.md"][0]
    assert note["title"] == "Nota ok"
    assert "forge" in note["tags"]
    assert "Inbox/x" in note["links"]
    assert SENTINEL not in str(listed)


def test_read_and_symlink_escape_blocked(tmp_path):
    vault = _vault(tmp_path)
    body = vault.read_note("Forge/ok.md")
    assert SENTINEL in body["body"]
    outside = tmp_path / "outside.md"
    outside.write_text("ESCAPED " + SENTINEL, encoding="utf-8")
    link = vault._root / "Forge" / "escape.md"
    try:
        link.symlink_to(outside)
    except OSError:
        return
    try:
        vault.read_note("Forge/escape.md")
        assert False, "symlink should be blocked"
    except VaultRuleError as exc:
        assert exc.code == "path_forbidden"
    try:
        vault.read_note("../Secret/hidden.md")
        assert False, "path escape should be blocked"
    except VaultRuleError as exc:
        assert exc.code == "path_forbidden"


def test_write_helper_only_under_forge_atomic(tmp_path):
    root = tmp_path / "vault"
    (root / "Forge").mkdir(parents=True)
    dest = prepare_write(root, "nova.md", b"# hi\n")
    assert dest.name == "nova.md"
    assert dest.parent.name == "Forge"
    assert dest.read_text(encoding="utf-8") == "# hi\n"
    nested = prepare_write(root, "site/34.md", b"# issue\n")
    assert nested.parent.name == "site"
    assert nested.parent.parent.name == "Forge"
    assert nested.read_text(encoding="utf-8") == "# issue\n"
    try:
        prepare_write(root, "../x.md", b"no")
        assert False
    except VaultRuleError as exc:
        assert exc.code == "invalid_name"
