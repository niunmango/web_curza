#!/usr/bin/env python3
"""
Script de importación e ingesta para CURZA UNCo.
Descarga contenido desde la API real de WordPress (admin.curza.uncoma.edu.ar/curza-api/wp/v2)
e indexa en Qdrant (a través de RAG API) y en Meilisearch.
"""

import os
import re
import sys
import time
import requests
from bs4 import BeautifulSoup

# Configuración configurable por entorno
WP_BASE_URL = os.getenv("WP_BASE_URL", "https://admin.curza.uncoma.edu.ar/curza-api/wp/v2")
RAG_INGEST_URL = os.getenv("RAG_INGEST_URL", "http://localhost:8888/api/rag/ingest")
MEILI_URL = os.getenv("MEILI_URL", "http://localhost:8888/api/search")
MEILI_KEY = os.getenv("MEILISEARCH_MASTER_KEY", "meili_master_key_curza")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "50"))

def clean_html(raw_html: str) -> str:
    """Elimina etiquetas HTML, scripts, estilos y normaliza espacios."""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    for script in soup(["script", "style"]):
        script.decompose()
    text = soup.get_text(separator=" ")
    return " ".join(text.split())

def modernize_institutional_text(text: str) -> str:
    """
    Reemplaza referencias históricas a CURZA por CURZAS (Complejo Universitario Regional Zona Atlántica y Sur)
    y acrónimo de UNCo por UNComa (Universidad Nacional del Comahue), preservando URLs y correos electrónicos.
    """
    if not text:
        return ""
    url_or_email_pattern = r'(https?://[^\s]+|[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)'
    parts = re.split(url_or_email_pattern, text)
    for i in range(len(parts)):
        if re.match(url_or_email_pattern, parts[i]):
            continue
        p = parts[i]
        p = re.sub(
            r'Centro\s+Universitario\s+Regional\s+Zona\s+Atl[aá]ntica(?:\s+y\s+Sur)?',
            'Complejo Universitario Regional Zona Atlántica y Sur',
            p,
            flags=re.IGNORECASE
        )
        p = re.sub(r'\bCURZA\b', 'CURZAS', p)
        p = re.sub(r'\bCurza\b', 'Curzas', p)
        p = re.sub(r'\bUNCo\b', 'UNComa', p)
        p = re.sub(r'\bUNCO\b', 'UNComa', p)
        p = re.sub(r'\bUnco\b', 'UNComa', p)
        parts[i] = p
    return "".join(parts)

def fetch_all(endpoint: str, max_pages: int = 100):
    """Itera la paginación de la API de WordPress para traer todos los registros."""
    results = []
    page = 1
    session = requests.Session()
    session.headers.update({"User-Agent": "CURZA-Modernization-Importer/1.0"})

    while page <= max_pages:
        url = f"{WP_BASE_URL}/{endpoint}?per_page=100&page={page}"
        print(f"[{endpoint}] Descargando página {page}...")
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code == 400 or resp.status_code == 404:
                # Fin de la paginación
                break
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list) or not data:
                break
            results.extend(data)
            total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
            if page >= total_pages:
                break
            page += 1
        except Exception as e:
            print(f"Error descargando {url}: {e}")
            break
    return results

def main():
    print("=" * 65)
    print("  INICIANDO IMPORTACIÓN CURZA (UNCo)")
    print(f"  Fuente WordPress: {WP_BASE_URL}")
    print(f"  Destino RAG:      {RAG_INGEST_URL}")
    print(f"  Destino Búsqueda: {MEILI_URL}")
    print("=" * 65)

    # 1. Obtener Entradas (Noticias, Novedades)
    posts = fetch_all("posts")
    print(f"-> Total de entradas obtenidas: {len(posts)}")

    # 2. Obtener Páginas Institucionales (Carreras, Estructura, etc.)
    pages = fetch_all("pages")
    print(f"-> Total de páginas obtenidas: {len(pages)}")

    payload_docs = []
    meili_docs = []

    all_items = posts + pages
    for item in all_items:
        raw_id = item.get("id")
        if not raw_id:
            continue

        item_type = item.get("type", "post")
        # Prevenir colisión de IDs enteros entre 'post' y 'page' para Qdrant:
        doc_int_id = int(raw_id) if item_type == "post" else int(raw_id) + 1_000_000

        title = item.get("title", {}).get("rendered", "")
        clean_title = clean_html(title)
        raw_content = item.get("content", {}).get("rendered", "")
        clean_text = clean_html(raw_content)
        link = item.get("link", "")

        # Modernizar referencias históricas a CURZAS y UNComa
        clean_title = modernize_institutional_text(clean_title)
        clean_text = modernize_institutional_text(clean_text)

        if len(clean_text) < 40 and len(clean_title) < 5:
            continue

        doc_id_str = f"{item_type}_{raw_id}"
        local_url = f"/contenido/{doc_id_str}"

        doc_entry = {
            "id": doc_int_id,
            "title": clean_title,
            "content": clean_text[:4000],  # Límite por fragmento para embeddings
            "url": local_url,              # Enlace directo al contenido local del portal
            "original_url": link
        }
        payload_docs.append(doc_entry)

        meili_docs.append({
            "id": doc_id_str,
            "original_id": raw_id,
            "title": clean_title,
            "content": clean_text,
            "url": local_url,              # Enlace directo al contenido local del portal
            "original_url": link,          # Enlace histórico de origen
            "type": item_type,
            "date": item.get("date", "")
        })

    print(f"\nDocumentos procesados válidos: {len(payload_docs)}")

    # Ingestar en RAG (Vector DB) por lotes
    print(f"\n--- Ingesta Vectorial en Qdrant (vía RAG API) ---")
    indexed_rag = 0
    for i in range(0, len(payload_docs), BATCH_SIZE):
        batch = payload_docs[i:i + BATCH_SIZE]
        print(f"Enviando lote RAG {i // BATCH_SIZE + 1} ({len(batch)} docs)...")
        try:
            r_rag = requests.post(RAG_INGEST_URL, json=batch, timeout=180)
            if r_rag.status_code == 200:
                indexed_rag += r_rag.json().get("indexed_documents", len(batch))
            else:
                print(f"Advertencia en lote RAG: {r_rag.status_code} - {r_rag.text[:150]}")
        except Exception as e:
            print(f"Error al contactar RAG API ({RAG_INGEST_URL}): {e}")
            break

    print(f"Total indexados en Qdrant: {indexed_rag}")

    # Ingestar en Meilisearch
    print(f"\n--- Ingesta de Búsqueda Instantánea en Meilisearch ---")
    headers = {
        "Authorization": f"Bearer {MEILI_KEY}",
        "Content-Type": "application/json"
    }

    # Asegurar índice configurado
    try:
        index_url = f"{MEILI_URL.rstrip('/')}/indexes/curza_content"
        r_init = requests.post(
            f"{MEILI_URL.rstrip('/')}/indexes",
            headers=headers,
            json={"uid": "curza_content", "primaryKey": "id"},
            timeout=15
        )
    except Exception as e:
        print(f"Aviso inicializando índice en Meilisearch: {e}")

    indexed_meili = 0
    for i in range(0, len(meili_docs), BATCH_SIZE * 2):
        batch = meili_docs[i:i + (BATCH_SIZE * 2)]
        print(f"Enviando lote Meilisearch {i // (BATCH_SIZE * 2) + 1} ({len(batch)} docs)...")
        try:
            r_meili = requests.post(
                f"{MEILI_URL.rstrip('/')}/indexes/curza_content/documents",
                headers=headers,
                json=batch,
                timeout=60
            )
            if r_meili.status_code in (200, 202):
                indexed_meili += len(batch)
            else:
                print(f"Advertencia Meilisearch: {r_meili.status_code} - {r_meili.text[:150]}")
        except Exception as e:
            print(f"Error indexando en Meilisearch ({MEILI_URL}): {e}")
            break

    print(f"Total enviados a Meilisearch: {indexed_meili}")
    print("\n" + "=" * 65)
    print("  IMPORTACIÓN FINALIZADA CON ÉXITO")
    print("=" * 65)

if __name__ == "__main__":
    main()
