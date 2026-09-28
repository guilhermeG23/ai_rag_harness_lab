#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

compose() { docker compose --env-file .env "$@"; }
random_secret() { openssl rand -hex 24; }

ensure_env() {
  if [[ ! -f .env ]]; then
    cp .env.example .env
    local pg rabbit valkey grafana app
    pg="$(random_secret)"; rabbit="$(random_secret)"; valkey="$(random_secret)"; grafana="$(random_secret)"; app="$(random_secret)"
    sed -i "s/change-me-postgres/$pg/;s/change-me-rabbitmq/$rabbit/;s/change-me-valkey/$valkey/;s/change-me-grafana/$grafana/;s/change-me-app-secret-at-least-32-characters/$app/" .env
    chmod 600 .env
    echo "Arquivo .env criado. Altere as credenciais bootstrap antes de expor o ambiente."
  fi
}

check_requirements() {
  command -v docker >/dev/null || { echo "Docker não encontrado." >&2; exit 1; }
  docker compose version >/dev/null || { echo "Docker Compose não encontrado." >&2; exit 1; }
  command -v openssl >/dev/null || { echo "OpenSSL não encontrado." >&2; exit 1; }
  local memory_kb disk_kb
  memory_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
  disk_kb="$(df -Pk . | awk 'NR==2 {print $4}')"
  if (( memory_kb < 6000000 )); then echo "AVISO: recomenda-se ao menos 6 GiB de RAM."; fi
  if (( disk_kb < 12000000 )); then echo "AVISO: há menos de 12 GiB livres."; fi
}

wait_url() {
  local url="$1" name="$2"
  for _ in $(seq 1 60); do
    if curl -fsS "$url" >/dev/null 2>&1; then echo "$name disponível"; return 0; fi
    sleep 3
  done
  echo "Timeout aguardando $name" >&2
  return 1
}

pull_models() {
  echo "Baixando modelos ausentes..."
  compose up -d ollama
  compose exec -T ollama ollama pull "${OLLAMA_CHAT_MODEL:-gemma3:1b}"
  compose exec -T ollama ollama pull "${OLLAMA_EMBED_MODEL:-embeddinggemma}"
}

start_all() {
  check_requirements
  ensure_env
  set -a; source ./.env; set +a
  compose config >/dev/null
  compose pull
  compose up -d postgres qdrant valkey rabbitmq ollama
  pull_models
  compose up -d --build
  wait_url "http://localhost:8080/health" "Frontend"
  wait_url "http://localhost:8081/health" "Mapa de serviços"
  wait_url "http://localhost:8083/health" "Portal de acessos"
  echo
  echo "AI RAG Harness iniciado:"
  echo "  Chat:       http://$(hostname -I | awk '{print $1}'):8080/chat"
  echo "  Lab:        http://$(hostname -I | awk '{print $1}'):8080/lab"
  echo "  Serviços:   http://$(hostname -I | awk '{print $1}'):8081"
  echo "  Identidade: http://$(hostname -I | awk '{print $1}'):8082"
  echo "  Acessos:    http://$(hostname -I | awk '{print $1}'):8083"
  echo "  Grafana:    http://$(hostname -I | awk '{print $1}'):3000"
  echo "  RabbitMQ:   http://$(hostname -I | awk '{print $1}'):15672"
  echo "  Admin IA:   admin1@admin.com"
}

ensure_env
case "${1:-start}" in
  start) start_all ;;
  --status|status) compose ps ;;
  --stop|stop) compose down ;;
  --restart|restart) compose restart ;;
  --logs|logs) compose logs -f --tail=200 ;;
  --pull-model|pull-model) set -a; source ./.env; set +a; pull_models ;;
  --smoke-test|smoke-test) ./scripts/smoke-test.sh ;;
  --e2e-test|e2e-test) ./scripts/e2e-test.sh ;;
  --identity-test|identity-test) ./scripts/identity-isolation-test.sh ;;
  *) echo "Uso: $0 [start|status|stop|restart|logs|pull-model|smoke-test|e2e-test|identity-test]"; exit 2 ;;
esac
