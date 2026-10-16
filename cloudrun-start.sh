#!/bin/sh
set -e
redis-server --protected-mode no --bind 127.0.0.1 --save "" --appendonly no \
  --loadmodule /var/lib/falkordb/bin/falkordb.so $FALKORDB_ARGS &
until redis-cli ping >/dev/null 2>&1; do sleep 0.2; done
/venv/bin/python -m staircase.demo
exec /venv/bin/uvicorn app:api --host 0.0.0.0 --port "${PORT:-8080}"
