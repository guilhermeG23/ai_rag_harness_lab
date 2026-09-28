# Contexto para agentes

## Objetivo

Manter um harness didático local que exponha, e não esconda, o ciclo de uma aplicação de IA: request, autenticação, sessão, contexto, embeddings, recuperação, prompt, inferência, cache, fila e telemetria.

## Regras arquiteturais

1. PostgreSQL é a fonte persistente de verdade; Valkey nunca é obrigatório para correção.
2. Nunca pesquise uma coleção Qdrant antes de validar tenant, ACL e estado `active`.
3. Cada base RAG usa coleção independente. Não consolide tenants em uma coleção filtrada.
4. `/lab` é apenas UI; autorização administrativa deve existir na API via nível `admin` e UID do grupo.
5. O container `identity` é o proprietário funcional de credenciais, grupos, tokens e ciclo de vida de usuários.
6. Chat streaming permanece direto; tarefas longas passam pelo RabbitMQ.
7. Jobs devem ser idempotentes porque RabbitMQ entrega pelo menos uma vez.
8. Não registrar senhas, tokens, conteúdo integral de documentos ou prompts sensíveis.
9. Toda mutação administrativa gera `AuditEvent`.
10. Alteração de documento, ACL ou base deve invalidar cache por versão.
11. Preserve compatibilidade com CPU, 2 vCPUs e 8 GiB de RAM.
12. `access-portal` é uma exceção didática deliberada: exibe somente credenciais de bootstrap, não consulta hashes e não deve ser exposto fora da LAN de estudo.

## Comandos obrigatórios antes de entregar

```bash
python3 -m compileall -q apps/api/app
bash -n start.sh scripts/*.sh
docker compose --env-file .env config
./start.sh smoke-test
```

Após alterações de RAG, valide isolamento com dois tenants e conteúdo contraditório. Após alterações no worker, teste sucesso, retentativa e DLQ. Após alterações em sessões, teste fixação, exclusão, restauração e expurgo.

## Mapa do código

- `apps/api/app/main.py`: rotas e orquestração HTTP/SSE.
- `models.py`: esquema relacional.
- `integrations.py`: Valkey, RabbitMQ, Ollama e Qdrant.
- `worker.py`: consumo RabbitMQ e ciclo de documentos.
- `maintenance.py`: retenção de sessões e tokens.
- `apps/frontend`: `/chat` e `/lab`.
- `apps/identity`: login, Argon2, grupos, usuários, portal global e expurgo de contas.
- `apps/service-map`: visão operacional independente.
- `apps/access-portal`: referência somente leitura de acessos iniciais por serviço.
- `infra`: configurações dos produtos de infraestrutura.

## Segurança

Nunca commitar `.env`. A autenticação é aplicada no backend. IDs vindos do browser são não confiáveis. Operações destrutivas precisam de confirmação na UI e auditoria. O portal de acessos torna o ambiente intencionalmente inseguro fora do laboratório. A versão atual é adequada a LAN de estudo, não à Internet pública.
