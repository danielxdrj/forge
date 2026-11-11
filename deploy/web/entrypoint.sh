#!/bin/sh
# Root só para ajustar o volume de credenciais CLI; o processo da API corre como forge.
set -eu
if [ "$(id -u)" = "0" ]; then
  mkdir -p /home/forge
  chown -R forge:forge /home/forge
  exec setpriv --reuid=1000 --regid=1000 --init-groups -- python -m forge_core.web
fi
exec python -m forge_core.web
