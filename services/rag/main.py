import os
import time
import json
import re
import logging
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
    ARGENTINA_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
except Exception:
    ARGENTINA_TZ = None
from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
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
        qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=10.0, check_compatibility=False)
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

class ChatMessage(BaseModel):
    role: str = Field(..., description="Rol del mensaje: 'user' o 'assistant'")
    content: str = Field(..., description="Texto del mensaje")

class ChatQuery(BaseModel):
    prompt: str = Field(..., min_length=2, max_length=1500, description="Consulta del usuario (entre 2 y 1500 caracteres)")
    history: Optional[List[ChatMessage]] = []
    stream: Optional[bool] = False

# Mapeo y palabras clave de los Departamentos Académicos para resolución de entidades y contexto
DEPARTMENTS_META = {
    "tecnologia": {
        "name": "Departamento de Ciencia y Tecnología",
        "url": "/tecnologia",
        "contact_id": 98301,
        "dept_id": 98101,
        "keywords": ["ciencia y tecnologia", "tecnologia", "cyt", "sistemas", "software", "desarrollo web", "informatica", "programacion", "computacion"]
    },
    "psicopedagogia": {
        "name": "Departamento de Psicopedagogía",
        "url": "/psicopedagogia",
        "contact_id": 98302,
        "dept_id": 98102,
        "keywords": ["psicopedagogia", "pedagogia", "psico", "psicopedagogo", "psicopedagoga", "aprendizaje"]
    },
    "lengua-comunicacion": {
        "name": "Departamento de Lengua, Literatura y Comunicación",
        "url": "/lengua-comunicacion",
        "contact_id": 98303,
        "dept_id": 98103,
        "keywords": ["lengua y comunicacion", "literatura y comunicacion", "lengua", "literatura", "comunicacion", "letras", "gestion cultural", "arte y sociedad"]
    },
    "admin-publica": {
        "name": "Departamento de Administración Pública",
        "url": "/admin-publica",
        "contact_id": 98304,
        "dept_id": 98104,
        "keywords": ["administracion publica", "administracion", "recursos humanos", "rrhh", "administracion general"]
    },
    "estudios-politicos": {
        "name": "Departamento de Estudios Políticos",
        "url": "/estudios-politicos",
        "contact_id": 98305,
        "dept_id": 98105,
        "keywords": ["estudios politicos", "ciencias politicas", "ciencia politica", "politica", "estudios sociales"]
    },
    "gestion-agropecuaria": {
        "name": "Departamento de Gestión Agropecuaria",
        "url": "/gestion-agropecuaria",
        "contact_id": 98306,
        "dept_id": 98106,
        "keywords": ["gestion agropecuaria", "ciencias agropecuarias", "agropecuaria", "agro", "espacios verdes", "produccion agropecuaria"]
    },
    "enfermeria": {
        "name": "Coordinación de la Carrera de Enfermería",
        "url": "/enfermeria",
        "contact_id": 98307,
        "dept_id": 98107,
        "keywords": ["carrera de enfermeria", "coordinacion de enfermeria", "enfermeria", "enfermero", "enfermera"]
    }
}

def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[áàäâ]', 'a', text)
    text = re.sub(r'[éèëê]', 'e', text)
    text = re.sub(r'[íìïî]', 'i', text)
    text = re.sub(r'[óòöô]', 'o', text)
    text = re.sub(r'[úùüû]', 'u', text)
    text = re.sub(r'[ñ]', 'n', text)
    return text

def matches_department_keyword(norm_text: str, keyword: str) -> bool:
    norm_kw = normalize_text(keyword)
    if len(norm_kw) <= 4:
        return bool(re.search(r'\b' + re.escape(norm_kw) + r'\b', norm_text))
    return norm_kw in norm_text

# Mapeo y palabras clave para Calendario Académico, Clases y Fechas
CALENDAR_DOC_IDS = [1000295, 1000296]
CALENDAR_TOPIC_KEYWORDS = [
    "calendario", "calendario academico", "clase", "clases", "cursar", "cursado",
    "semana del estudiante", "receso", "vacaciones", "final", "finales", "mesa de examen",
    "mesas de examen", "turno de examen", "inscripcion", "inscripciones", "asueto", "cuatrimestre",
    "actividad academica", "abierto", "abre", "atiende", "feriado", "feriados",
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]
TEMPORAL_KEYWORDS = [
    "hoy", "manana", "esta semana", "este mes", "este cuatrimestre", "ayer"
]

def get_current_date_info():
    if ARGENTINA_TZ:
        now_ar = datetime.now(ARGENTINA_TZ)
    else:
        now_ar = datetime.now()
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    dia_nombre = dias[now_ar.weekday()]
    mes_nombre = meses[now_ar.month - 1]
    fecha_formateada = f"{dia_nombre.capitalize()} {now_ar.day} de {mes_nombre} de {now_ar.year}"
    return now_ar, fecha_formateada, dia_nombre, mes_nombre

class IngestDocument(BaseModel):
    id: int
    title: str
    content: str
    url: str
    date: Optional[str] = ""

class PayloadUpdate(BaseModel):
    id: int
    date: str

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
            payload={"title": d.title, "content": d.content, "url": d.url, "date": d.date or ""}
        )
        for d, v in zip(docs, vectors)
    ]
    client.upsert(collection_name=COLLECTION_NAME, points=points)
    logger.info(f"Indexados {len(points)} documentos en {COLLECTION_NAME}")
    return {"status": "success", "indexed_documents": len(points)}

@app.post("/api/rag/update-dates")
def update_dates(updates: List[PayloadUpdate]):
    """Actualiza las fechas de documentos existentes en Qdrant sin recalcular embeddings."""
    client = get_qdrant()
    count = 0
    for u in updates:
        try:
            client.set_payload(
                collection_name=COLLECTION_NAME,
                payload={"date": u.date},
                points=[u.id]
            )
            count += 1
        except Exception as e:
            logger.error(f"Error actualizando payload para {u.id}: {e}")
    return {"status": "success", "updated": count}

@app.post("/api/rag/chat")
async def chat_rag(query: ChatQuery):
    """Recupera contexto de Qdrant ponderando antigüedad y consulta a Ollama externo."""
    clean_prompt = query.prompt.strip()
    if not clean_prompt or len(clean_prompt) < 2:
        raise HTTPException(status_code=400, detail="La consulta ingresada no es válida.")

    ensure_collection_exists(max_retries=2, delay=1.0)
    model = get_embedding_model()
    client = get_qdrant()

    now_ar, fecha_str, dia_nombre, mes_nombre = get_current_date_info()

    # Detección y contextualización conversacional de departamentos
    norm_prompt = normalize_text(clean_prompt)
    detected_dept = None

    # 1. Buscar coincidencia de departamento en el prompt actual
    for dept_key, info in DEPARTMENTS_META.items():
        if any(matches_department_keyword(norm_prompt, kw) for kw in info["keywords"]):
            detected_dept = info
            break

    # 2. Si no se detectó en el prompt actual, buscar en el historial de conversación reciente (turnos anteriores)
    if not detected_dept and query.history:
        for msg in reversed(query.history):
            norm_content = normalize_text(msg.content)
            for dept_key, info in DEPARTMENTS_META.items():
                if any(matches_department_keyword(norm_content, kw) for kw in info["keywords"]) or normalize_text(info["name"]) in norm_content:
                    detected_dept = info
                    break
            if detected_dept:
                break

    # Detección de consultas sobre Calendario Académico / Clases / Fechas / Asuetos
    is_calendar_query = any(matches_department_keyword(norm_prompt, kw) for kw in CALENDAR_TOPIC_KEYWORDS)
    if not is_calendar_query and query.history:
        for msg in reversed(query.history):
            norm_content = normalize_text(msg.content)
            if any(matches_department_keyword(norm_content, kw) for kw in CALENDAR_TOPIC_KEYWORDS):
                is_calendar_query = True
                break

    is_temporal_query = any(matches_department_keyword(norm_prompt, kw) for kw in TEMPORAL_KEYWORDS)

    # Enriquecer la búsqueda vectorial
    search_prompt = clean_prompt
    if detected_dept and not any(matches_department_keyword(norm_prompt, kw) for kw in detected_dept["keywords"]):
        search_prompt = f"{clean_prompt} {detected_dept['name']}"
    elif is_calendar_query and is_temporal_query:
        search_prompt = f"{clean_prompt} {now_ar.day} de {mes_nombre} de {now_ar.year} calendario academico semana del estudiante"
    elif is_calendar_query and not any(kw in norm_prompt for kw in ["calendario", "academico"]):
        search_prompt = f"{clean_prompt} calendario academico curzas"

    # Vectorizar prompt enriquecido
    query_vector = list(model.embed([search_prompt]))[0].tolist()

    # Documentos directos canónicos prioritarios
    direct_hits = []
    direct_ids = []
    if detected_dept:
        direct_ids.extend([detected_dept["contact_id"], detected_dept["dept_id"]])
    if is_calendar_query:
        direct_ids.extend(CALENDAR_DOC_IDS)

    if direct_ids:
        try:
            if hasattr(client, "retrieve"):
                pts = client.retrieve(collection_name=COLLECTION_NAME, ids=direct_ids, with_payload=True)
                for pt in pts:
                    direct_hits.append(pt)
        except Exception as e:
            logger.warning(f"Error recuperando puntos directos canónicos: {e}")

    raw_hits = []
    try:
        # Recuperar hasta 35 candidatos para poder re-ponderar por antigüedad sin descartar documentos institucionales
        if hasattr(client, "search"):
            raw_hits = client.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_vector,
                limit=35
            )
        elif hasattr(client, "query_points"):
            res = client.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vector,
                limit=35
            )
            raw_hits = res.points
    except Exception as e:
        logger.error(f"Error buscando en Qdrant: {e}")
        raw_hits = []

    # Combinar direct_hits con raw_hits evitando duplicados
    seen_ids = set()
    combined_hits = []
    for dh in direct_hits:
        seen_ids.add(dh.id)
        combined_hits.append((dh, 0.98))

    for h in raw_hits:
        if h.id not in seen_ids:
            seen_ids.add(h.id)
            combined_hits.append((h, float(getattr(h, "score", 1.0))))

    # Re-ponderar candidatos según antigüedad (> 1 año = penalización drástica)
    now = datetime.now()
    scored_hits = []
    for h, initial_score in combined_hits:
        payload = h.payload or {}
        date_str = payload.get("date", "")
        score = initial_score
        is_old = False
        if direct_ids and h.id in direct_ids:
            is_old = False
        elif date_str:
            try:
                doc_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                age_days = (now - doc_dt).days
                if age_days > 365:
                    is_old = True
                    # Dar un peso mucho menor a artículos antiguos (penalización del 55%)
                    score = score * 0.45
            except Exception:
                pass
        scored_hits.append((score, is_old, date_str, h))

    # Ordenar por score re-ponderado descendente
    scored_hits.sort(key=lambda x: x[0], reverse=True)

    # Límite estricto de contexto (MAX_CONTEXT_CHARS = 4800) para no saturar la ventana de atención de Ollama
    # y evitar que Ollama trunque los primeros documentos del prompt donde están los datos prioritarios.
    MAX_CONTEXT_CHARS = 4800
    context_parts = []
    sources = []
    current_chars = 0

    for score, is_old, date_str, h in scored_hits:
        p = h.payload or {}
        title = p.get('title', 'Sin título')
        url = p.get('url', '')
        content = p.get('content', '')
        chunk_len = len(content)

        # Si agregar este documento excede el presupuesto y ya tenemos contexto prioritario, cortar
        if current_chars + chunk_len > MAX_CONTEXT_CHARS and context_parts:
            break

        if url and url not in sources:
            sources.append(url)

        if is_old:
            header = f"[DOCUMENTO ANTIGUO - Publicado hace más de 1 año ({date_str[:10]})] Fuente: {title} ({url})"
        elif date_str:
            header = f"[DOCUMENTO RECIENTE ({date_str[:10]})] Fuente: {title} ({url})"
        else:
            header = f"[DOCUMENTO INSTITUCIONAL] Fuente: {title} ({url})"

        context_parts.append(f"{header}\n{content}")
        current_chars += len(header) + chunk_len

        # Limitar a máximo 3 documentos seleccionados
        if len(context_parts) >= 3:
            break

    context = "\n---\n".join(context_parts) if context_parts else "No se encontró contexto indexado."

    system_prompt = (
        "Sos el asistente virtual institucional del CURZAS (Complejo Universitario Regional Zona Atlántica y Sur - UNComa). "
        "Respondé a las preguntas de estudiantes, docentes y público de manera formal, concisa y basada estrictamente "
        "en el contexto institucional provisto a continuación. Tratá siempre al estudiante o consultante de 'vos' "
        "(utilizá voseo argentino: 'podés', 'debés', 'tenés', etc., nunca trates de 'tú').\n\n"
        f"Fecha oficial y contexto temporal actual:\n"
        f"- Fecha de hoy: {fecha_str} (Horario oficial de Argentina / CURZAS).\n"
        "- Usá siempre esta fecha exacta para responder consultas sobre 'hoy', 'mañana', 'esta semana', 'este mes', etc. "
        "Bajo ninguna circunstancia le pidas al usuario que te diga la fecha actual, ya que la conocés con total precisión.\n"
        "- Si el usuario consulta si hoy o esta semana hay clases o actividades, cotejá la fecha de hoy con el Calendario Académico oficial. "
        "Por ejemplo, si la fecha actual cae entre el 21 y el 26 de septiembre (Semana de les Estudiantes), feriados, asuetos o receso, "
        "confirmale con seguridad que no hay clases ni actividad académica.\n\n"
        "Criterio estricto de vigencia temporal:\n"
        "- Los artículos o documentos marcados como [DOCUMENTO ANTIGUO] tienen una fecha de publicación de más de un año. "
        "Dales un peso mucho menor en tu respuesta y priorizá siempre la información de documentos recientes o vigentes.\n"
        "- Si una respuesta proviene únicamente de un [DOCUMENTO ANTIGUO], informale al usuario con claridad que se trata "
        "de información histórica que podría haber variado o no estar vigente.\n"
        "- Si la información solicitada no figura en el contexto, indicá que deben consultar en ventanilla de Alumnos, Bedelía o Secretaría de Bienestar.\n\n"
        f"Contexto institucional:\n{context}"
    )

    # Construir historial de mensajes conversacionales para el LLM
    conversation_messages = [{"role": "system", "content": system_prompt}]
    if query.history:
        for msg in query.history[-6:]:
            role = "user" if msg.role == "user" else "assistant"
            conversation_messages.append({"role": role, "content": msg.content})
    conversation_messages.append({"role": "user", "content": clean_prompt})

    # Texto con historial para endpoints heredados
    if query.history:
        history_text = "\n".join([f"{'Usuario' if m.role == 'user' else 'Asistente'}: {m.content}" for m in query.history[-6:]])
        prompt_with_history = f"Historial previo de la conversación:\n{history_text}\n\nConsulta actual:\n{clean_prompt}"
    else:
        prompt_with_history = clean_prompt

    # Si se solicita streaming (Server-Sent Events)
    if query.stream:
        async def event_generator():
            # 1. Enviar fuentes y metadatos de inmediato
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

            try:
                timeout_config = httpx.Timeout(60.0, connect=5.0)
                async with httpx.AsyncClient(timeout=timeout_config) as http_client:
                    if OLLAMA_URL.rstrip("/").endswith("/v1"):
                        endpoint = f"{OLLAMA_URL.rstrip('/')}/chat/completions"
                        payload = {
                            "model": OLLAMA_MODEL,
                            "messages": conversation_messages,
                            "temperature": 0.2,
                            "max_tokens": 650,
                            "reasoning_effort": "none",
                            "stream": True
                        }
                        async with http_client.stream("POST", endpoint, json=payload) as resp:
                            if resp.status_code != 200:
                                yield f"data: {json.dumps({'type': 'error', 'error': f'Error en modelo LLM ({resp.status_code})'})}\n\n"
                                return

                            async for line in resp.aiter_lines():
                                if line.startswith("data: "):
                                    raw = line[6:].strip()
                                    if raw == "[DONE]":
                                        break
                                    try:
                                        chunk_data = json.loads(raw)
                                        delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                                        content = delta.get("content", "")
                                        if content:
                                            yield f"data: {json.dumps({'type': 'token', 'token': content})}\n\n"
                                    except Exception:
                                        continue
                    else:
                        endpoint = f"{OLLAMA_URL.rstrip('/')}/api/generate"
                        payload = {
                            "model": OLLAMA_MODEL,
                            "prompt": prompt_with_history,
                            "system": system_prompt,
                            "stream": True,
                            "options": {
                                "num_predict": 650,
                                "temperature": 0.2
                            }
                        }
                        async with http_client.stream("POST", endpoint, json=payload) as resp:
                            if resp.status_code != 200:
                                yield f"data: {json.dumps({'type': 'error', 'error': f'Error en modelo LLM ({resp.status_code})'})}\n\n"
                                return

                            async for line in resp.aiter_lines():
                                if line.strip():
                                    try:
                                        chunk_data = json.loads(line)
                                        token = chunk_data.get("response", "")
                                        if token:
                                            yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"
                                        if chunk_data.get("done", False):
                                            break
                                    except Exception:
                                        continue

                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            except Exception as exc:
                logger.error(f"Error en streaming con LLM ({OLLAMA_URL}): {exc}")
                yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    # Respuesta tradicional JSON (sin streaming)
    try:
        timeout_config = httpx.Timeout(60.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout_config) as http_client:
            if OLLAMA_URL.rstrip("/").endswith("/v1"):
                endpoint = f"{OLLAMA_URL.rstrip('/')}/chat/completions"
                payload = {
                    "model": OLLAMA_MODEL,
                    "messages": conversation_messages,
                    "temperature": 0.2,
                    "max_tokens": 650,
                    "reasoning_effort": "none",
                    "stream": False
                }
                resp = await http_client.post(endpoint, json=payload)
                resp.raise_for_status()
                data = resp.json()
                raw_answer = data.get("choices", [{}])[0].get("message", {}).get("content", "Sin respuesta del modelo.")
            else:
                endpoint = f"{OLLAMA_URL.rstrip('/')}/api/generate"
                payload = {
                    "model": OLLAMA_MODEL,
                    "prompt": prompt_with_history,
                    "system": system_prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 650,
                        "temperature": 0.2
                    }
                }
                resp = await http_client.post(endpoint, json=payload)
                resp.raise_for_status()
                data = resp.json()
                raw_answer = data.get("response", "Sin respuesta del modelo.")

            answer = re.sub(r"<thought>.*?</thought>", "", raw_answer, flags=re.DOTALL).strip()
            if not answer:
                answer = raw_answer.strip()

            return {
                "answer": answer if answer else "Sin respuesta del modelo.",
                "sources": sources
            }
    except Exception as exc:
        logger.error(f"Error consultando LLM ({OLLAMA_URL}): {exc}")
        return {
            "answer": (
                "Aviso: No se pudo contactar el servicio LLM configurado en "
                f"{OLLAMA_URL} ({exc}). Sin embargo, la búsqueda semántica vectorial funcionó y recuperó el contexto relevante."
            ),
            "sources": sources,
            "context_retrieved": [p.get("title") for score, is_old, date_str, h in top_candidates if (p := (h.payload or {}))]
        }
