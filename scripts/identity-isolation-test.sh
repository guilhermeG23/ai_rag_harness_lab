#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
BASE="${APP_BASE_URL:-http://localhost:8080}"
C1="$(mktemp)"; C2="$(mktemp)"; CC="$(mktemp)"; CT="$(mktemp)"
trap 'rm -f "$C1" "$C2" "$CC" "$CT"' EXIT
login() { curl -fsS -c "$1" -H 'Content-Type: application/json' -d "$2" "$BASE/identity/api/v1/auth/login" >/dev/null; }
login "$C1" '{"email":"admin1@admin.com","password":"admin1"}'
login "$C2" '{"email":"admin2@admin.com","password":"admin2"}'
login "$CC" '{"email":"teste1@teste.com","password":"teste1"}'
G1="$(curl -fsS -b "$C1" "$BASE/api/v1/auth/me" | python3 -c 'import json,sys; print(json.load(sys.stdin)["tenant_id"])')"
G2="$(curl -fsS -b "$C2" "$BASE/api/v1/auth/me" | python3 -c 'import json,sys; print(json.load(sys.stdin)["tenant_id"])')"
[[ "$G1" != "$G2" ]] || { echo "Falha: grupos têm o mesmo UID" >&2; exit 1; }
STAMP="$(date +%s)"
KB="$(curl -fsS -b "$C1" -H 'Content-Type: application/json' -d "{\"name\":\"Isolamento $STAMP\"}" "$BASE/api/v1/knowledge-bases" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
CODE="$(curl -sS -o /dev/null -w '%{http_code}' -b "$C2" -X PATCH -H 'Content-Type: application/json' -d '{"name":"INVASAO"}' "$BASE/api/v1/knowledge-bases/$KB")"
[[ "$CODE" == 404 ]] || { echo "Falha: admin2 acessou base do admin1 (HTTP $CODE)" >&2; exit 1; }
curl -fsS -b "$C2" "$BASE/api/v1/knowledge-bases" | python3 -c 'import json,sys; target=sys.argv[1]; assert all(x["id"] != target for x in json.load(sys.stdin))' "$KB"
CODE="$(curl -sS -o /dev/null -w '%{http_code}' -b "$CC" "$BASE/api/v1/jobs")"
[[ "$CODE" == 403 ]] || { echo "Falha: cliente acessou laboratório (HTTP $CODE)" >&2; exit 1; }
CODE="$(curl -sS -o /dev/null -w '%{http_code}' -b "$C1" -H 'Content-Type: application/json' -d '{"email":"teste1@teste.com","display_name":"Duplicado","password":"teste1","role":"client"}' "$BASE/identity/api/v1/group/users")"
[[ "$CODE" == 409 ]] || { echo "Falha: duplicidade não bloqueada (HTTP $CODE)" >&2; exit 1; }
TEMP_EMAIL="temporario-$STAMP@teste.com"
TEMP_ID="$(curl -fsS -b "$C1" -H 'Content-Type: application/json' -d "{\"email\":\"$TEMP_EMAIL\",\"display_name\":\"Temporário\",\"password\":\"temp123\",\"role\":\"client\"}" "$BASE/identity/api/v1/group/users" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
login "$CT" "{\"email\":\"$TEMP_EMAIL\",\"password\":\"temp123\"}"
curl -fsS -b "$CT" -X PATCH -H 'Content-Type: application/json' -d '{"display_name":"Perfil alterado","password":"temp456"}' "$BASE/identity/api/v1/me" | python3 -c 'import json,sys; assert json.load(sys.stdin)["display_name"] == "Perfil alterado"'
CODE="$(curl -sS -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' -d "{\"email\":\"$TEMP_EMAIL\",\"password\":\"temp123\"}" "$BASE/identity/api/v1/auth/login")"
[[ "$CODE" == 401 ]] || { echo "Falha: senha antiga ainda funciona (HTTP $CODE)" >&2; exit 1; }
login "$CT" "{\"email\":\"$TEMP_EMAIL\",\"password\":\"temp456\"}"
curl -fsS -b "$C1" -X PATCH -H 'Content-Type: application/json' -d '{"is_active":false}' "$BASE/identity/api/v1/group/users/$TEMP_ID" >/dev/null
CODE="$(curl -sS -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' -d "{\"email\":\"$TEMP_EMAIL\",\"password\":\"temp456\"}" "$BASE/identity/api/v1/auth/login")"
[[ "$CODE" == 403 ]] || { echo "Falha: usuário desativado entrou (HTTP $CODE)" >&2; exit 1; }
curl -fsS -b "$C1" -X DELETE "$BASE/identity/api/v1/group/users/$TEMP_ID?mode=30d" >/dev/null
curl -fsS -b "$C1" "$BASE/identity/api/v1/group/users" | python3 -c '
import datetime, json, sys
target = next(x for x in json.load(sys.stdin) if x["id"] == sys.argv[1])
assert target["is_active"] is False
deleted = datetime.datetime.fromisoformat(target["deleted_at"])
purge = datetime.datetime.fromisoformat(target["purge_after"])
assert datetime.timedelta(days=29, hours=23) < purge - deleted < datetime.timedelta(days=30, minutes=1)
' "$TEMP_ID"
curl -fsS -b "$C1" -X PATCH -H 'Content-Type: application/json' -d '{"is_active":true}' "$BASE/identity/api/v1/group/users/$TEMP_ID" | python3 -c '
import json, sys
target = json.load(sys.stdin)
assert target["is_active"] is True and target["deleted_at"] is None and target["purge_after"] is None
'
curl -fsS -b "$C1" -X DELETE "$BASE/identity/api/v1/group/users/$TEMP_ID?mode=immediate" >/dev/null
curl -fsS -b "$C1" -X DELETE "$BASE/api/v1/knowledge-bases/$KB" >/dev/null
echo "Isolamento aprovado: UIDs distintos, RBAC, perfil/senha, anti-duplicidade, desativação, retenção de 30 dias, restauração e exclusão permanente validados."
