#!/usr/bin/env bash
# Verifica, com o próprio Docker do runner, os controles do perfil restrito. Falha ao primeiro desvio.
set -euo pipefail
IMAGE="$1"
RUN=(docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges
     --user 65532:65532 --memory 128m --pids-limit 32 --cpus 0.5 --tmpfs /tmp:rw,size=16m,mode=1777)

echo "1) rede negada"
if "${RUN[@]}" "$IMAGE" python -c "import socket; socket.create_connection(('1.1.1.1', 53), 3)" 2>/dev/null; then
  echo "FALHA: conexão de rede permitida"; exit 1
fi

echo "2) filesystem raiz somente leitura"
if "${RUN[@]}" "$IMAGE" python -c "open('/opt/forge/x','w')" 2>/dev/null; then
  echo "FALHA: escrita em / permitida"; exit 1
fi

echo "3) usuário não root e sem capacidades"
out=$("${RUN[@]}" "$IMAGE" python -c "import os;print(os.getuid());print(open('/proc/self/status').read().split('CapEff:')[1].split()[0])")
uid=$(echo "$out" | sed -n 1p); caps=$(echo "$out" | sed -n 2p)
[ "$uid" = "65532" ] || { echo "FALHA: uid=$uid"; exit 1; }
[ "$caps" = "0000000000000000" ] || { echo "FALHA: capacidades efetivas=$caps"; exit 1; }

echo "4) limite de processos"
if "${RUN[@]}" "$IMAGE" python -c "
import os
for _ in range(200): os.fork()" 2>/dev/null; then
  echo "FALHA: fork ilimitado"; exit 1
fi

echo "5) memória limitada"
if "${RUN[@]}" "$IMAGE" python -c "x = bytearray(512*1024*1024)" 2>/dev/null; then
  echo "FALHA: alocação de 512 MB aceita"; exit 1
fi

echo "OK: controles do perfil restrito verificados"
