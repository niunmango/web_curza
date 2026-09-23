#!/usr/bin/env python3
"""
Script para modernizar documentos existentes en Meilisearch y Qdrant:
Reemplaza CURZA por CURZAS y UNCo por UNComa (respetando URLs y correos electrónicos).
"""

import re
import requests
import sys

MEILI_URL = "http://localhost:8888/api/search"
MEILI_KEY = "meili_master_key_curza"
RAG_INGEST_URL = "http://localhost:8888/api/rag/ingest"

def modernize_institutional_text(text: str) -> str:
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

def main():
    headers = {
        "Authorization": f"Bearer {MEILI_KEY}",
        "Content-Type": "application/json"
    }

    print("Obteniendo documentos desde Meilisearch...")
    res = requests.get(f"{MEILI_URL}/indexes/curza_content/documents?limit=1000", headers=headers)
    if not res.ok:
        print(f"Error accediendo a Meilisearch: {res.status_code} - {res.text}")
        sys.exit(1)

    docs = res.json().get("results", [])
    print(f"Total documentos encontrados: {len(docs)}")

    updated_meili = []
    updated_rag = []

    for d in docs:
        orig_title = d.get("title", "")
        orig_content = d.get("content", "")

        new_title = modernize_institutional_text(orig_title)
        new_content = modernize_institutional_text(orig_content)

        if new_title != orig_title or new_content != orig_content:
            doc_id = d.get("id")
            raw_id = d.get("original_id")
            doc_type = d.get("type", "post")
            doc_int_id = int(raw_id) if doc_type == "post" else int(raw_id) + 1_000_000

            d["title"] = new_title
            d["content"] = new_content
            updated_meili.append(d)

            updated_rag.append({
                "id": doc_int_id,
                "title": new_title,
                "content": new_content[:4000],
                "url": d.get("url", f"/contenido/{doc_id}"),
                "original_url": d.get("original_url", "")
            })

    print(f"Documentos que requieren modernización a CURZAS / UNComa: {len(updated_meili)}")

    if not updated_meili:
        print("No hay documentos para actualizar.")
        return

    # 1. Actualizar en Meilisearch
    print(f"Enviando {len(updated_meili)} documentos a Meilisearch...")
    meili_update_res = requests.post(
        f"{MEILI_URL}/indexes/curza_content/documents",
        headers=headers,
        json=updated_meili
    )
    if meili_update_res.ok:
        print(f"Éxito actualizando Meilisearch (taskUid: {meili_update_res.json().get('taskUid')})")
    else:
        print(f"Error actualizando Meilisearch: {meili_update_res.text}")

    # 2. Actualizar en Qdrant vía RAG API por lotes
    print(f"Enviando {len(updated_rag)} documentos a Qdrant vía RAG API...")
    batch_size = 50
    for i in range(0, len(updated_rag), batch_size):
        batch = updated_rag[i:i + batch_size]
        r_rag = requests.post(RAG_INGEST_URL, json=batch, timeout=120)
        if r_rag.ok:
            print(f"  Lote RAG {i // batch_size + 1}/{(len(updated_rag)-1)//batch_size + 1} actualizado.")
        else:
            print(f"  Error en lote RAG {i}: {r_rag.status_code} - {r_rag.text}")

    print("\nModernización de documentos completada con éxito.")

if __name__ == "__main__":
    main()
