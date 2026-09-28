# API e streaming

FastAPI publica OpenAPI em `/api/docs`. O chat usa Server-Sent Events sobre uma requisição POST lida com `fetch`: eventos `metadata`, `token`, `done` e `error` chegam sequencialmente.

SSE é unidirecional e simples para tokens. WebSocket seria útil para comunicação bidirecional contínua, mas adicionaria estado. `proxy_buffering off` no Nginx evita acumular tokens antes de entregá-los.

