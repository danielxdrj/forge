"""Executa comando dentro do perfil restrito de produção (mesmas flags de forge_core.agents.sandbox.run_args)."""
import subprocess
import sys

from forge_core.agents.sandbox import run_args

if __name__ == "__main__":
    image, command = sys.argv[1], tuple(sys.argv[2:])
    args = run_args("forge-smoke-" + str(abs(hash(command)))[:8], image, command)
    raise SystemExit(subprocess.run(["docker", *args], check=False).returncode)
