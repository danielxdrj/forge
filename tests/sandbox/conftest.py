import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

IMAGE = os.environ.get("FORGE_SANDBOX_IMAGE")


def _docker_ok() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def pytest_collection_modifyitems(config, items):
    if IMAGE and _docker_ok():
        return
    skip = pytest.mark.skip(reason="Docker real e FORGE_SANDBOX_IMAGE necessários (rodam no job sandbox-smoke do CI)")
    for item in items:
        item.add_marker(skip)


@pytest.fixture
def sandbox():
    from forge_core.agents.sandbox import DockerSandbox

    return DockerSandbox(IMAGE, command=("python", "-m", "forge_core.agents.sandbox_child", "forge_test_probe:build"))


def leftover_containers() -> list[str]:
    out = subprocess.run(["docker", "ps", "-aq", "--filter", "name=forge-agent-"], capture_output=True, text=True)
    return [x for x in out.stdout.split() if x]
