#!/usr/bin/env bash
# Verifica os controles do perfil restrito REAL (run_args), com o Docker do runner. Falha ao primeiro desvio.
set -euo pipefail
IMAGE="$1"
HERE="$(cd "$(dirname "$0")" && pwd)"
RUN=(env PYTHONPATH="${PYTHONPATH:-src}" python3 "$HERE/profile_run.py" "$IMAGE")

echo "1) rede negada"
if "${RUN[@]}" python -c "import socket; socket.create_connection(('1.1.1.1', 53), 3)" 2>/dev/null; then
  echo "FALHA: conexão de rede permitida"; exit 1
fi

echo "2) raiz somente leitura (mountinfo)"
"${RUN[@]}" python -c "
for line in open('/proc/self/mountinfo'):
    f = line.split()
    if f[4] == '/':
        raise SystemExit(0 if 'ro' in f[5].split(',') else 1)
raise SystemExit(2)" || { echo "FALHA: raiz gravável"; exit 1; }
if "${RUN[@]}" python -c "open('/opt/forge/x','w')" 2>/dev/null; then
  echo "FALHA: escrita na raiz permitida"; exit 1
fi

echo "3) usuário não root e sem capacidades"
out=$("${RUN[@]}" python -c "import os;print(os.getuid());print(open('/proc/self/status').read().split('CapEff:')[1].split()[0])")
uid=$(echo "$out" | sed -n 1p); caps=$(echo "$out" | sed -n 2p)
[ "$uid" = "65532" ] || { echo "FALHA: uid=$uid"; exit 1; }
[ "$caps" = "0000000000000000" ] || { echo "FALHA: capacidades efetivas=$caps"; exit 1; }

echo "4) limite de processos"
if "${RUN[@]}" python -c "
import os
for _ in range(200):
    pid = os.fork()
    if pid == 0:
        os._exit(0)" 2>/dev/null; then
  echo "FALHA: fork ilimitado"; exit 1
fi

echo "5) memória limitada (no filho)"
if "${RUN[@]}" python -c "
import os
pid = os.fork()
if pid == 0:
    bytearray(512 * 1024 * 1024); os._exit(0)
_, st = os.waitpid(pid, 0)
raise SystemExit(0 if os.waitstatus_to_exitcode(st) == 0 else 1)" 2>/dev/null; then
  echo "FALHA: alocação de 512 MB aceita"; exit 1
fi

echo "OK: controles do perfil restrito verificados"
