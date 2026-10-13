#!/usr/bin/env bash
# Entrypoint for every Railway service in this project.
#
# Railway builds ONE image from this repo and runs it as three services. The
# dispatch lives here, in code that is reviewed and versioned, rather than in
# three start-command fields in a web UI that nothing tests.
#
#   web     SERVICE_ROLE=web     dashboard SPA + JSON API      (HTTP, behind Access)
#   hooks   SERVICE_ROLE=hooks   Plaid webhook receiver        (HTTP, signed requests)
#   worker  SERVICE_ROLE=worker  job queue consumer + scheduler (no HTTP)
#
# See docs/10-architecture.md §1 for why these are three processes.
set -euo pipefail

case "${SERVICE_ROLE:-}" in
  web)
    # --proxy-headers: Railway (and Cloudflare in front of it) terminates TLS;
    # without it every client IP in the logs is a load balancer.
    exec python -m uvicorn server.app.web:app \
         --host 0.0.0.0 --port "${PORT:-8080}" \
         --workers "${WEB_WORKERS:-2}" --proxy-headers --forwarded-allow-ips='*'
    ;;
  hooks)
    exec python -m uvicorn server.app.hooks:app \
         --host 0.0.0.0 --port "${PORT:-8080}" \
         --workers 1 --proxy-headers --forwarded-allow-ips='*'
    ;;
  worker)
    exec python -m server.app.worker
    ;;
  *)
    echo "SERVICE_ROLE must be 'web', 'hooks' or 'worker', got '${SERVICE_ROLE:-<unset>}'" >&2
    exit 64
    ;;
esac
