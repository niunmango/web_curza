#!/usr/bin/env python3
"""
Script para sincronizar y actualizar todos los documentos en Meilisearch
preservando la estructura HTML completa (párrafos, títulos, listas, tablas,
enlaces de descarga y multimedia) y modernizando referencias a CURZAS y UNComa.
"""

import os
import sys
import re
import time
import requests
from bs4 import BeautifulSoup

WP_BASE_URL = os.getenv("WP_BASE_URL", "https://admin.curza.uncoma.edu.ar/curza-api/wp/v2")
MEILI_URL = os.getenv("MEILI_URL", "http://search:7700")
MEILI_KEY = os.getenv("MEILISEARCH_MASTER_KEY", "meili_master_key_curza")
BATCH_SIZE = 100

def fetch_all(endpoint: str):
    results = []
    page = 1
    per_page = 100
    while True:
        url = f"{WP_BASE_URL}/{endpoint}?per_page={per_page}&page={page}"
        print(f"Descargando {endpoint} (página {page})...")
        try:
            res = requests.get(url, timeout=45)
            if res.status_code != 200:
                print(f"Fin o código no 200 ({res.status_code}) para {endpoint}")
                break
            items = res.json()
            if not items:
                break
            results.extend(items)
            total_pages = int(res.headers.get("X-WP-TotalPages", 1))
            if page >= total_pages:
                break
            page += 1
        except Exception as e:
            print(f"Error descargando {url}: {e}")
            break
    return results

def modernize_text(text: str) -> str:
    """Reemplaza CURZA por CURZAS y UNCo por UNComa preservando URLs y correos."""
    if not text:
        return ""
    url_or_email_pattern = r'(https?://[^\s<>"]+|[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)'
    parts = re.split(url_or_email_pattern, text)
    for i in range(len(parts)):
        if re.match(url_or_email_pattern, parts[i]):
            continue
        p = parts[i]
        # Arreglar posible 'Zona Atlánticas' previo
        p = re.sub(
            r'Complejo\s+Universitario\s+Regional\s+Zona\s+Atl[aá]nticas\s+y\s+Sur',
            'Complejo Universitario Regional Zona Atlántica y Sur',
            p,
            flags=re.IGNORECASE
        )
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

def process_html_and_text(raw_html: str):
    if not raw_html:
        return "", ""
    soup = BeautifulSoup(raw_html, "html.parser")

    # Eliminar etiquetas de script o estilos
    for tag in soup(["script", "style", "form", "input"]):
        tag.decompose()

    # Modernizar texto en los nodos de texto preservando atributos y URLs
    for text_node in soup.find_all(string=True):
        if text_node.parent and text_node.parent.name in ["script", "style"]:
            continue
        original = str(text_node)
        updated = modernize_text(original)
        if updated != original:
            text_node.replace_with(updated)

    # Asegurar rel seguro en enlaces externos
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("http"):
            a["target"] = "_blank"
            a["rel"] = "noopener noreferrer"

    clean_html = str(soup).strip()

    # Extraer texto plano con saltos de párrafo preservados
    clean_text = soup.get_text(separator="\n\n", strip=True)
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)
    clean_text = modernize_text(clean_text)

    return clean_html, clean_text

def main():
    print("=" * 65)
    print("  ACTUALIZACIÓN DE CONTENIDOS EN MEILISEARCH CON HTML COMPLETO")
    print(f"  Fuente:  {WP_BASE_URL}")
    print(f"  Destino: {MEILI_URL}")
    print("=" * 65)

    posts = fetch_all("posts")
    print(f"-> Total de entradas obtenidas: {len(posts)}")

    pages = fetch_all("pages")
    print(f"-> Total de páginas obtenidas: {len(pages)}")

    all_items = posts + pages
    documents_to_update = []

    for item in all_items:
        raw_id = item.get("id")
        if not raw_id:
            continue
        item_type = item.get("type", "post")
        doc_id = f"{item_type}_{raw_id}"

        title_rendered = item.get("title", {}).get("rendered", "")
        clean_title = BeautifulSoup(title_rendered, "html.parser").get_text(strip=True)
        clean_title = modernize_text(clean_title)

        raw_content = item.get("content", {}).get("rendered", "")
        content_html, content_text = process_html_and_text(raw_content)

        if len(content_text) < 10 and len(clean_title) < 3:
            continue

        doc = {
            "id": doc_id,
            "original_id": raw_id,
            "title": clean_title,
            "content": content_text,
            "content_html": content_html,
            "url": f"/contenido/{doc_id}",
            "original_url": item.get("link", ""),
            "type": item_type,
            "date": item.get("date", "")
        }
        documents_to_update.append(doc)

    print(f"\nDocumentos procesados para Meilisearch: {len(documents_to_update)}")

    headers = {
        "Authorization": f"Bearer {MEILI_KEY}",
        "Content-Type": "application/json"
    }

    # Enviar por lotes a Meilisearch
    tasks = []
    for i in range(0, len(documents_to_update), BATCH_SIZE):
        batch = documents_to_update[i:i + BATCH_SIZE]
        print(f"Enviando lote {i // BATCH_SIZE + 1} ({len(batch)} documentos)...")
        res = requests.post(f"{MEILI_URL}/indexes/curza_content/documents", headers=headers, json=batch)
        if res.status_code in [200, 202]:
            task_info = res.json()
            tasks.append(task_info.get("taskUid"))
            print(f"  -> Tarea encolada: taskUid {task_info.get('taskUid')}")
        else:
            print(f"  -> Error: {res.status_code} - {res.text[:200]}")

    print("\nEsperando que Meilisearch complete la indexación...")
    for task_uid in tasks:
        if not task_uid:
            continue
        while True:
            t_res = requests.get(f"{MEILI_URL}/tasks/{task_uid}", headers=headers)
            if t_res.status_code == 200:
                status = t_res.json().get("status")
                if status in ["succeeded", "failed"]:
                    print(f"Tarea {task_uid}: {status}")
                    break
            time.sleep(0.5)

    print("\n¡Actualización completada exitosamente!")

if __name__ == "__main__":
    main()
