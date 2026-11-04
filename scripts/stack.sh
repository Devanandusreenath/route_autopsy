#!/usr/bin/env bash
# Start/stop the whole Route Autopsy stack for local demos and browser tests. PIDs are tracked in .stack/ (no pkill).
#   scripts/stack.sh start [stub|none]   # stub = backend wired to the LOCAL STUB provider (not Meta); none = no vision provider
#   scripts/stack.sh stop
#   scripts/stack.sh status
# Ports: backend 8000, stub provider 9100, frontend (backend mode) 5180, frontend (demo mode) 5181.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; RUN="$ROOT/.stack"; mkdir -p "$RUN"
PY="${PYTHON:-python3}"
start_bg() { # name, cwd, logfile, command...   (cd first, THEN background only the command, fully detached)
  local name=$1 cwd=$2 log=$3; shift 3
  cd "$cwd" || return 1
  setsid nohup "$@" > "$log" 2>&1 < /dev/null &
  echo $! > "$RUN/$name.pid"
  cd "$ROOT" || return 1
}
wait_http() { for _ in $(seq 1 40); do curl -s -m 2 -o /dev/null "$1" && return 0; sleep 0.5; done; echo "TIMEOUT waiting for $1"; return 1; }
case "${1:-}" in
  start)
    mode="${2:-stub}"
    rm -f "$RUN/demo.db"
    if [ "$mode" = "stub" ]; then
      start_bg stub "$ROOT/backend" "$RUN/stub.log" "$PY" -W ignore scripts/stub_meta_server.py --port 9100
      wait_http http://127.0.0.1:9100/stub/last-request
      export META_API_BASE_URL=http://127.0.0.1:9100/v1 META_API_KEY=stub-key META_MODEL=stub-not-meta-model
    fi
    export DATABASE_PATH="$RUN/demo.db"
    start_bg backend "$ROOT/backend" "$RUN/backend.log" "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
    wait_http http://127.0.0.1:8000/health
    export VITE_APP_MODE=backend VITE_API_BASE_URL=http://127.0.0.1:8000
    start_bg fe-backend "$ROOT/frontend" "$RUN/fe-backend.log" npx vite dev --port 5180 --host 127.0.0.1
    export VITE_APP_MODE=demo; unset VITE_API_BASE_URL
    start_bg fe-demo "$ROOT/frontend" "$RUN/fe-demo.log" npx vite dev --port 5181 --host 127.0.0.1
    wait_http http://127.0.0.1:5180/ && wait_http http://127.0.0.1:5181/
    echo "backend  http://127.0.0.1:8000/docs"; echo "UI (backend mode) http://127.0.0.1:5180"; echo "UI (demo mode)    http://127.0.0.1:5181 (synthetic data)"
    ;;
  stop)
    for f in "$RUN"/*.pid; do [ -f "$f" ] || continue; pid=$(cat "$f"); pkill -P "$pid" 2>/dev/null; kill "$pid" 2>/dev/null; rm -f "$f"; done; echo stopped ;;
  status)
    for u in 8000/health 9100/stub/last-request 5180/ 5181/; do echo "$u -> $(curl -s -m 2 -o /dev/null -w '%{http_code}' http://127.0.0.1:$u)"; done ;;
  *) echo "usage: $0 start [stub|none] | stop | status"; exit 1 ;;
esac
