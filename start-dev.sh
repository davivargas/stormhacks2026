#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  printf 'Usage: %s\n\nStarts the backend on port 8000 and frontend on port 5173.\nOverride ports with BACKEND_PORT and FRONTEND_PORT, for example:\n  BACKEND_PORT=8001 ./start-dev.sh\nInstalls missing dependencies on first launch. Press Ctrl+C to stop both.\n' "$0"
  exit 0
fi

if [[ $# -ne 0 ]]; then
  printf 'Unknown argument: %s. Use --help for usage.\n' "$1" >&2
  exit 2
fi

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
BACKEND_PYTHON="$BACKEND_DIR/.venv/bin/python"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

for dependency in python3 npm setsid; do
  if ! command -v "$dependency" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "$dependency" >&2
    exit 1
  fi
done

python3 -c 'import sys; sys.exit("Python 3.12 or newer is required." if sys.version_info < (3, 12) else 0)'

python3 - "$BACKEND_PORT" "$FRONTEND_PORT" <<'PY'
import errno
import socket
import sys

ports = []
for label, value in zip(("BACKEND_PORT", "FRONTEND_PORT"), sys.argv[1:]):
    if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= 65535:
        sys.exit(f"{label} must be a port number between 1 and 65535.")
    ports.append(int(value))

if ports[0] == ports[1]:
    sys.exit("The frontend and backend must use different ports.")

for label, port in zip(("Backend", "Frontend"), ports):
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                probe.bind((host, port))
        except OSError as error:
            if family == socket.AF_INET6 and error.errno in (errno.EAFNOSUPPORT, errno.EADDRNOTAVAIL):
                continue
            if error.errno == errno.EADDRINUSE:
                sys.exit(
                    f"{label} port {port} is already in use.\n"
                    f"Inspect it with: ss -ltnp '( sport = :{port} )'\n"
                    "Stop the existing service or choose another port, for example:\n"
                    "  BACKEND_PORT=8001 FRONTEND_PORT=5174 ./start-dev.sh"
                )
            sys.exit(f"Cannot use {label.lower()} port {port}: {error}")
PY

if [[ ! -x "$BACKEND_PYTHON" ]]; then
  printf 'Creating backend virtual environment...\n'
  python3 -m venv "$BACKEND_DIR/.venv"
fi

if ! "$BACKEND_PYTHON" -m pip --version >/dev/null 2>&1; then
  printf 'Installing pip in the backend virtual environment...\n'
  if ! "$BACKEND_PYTHON" -m ensurepip --upgrade; then
    printf '\nCould not install pip. On Ubuntu/Debian, install Python virtual-environment support:\n  sudo apt install python3-venv\nThen rerun ./start-dev.sh.\n' >&2
    exit 1
  fi
  "$BACKEND_PYTHON" -m pip --version
fi

if ! "$BACKEND_PYTHON" -c 'import app.main, uvicorn' >/dev/null 2>&1; then
  printf 'Installing backend dependencies...\n'
  (
    cd -- "$BACKEND_DIR"
    "$BACKEND_PYTHON" -m pip install -e '.[dev]'
  )
  "$BACKEND_PYTHON" -c 'import app.main, uvicorn'
fi

if [[ ! -x "$ROOT_DIR/node_modules/.bin/vite" ]]; then
  printf 'Installing frontend dependencies...\n'
  (
    cd -- "$ROOT_DIR"
    npm ci
  )
fi

server_pids=()

cleanup() {
  trap - EXIT INT TERM
  printf '\nStopping frontend and backend...\n'
  for pid in "${server_pids[@]}"; do
    # Each server has its own process group, including reload/watch children.
    kill -TERM -- "-$pid" 2>/dev/null || true
  done
  for pid in "${server_pids[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

(
  cd -- "$BACKEND_DIR"
  export CORS_ORIGIN="${CORS_ORIGIN:-http://localhost:$FRONTEND_PORT,http://127.0.0.1:$FRONTEND_PORT}"
  exec setsid "$BACKEND_PYTHON" -m uvicorn app.main:app --reload --host 127.0.0.1 --port "$BACKEND_PORT"
) &
server_pids+=("$!")

(
  cd -- "$ROOT_DIR"
  export VITE_API_BASE_URL="http://localhost:$BACKEND_PORT"
  exec setsid npm run dev -- --host localhost --port "$FRONTEND_PORT" --strictPort
) &
server_pids+=("$!")

printf '\nStarting LitterVoyage:\n  Frontend: http://localhost:%s\n  API docs: http://localhost:%s/docs\n\nPress Ctrl+C to stop both servers.\n\n' "$FRONTEND_PORT" "$BACKEND_PORT"

if wait -n "${server_pids[@]}"; then
  status=0
else
  status=$?
fi

printf '\nA server exited. Shutting down the other server.\n'
exit "$status"
