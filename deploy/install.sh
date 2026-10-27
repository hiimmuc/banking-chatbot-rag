#!/usr/bin/env bash
# Install and start the API as a systemd user service, and make vLLM restart with Docker.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -x "$ROOT/.venv/bin/uvicorn" ] || { echo "create .venv first (see README)"; exit 1; }
[ -f "$ROOT/.env" ] || { echo "create .env first (cp .env.example .env)"; exit 1; }
grep -qE '^APP_PASSWORD=.+' "$ROOT/.env" && ! grep -qE '^APP_PASSWORD=(\*\*\*REMOVED\*\*\*|your-)' "$ROOT/.env" \
  || echo "WARNING: APP_PASSWORD is empty, so anyone who can reach the service can chat, upload and read documents. Keep it on localhost/tailnet, or set a password before exposing it publicly."

mkdir -p "$HOME/.config/systemd/user"
sed "s|@ROOT@|$ROOT|g" "$ROOT/deploy/rag-api.service.in" > "$HOME/.config/systemd/user/rag-api.service"
systemctl --user daemon-reload
systemctl --user enable --now rag-api
loginctl enable-linger "$USER" 2>/dev/null || echo "run once as root so the service survives logout: loginctl enable-linger $USER"
"$ROOT/scripts/run_vllm.sh" >/dev/null
sleep 3
curl -fsS http://127.0.0.1:8080/api/health && echo " <- API is up"
echo "next: deploy/expose.sh tailscale   (or cloudflared)"
