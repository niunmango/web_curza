#!/usr/bin/env python3
"""
Script para indexar todos los Departamentos Académicos y la Oferta Completa de Carreras del CURZAS
en Qdrant (RAG Vector Store) y en Meilisearch (Buscador instantáneo).
"""
import os
import re
import json
import urllib.request
from datetime import datetime

# Rutas y configuración de red interna o local
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEPTO_JSON_PATH = os.path.join(SCRIPT_DIR, "../frontend/src/data/departamentos.json")
if not os.path.exists(DEPTO_JSON_PATH):
    # Alternativa si se ejecuta desde /app en el contenedor
    DEPTO_JSON_PATH = "/app/departamentos.json" if os.path.exists("/app/departamentos.json") else "/data/departamentos.json"

QDRANT_HOST = os.getenv("QDRANT_HOST", "vector-db")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
MEILI_HOST = os.getenv("MEILISEARCH_HOST", "http://search:7700")
MEILI_KEY = os.getenv("MEILISEARCH_MASTER_KEY", "meili_master_key_curza")

def clean_html(html_text: str) -> str:
    if not html_text:
        return ""
    clean = re.sub(r'<br\s*/?>', '\n', html_text, flags=re.I)
    clean = re.sub(r'</p>', '\n\n', clean, flags=re.I)
    clean = re.sub(r'<[^>]+>', ' ', clean)
    clean = clean.replace('&nbsp;', ' ').replace('&aacute;', 'á').replace('&eacute;', 'é').replace('&iacute;', 'í').replace('&oacute;', 'ó').replace('&uacute;', 'ú').replace('&ntilde;', 'ñ')
    return re.sub(r'\s+', ' ', clean).strip()

def build_documents(data_path: str):
    with open(data_path, "r", encoding="utf-8") as f:
        departamentos = json.load(f)

    today_iso = datetime.now().strftime("%Y-%m-%dT12:00:00Z")
    docs_rag = []
    docs_meili = []

    # 1. Documento Maestro: Oferta Académica Completa
    master_lines = [
        "En la Universidad Nacional del Comahue (UNComa) y en el Complejo Universitario Regional Zona Atlántica y Sur (CURZAS), con sede en Viedma (Río Negro), se dictan las siguientes carreras de grado y pregrado, todas 100% públicas, gratuitas y con ingreso directo sin examen eliminatorio ni cupo de admisión.",
        "",
        "Oferta académica completa organizada por Departamento Académico:",
        ""
    ]

    for d in departamentos:
        d_nombre = d["nombre"]
        d_slug = d["slug"]
        d_url = f"/{d_slug}"
        master_lines.append(f"• {d_nombre} (Sitio web: {d_url}):")
        for c in d.get("carreras", []):
            c_nombre = c["nombre"]
            c_dur = c.get("duracion_total_anos", "")
            dur_str = f" - Duración: {c_dur} años" if c_dur and float(c_dur) > 0 else ""
            mods = ", ".join(c.get("modalidades", []))
            mod_str = f" [Modalidad: {mods}]" if mods else ""
            master_lines.append(f"   - {c_nombre}{dur_str}{mod_str}")
        master_lines.append("")

    master_lines.append("Para consultar planes de estudio, materias y requisitos, visitá la sección /departamentos o cada departamento en particular (/tecnologia, /psicopedagogia, /lengua-comunicacion, /admin-publica, /estudios-politicos, /gestion-agropecuaria, /enfermeria).")
    master_content = "\n".join(master_lines)

    docs_rag.append({
        "id": 98000,
        "title": "Oferta Académica Completa y Carreras del CURZAS - UNComa",
        "content": master_content,
        "url": "/departamentos",
        "date": today_iso
    })

    docs_meili.append({
        "id": "page_oferta_academica_completa",
        "title": "Oferta Académica Completa y Carreras del CURZAS - UNComa",
        "content": master_content,
        "content_html": "<p>" + master_content.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>",
        "url": "/departamentos",
        "original_url": "https://web.curza.uncoma.edu.ar/departamentos",
        "type": "page",
        "date": today_iso
    })

    # 2. Documentos específicos por cada Departamento
    base_id = 98100
    for idx, d in enumerate(departamentos, start=1):
        d_id = base_id + idx
        d_slug = d["slug"]
        d_url = f"/{d_slug}"
        d_desc = d.get("descripcion", "")
        d_info = clean_html(d.get("informacion_html", ""))

        carreras_list = []
        for c in d.get("carreras", []):
            c_nom = c["nombre"]
            c_dur = c.get("duracion_total_anos", "")
            dur_str = f" ({c_dur} años)" if c_dur and float(c_dur) > 0 else ""
            c_perf = clean_html(c.get("perfil", ""))
            carreras_list.append(f"• {c_nom}{dur_str}: {c_perf}")

        carreras_text = "\n".join(carreras_list)
        dept_content = f"{d['nombre']} del CURZAS (UNComa).\n{d_desc}\n\nContacto y Equipo:\n{d_info}\n\nCarreras que se dictan en este departamento:\n{carreras_text}"

        docs_rag.append({
            "id": d_id,
            "title": f"{d['nombre']} - Carreras y Oferta Académica CURZAS",
            "content": dept_content,
            "url": d_url,
            "date": today_iso
        })

        docs_meili.append({
            "id": f"dept_{d_slug}",
            "title": f"{d['nombre']} - Carreras y Autoridades",
            "content": dept_content,
            "content_html": "<p>" + dept_content.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>",
            "url": d_url,
            "original_url": f"https://web.curza.uncoma.edu.ar/{d_slug}",
            "type": "page",
            "date": today_iso
        })

    # 3. Documentos individuales por cada Carrera
    carr_base_id = 98200
    carr_counter = 1
    for d in departamentos:
        d_nombre = d["nombre"]
        d_slug = d["slug"]
        for c in d.get("carreras", []):
            c_id = carr_base_id + carr_counter
            carr_counter += 1
            c_nombre = c["nombre"]
            c_dur = c.get("duracion_total_anos", "")
            dur_str = f"{c_dur} años" if c_dur and float(c_dur) > 0 else "Consultar"
            c_perfil = clean_html(c.get("perfil", ""))
            c_alcance = clean_html(c.get("alcance", ""))
            c_modalidades = ", ".join(c.get("modalidades", []))
            plan_info = c.get("plan_vigente", {}) or {}
            ordenanza = plan_info.get("ordenanza", "")

            # Asignaturas principales
            asigs = [a.get("nombre") for a in c.get("asignaturas", []) if a.get("nombre")]
            asigs_text = ", ".join(asigs[:12]) if asigs else ""

            carr_content = (
                f"Carrera: {c_nombre}.\n"
                f"Departamento Académico: {d_nombre} del CURZAS UNComa.\n"
                f"Duración: {dur_str}. Modalidades: {c_modalidades or 'Presencial'}.\n"
                f"Ordenanza de Plan de Estudio: {ordenanza}.\n\n"
                f"Perfil del Egresado:\n{c_perfil}\n\n"
                f"Alcances del Título y Campo Laboral:\n{c_alcance}\n\n"
                f"Algunas asignaturas del plan de estudio: {asigs_text}."
            )

            docs_rag.append({
                "id": c_id,
                "title": f"Carrera: {c_nombre} - Plan de Estudio y Perfil ({d_nombre})",
                "content": carr_content,
                "url": f"/{d_slug}",
                "date": today_iso
            })

            docs_meili.append({
                "id": f"carrera_{c['id']}",
                "title": f"Carrera: {c_nombre} - CURZAS",
                "content": carr_content,
                "content_html": "<p>" + carr_content.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>",
                "url": f"/{d_slug}",
                "original_url": f"https://web.curza.uncoma.edu.ar/{d_slug}",
                "type": "page",
                "date": today_iso
            })

    return docs_rag, docs_meili

def run():
    print(f"Leyendo departamentos desde: {DEPTO_JSON_PATH}")
    docs_rag, docs_meili = build_documents(DEPTO_JSON_PATH)
    print(f"Generados {len(docs_rag)} documentos para Qdrant y {len(docs_meili)} documentos para Meilisearch.")

    # 1. Ingestar en Qdrant
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct, VectorParams, Distance
        from fastembed import TextEmbedding

        print(f"Conectando a Qdrant en {QDRANT_HOST}:{QDRANT_PORT}...")
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, check_compatibility=False)
        embedding_model = TextEmbedding(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

        texts = [f"{d['title']}\n{d['content']}" for d in docs_rag]
        print(f"Calculando embeddings para {len(texts)} documentos...")
        vectors = list(embedding_model.embed(texts))

        points = [
            PointStruct(
                id=d["id"],
                vector=v.tolist(),
                payload={
                    "title": d["title"],
                    "content": d["content"],
                    "url": d["url"],
                    "date": d["date"]
                }
            )
            for d, v in zip(docs_rag, vectors)
        ]

        client.upsert(collection_name="curza_knowledge", points=points)
        print(f"✅ Qdrant: {len(points)} documentos indexados exitosamente en 'curza_knowledge'.")
    except Exception as e:
        print(f"❌ Error indexando en Qdrant: {e}")

    # 2. Ingestar en Meilisearch
    try:
        print(f"Indexando en Meilisearch ({MEILI_HOST})...")
        meili_endpoint = f"{MEILI_HOST.rstrip('/')}/indexes/curza_content/documents"
        req = urllib.request.Request(
            meili_endpoint,
            data=json.dumps(docs_meili).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {MEILI_KEY}"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            print(f"✅ Meilisearch: {len(docs_meili)} documentos indexados exitosamente (Task: {resp_data.get('taskUid')}).")
    except Exception as e:
        print(f"❌ Error indexando en Meilisearch: {e}")

if __name__ == "__main__":
    run()
