# Operação e troubleshooting

Comandos principais estão no `start.sh`. Para investigar:

```bash
docker compose ps
docker compose logs --tail=200 api worker rabbitmq ollama
docker compose exec ollama ollama list
docker compose exec rabbitmq rabbitmq-diagnostics check_running
```

Job parado em `queued`: confira worker e RabbitMQ. `failed`: veja campo erro e DLQ. Resposta lenta: observe CPU, modelo carregado e tamanho do contexto. Documento sem chunks: PDFs digitalizados precisam de OCR, que não está incluído nesta versão.

