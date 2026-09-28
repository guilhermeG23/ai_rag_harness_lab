# Estrutura e comunicação

## Fluxo síncrono do chat

```text
Browser ─login────► frontend ─HTTP─► identity ─SQL─► postgres
Browser ─HTTP/SSE─► frontend ─HTTP─► api ─HTTP streaming─► ollama
                                  ├─SQL───────────────► postgres
                                  ├─RESP──────────────► valkey
                                  ├─HTTP──────────────► qdrant
                                  └─OTLP──────────────► otel-collector ─► tempo
Browser ─HTTP─► access-portal ─► credenciais de bootstrap recebidas por variáveis de ambiente
```

O Identity Manager autentica e emite o token. A API valida novamente token, UID do grupo e ACL, consulta somente coleções autorizadas, monta o contexto e transmite tokens por SSE. PostgreSQL é a fonte de verdade; Valkey pode ser perdido sem perda funcional.

## Fluxo assíncrono

```text
/lab ─► api ─► PostgreSQL (Job=queued)
            └► RabbitMQ exchange ai.jobs
                       └► queue documents
                                └► worker ─► Ollama embeddings
                                           ├► Qdrant
                                           └► PostgreSQL
Falha final ─► ai.jobs.dlx ─► documents.dlq
```

Mensagens carregam IDs, não o arquivo. O worker usa confirmação após sucesso, prefetch 1, até três tentativas e idempotência pelo estado do job/documento.

## Isolamento RAG

Cada base possui uma coleção Qdrant própria, nomeada internamente com tenant e identificador aleatório. Usuários comuns precisam de uma linha em `knowledge_base_permissions`. A API recalcula autorização em toda requisição; a seleção da sessão nunca contorna o estado administrativo.

## Redes e portas

- `internal`: tráfego privado entre containers; marcada como internal no Compose.
- `public`: somente frontend, service-map, Grafana e RabbitMQ Management.
- 8080: web e proxy da API.
- 8081: mapa de serviços.
- 8082: portal global do Identity Manager.
- 8083: portal didático de acessos iniciais; sem autenticação.
- 3000: Grafana.
- 15672: administração RabbitMQ.

PostgreSQL, Qdrant, Valkey, Ollama, Prometheus, Loki, Tempo e OTLP não publicam portas no host.

## Dados persistentes

Volumes: `postgres_data`, `qdrant_data`, `rabbitmq_data`, `ollama_data`, `uploads`, `prometheus_data`, `loki_data`, `tempo_data` e `grafana_data`. Valkey é deliberadamente efêmero.

## Observabilidade

Prometheus coleta `/metrics`; OpenTelemetry envia traces ao Collector e ao Tempo; Promtail lê logs JSON dos containers e os envia ao Loki; Grafana provisiona as três fontes.
