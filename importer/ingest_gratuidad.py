#!/usr/bin/env python3
"""
Script para asegurar la indexación del documento institucional sobre
Gratuidad Universitaria, Ingreso sin Cupo y Aranceles en Qdrant (RAG) y Meilisearch.
"""
import os
import urllib.request
import json

RAG_URL = os.getenv("RAG_INGEST_URL", "http://localhost:8888/api/rag/ingest")
MEILI_URL = os.getenv("MEILI_URL", "http://localhost:8888/api/search")
MEILI_KEY = os.getenv("MEILISEARCH_MASTER_KEY", "meili_master_key_curza")

doc_title = 'Gratuidad Universitaria, Ingreso sin Cupo y Aranceles en el CURZAS UNComa'
doc_content = '''En la Universidad Nacional del Comahue (UNComa) y en el Complejo Universitario Regional Zona Atlántica y Sur (CURZAS), todas las carreras de grado (licenciaturas, profesorados) y de pregrado (tecnicaturas universitarias) son 100% públicas y totalmente gratuitas.

No se cobra matrícula de inscripción ni aranceles mensuales, ni costos por rendir exámenes parciales, finales o tramitar el título. Estudiar una carrera de grado o tecnicatura en la UNComa es completamente gratuito.

Ingreso irrestricto sin examen de ingreso ni cupo de admisión:
En la Universidad Nacional del Comahue y en el CURZAS no hay examen de ingreso eliminatorio ni cupo de admisión. El ingreso es directo para todas las personas que hayan completado sus estudios de nivel secundario (o mayores de 25 años mediante el artículo 7° de la Ley de Educación Superior 24.521). Los cursos o talleres de ambientación e inicio son de apoyo y acompañamiento pedagógico, nunca selectivos ni eliminatorios.

Aranceles en posgrados y cursos especiales:
Solamente las carreras de posgrado (maestrías, especializaciones, doctorados) y determinados cursos especiales de capacitación profesional o actividades de extensión específicas pueden ser rentados o arancelados. Las carreras de pregrado y grado son siempre gratuitas y de acceso público.'''

doc_url = '/gratuidad-e-ingreso'
doc_date = '2026-09-23T21:50:00Z'

def ingest():
    # 1. Ingestar puntos en RAG (Qdrant)
    rag_payload = [
        {
            'id': 99001,
            'title': doc_title,
            'content': doc_content,
            'url': doc_url,
            'date': doc_date
        },
        {
            'id': 99002,
            'title': 'Régimen de Aranceles: Posgrados y Cursos Especiales Rentados en la UNComa CURZAS',
            'content': 'En la Universidad Nacional del Comahue (UNComa) y en el CURZAS, las carreras de grado (licenciaturas, profesorados) y de pregrado (tecnicaturas) NO son rentadas ni aranceladas: son 100% públicas y gratuitas. No existe costo alguno ni examen de ingreso o cupo.\n\n¿Qué carreras o estudios son rentados o arancelados?\nSolamente las carreras de posgrado (maestrías, especializaciones y doctorados) y determinados cursos especiales de capacitación continua, diplomaturas de extensión específicas o talleres extracurriculares pueden ser rentados o requerir el pago de aranceles y matrícula. Todas las carreras de grado y pregrado son completamente gratuitas.',
            'url': doc_url,
            'date': doc_date
        }
    ]

    req_rag = urllib.request.Request(
        RAG_URL,
        data=json.dumps(rag_payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req_rag, timeout=30) as resp:
            print("RAG Ingest:", json.loads(resp.read().decode('utf-8')))
    except Exception as e:
        print("Error en RAG Ingest:", e)

    # 2. Ingestar en Meilisearch
    meili_payload = [{
        'id': 'page_gratuidad_ingreso',
        'title': doc_title,
        'content': doc_content,
        'content_html': '<p>' + doc_content.replace('\n\n', '</p><p>').replace('\n', '<br>') + '</p>',
        'url': doc_url,
        'original_url': 'https://web.curza.uncoma.edu.ar/gratuidad-e-ingreso',
        'type': 'page',
        'date': doc_date
    }]

    req_meili = urllib.request.Request(
        f"{MEILI_URL.rstrip('/')}/indexes/curza_content/documents",
        data=json.dumps(meili_payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {MEILI_KEY}"
        },
        method='POST'
    )
    try:
        with urllib.request.urlopen(req_meili, timeout=15) as resp_m:
            print("Meilisearch Ingest:", json.loads(resp_m.read().decode('utf-8')))
    except Exception as e:
        print("Error en Meilisearch Ingest:", e)

if __name__ == '__main__':
    ingest()
