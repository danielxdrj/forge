import pytest

from forge_core.logging import redact


@pytest.mark.parametrize(
    "text, secrets",
    [
        ("falhou: Bearer abc def ghi", ["abc", "def", "ghi"]),
        ('Authorization: Bearer "abc def"', ["abc", "def"]),
        ("Authorization: Basic dXNlcjpwYXNz extra", ["dXNlcjpwYXNz", "extra"]),
        ("{'Authorization': 'Bearer abc def'}", ["abc", "def"]),
        ('{"Authorization": "Bearer abc def"}', ["abc", "def"]),
        ('Bearer ab"cd ef', ["ab", "cd", "ef"]),
        ("Authorization: token abc def", ["abc", "def"]),
    ],
)
def test_redact_masks_whole_secret(text, secrets):
    out = redact(text)
    for part in secrets:
        assert part not in out
