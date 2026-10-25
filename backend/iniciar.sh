#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$ROOT/.venv/bin/python"
HEALTH="http://127.0.0.1:8000/api/saude"
LOG="$ROOT/.runtime/api.log"
API_PID=""

if [[ ! -x "$PYTHON" ]]; then
    echo "Ambiente virtual nao encontrado em .venv" >&2
    exit 1
fi

cd "$ROOT"

echo "Instalando as dependencias do backend..."
uv pip install -r "$ROOT/requirements.txt"

echo "Preparando os modelos faciais..."
"$PYTHON" scripts/preparar_modelos.py

echo "Preparando o banco MySQL..."
"$PYTHON" -m app.inicializar

mkdir -p "$ROOT/.runtime"
echo "Iniciando a API local..."
nohup "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 \
    >>"$LOG" 2>&1 &
API_PID=$!

cleanup() {
    if [[ -n "$API_PID" ]] && kill -0 "$API_PID" 2>/dev/null; then
        kill "$API_PID" 2>/dev/null || true
    fi
}

trap cleanup INT TERM

echo "Aguardando a API responder..."
for _ in {1..30}; do
    if curl --silent --fail "$HEALTH" >/dev/null 2>&1; then
        trap - INT TERM
        echo "API iniciada com sucesso."
        echo "Logs: $LOG"
        exit 0
    fi
    sleep 1
done

echo "A API nao respondeu no tempo esperado." >&2
echo "Consulte os logs em: $LOG" >&2
cleanup
exit 1
