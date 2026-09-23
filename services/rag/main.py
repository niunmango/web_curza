import os
import time
import logging
from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from fastembed import TextEmbedding

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("curza_rag")

QDRANT_HOST = os.getenv("QDRANT_HOST", "vector-db")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
OLLAMA_URL = os.getenv("OLLAMA_EXTERNAL_URL", "http://ollama-host:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
COLLECTION_NAME = "curza_knowledge"
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

embedding_model = None
qdrant_client = None

def get_embedding_model() -> TextEmbedding:
    global embedding_model
    if embedding_model is None:
        logger.info(f"Cargando modelo de embeddings: {EMBEDDING_MODEL_NAME}")
        embedding_model = TextEmbedding(model_name=EMBEDDING_MODEL_NAME)
    return embedding_model

def get_qdrant() -> QdrantClient:
    global qdrant_client
    if qdrant_client is None:
        qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=10.0)
    return qdrant_client

def ensure_collection_exists(max_retries: int = 5, delay: float = 2.0) -> bool:
    client = get_qdrant()
    for attempt in range(1, max_retries + 1):
        try:
            collections = client.get_collections().collections
            if not any(c.name == COLLECTION_NAME for c in collections):
                logger.info(f"Creando colección {COLLECTION_NAME} en Qdrant (dim 384, COSINE)...")
                client.create_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=VectorParams(size=384, distance=Distance.COSINE)
                )
            logger.info(f"Colección {COLLECTION_NAME} verificada exitosamente.")
            return True
        except Exception as e:
            logger.warning(f"Intento {attempt}/{max_retries} al verificar colección en Qdrant: {e}")
            if attempt < max_retries:
                time.sleep(delay)
    return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando servicio CURZAS RAG...")
    try:
        get_embedding_model()
    except Exception as e:
        logger.error(f"Error cargando modelo de embeddings: {e}")
    try:
        ensure_collection_exists(max_retries=10, delay=2.0)
    except Exception as e:
        logger.warning(f"No se pudo inicializar la colección en el arranque: {e}")
    yield
    logger.info("Deteniendo servicio CURZAS RAG...")

app = FastAPI(title="CURZAS RAG API", version="1.0", lifespan=lifespan)

class ChatQuery(BaseModel):
    prompt: str

class IngestDocument(BaseModel):
    id: int
    title: str
    content: str
    url: str

@app.get("/health")
@app.get("/api/rag/health")
def health_check():
    """Estado de salud del microservicio y conectividad con Qdrant."""
    qdrant_ok = False
    collection_ok = False
    try:
        client = get_qdrant()
        collections = client.get_collections().collections
        qdrant_ok = True
        collection_ok = any(c.name == COLLECTION_NAME for c in collections)
    except Exception as e:
        logger.warning(f"Fallo en healthcheck de Qdrant: {e}")

    return {
        "status": "healthy" if (qdrant_ok and collection_ok) else "degraded",
        "qdrant_connected": qdrant_ok,
        "collection_exists": collection_ok,
        "collection_name": COLLECTION_NAME,
        "ollama_url": OLLAMA_URL,
        "ollama_model": OLLAMA_MODEL
    }

@app.post("/api/rag/ingest")
def ingest_documents(docs: List[IngestDocument]):
    """Calcula embeddings en CPU local e indexa en Qdrant."""
    if not docs:
        return {"status": "success", "indexed_documents": 0}

    ensure_collection_exists(max_retries=3, delay=1.0)
    model = get_embedding_model()
    client = get_qdrant()

    texts = [f"{d.title}\n{d.content}" for d in docs]
    vectors = list(model.embed(texts))

    points = [
        PointStruct(
            id=d.id,
            vector=v.tolist(),
            payload={"title": d.title, "content": d.content, "url": d.url}
        )
        for d, v in zip(docs, vectors)
    ]
    client.upsert(collection_name=COLLECTION_NAME, points=points)
    logger.info(f"Indexados {len(points)} documentos en {COLLECTION_NAME}")
    return {"status": "success", "indexed_documents": len(points)}

@app.post("/api/rag/chat")
async def chat_rag(query: ChatQuery):
    """Recupera contexto de Qdrant y consulta a Ollama externo."""
    ensure_collection_exists(max_retries=2, delay=1.0)
    model = get_embedding_model()
    client = get_qdrant()

    query_vector = list(model.embed([query.prompt]))[0].tolist()

    hits = []
    try:
        # Intentar búsqueda vectorial
        if hasattr(client, "search"):
            hits = client.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_vector,
                limit=3
            )
        elif hasattr(client, "query_points"):
            res = client.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vector,
                limit=3
            )
            hits = res.points
    except Exception as e:
        logger.error(f"Error buscando en Qdrant: {e}")
        hits = []

    context = "\n---\n".join([
        f"Fuente: {h.payload.get('title', 'Sin título')} ({h.payload.get('url', '')})\n{h.payload.get('content', '')}"
        for h in hits
    ]) if hits else "No se encontró contexto indexado."

    system_prompt = (
        "Sos el asistente virtual institucional del CURZAS (Complejo Universitario Regional Zona Atlántica y Sur - UNComa). "
        "Respondé a las preguntas de estudiantes, docentes y público de manera formal, concisa y basada estrictamente "
        "en el siguiente contexto provisto. Si la información solicitada no figura en el contexto, indicá que deben consultar "
        "en ventanilla de Alumnos, Bedelía o Secretaría de Bienestar.\n\n"
        f"Contexto institucional:\n{context}"
    )

    try:
        timeout_config = httpx.Timeout(90.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout_config) as http_client:
            # Compatibilidad: si la URL incluye /v1 usa OpenAI-compatible chat completions
            if OLLAMA_URL.rstrip("/").endswith("/v1"):
                endpoint = f"{OLLAMA_URL.rstrip('/')}/chat/completions"
                payload = {
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": query.prompt}
                    ],
                    "temperature": 0.2,
                    "stream": False
                }
                resp = await http_client.post(endpoint, json=payload)
                resp.raise_for_status()
                data = resp.json()
                answer = data.get("choices", [{}])[0].get("message", {}).get("content", "Sin respuesta del modelo.")
            else:
                endpoint = f"{OLLAMA_URL.rstrip('/')}/api/generate"
                payload = {
                    "model": OLLAMA_MODEL,
                    "prompt": query.prompt,
                    "system": system_prompt,
                    "stream": False
                }
                resp = await http_client.post(endpoint, json=payload)
                resp.raise_for_status()
                data = resp.json()
                answer = data.get("response", "Sin respuesta del modelo.")

            return {
                "answer": answer.strip() if answer else "Sin respuesta del modelo.",
                "sources": [h.payload.get("url") for h in hits if h.payload and "url" in h.payload]
            }
    except Exception as exc:
        logger.error(f"Error consultando LLM ({OLLAMA_URL}): {exc}")
        # En caso de error o indisponibilidad externa, devolver respuesta con el contexto recuperado
        return {
            "answer": (
                "Aviso: No se pudo contactar el servicio LLM configurado en "
                f"{OLLAMA_URL} ({exc}). Sin embargo, la búsqueda semántica vectorial funcionó y recuperó el contexto relevante."
            ),
            "sources": [h.payload.get("url") for h in hits if h.payload and "url" in h.payload],
            "context_retrieved": [h.payload.get("title") for h in hits if h.payload]
        }
