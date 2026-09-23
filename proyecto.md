# Especificación de Modernización del Portal Web CURZA (UNCo)

Documento maestro de arquitectura y ejecución para la migración del portal `https://web.curza.uncoma.edu.ar/` hacia una plataforma desacoplada, contenedorizada con Podman (Desarrollo/Pruebas) y Docker (Producción), motor de búsqueda en tiempo real e indexación RAG con IA local.

---

## 1. Principios de Arquitectura y Stack Tecnológico

1. **CMS Headless**: **Strapi v5** (`node:20.18.0-alpine` / `curza-strapi:1.0.0`) respaldado por **PostgreSQL 16** (`postgres:16.4-alpine`). Gestión editorial de carreras, noticias, autoridades, resoluciones y normativas.
2. **Frontend Público**: **Astro v4** en modo híbrido (`node:20.18.0-alpine` / `curza-web:1.0.0`) con Tailwind CSS v3. Generación estática para páginas informativas y renderizado bajo demanda (SSR) para vistas dinámicas e interfaz interactiva.
3. **Motor de Búsqueda**: **Meilisearch v1.10** (`getmeili/meilisearch:v1.10.0`). Búsqueda instantánea con tolerancia a errores tipográficos y filtrado facetado.
4. **Base Vectorial (RAG)**: **Qdrant v1.11** (`qdrant/qdrant:v1.11.0`). Base de datos vectorial optimizada en Rust, ejecutada en CPU con consumo mínimo de RAM.
5. **Servicio RAG y Embeddings**: Microservicio en **FastAPI** (`python:3.11-slim` / `curza-rag-api:1.0.0`).
   * **Embeddings en CPU local**: Modelo `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` pre-empaquetado y ejecutado con `fastembed` en CPU (sin dependencias de GPU).
   * **Inferencia LLM**: Cliente HTTP hacia instancia **Ollama externa** vía endpoint configurable (`OLLAMA_EXTERNAL_URL`).
6. **Reverse Proxy, URL Base y SSL**: **Caddy v2** (`caddy:2.8.4-alpine`).
   * **URL Base y Puerto Configurables**: Mediante variables `SITE_URL` y `PUBLIC_SITE_URL` (ej. `http://air.local:8888` en desarrollo, `https://web.curza.uncoma.edu.ar` en producción).
   * **Contenido Local en Búsqueda y RAG**: Las búsquedas y respuestas del asistente apuntan a rutas locales en el portal (`/contenido/[id]`), sirviendo el contenido importado de manera nativa e instantánea sin enlaces rotos al servidor original.
   * En **desarrollo/pruebas**: Escucha en el puerto alternativo **8888** en modo HTTP directo con soporte para cualquier host (ej. `localhost`, `air.local`).
   * En **producción**: Emisión automática de certificados Let's Encrypt / ZeroSSL en los puertos 80/443 para el dominio institucional `web.curza.uncoma.edu.ar`.
7. **Política y Compatibilidad de Contenedores**:
   * Prohibido el uso del tag `:latest` en servicios base. Todas las imágenes oficiales utilizan tags semánticos exactos.
   * Compatibilidad total y transparente entre **Podman** (`podman-compose`) en el entorno de desarrollo y **Docker** (`docker compose`) en producción mediante estándares OCI.

---

## 2. Topología de Red y Arquitectura de Servicios

```
                           [ CLIENTE / BROWSER ]
                                     │
                     (Puerto 8888 en Dev / 80-443 en Prod)
                                     ▼
                            ┌─────────────────┐
                            │  Caddy 2.8.4    │
                            └────────┬────────┘
         ┌───────────────────────────┼───────────────────────────┐
         ▼                           ▼                           ▼
   /admin, /api/cms, /uploads  /api/search                 /, /search, /chat
 ┌──────────────┐            ┌──────────────┐            ┌──────────────────┐
 │ Strapi 5.1.0 │            │ Meilisearch  │            │ Astro 4.x        │
 │ (CMS)        │            │ (Motor Busca)│            │ (Frontend Web)   │
 └───────┬──────┘            └──────────────┘            └────────┬─────────┘
         │                                                        │
    (PostgreSQL)                                                  │ /api/rag/*
         ▼                                                        ▼
 ┌──────────────┐                                        ┌──────────────────┐
 │ PostgreSQL16 │                                        │ RAG API Service  │
 │              │                                        │ (FastAPI Python) │
 └──────────────┘                                        └────────┬─────────┘
                                                                  │
                         ┌────────────────────────────────────────┼──────────────────────┐
                         ▼                                                               ▼
                ┌─────────────────┐                                            ┌───────────────────┐
                │ Qdrant Vector DB│ (Embeddings locales en CPU)                 │ Ollama Externo    │
                │ (v1.11.0)       │                                            │ (http://host:11434│
                └─────────────────┘                                            └───────────────────┘
```

---

## 3. Composición de Contenedores (`docker-compose.yml`)

```yaml
version: "3.8"

networks:
  curza-net:
    driver: bridge

volumes:
  pg_data:
  strapi_uploads:
  meili_data:
  qdrant_data:
  caddy_data:
  caddy_config:

services:
  # ==============================================================================
  # Reverse Proxy & SSL Automático
  # ==============================================================================
  proxy:
    image: caddy:2.8.4-alpine
    container_name: curza_proxy
    restart: unless-stopped
    ports:
      - "${CADDY_PORT:-8888}:${CADDY_INTERNAL_PORT:-8888}"
    environment:
      - SITE_ADDRESS=${SITE_ADDRESS:-:8888}
    volumes:
      - ./deploy/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - curza-net
    depends_on:
      - web
      - strapi
      - search
      - rag-api

  # ==============================================================================
  # Base de Datos Relacional para Strapi
  # ==============================================================================
  postgres:
    image: postgres:16.4-alpine
    container_name: curza_postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-strapi}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-strapi_secure_pwd_curza_2026}
      POSTGRES_DB: ${POSTGRES_DB:-curza_cms}
    volumes:
      - pg_data:/var/lib/postgresql/data
    networks:
      - curza-net

  # ==============================================================================
  # CMS Headless: Strapi v5
  # ==============================================================================
  strapi:
    build:
      context: ./cms
      dockerfile: Dockerfile
    image: curza-strapi:1.0.0
    container_name: curza_strapi
    restart: unless-stopped
    working_dir: /srv/app
    environment:
      DATABASE_CLIENT: postgres
      DATABASE_HOST: postgres
      DATABASE_PORT: 5432
      DATABASE_NAME: ${POSTGRES_DB:-curza_cms}
      DATABASE_USERNAME: ${POSTGRES_USER:-strapi}
      DATABASE_PASSWORD: ${POSTGRES_PASSWORD:-strapi_secure_pwd_curza_2026}
      DATABASE_SSL: "false"
      JWT_SECRET: ${JWT_SECRET:-super_secret_jwt_curza_unco_2026}
      ADMIN_JWT_SECRET: ${ADMIN_JWT_SECRET:-super_secret_admin_jwt_curza_2026}
      APP_KEYS: ${APP_KEYS:-curza_key1,curza_key2}
      API_TOKEN_SALT: ${API_TOKEN_SALT:-salt_api_curza_2026}
      TRANSFER_TOKEN_SALT: ${TRANSFER_TOKEN_SALT:-salt_transfer_curza_2026}
      MEILISEARCH_HOST: http://search:7700
      MEILISEARCH_API_KEY: ${MEILISEARCH_MASTER_KEY:-meili_master_key_curza}
    volumes:
      - ./cms:/srv/app
      - /srv/app/node_modules
      - strapi_uploads:/srv/app/public/uploads
    networks:
      - curza-net
    depends_on:
      - postgres

  # ==============================================================================
  # Motor de Búsqueda Instantánea
  # ==============================================================================
  search:
    image: getmeili/meilisearch:v1.10.0
    container_name: curza_search
    restart: unless-stopped
    environment:
      MEILI_ENV: production
      MEILI_MASTER_KEY: ${MEILISEARCH_MASTER_KEY:-meili_master_key_curza}
      MEILI_NO_ANALYTICS: "true"
    volumes:
      - meili_data:/meili_data
    networks:
      - curza-net

  # ==============================================================================
  # Base Vectorial para RAG
  # ==============================================================================
  vector-db:
    image: qdrant/qdrant:v1.11.0
    container_name: curza_qdrant
    restart: unless-stopped
    environment:
      QDRANT__SERVICE__GRPC_PORT: 6334
      QDRANT__SERVICE__HTTP_PORT: 6333
      QDRANT__TELEMETRY_DISABLED: "true"
    volumes:
      - qdrant_data:/qdrant/storage
    networks:
      - curza-net

  # ==============================================================================
  # Servicio Backend RAG (Embeddings locales en CPU + Inferencia Ollama Externa)
  # ==============================================================================
  rag-api:
    build:
      context: ./services/rag
      dockerfile: Dockerfile
    image: curza-rag-api:1.0.0
    container_name: curza_rag_api
    restart: unless-stopped
    working_dir: /app
    environment:
      QDRANT_HOST: vector-db
      QDRANT_PORT: 6333
      OLLAMA_EXTERNAL_URL: ${OLLAMA_EXTERNAL_URL:-https://ollama.curza.com.ar/v1}
      OLLAMA_MODEL: ${OLLAMA_MODEL:-gemma4:12b}
      EMBEDDING_MODEL: "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    volumes:
      - ./services/rag:/app
    networks:
      - curza-net
    depends_on:
      - vector-db

  # ==============================================================================
  # Frontend Público: Astro
  # ==============================================================================
  web:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    image: curza-web:1.0.0
    container_name: curza_web
    restart: unless-stopped
    working_dir: /app
    environment:
      SITE_URL: ${SITE_URL:-http://air.local:8888}
      PUBLIC_SITE_URL: ${PUBLIC_SITE_URL:-${SITE_URL:-http://air.local:8888}}
      STRAPI_API_URL: http://strapi:1337
      MEILISEARCH_HOST: http://search:7700
      MEILISEARCH_SEARCH_KEY: ${MEILISEARCH_SEARCH_KEY:-meili_master_key_curza}
      RAG_API_URL: http://rag-api:8000
    volumes:
      - ./frontend:/app
      - /app/node_modules
    networks:
      - curza-net
    depends_on:
      - strapi
      - search
      - rag-api
```

---

## 4. Servicio RAG y Embeddings Locales (`services/rag/main.py`)

Microservicio en CPU pura con `fastembed` y `qdrant-client` para cómputo de embeddings semánticos a alta velocidad sin requerir GPU, complementado con conexión a Ollama externo y tolerancia a fallos.

* Endpoints disponibles:
  * `GET /api/rag/health`: Chequeo de salud y conexión con Qdrant.
  * `POST /api/rag/ingest`: Cálculo de vectores y subida a la colección `curza_knowledge`.
  * `POST /api/rag/chat`: Búsqueda vectorial semántica de contexto e inferencia institucional.

---

## 5. Script de Importación Directa (`importer/import_curza.py`)

### ⚠️ Corrección Técnica Detectada
El endpoint original (`https://web.curza.uncoma.edu.ar/wp-json/wp/v2`) devuelve el archivo HTML de la SPA de React. El backend real de WordPress con la API REST activa se encuentra en:
`https://admin.curza.uncoma.edu.ar/curza-api/wp/v2`

El script implementa:
1. Paginación automática sobre los endpoints `posts` (423 registros) y `pages` (282 registros).
2. Limpieza de HTML con BeautifulSoup.
3. Desambiguación de claves primarias para evitar colisiones entre posts y páginas.
4. Ingesta por lotes hacia Qdrant y Meilisearch con reporte de progreso en tiempo real.

---

## 6. Configuración del Reverse Proxy (`deploy/Caddyfile`)

```caddy
# En desarrollo: {$SITE_ADDRESS::8888}
# En producción: web.curza.uncoma.edu.ar
{$SITE_ADDRESS::8888} {
    encode gzip zstd

    # Interfaz Web Astro (SSR / Estático)
    handle /_astro/* {
        reverse_proxy web:4321
    }
    
    # Endpoint RAG & Chatbot
    handle /api/rag/* {
        reverse_proxy rag-api:8000
    }

    # Búsqueda Instantánea Meilisearch
    handle /api/search/* {
        uri strip_prefix /api/search
        reverse_proxy search:7700
    }

    # Panel de Administración CMS y API Strapi
    handle /admin* {
        reverse_proxy strapi:1337
    }
    handle /api/cms/* {
        uri strip_prefix /api/cms
        reverse_proxy strapi:1337
    }
    handle /uploads/* {
        reverse_proxy strapi:1337
    }

    # Resto de solicitudes dirigidas al Frontend Astro
    handle {
        reverse_proxy web:4321
    }
}
```

---

## 7. Procedimiento de Ejecución y Pruebas

### En esta máquina de desarrollo (usando Podman):

1. **Variables de entorno**:
   Asegurar archivo `.env`:
   ```bash
   CADDY_PORT=8888
   CADDY_INTERNAL_PORT=8888
   SITE_ADDRESS=:8888
   ```

2. **Arranque del Stack**:
   ```bash
   podman-compose up -d
   ```

3. **Verificación de servicios**:
   * Portal Web Astro: `http://localhost:8888/`
   * Búsqueda Instantánea: `http://localhost:8888/search`
   * Asistente RAG: `http://localhost:8888/chat`
   * Health RAG: `http://localhost:8888/api/rag/health`
   * Panel Strapi CMS: `http://localhost:8888/admin`

4. **Ejecución de la Importación Directa**:
   ```bash
   # Opción recomendada utilizando el contenedor con librerías ya instaladas:
   podman run --rm --network web_curza_curza-net \
     -v ./importer:/importer:ro \
     -e RAG_INGEST_URL="http://rag-api:8000/api/rag/ingest" \
     -e MEILI_URL="http://search:7700" \
     curza-rag-api:1.0.0 python /importer/import_curza.py
   ```

---

## 8. Guía para Despliegue en Producción (Docker)

Para desplegar en el servidor final de producción utilizando **Docker**:

1. En el archivo `.env` del servidor de producción, configurar:
   ```bash
   CADDY_PORT=80
   CADDY_INTERNAL_PORT=80
   SITE_ADDRESS=web.curza.uncoma.edu.ar
   ```
2. Ejecutar con Docker Compose:
   ```bash
   docker compose up -d --build
   ```
3. Caddy gestionará de forma automática los certificados SSL con Let's Encrypt para `web.curza.uncoma.edu.ar`.
