import os


class Settings:
    database_url = os.environ["DATABASE_URL"]
    rabbitmq_url = os.environ["RABBITMQ_URL"]
    valkey_url = os.environ["VALKEY_URL"]
    qdrant_url = os.environ.get("QDRANT_URL", "http://qdrant:6333")
    ollama_url = os.environ.get("OLLAMA_URL", "http://ollama:11434")
    chat_model = os.environ.get("OLLAMA_CHAT_MODEL", "gemma3:1b")
    embed_model = os.environ.get("OLLAMA_EMBED_MODEL", "embeddinggemma")
    context_tokens = int(os.environ.get("MODEL_CONTEXT_TOKENS", "4096"))
    retention_days = int(os.environ.get("DEFAULT_RETENTION_DAYS", "30"))
    upload_max_mb = int(os.environ.get("UPLOAD_MAX_MB", "25"))
    app_secret = os.environ["APP_SECRET"]
    upload_dir = "/data/uploads"


settings = Settings()
