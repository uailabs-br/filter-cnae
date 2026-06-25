#!/usr/bin/env bash
# Inicia o app Streamlit e abre o navegador (Mac/Linux).
set -e
cd "$(dirname "$0")"

# Ativa a virtualenv, se existir.
if [ -d ".venv" ]; then
  source .venv/bin/activate
elif [ -d "venv" ]; then
  source venv/bin/activate
fi

PORT=8501

# Abre o navegador depois de um pequeno atraso, em background.
( sleep 2
  URL="http://localhost:${PORT}"
  if command -v open >/dev/null 2>&1; then open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"
  fi
) &

exec streamlit run app.py --server.port "${PORT}" --server.headless true
