#!/usr/bin/env python3
"""
Herramienta de publicación rápida para el Portal CURZAS.
Permite publicar noticias o páginas institucionales directamente en el portal:
- Genera la vista en /contenido/<id>
- Lo indexa en el buscador instantáneo (Meilisearch)
- Lo entrena en la base de conocimientos vectorial del Asistente IA (Qdrant)
"""

import sys
import os
import time
import json
import argparse
import urllib.request
from datetime import datetime, timezone

RAG_URL = os.getenv("RAG_INGEST_URL", "http://localhost:8888/api/rag/ingest")
MEILI_URL = os.getenv("MEILI_URL", "http://localhost:8888/api/search")
MEILI_KEY = os.getenv("MEILISEARCH_MASTER_KEY", "meili_master_key_curza")

def publicar(titulo: str, contenido: str, tipo: str = "noticia", url_personalizada: str = None):
    timestamp_id = int(time.time())
    prefix = "post" if tipo == "noticia" else "page"
    doc_str_id = f"{prefix}_{timestamp_id}"
    
    local_url = url_personalizada if url_personalizada else f"/contenido/{doc_str_id}"
    fecha_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"\n📢 Publicando '{titulo}'...")

    # 1. Enviar a Meilisearch (Buscador y visor de contenidos /contenido/...)
    parrafos_html = "".join([f"<p>{p.strip()}</p>" for p in contenido.split("\n\n") if p.strip()])
    meili_doc = [{
        "id": doc_str_id,
        "title": titulo,
        "content": contenido,
        "content_html": parrafos_html,
        "url": local_url,
        "type": tipo,
        "date": fecha_iso
    }]

    req_meili = urllib.request.Request(
        f"{MEILI_URL.rstrip('/')}/indexes/curza_content/documents",
        data=json.dumps(meili_doc).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {MEILI_KEY}"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req_meili, timeout=15) as resp:
            print("✅ Indexado en el buscador y visor de contenidos.")
    except Exception as e:
        print(f"❌ Error al indexar en Meilisearch: {e}")
        return False

    # 2. Enviar a Qdrant vía RAG API (Asistente IA)
    rag_doc = [{
        "id": timestamp_id,
        "title": titulo,
        "content": contenido,
        "url": local_url,
        "date": fecha_iso
    }]

    req_rag = urllib.request.Request(
        RAG_URL,
        data=json.dumps(rag_doc).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req_rag, timeout=30) as resp:
            print("✅ Aprendido por el Asistente IA (Vector DB).")
    except Exception as e:
        print(f"⚠️ Error al enviar al Asistente IA: {e}")

    print("\n🎉 ¡Publicación exitosa!")
    print(f"🔗 Podés ver tu contenido en: {local_url}")
    print(f"🔎 Ya aparece en el buscador instantáneo (/search)")
    print(f"🤖 Ya está disponible para las respuestas del Asistente IA (/chat)\n")
    return True

def main():
    parser = argparse.ArgumentParser(description="Publicar contenido manualmente en el portal CURZAS")
    parser.add_argument("--titulo", type=str, help="Título de la publicación")
    parser.add_argument("--contenido", type=str, help="Texto o cuerpo de la publicación")
    parser.add_argument("--tipo", choices=["noticia", "pagina"], default="noticia", help="Tipo: noticia o pagina")
    parser.add_argument("--url", type=str, default=None, help="URL opcional (por defecto /contenido/...)")

    args = parser.parse_args()

    titulo = args.titulo
    contenido = args.contenido
    tipo = args.tipo

    # Si no se pasaron argumentos, modo interactivo amigable
    if not titulo:
        print("=" * 60)
        print("  PUBLICACIÓN RÁPIDA DE CONTENIDOS - PORTAL CURZAS")
        print("=" * 60)
        titulo = input("\nIngrese el Título: ").strip()
        if not titulo:
            print("El título no puede estar vacío.")
            sys.exit(1)

        print("\nSeleccione el tipo de publicación:")
        print("  1) Noticia / Novedad")
        print("  2) Página institucional / Trámite")
        opc = input("Opción (1/2, defecto 1): ").strip()
        tipo = "pagina" if opc == "2" else "noticia"

        print("\nIngrese el contenido (puede pegar varios párrafos).")
        print("Para finalizar, escriba 'FIN' en una línea separada y presione Enter:\n")
        lineas = []
        while True:
            try:
                linea = input()
                if linea.strip() == "FIN":
                    break
                lineas.append(linea)
            except EOFError:
                break
        contenido = "\n".join(lineas).strip()
        if not contenido:
            print("El contenido no puede estar vacío.")
            sys.exit(1)

    publicar(titulo, contenido, tipo, args.url)

if __name__ == "__main__":
    main()
