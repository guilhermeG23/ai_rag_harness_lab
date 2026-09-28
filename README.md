# AI RAG Harness

Laboratório autocontido para estudar uma aplicação de IA local: chat em PT-BR, RAG multitenant, sessões, cache, filas, guardrails e observabilidade. O modelo de chat padrão é o `gemma3:1b`; embeddings usam `embeddinggemma`. Ambos rodam localmente via Ollama.

## Início rápido

Requisitos: Linux x86_64, Docker com Compose, `curl`, `openssl`, 6 GiB de RAM e cerca de 12 GiB livres.

```bash
chmod +x start.sh scripts/*.sh
./start.sh
```

Na primeira execução o script cria `.env`, gera segredos, baixa imagens e modelos, constrói a aplicação e aguarda os healthchecks. Revise no `.env` todas as credenciais antes de expor a VM.

Endereços padrão:

| Interface | URL |
|---|---|
| Chat comum | `http://HOST:8080/chat` |
| Laboratório | `http://HOST:8080/lab` |
| Mapa de serviços | `http://HOST:8081` |
| Identity Manager | `http://HOST:8082` |
| Acessos iniciais | `http://HOST:8083` |
| Grafana | `http://HOST:3000` |
| RabbitMQ Management | `http://HOST:15672` |
| OpenAPI | `http://HOST:8080/api/docs` |

O administrador global do Identity Manager é `admin` / `admin`. Troque essa senha no `.env` antes de qualquer exposição externa. Os grupos iniciais são `admin1` e `admin2`; seus UIDs, e não os nomes, definem os relacionamentos.

No grupo `admin1`: `admin1@admin.com` / `admin1` e `teste1@teste.com` até `teste3@teste.com`, com senhas `teste1` até `teste3`. No grupo `admin2`: `admin2@admin.com` / `admin2` e `teste4@teste.com` até `teste6@teste.com`, com senhas correspondentes.

## Operação

```bash
./start.sh status
./start.sh logs
./start.sh restart
./start.sh stop
./start.sh pull-model
./start.sh smoke-test
./start.sh e2e-test
./start.sh identity-test
```

## Primeiro experimento RAG

1. Entre no `/lab` como administrador.
2. Use um dos grupos iniciais ou crie grupo e usuários no Identity Manager.
3. Crie uma base RAG para o grupo autenticado.
4. Envie um `.pdf`, `.txt` ou `.md`.
5. Acompanhe o job RabbitMQ até `completed`.
6. Entre no `/chat` com um usuário autorizado.
7. Selecione a base e faça uma pergunta cujo conteúdo esteja no documento.
8. Compare fontes, scores, cache e tempos no painel técnico.

## Componentes

- FastAPI: API, RBAC, sessões, contexto, RAG, guardrails e SSE.
- Identity Manager: container separado para login, Argon2, grupos, usuários, bloqueios e exclusões.
- Portal de acessos: referência didática das credenciais iniciais, separadas por serviço.
- Ollama: inferência e embeddings locais.
- PostgreSQL: fonte persistente de usuários, sessões, documentos, jobs e auditoria.
- Qdrant: uma coleção vetorial independente por base de conhecimento.
- Valkey: cache descartável de embeddings e buscas.
- RabbitMQ: jobs duráveis; um worker executa ingestão e exclusões.
- Grafana, Prometheus, Loki, Tempo e OpenTelemetry: métricas, logs e traces.
- Nginx: frontend e mapa de serviços.

## Limitações intencionais

Este é um harness educacional, não uma distribuição pronta para Internet. O portal da porta 8083 expõe deliberadamente credenciais de bootstrap e nunca deve ser publicado em rede não confiável. O guardrail é heurístico, não há TLS embutido, o modelo 1B tem capacidade limitada e a criação automática de tabelas não substitui migrações versionadas em produção. Para exposição pública, remova o portal de acessos e adicione proxy TLS, rotação de segredos, SSO, backup, políticas corporativas e testes de segurança.

## Documentação

Para operar a plataforma, consulte o [manual de uso](manual.md). Para estudar os conceitos, comece por [docs/README.md](docs/README.md). A topologia detalhada está em [STRUCT.md](STRUCT.md) e o contexto para agentes está em [AGENT.md](AGENT.md).
