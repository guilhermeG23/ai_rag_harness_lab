import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).parent
PORT = 8083


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def account(username: str, password: str, role: str = "") -> dict:
    return {"username": username, "password": password, "role": role}


def payload() -> dict:
    return {
        "warning": "Valores iniciais de bootstrap. Se uma senha for alterada na aplicação, este portal não descobrirá o novo valor e poderá ficar desatualizado.",
        "sections": [
            {
                "name": "Chat e Laboratório",
                "description": "Contas iniciais dos grupos didáticos. Administradores acessam /chat e /lab; clientes acessam /chat.",
                "url": ":8080/chat",
                "accounts": [
                    account("admin1@admin.com", "admin1", "admin · grupo admin1"),
                    account("teste1@teste.com", "teste1", "cliente · grupo admin1"),
                    account("teste2@teste.com", "teste2", "cliente · grupo admin1"),
                    account("teste3@teste.com", "teste3", "cliente · grupo admin1"),
                    account("admin2@admin.com", "admin2", "admin · grupo admin2"),
                    account("teste4@teste.com", "teste4", "cliente · grupo admin2"),
                    account("teste5@teste.com", "teste5", "cliente · grupo admin2"),
                    account("teste6@teste.com", "teste6", "cliente · grupo admin2"),
                ],
            },
            {
                "name": "Identity Manager",
                "description": "Administração global de grupos e usuários.",
                "url": ":8082",
                "accounts": [account(env("IDENTITY_ADMIN_USER", "admin"), env("IDENTITY_ADMIN_PASSWORD", "admin"), "administrador global")],
            },
            {
                "name": "Grafana",
                "description": "Dashboards de métricas, logs e traces.",
                "url": ":3000",
                "accounts": [account(env("GRAFANA_ADMIN_USER", "admin"), env("GRAFANA_ADMIN_PASSWORD"), "administrador")],
            },
            {
                "name": "RabbitMQ Management",
                "description": "Filas, consumidores, retentativas e dead-letter queue.",
                "url": ":15672",
                "accounts": [account(env("RABBITMQ_USER"), env("RABBITMQ_PASSWORD"), "administrador do broker")],
            },
            {
                "name": "PostgreSQL",
                "description": "Banco interno; não possui porta publicada no host.",
                "endpoint": "postgres:5432",
                "database": env("POSTGRES_DB"),
                "accounts": [account(env("POSTGRES_USER"), env("POSTGRES_PASSWORD"), "usuário do banco")],
            },
            {
                "name": "Valkey",
                "description": "Cache interno; usa o usuário ACL padrão e não possui porta publicada.",
                "endpoint": "valkey:6379",
                "accounts": [account("default", env("VALKEY_PASSWORD"), "usuário ACL padrão · cache interno")],
            },
            {
                "name": "Serviços sem login",
                "description": "Interfaces e APIs sem credencial própria. Serviços internos não são publicados no host.",
                "links": [
                    {"label": "Mapa de serviços", "url": ":8081"},
                    {"label": "OpenAPI/FastAPI", "url": ":8080/api/docs"},
                    {"label": "Ollama", "endpoint": "ollama:11434 (interno)"},
                    {"label": "Qdrant", "endpoint": "qdrant:6333 (interno)"},
                    {"label": "Prometheus", "endpoint": "prometheus:9090 (interno)"},
                    {"label": "Loki", "endpoint": "loki:3100 (interno)"},
                    {"label": "Tempo", "endpoint": "tempo:3200 (interno)"},
                ],
            },
        ],
    }


class Handler(BaseHTTPRequestHandler):
    static = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8")}

    def send_bytes(self, body: bytes, content_type: str, status: int = 200, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_bytes(b'{"status":"ok","service":"access-portal"}', "application/json")
        elif self.path == "/api/accesses":
            self.send_bytes(json.dumps(payload(), ensure_ascii=False).encode(), "application/json")
        elif self.path in self.static:
            name, content_type = self.static[self.path]
            self.send_bytes((ROOT / name).read_bytes(), content_type, cache="public, max-age=300")
        else:
            self.send_bytes(b"not found", "text/plain; charset=utf-8", 404)

    def log_message(self, message: str, *args) -> None:
        print(json.dumps({"service": "access-portal", "client": self.client_address[0], "message": message % args}))


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
