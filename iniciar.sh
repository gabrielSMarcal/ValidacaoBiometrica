#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend/validacaoBiometricaFront"
HEALTH="http://127.0.0.1:8000/api/saude"
LOG="$BACKEND/.runtime/api.log"
API_PID=""
FRONTEND_PID=""

cleanup() {
    local status=$?
    trap - EXIT
    trap '' INT TERM

    if [[ -n "$FRONTEND_PID" ]]; then
        kill -TERM -- "-$FRONTEND_PID" 2>/dev/null || kill -TERM "$FRONTEND_PID" 2>/dev/null || true
    fi
    if [[ -n "$API_PID" ]]; then
        kill -TERM "$API_PID" 2>/dev/null || true
    fi

    for _ in {1..30}; do
        if { [[ -z "$API_PID" ]] || ! kill -0 "$API_PID" 2>/dev/null; } \
            && { [[ -z "$FRONTEND_PID" ]] || ! kill -0 -- "-$FRONTEND_PID" 2>/dev/null; }; then
            break
        fi
        sleep 0.1
    done

    if [[ -n "$FRONTEND_PID" ]]; then
        kill -KILL -- "-$FRONTEND_PID" 2>/dev/null || true
        wait "$FRONTEND_PID" 2>/dev/null || true
    fi
    if [[ -n "$API_PID" ]]; then
        kill -KILL "$API_PID" 2>/dev/null || true
        wait "$API_PID" 2>/dev/null || true
    fi
    return "$status"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ -x "$ROOT/.venv/bin/python" ]] && "$ROOT/.venv/bin/python" --version >/dev/null 2>&1; then
    PYTHON="$ROOT/.venv/bin/python"
elif [[ -x "$BACKEND/.venv/bin/python" ]] && "$BACKEND/.venv/bin/python" --version >/dev/null 2>&1; then
    PYTHON="$BACKEND/.venv/bin/python"
else
    echo "Ambiente virtual funcional nao encontrado na raiz nem em backend/.venv." >&2
    echo "Na raiz do projeto, crie um unico ambiente com: python3.12 -m venv .venv" >&2
    exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
    echo "npm nao encontrado. Instale o Node.js e o npm antes de iniciar o projeto." >&2
    exit 1
fi
if [[ ! -f "$BACKEND/requirements.txt" || ! -f "$FRONTEND/package.json" ]]; then
    echo "Estrutura do projeto incompleta: confira as pastas backend e frontend/validacaoBiometricaFront." >&2
    exit 1
fi

check_ports() {
    "$PYTHON" - "$@" <<'PY'
import errno
import socket
import sys

for value in sys.argv[1:]:
    port = int(value)
    hosts = ("127.0.0.1",) if port == 8000 else ("127.0.0.1", "::1")
    for host in hosts:
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        try:
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind((host, port))
        except OSError as exc:
            if family == socket.AF_INET6 and exc.errno in (errno.EAFNOSUPPORT, errno.EADDRNOTAVAIL):
                continue
            print(f"A porta {port} nao esta disponivel em {host}: {exc}", file=sys.stderr)
            print("Encerre a instancia que esta usando essa porta e execute o script novamente.", file=sys.stderr)
            sys.exit(1)
PY
}

check_ports 8000 4200

cd "$BACKEND"
echo "Usando o ambiente virtual: $PYTHON"
echo "Instalando as dependencias do backend..."
"$PYTHON" -m pip install -r "$BACKEND/requirements.txt"

echo "Preparando os modelos faciais..."
"$PYTHON" "$BACKEND/scripts/preparar_modelos.py"

echo "Preparando o banco MySQL..."
"$PYTHON" -m app.inicializar

echo "Instalando as dependencias do frontend..."
cd "$FRONTEND"
npm install

check_ports 8000 4200
mkdir -p "$BACKEND/.runtime"
cd "$BACKEND"
echo "Iniciando a API local..."
"$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >>"$LOG" 2>&1 &
API_PID=$!

echo "Aguardando a API responder..."
READY=0
for _ in {1..30}; do
    if ! kill -0 "$API_PID" 2>/dev/null; then
        echo "A API encerrou durante a inicializacao. Consulte: $LOG" >&2
        exit 1
    fi
    if "$PYTHON" - "$HEALTH" <<'PY'
import sys
import urllib.error
import urllib.request

try:
    with urllib.request.urlopen(sys.argv[1], timeout=1) as response:
        sys.exit(0 if response.status == 200 else 1)
except (OSError, urllib.error.URLError):
    sys.exit(1)
PY
    then
        if kill -0 "$API_PID" 2>/dev/null; then
            READY=1
            break
        fi
        echo "A API encerrou durante a inicializacao. Consulte: $LOG" >&2
        exit 1
    fi
    sleep 1
done

if [[ "$READY" != 1 ]]; then
    echo "A API nao respondeu no tempo esperado. Consulte: $LOG" >&2
    exit 1
fi

echo "API iniciada: http://127.0.0.1:8000/docs"
echo "Logs da API: $LOG"
echo "Iniciando o frontend em http://localhost:4200. Use Ctrl+C para encerrar os dois servidores."
cd "$FRONTEND"
# Sessao propria permite encerrar tambem o processo Angular iniciado pelo npm.
"$PYTHON" - <<'PY' &
import os

os.setsid()
os.execvp("npm", ["npm", "start", "--", "--host", "localhost", "--port", "4200"])
PY
FRONTEND_PID=$!
while kill -0 "$FRONTEND_PID" 2>/dev/null; do
    if ! kill -0 "$API_PID" 2>/dev/null; then
        echo "A API encerrou inesperadamente. O frontend sera encerrado. Consulte: $LOG" >&2
        exit 1
    fi
    sleep 0.25
done
wait "$FRONTEND_PID"
