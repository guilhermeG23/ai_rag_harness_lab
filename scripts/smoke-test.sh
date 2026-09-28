#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
set -a; source ./.env; set +a
BASE="${APP_BASE_URL:-http://localhost:8080}"
COOKIE_FILE="$(mktemp)"
trap 'rm -f "$COOKIE_FILE"' EXIT
curl -fsS "$BASE/health" >/dev/null
curl -fsS -c "$COOKIE_FILE" -H 'Content-Type: application/json' -d '{"email":"admin1@admin.com","password":"admin1"}' "$BASE/identity/api/v1/auth/login" >/dev/null
curl -fsS -b "$COOKIE_FILE" "$BASE/api/v1/auth/me" >/dev/null
curl -fsS "http://localhost:8082/health" >/dev/null
curl -fsS "http://localhost:8081/health" >/dev/null
curl -fsS "http://localhost:8083/health" >/dev/null
curl -fsS "http://localhost:8083/api/accesses" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert any(x["name"] == "Grafana" for x in data["sections"]); assert any(x["name"] == "Chat e Laboratório" and len(x["accounts"]) == 8 for x in data["sections"])'
echo "Smoke test concluído com sucesso."
