import hashlib
import json
import logging
from typing import Any

import httpx
import pika
import redis

from .config import settings

log = logging.getLogger(__name__)


def cache_client():
    return redis.Redis.from_url(settings.valkey_url, decode_responses=True, socket_timeout=2)


def cache_key(prefix: str, payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return f"{prefix}:{hashlib.sha256(raw.encode()).hexdigest()}"


def publish_job(routing_key: str, payload: dict):
    connection = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
    channel = connection.channel()
    channel.exchange_declare(exchange="ai.jobs", exchange_type="topic", durable=True)
    channel.basic_publish(
        exchange="ai.jobs",
        routing_key=routing_key,
        body=json.dumps(payload).encode(),
        properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
    )
    connection.close()


def embed_sync(texts: list[str]) -> list[list[float]]:
    key = cache_key("emb", {"model": settings.embed_model, "texts": texts})
    try:
        cached = cache_client().get(key)
        if cached:
            return json.loads(cached)
    except Exception:
        log.warning("cache_unavailable", exc_info=True)
    with httpx.Client(timeout=180) as client:
        response = client.post(
            f"{settings.ollama_url}/api/embed",
            json={"model": settings.embed_model, "input": texts},
        )
        response.raise_for_status()
        vectors = response.json()["embeddings"]
    try:
        cache_client().setex(key, 86400, json.dumps(vectors))
    except Exception:
        pass
    return vectors


async def embed_async(text: str) -> list[float]:
    key = cache_key("emb", {"model": settings.embed_model, "text": text})
    try:
        cached = cache_client().get(key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            f"{settings.ollama_url}/api/embed",
            json={"model": settings.embed_model, "input": text},
        )
        response.raise_for_status()
        vector = response.json()["embeddings"][0]
    try:
        cache_client().setex(key, 86400, json.dumps(vector))
    except Exception:
        pass
    return vector


def ensure_collection(name: str, dimensions: int):
    with httpx.Client(timeout=30) as client:
        response = client.get(f"{settings.qdrant_url}/collections/{name}")
        if response.status_code == 404:
            response = client.put(
                f"{settings.qdrant_url}/collections/{name}",
                json={"vectors": {"size": dimensions, "distance": "Cosine"}},
            )
            response.raise_for_status()
        elif response.status_code >= 400:
            response.raise_for_status()


def upsert_points(collection: str, points: list[dict]):
    with httpx.Client(timeout=120) as client:
        response = client.put(
            f"{settings.qdrant_url}/collections/{collection}/points?wait=true",
            json={"points": points},
        )
        response.raise_for_status()


def delete_document_points(collection: str, document_id: str):
    with httpx.Client(timeout=60) as client:
        response = client.post(
            f"{settings.qdrant_url}/collections/{collection}/points/delete?wait=true",
            json={"filter": {"must": [{"key": "document_id", "match": {"value": document_id}}]}},
        )
        response.raise_for_status()


async def search_collection(collection: str, vector: list[float], limit: int = 4) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{settings.qdrant_url}/collections/{collection}/points/search",
            json={"vector": vector, "limit": limit, "with_payload": True, "score_threshold": 0.35},
        )
        response.raise_for_status()
        return response.json().get("result", [])


def delete_collection(collection: str):
    with httpx.Client(timeout=60) as client:
        response = client.delete(f"{settings.qdrant_url}/collections/{collection}")
        if response.status_code not in (200, 404):
            response.raise_for_status()

