#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
set -a; source ./.env; set +a
BASE="${APP_BASE_URL:-http://localhost:8080}"
COOKIE_FILE="$(mktemp)"; DOCUMENT_FILE="$(mktemp)"; STREAM_FILE="$(mktemp)"
trap 'rm -f "$COOKIE_FILE" "$DOCUMENT_FILE" "$STREAM_FILE"' EXIT
json_field() { python3 -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"; }

curl -fsS -c "$COOKIE_FILE" -H 'Content-Type: application/json' \
  -d '{"email":"admin1@admin.com","password":"admin1"}' \
  "$BASE/identity/api/v1/auth/login" >/dev/null

STAMP="$(date +%s)"
KB_JSON="$(curl -fsS -b "$COOKIE_FILE" -H 'Content-Type: application/json' -d "{\"name\":\"Validação $STAMP\"}" "$BASE/api/v1/knowledge-bases")"
KB_ID="$(printf '%s' "$KB_JSON" | json_field id)"
printf 'O código de validação exclusivo deste documento é AZUL-742. A resposta deve preservar letras e números.\n' >"$DOCUMENT_FILE"
UPLOAD_JSON="$(curl -fsS -b "$COOKIE_FILE" -F "file=@$DOCUMENT_FILE;filename=validacao.txt" "$BASE/api/v1/knowledge-bases/$KB_ID/documents")"
JOB_ID="$(printf '%s' "$UPLOAD_JSON" | json_field job_id)"

for _ in $(seq 1 90); do
  STATUS="$(curl -fsS -b "$COOKIE_FILE" "$BASE/api/v1/jobs" | python3 -c 'import json,sys; jobs=json.load(sys.stdin); target=sys.argv[1]; print(next((x["status"] for x in jobs if x["id"]==target),"missing"))' "$JOB_ID")"
  [[ "$STATUS" == completed ]] && break
  [[ "$STATUS" == failed ]] && { echo "Job de ingestão falhou" >&2; exit 1; }
  sleep 2
done
[[ "${STATUS:-}" == completed ]] || { echo "Timeout aguardando ingestão: ${STATUS:-unknown}" >&2; exit 1; }

SESSION_JSON="$(curl -fsS -b "$COOKIE_FILE" -H 'Content-Type: application/json' -d '{"title":"Validação RAG"}' "$BASE/api/v1/sessions")"
SESSION_ID="$(printf '%s' "$SESSION_JSON" | json_field id)"
curl -fsS --max-time 240 -b "$COOKIE_FILE" -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SESSION_ID\",\"message\":\"Qual é o código de validação exclusivo?\",\"knowledge_base_ids\":[\"$KB_ID\"]}" \
  "$BASE/api/v1/chat/stream" >"$STREAM_FILE"
grep -q 'AZUL-742' "$STREAM_FILE" || { echo "A resposta não contém AZUL-742" >&2; sed -n '1,80p' "$STREAM_FILE"; exit 1; }

curl -fsS --max-time 240 -b "$COOKIE_FILE" -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SESSION_ID\",\"message\":\"Qual é o código de validação exclusivo?\",\"knowledge_base_ids\":[\"$KB_ID\"]}" \
  "$BASE/api/v1/chat/stream" >"$STREAM_FILE"
grep -q '"rag_cache": "hit"' "$STREAM_FILE" || { echo "A segunda consulta não registrou cache hit" >&2; exit 1; }

curl -fsS -b "$COOKIE_FILE" -X PATCH "$BASE/api/v1/sessions/$SESSION_ID/pin" >/dev/null
curl -fsS -b "$COOKIE_FILE" "$BASE/api/v1/sessions/$SESSION_ID" | grep -q '"is_pinned":true'
echo "E2E concluído: RabbitMQ, embeddings, Qdrant, chat PT-BR, cache e fixação validados."
