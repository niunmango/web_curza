# Portal Web CURZAS - UNComa

Modernización de la plataforma institucional del **Complejo Universitario Regional Zona Atlántica y Sur (CURZAS)** de la **Universidad Nacional del Comahue (UNComa)**.

El proyecto implementa una arquitectura desacoplada, modular y de alto rendimiento que combina un frontend estático/SSR ultra veloz, un gestor de contenidos headless (CMS), un motor de búsqueda instantánea y un asistente inteligente basado en Retrieval-Augmented Generation (RAG).

---

## 🏛️ Arquitectura del Sistema

```
                       [ Usuarios / Navegador ]
                                  │
                                  ▼
                 ┌─────────────────────────────────┐
                 │          Caddy Proxy            │ :8888 (Dev/Test)
                 │     (Reverse Proxy Gateway)     │ :80 / :443 (Prod)
                 └──────────────┬──────────────────┘
                                │
         ┌──────────────────────┼──────────────────────┬──────────────────────┐
         ▼                      ▼                      ▼                      ▼
  ┌──────────────┐       ┌──────────────┐       ┌──────────────┐       ┌──────────────┐
  │  Astro v4    │       │  FastAPI RAG │       │ Meilisearch  │       │  Strapi v5   │
  │  (Frontend)  │       │ (Vector/IA)  │       │ (Búsqueda)   │       │ (Headless)   │
  │   Puerto 4321│       │  Puerto 8000 │       │  Puerto 7700 │       │  Puerto 1337 │
  └──────────────┘       └──────┬───────┘       └──────────────┘       └──────┬───────┘
                                │                                             │
                        ┌───────┴───────┐                             ┌───────┴───────┐
                        ▼               ▼                             ▼               ▼
                 ┌──────────────┐ ┌──────────────┐             ┌──────────────┐
                 │ Qdrant DB    │ │ Ollama LLM   │             │ PostgreSQL 16│
                 │ (Embeddings) │ │ (gemma4:12b) │             │ (Relacional) │
                 │  Puerto 6333 │ │ (Externo)    │             │  Puerto 5432 │
                 └──────────────┘ └──────────────┘             └──────────────┘
```

### Componentes Principales

1. **Frontend (`frontend/`)**:
   - **Astro v4** (modo híbrido/SSR con `@astrojs/node` y Tailwind CSS).
   - Componentes reactivos nativos sin dependencias pesadas.
   - Interfaz institucional moderna, responsive y accesible.
   - Visor dinámico de contenidos locales en `/contenido/[id]`.

2. **Búsqueda Instantánea (`curza_search`)**:
   - **Meilisearch v1.10** con tolerancia tipográfica y respuesta en < 20ms.
   - Indexación automática de contenidos institucionales con URLs locales.

3. **Asistente IA Institucional & RAG (`services/rag/`)**:
   - **FastAPI** + **FastEmbed** (`BAAI/bge-small-en-v1.5` en CPU, 384 dimensiones).
   - **Qdrant v1.11**: Base vectorial para almacenamiento de embeddings de noticias y páginas institucionales.
   - **LLM Externo**: Integración con Ollama (API compatible OpenAI) en `https://ollama.curza.com.ar/v1` con modelo `gemma4:12b`.
   - Respuestas contextualizadas institucionalmente con enlaces de verificación hacia el portal local.

4. **CMS Headless (`cms/`)**:
   - **Strapi v5** conectado a **PostgreSQL 16**.
   - Gestión desacoplada de contenidos, noticias, carreras y secciones.

5. **Gateway / Proxy (`deploy/Caddyfile`)**:
   - **Caddy v2**: Orquesta el ruteo interno de rutas y APIs:
     - `/` ➔ Frontend Astro
     - `/contenido/*`, `/search`, `/chat` ➔ Frontend Astro
     - `/admin/*`, `/api/cms/*`, `/uploads/*` ➔ Strapi CMS
     - `/api/rag/*` ➔ FastAPI RAG Service
     - `/api/search/*` ➔ Meilisearch Proxy
   - Diseñado para funcionar en puertos alternativos en desarrollo (ej. `8888`) o en `80/443` con HTTPS automático en producción.

6. **Script de Ingestión / Migración (`importer/`)**:
   - `importer/import_curza.py`: Descarga publicaciones y páginas desde la API REST de WordPress (`https://admin.curza.uncoma.edu.ar/curza-api/wp/v2`), procesa HTML, genera vectores y sincroniza simultáneamente con Meilisearch y Qdrant.

---

## ⚙️ Variables de Entorno

Copiar la plantilla de configuración antes de iniciar:

```bash
cp .env.example .env
```

### Parámetros Principales (`.env`)

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `CADDY_PORT` | Puerto de escucha en el host para el proxy Caddy | `8888` (Dev/Test) / `80` (Prod) |
| `SITE_URL` | URL base accesible por el usuario final | `http://air.local:8888` |
| `PUBLIC_SITE_URL` | URL base pública expuesta para el frontend Astro | `http://air.local:8888` |
| `OLLAMA_EXTERNAL_URL` | Endpoint base de Ollama (compatible OpenAI) | `https://ollama.curza.com.ar/v1` |
| `OLLAMA_MODEL` | Nombre del modelo en Ollama | `gemma4:12b` |
| `MEILI_MASTER_KEY` | Llave de administración de Meilisearch | Cadena segura |
| `DATABASE_NAME` | Nombre de base de datos PostgreSQL | `curza_strapi` |
| `DATABASE_USERNAME` | Usuario PostgreSQL | `curza_user` |
| `DATABASE_PASSWORD` | Contraseña PostgreSQL | Cadena segura |

---

## 🚀 Despliegue en Desarrollo / Pruebas (Podman)

Esta máquina de desarrollo utiliza **Podman** y **podman-compose**.

### 1. Iniciar los servicios
```bash
podman-compose up -d --build
```

### 2. Verificar el estado de los contenedores
```bash
podman ps
```
Debe mostrar los 7 contenedores activos:
- `curza_proxy`
- `curza_web`
- `curza_rag_api`
- `curza_qdrant`
- `curza_search`
- `curza_strapi`
- `curza_postgres`

### 3. Ejecutar la Ingestión Inicial de Contenidos
Para popular Meilisearch y Qdrant con los contenidos históricos de CURZAS:
```bash
podman run --rm --network curza_network \
  -v $(pwd)/importer:/importer:ro \
  -e QDRANT_HOST=curza_qdrant \
  -e QDRANT_PORT=6333 \
  -e MEILISEARCH_HOST=curza_search \
  -e MEILISEARCH_PORT=7700 \
  -e MEILI_MASTER_KEY=curza_secure_search_key_2026 \
  -e SITE_URL=http://air.local:8888 \
  python:3.11-slim bash -c "pip install -r /importer/requirements.txt && python /importer/import_curza.py"
```

---

## 🌐 Despliegue en Producción (Docker)

El proyecto mantiene total compatibilidad con Docker y Docker Compose estándar.

### 1. Configurar variables de producción
Editar `.env`:
```env
CADDY_PORT=80
SITE_URL=https://curza.uncoma.edu.ar
PUBLIC_SITE_URL=https://curza.uncoma.edu.ar
```

### 2. Iniciar con Docker Compose
```bash
docker compose up -d --build
```

### 3. Certificados SSL/TLS con Caddy
En producción, Caddy puede gestionar automáticamente certificados SSL de Let's Encrypt actualizando `deploy/Caddyfile` para especificar el dominio directo:
```caddyfile
curza.uncoma.edu.ar {
    # reglas de proxy inversas existentes
}
```

---

## 📍 Rutas del Sistema

- **Portal Web**: `http://air.local:8888/`
- **Buscador Instantáneo**: `http://air.local:8888/search`
- **Asistente IA**: `http://air.local:8888/chat`
- **Detalle de Contenidos**: `http://air.local:8888/contenido/[id]`
- **Panel Strapi CMS**: `http://air.local:8888/admin`
- **Healthcheck RAG API**: `http://air.local:8888/api/rag/health`
- **Healthcheck Meilisearch**: `http://air.local:8888/api/search/health`
