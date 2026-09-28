# Observabilidade

Observabilidade responde “o que aconteceu e por quê?” usando três sinais: métricas agregadas, logs de eventos e traces de uma requisição. OpenTelemetry instrumenta FastAPI e HTTPX e envia spans ao Collector/Tempo.

Use o `request_id` HTTP e trace para correlacionar browser, API e dependências. Evite atributos com conteúdo de usuário; cardinalidade alta e dados sensíveis prejudicam custo e segurança.

