#!/usr/bin/env python3
"""
Script de carga rápida offline (Seeding) para CURZAS UNComa.
Permite poblar Meilisearch y Qdrant instantáneamente desde el archivo de respaldo local
(importer/seed_curza_content.json) sin depender de la API externa de WordPress.
"""

import os
import sys
import json
import time
import urllib.request

RAG_INGEST_URL = os.getenv("RAG_INGEST_URL", "http://localhost:8888/api/rag/ingest")
MEILI_URL = os.getenv("MEILI_URL", "http://localhost:8888/api/search")
MEILI_KEY = os.getenv("MEILISEARCH_MASTER_KEY", "meili_master_key_curza")
SEED_FILE = os.path.join(os.path.dirname(__file__), "seed_curza_content.json")

def seed():
    if not os.path.exists(SEED_FILE):
        print(f"❌ No se encontró el archivo de seed: {SEED_FILE}")
        sys.exit(1)

    with open(SEED_FILE, "r", encoding="utf-8") as f:
        docs = json.load(f)

    print(f"📦 Cargando {len(docs)} documentos desde {SEED_FILE}...")

    # 1. Configurar índice e Ingestar en Meilisearch
    print("\n--- 1/2 Poblando Meilisearch (Búsqueda y Visor) ---")
    headers_meili = {
        "Authorization": f"Bearer {MEILI_KEY}",
        "Content-Type": "application/json"
    }

    try:
        # Asegurar creación del índice y configuración de ranking
        req_idx = urllib.request.Request(
            f"{MEILI_URL.rstrip('/')}/indexes",
            data=json.dumps({"uid": "curza_content", "primaryKey": "id"}).encode("utf-8"),
            headers=headers_meili,
            method="POST"
        )
        try:
            urllib.request.urlopen(req_idx, timeout=10)
        except Exception:
            pass  # ya existe

        req_settings = urllib.request.Request(
            f"{MEILI_URL.rstrip('/')}/indexes/curza_content/settings",
            data=json.dumps({
                "sortableAttributes": ["date"],
                "rankingRules": [
                    "words",
                    "typo",
                    "date:desc",
                    "proximity",
                    "attribute",
                    "exactness"
                ]
            }).encode("utf-8"),
            headers=headers_meili,
            method="PATCH"
        )
        try:
            urllib.request.urlopen(req_settings, timeout=10)
        except Exception:
            pass

        # Ingestar en lotes de 100
        batch_size = 100
        for i in range(0, len(docs), batch_size):
            batch = docs[i:i + batch_size]
            req_docs = urllib.request.Request(
                f"{MEILI_URL.rstrip('/')}/indexes/curza_content/documents",
                data=json.dumps(batch).encode("utf-8"),
                headers=headers_meili,
                method="POST"
            )
            with urllib.request.urlopen(req_docs, timeout=30) as resp:
                pass
            print(f"  ✓ Meilisearch: Lote {i // batch_size + 1} ({len(batch)} docs)")
        print("✅ Meilisearch poblado con éxito.")
    except Exception as e:
        print(f"❌ Error poblando Meilisearch: {e}")

    # 2. Ingestar en Qdrant vía RAG API
    print("\n--- 2/2 Poblando Qdrant (Memoria Vectorial del Asistente IA) ---")
    headers_rag = {"Content-Type": "application/json"}
    rag_docs = []
    for d in docs:
        raw_id = d.get("original_id") or d.get("id")
        try:
            if isinstance(raw_id, str):
                numeric_id = int("".join(filter(str.isdigit, raw_id)) or "0")
            else:
                numeric_id = int(raw_id)
        except Exception:
            numeric_id = 0

        if numeric_id == 0:
            continue

        rag_docs.append({
            "id": numeric_id,
            "title": d.get("title", ""),
            "content": (d.get("content", "") or "")[:4000],
            "url": d.get("url", ""),
            "date": d.get("date", "")
        })

    batch_size_rag = 50
    total_rag = 0
    for i in range(0, len(rag_docs), batch_size_rag):
        batch = rag_docs[i:i + batch_size_rag]
        req_rag = urllib.request.Request(
            RAG_INGEST_URL,
            data=json.dumps(batch).encode("utf-8"),
            headers=headers_rag,
            method="POST"
        )
        try:
            with urllib.request.urlopen(req_rag, timeout=120) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                total_rag += res.get("indexed_documents", len(batch))
            print(f"  ✓ Qdrant: Lote {i // batch_size_rag + 1} ({len(batch)} docs)")
        except Exception as e:
            print(f"  ⚠️ Error en lote {i // batch_size_rag + 1} de RAG: {e}")

    print(f"✅ Qdrant poblado con éxito ({total_rag} documentos).")

    # 3. Ingestar documento de Gratuidad
    try:
        from ingest_gratuidad import ingest as ingest_gratuidad_func
        ingest_gratuidad_func()
    except Exception:
        pass

    print("\n🎉 Base de datos completamente inicializada y lista para su uso.")

if __name__ == "__main__":
    seed()
