# Portal Web CURZAS - UNComa

Modernización de la plataforma institucional del **Complejo Universitario Regional Zona Atlántica y Sur (CURZAS)** de la **Universidad Nacional del Comahue (UNComa)**.

El proyecto implementa una arquitectura desacoplada, modular y de alto rendimiento que combina un frontend estático/SSR ultra veloz, un gestor de contenidos headless (CMS), un motor de búsqueda instantánea, un módulo de departamentos y carreras académicas, plano interactivo del campus y un asistente inteligente basado en Retrieval-Augmented Generation (RAG).

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
                        ┌───────┴───────┐                                     ▼
                        ▼               ▼                              ┌──────────────┐
                 ┌──────────────┐ ┌──────────────┐                     │ PostgreSQL 16│
                 │ Qdrant DB    │ │ Ollama LLM   │                     │ (Relacional) │
                 │ (Embeddings) │ │ (gemma4:12b) │                     │  Puerto 5432 │
                 │  Puerto 6333 │ │ (Externo)    │                     └──────────────┘
                 └──────────────┘ └──────────────┘
```

### Componentes Principales

1. **Frontend (`frontend/`)**:
   - **Astro v4** (modo híbrido/SSR con `@astrojs/node` y Tailwind CSS).
   - Look & feel institucional UNComa (azul institucional `#003366`, dorado `#F39200` y tipografía *Poppins*).
   - **Departamentos y Carreras**: Módulo de unidades académicas (`/departamentos`, `/tecnologia`, etc.) con perfiles de egreso, planes de estudio y descarga de folletos y resoluciones PDF.
   - **Plano Interactivo del Campus**: Mapa vectorial con buscador de aulas, categorías y niveles (`/plano`).
   - **Gratuidad e Ingreso**: Información oficial sobre acceso libre, sin cupos ni aranceles en grado y pregrado (`/gratuidad-e-ingreso`).
   - **Visor Dinámico de Contenidos**: Rizado de páginas y noticias históricas en `/contenido/[id]`.

2. **Búsqueda Instantánea (`curza_search`)**:
   - **Meilisearch v1.10** con tolerancia tipográfica y tiempos de respuesta inferiores a 20 ms.
   - Indexación automática de contenidos institucionales con URLs locales y ponderación por vigencia temporal.

3. **Asistente IA Institucional & RAG (`services/rag/`)**:
   - **FastAPI** + **FastEmbed** (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` en CPU, 384 dimensiones).
   - **Qdrant v1.11**: Base vectorial para almacenamiento de embeddings de noticias, normativas y páginas institucionales.
   - **LLM**: Integración con Ollama (API compatible OpenAI) con modelo instructivo y tratamiento de voseo formal.
   - Respuestas contextualizadas institucionalmente con citas y enlaces de verificación hacia el portal.

4. **CMS Headless (`cms/`)**:
   - **Strapi v5** conectado a **PostgreSQL 16**.
   - Gestión desacoplada de contenidos, noticias, carreras y secciones.

5. **Gateway / Proxy Inverso (`deploy/Caddyfile`)**:
   - **Caddy v2**: Orquesta el ruteo interno de rutas y APIs:
     - `/` ➔ Frontend Astro
     - `/departamentos*`, `/tecnologia`, etc. ➔ Frontend Astro
     - `/plano`, `/gratuidad-e-ingreso`, `/chat`, `/search` ➔ Frontend Astro
     - `/contenido/*` ➔ Frontend Astro
     - `/admin`, `/admin/*`, `/api/cms/*`, `/uploads/*` ➔ Strapi CMS
     - `/api/rag/*` ➔ FastAPI RAG Service
     - `/api/search/*` ➔ Meilisearch Proxy
   - Diseñado para funcionar en puertos alternativos en desarrollo (ej. `8888`) o en `80/443` con HTTPS automático en producción.

6. **Scripts de Ingestión y Migración (`importer/`)**:
   - `importer/import_curza.py`: Descarga y normaliza publicaciones y páginas desde la API REST de WordPress (`https://admin.curza.uncoma.edu.ar/curza-api/wp/v2`), generando vectores simultáneos para Meilisearch y Qdrant.
   - `importer/ingest_gratuidad.py`: Ingesta y asegura la persistencia de las normativas de gratuidad, ingreso y aranceles en el vector store.

---

## ⚙️ Variables de Entorno

Copiar la plantilla de configuración antes de iniciar:

```bash
cp .env.example .env
```

### Parámetros Principales (`.env`)

| Variable | Descripción | Ejemplo / Valor por defecto |
|---|---|---|
| `CADDY_PORT` | Puerto de escucha en el host para el proxy Caddy | `8888` (Dev/Test) / `80` (Prod) |
| `SITE_URL` | URL base accesible por el usuario final | `${SITE_URL}` (ej. `https://www.curza.uncoma.edu.ar`) |
| `PUBLIC_SITE_URL` | URL base pública expuesta para el frontend Astro | `${SITE_URL}` (ej. `https://www.curza.uncoma.edu.ar`) |
| `OLLAMA_EXTERNAL_URL` | Endpoint base de Ollama (compatible OpenAI) | `https://ollama.curza.com.ar/v1` |
| `OLLAMA_MODEL` | Nombre del modelo en Ollama | `gemma4:12b` |
| `MEILI_MASTER_KEY` | Llave de administración de Meilisearch | Cadena segura |
| `DATABASE_NAME` | Nombre de base de datos PostgreSQL | `curza_cms` |
| `DATABASE_USERNAME` | Usuario PostgreSQL | `strapi` |
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

### 3. Ejecutar la Inicialización de Contenidos (Seeding / Ingestión)

El repositorio incluye un archivo de respaldo con los 706 documentos institucionales ya procesados (`importer/seed_curza_content.json`).

**Opción A: Carga Rápida Offline (Recomendada - Lista en 1 minuto):**
Pobla Meilisearch y Qdrant directamente desde los datos empaquetados en el repositorio:
```bash
podman run --rm --network curza_network \
  -v $(pwd)/importer:/importer:ro \
  -e RAG_INGEST_URL=http://curza_rag_api:8000/api/rag/ingest \
  -e MEILI_URL=http://curza_search:7700 \
  -e MEILISEARCH_MASTER_KEY=curza_secure_search_key_2026 \
  python:3.11-slim bash -c "python /importer/seed_database.py"
```

**Opción B: Sincronización en Vivo desde la API de WordPress:**
Descarga las últimas publicaciones en vivo desde los servidores de la universidad:
```bash
podman run --rm --network curza_network \
  -v $(pwd)/importer:/importer:ro \
  -e QDRANT_HOST=curza_qdrant \
  -e QDRANT_PORT=6333 \
  -e MEILISEARCH_HOST=curza_search \
  -e MEILISEARCH_PORT=7700 \
  -e MEILI_MASTER_KEY=curza_secure_search_key_2026 \
  -e SITE_URL=${SITE_URL:-https://www.curza.uncoma.edu.ar} \
  python:3.11-slim bash -c "pip install -r /importer/requirements.txt && python /importer/import_curza.py && python /importer/ingest_gratuidad.py"
```

---

## 🌐 Despliegue en Producción (Docker)

El proyecto mantiene total compatibilidad con Docker y Docker Compose estándar.

### 1. Configurar variables de producción
Editar `.env`:
```env
CADDY_PORT=80
SITE_URL=https://www.curza.uncoma.edu.ar
PUBLIC_SITE_URL=https://www.curza.uncoma.edu.ar
```

### 2. Iniciar con Docker Compose
```bash
docker compose up -d --build
```

### 3. Certificados SSL/TLS con Caddy
En producción, Caddy puede gestionar automáticamente certificados SSL de Let's Encrypt especificando el dominio en `deploy/Caddyfile`:
```caddyfile
www.curza.uncoma.edu.ar {
    # reglas de proxy inversas existentes
}
```

---

## 📍 Rutas del Sistema

Todas las rutas se resuelven a partir de `${SITE_URL}` (ejemplo: `https://www.curza.uncoma.edu.ar`):

- **Portal Web (Inicio)**: `${SITE_URL}/`
- **Departamentos Académicos**: `${SITE_URL}/departamentos`
  - *Dpto. de Ciencia y Tecnología*: `${SITE_URL}/tecnologia`
  - *Dpto. de Psicopedagogía*: `${SITE_URL}/psicopedagogia`
  - *Dpto. de Lengua, Literatura y Comunicación*: `${SITE_URL}/lengua-comunicacion`
  - *Dpto. de Administración Pública*: `${SITE_URL}/admin-publica`
  - *Dpto. de Estudios Políticos*: `${SITE_URL}/estudios-politicos`
  - *Dpto. de Gestión Agropecuaria*: `${SITE_URL}/gestion-agropecuaria`
  - *Coord. de Enfermería*: `${SITE_URL}/enfermeria`
- **Plano Oficial del Campus**: `${SITE_URL}/plano`
- **Gratuidad e Ingreso Sin Cupo**: `${SITE_URL}/gratuidad-e-ingreso`
- **Buscador Instantáneo**: `${SITE_URL}/search`
- **Asistente IA**: `${SITE_URL}/chat`
- **Detalle de Contenidos**: `${SITE_URL}/contenido/[id]`
- **Panel Strapi CMS**: `${SITE_URL}/admin`
- **Healthcheck RAG API**: `${SITE_URL}/api/rag/health`
- **Healthcheck Meilisearch**: `${SITE_URL}/api/search/health`

---

## 📝 Cómo Publicar Contenido Manualmente en el Sitio

El portal ofrece diferentes métodos según el tipo de contenido que se desee publicar:

### Opción 1: Publicar Noticias, Avisos o Resoluciones (Recomendado)
Para publicar novedades o artículos que requieran tener su propia página web (`${SITE_URL}/contenido/...`), aparecer de inmediato en el buscador instantáneo y ser aprendidos por el Asistente IA:

Utilizar el script interactivo incluido en la raíz del proyecto:

```bash
./publicar.py
```

El script te solicitará:
1. **Título** de la publicación.
2. **Tipo**: Noticia / Novedad o Página institucional.
3. **Contenido**: Permite escribir o pegar texto multilínea. Al escribir `FIN` en una línea nueva, se publica automáticamente.

También puede ejecutarse de forma directa con argumentos por línea de comandos:

```bash
./publicar.py --titulo "Convocatoria a Becas de Residencia 2026" \
  --contenido "La Secretaría de Bienestar informa que se abren las inscripciones desde el 1 de octubre..." \
  --tipo noticia
```

**¿Qué hace automáticamente este comando?**
- Crea la vista en `${SITE_URL}/contenido/post_<id>` con encabezados, fechas y tipografía institucional.
- Indexa el documento en **Meilisearch** para que aparezca en el buscador instantáneo (`${SITE_URL}/search`).
- Genera el embedding vectorial y lo guarda en **Qdrant**, permitiendo que el **Asistente IA** (`${SITE_URL}/chat`) responda preguntas basadas en este contenido inmediatamente.

---

### Opción 2: Crear una Página Web Institucional fija (con diseño a medida)
Si deseás crear una sección institucional permanente (por ejemplo `${SITE_URL}/comedor` o `${SITE_URL}/institucional/historia`):

1. Creá un archivo `.astro` dentro del directorio `frontend/src/pages/` (ejemplo: `frontend/src/pages/comedor.astro`).
2. Utilizá la plantilla institucional con el componente `<Layout>`:

```astro
---
import Layout from '../layouts/Layout.astro';
---

<Layout title="Comedor Universitario - CURZAS">
  <div class="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
    <h1 class="text-3xl font-bold text-[#003366] mb-4">Comedor Universitario</h1>
    <p class="text-slate-600 leading-relaxed text-sm sm:text-base">
      Información sobre horarios de atención, menú estudiantil y solicitud de viandas...
    </p>
  </div>
</Layout>
```

Astro detectará el archivo nuevo y lo publicará automáticamente en `${SITE_URL}/comedor` sin necesidad de reiniciar contenedores.

---

### Opción 3: Actualizar Departamentos, Carreras o Autoridades
Si necesitás modificar datos de las autoridades de un departamento (director/a, horarios, correos) o de las carreras (planes de estudio vigentes, ordenanzas, materias):

- Editá directamente el archivo JSON estructurado: `frontend/src/data/departamentos.json`.
- Los cambios se reflejarán de inmediato tanto en la sección de inicio como en las páginas de cada departamento (`${SITE_URL}/tecnologia`, `${SITE_URL}/psicopedagogia`, etc.).

---

### Opción 4: A través del Panel Web CMS (Strapi)
Para gestionar contenidos mediante interfaz gráfica web:

- Accedé a: `${SITE_URL}/admin` (ejemplo: `https://www.curza.uncoma.edu.ar/admin`).
- Si es la primera vez, el sistema te solicitará crear la cuenta inicial de administrador.
- Permite crear colecciones de contenido personalizadas, redactar en editor enriquecido y subir imágenes a la biblioteca de medios.
