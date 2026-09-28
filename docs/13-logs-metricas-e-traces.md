# Logs, métricas e traces

Prometheus coleta contadores de chat, cache e histogramas de duração. Promtail lê logs dos containers e envia ao Loki. Tempo armazena traces; Grafana consulta os três. O dashboard provisionado apresenta nomes descritivos, unidades e ajuda contextual para volume de chats, sucesso, fila RabbitMQ, latência média/P95, cache e logs.

Métrica mostra tendência, log mostra evento e trace mostra caminho/tempo. Para experimentar, provoque uma busca cache miss e repita-a; compare `cache_events_total` e a duração do chat.
