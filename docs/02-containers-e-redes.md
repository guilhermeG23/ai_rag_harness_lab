# Containers e redes

`compose.yaml` declara todos os serviços, healthchecks, volumes, limites e dependências. A rede `internal` não é roteada a partir do host; a `public` contém apenas interfaces que precisam ser acessadas.

Não publique diretamente PostgreSQL, Qdrant, Valkey ou Ollama. Use `docker compose ps`, `docker compose logs SERVICO` e o mapa na porta 8081. O `access-portal`, na porta 8083, é público apenas para a LAN didática e mostra valores iniciais recebidos do `.env`; ele deve ser removido de qualquer implantação real. Healthcheck indica disponibilidade, não garante que toda operação de negócio funcione.
