#!/usr/bin/env bash
# Publish the local API on the internet. The data, models and API keys stay on this machine.
set -euo pipefail
case "${1:-}" in
  tailscale)  # needs: tailscale up, HTTPS certificates and Funnel enabled for this node in the admin console
    tailscale funnel --bg 8080
    tailscale funnel status ;;
  cloudflared)  # quick tunnel: random URL that changes on every start (named tunnel: see README)
    exec cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8080 ;;
  stop)
    tailscale funnel reset 2>/dev/null || true
    echo "funnel reset; stop cloudflared with Ctrl-C or: pkill -x cloudflared" ;;
  *) echo "usage: $0 tailscale|cloudflared|stop"; exit 2 ;;
esac
