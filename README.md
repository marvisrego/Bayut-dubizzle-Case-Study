# Dubizzle cars assistant

This repository implements the **inventory pipeline, retrieval service, FastAPI backend, conversational agent, and Streamlit client** for the car assistant. The canonical source is `data/processed/cars_merged.xlsx`, sheet `merged_inventory` (189 vehicles). The supplied `Cars_data.xlsx` and generated inventory files are kept local because seller descriptions contain contact numbers; they are not included in this public repository.

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and run:

```powershell
uv sync
```

If `uv` is not on your Windows `PATH`, use `py -m uv` in place of `uv` in the commands below.

Create a local `.env` (gitignored) with these values:

```text
Supabase_Link=<PostgreSQL host or connection URI>
Supabase_Pass=<database password>
port=5432
database=postgres
user=<database user>
nvidia_embed_model_key=<NVIDIA API key>
nvidia_LLM_model_key=<NVIDIA chat API key>
Vector_DB_Endpoint=<Qdrant HTTPS endpoint>
Vector_DB_Key=<Qdrant API key>
```

When `Supabase_Link` is a full PostgreSQL URI, it is authoritative for the connection, including its username, password, port, database, and query options. If it is only a hostname, the separate `Supabase_Pass`, `user`, `port`, and `database` settings are required; SQLAlchemy safely encodes reserved characters in that password. The NVIDIA chat key is required for `/chat`. For Supabase shared session pooling, copy the URI from the project's Connect dialog. [Supabase documents the connection modes and IPv4 support](https://supabase.com/docs/guides/database/connecting-to-postgres).

Optional environment settings: `NVIDIA_EMBED_MODEL`, `NVIDIA_EMBED_URL`, `NVIDIA_LLM_MODEL`, `NVIDIA_LLM_URL`, `NVIDIA_EMBED_BATCH_SIZE`, `NVIDIA_REQUESTS_PER_MINUTE` (capped at 40), and `QDRANT_COLLECTION`. The default collection is the existing `Dubizzle-collection`; set `QDRANT_COLLECTION` for another deployment. No credentials are written to code or logs.

## Import and search

Place your supplied `Cars_data.xlsx` in the repository root. Generate the local canonical inventory before ingestion or running the full inventory tests:

```powershell
uv run python -m scripts.prepare_inventory
uv run python -m scripts.ingest_inventory
uv run python -m scripts.search_inventory "comfortable family SUV" --top-k 5
uv run python -m unittest discover -s tests -q
```

Start the API after ingestion:

```powershell
uv run uvicorn app.main:app --reload
```

In a second terminal, start the Streamlit client:

```powershell
uv run streamlit run streamlit_app.py
```

Open `http://localhost:8501`. The client calls `http://127.0.0.1:8000` by default. To use another API host, set `FASTAPI_URL` in the environment or local `.env` before starting Streamlit. Enter your name, then choose **Start / switch user**. Streamlit calls `POST /users` to create or retrieve a UUID user and `POST /sessions` to start a conversation. **New Session** keeps that UUID, creates a new backend session, and clears only the displayed conversation; saved preferences and liked cars remain in PostgreSQL. Viewing requests are made in chat using Dubai date and time. Streamlit stores only display history and the active user/session IDs; FastAPI owns all search, memory, lead, and booking rules. Entering the same normalized name after a browser reload retrieves the same demo profile. Name-only identity does not authenticate a person: anyone who enters that name can access its saved profile. Deployment with real users needs authentication.

## Deploy FastAPI on Render and Streamlit on Community Cloud

Create a Render **Python web service** from the repository's `dev` branch, with the repository root as its root directory. The committed `uv.lock` lets Render provide `uv`; `.python-version` pins Python 3.13. Use:

```text
Build Command: uv sync --locked --no-dev
Start Command: uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Configure these Render environment variables with your own values: `Supabase_Link`, `Vector_DB_Endpoint`, `Vector_DB_Key`, `nvidia_embed_model_key`, and `nvidia_LLM_model_key`. If `Supabase_Link` is a host rather than a PostgreSQL URI, also set `Supabase_Pass`, `user`, `port`, and `database`. Run inventory preparation and ingestion locally against the same PostgreSQL and Qdrant services before deployment; the public repository does not include the seller data. Check `/health` for `ready`. The API stores users, sessions, preferences, liked cars, messages, bookings, and leads in PostgreSQL. Its local lead CSV is an export on Render's temporary filesystem.

On Streamlit Community Cloud, select the same repository and `dev` branch with `streamlit_app.py` as the main file. In the app's Secrets settings, add a root-level value such as `FASTAPI_URL = "https://your-render-service.onrender.com"`. Streamlit exposes root-level secrets as environment variables, which the client reads. Keep database and provider keys on Render only.

API docs are at `/docs`. The current routes are `GET /health`, `POST /users`, `POST /sessions`, `GET /sessions/{session_id}`, `GET /cars/{listing_id}`, `POST /cars/search`, `POST /bookings`, and `POST /chat`. Search accepts `structured`, `semantic`, or `hybrid` mode; for example:

```json
{
  "mode": "hybrid",
  "filters": {"make": "Toyota", "min_year": 2020},
  "semantic_query": "comfortable family car",
  "top_k": 5
}
```

Hard filters run against PostgreSQL. Qdrant ranks only SQL-eligible IDs, and final results are reloaded from PostgreSQL. Supported structured filters are make, model, trim, source, exact/min/max year, and min/max AED price or kilometre mileage. The workbook has no dedicated price or mileage column, but some descriptions state those values. Conservative source-text extraction now populates 39 AED purchase prices and 88 odometer readings, each with an evidence excerpt. Monthly payments, fees, speed, electric range, warranty limits, and service intervals are excluded. Unknown values remain null and cannot satisfy a hard numeric filter.

`POST /sessions` generates and stores a new UUID when `user_id` is omitted; passing an existing ID starts another session for that user. `POST /chat` accepts a message and returns a grounded answer, matching cars, listing IDs, and an optional follow-up prompt. It checks any supplied `user_id` against the session owner. `POST /bookings` and conversational bookings validate Monday–Saturday, 08:00–20:00 Dubai time and record a **simulated request** as `pending_confirmation`; slot availability and a real dealer reservation are not confirmed.

`POST /users` accepts `{"display_name":"Test User"}` and returns a stable UUID and display name. It reuses a unique older profile with the same normalized name; ambiguous older names receive a fresh mapped profile.

Example chat request after creating a session:

```json
{"user_id":"<returned user ID>","session_id":"<created session ID>","message":"Show me something sporty and comfortable"}
```

The [NVIDIA Nemotron 3 Super 120B](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-super-120b-a12b-infer) chat model chooses allowlisted backend tools. Python checks tool arguments against the user's words and session state, resolves numbered and pronoun references, validates bookings, and renders vehicle answers from PostgreSQL. Session messages, last search IDs, selected car, and temporary filters live in PostgreSQL. Explicit long-term preferences and liked cars persist by user ID across sessions. Leads are upserted to PostgreSQL and exported to gitignored `data/leads.csv`. Chat context uses at most eight recent messages, compact state, and the long-term profile.

`--postgres-only` loads factual records when Qdrant is unavailable. The full command upserts all 23 canonical workbook columns to PostgreSQL `cars` and stores per-listing vector state in `car_embedding_state`. Qdrant holds one deterministic point ID per listing with a `listing_id`, small filterable fields, model ID, and embedding hash. Search embeds the query once, searches Qdrant, then fetches complete records from PostgreSQL in result order.

Embeddings use `embedding_text` only. The default [NVIDIA Nemotron 3 Embed 1B](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-embed-1b) supports English and Arabic and returns 2048 dimensions. Its [hosted API](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-embed-1b-infer) requires `passage` mode for listings and `query` mode for searches. A live check on 24 September 2026 accepted all 189 current texts in one call; the default batch size is therefore 189. This is a tested size for this workbook, not a published provider maximum. Oversized batches are split if the endpoint returns 413 or 422. A shared local rolling limiter caps NVIDIA calls at 40/minute; 429 and transient failures use bounded retries and `Retry-After`.

Reruns skip embeddings when the Qdrant point already has the same text hash and model. A batch's PostgreSQL vector state is committed only after Qdrant acknowledges the upsert. The final audit checks source and database counts, text preservation, unique listing IDs, vector count, ID references, deterministic point IDs, and collection dimensions. Existing tables and collections are never dropped.

The older `data/processed/cars_merged.csv` is an equivalent export, but the workbook sheet is the required input for this pipeline. `preprocess_inventory.py` and its cleaned-sheet-only output are exploratory and are not imported.

## Verified live run (24 September 2026)

The first run imported 189 PostgreSQL cars and indexed 189 Qdrant points with zero failures. The second run reported `Embeddings Requested: 0`, `Embeddings Skipped Unchanged: 189`, and `Qdrant Vector Count: 189`. An Arabic semantic query returned three listing IDs and retrieved their complete records from PostgreSQL. The verifier compares all workbook columns with the stored records and checks Qdrant IDs, counts, and vector dimensions.

The retrieval and conversational backend passed 43 offline tests on 24 September 2026. A live retrieval check returned 12 Toyota listings from 2020 onward, five semantic results with PostgreSQL records, and five hybrid results that all obeyed the Toyota/year constraints. After source-text extraction, PostgreSQL contains 39 known prices and 88 known mileages; a price filter of AED 100,000 or less returns 18 listings. Re-ingestion requested zero new embeddings and left all 189 Qdrant vectors unchanged. `/health` reported `ready` with 189 cars and 189 vectors. A live NVIDIA chat check returned Toyota listings, resolved “the second one,” reported missing warranty, and recalled a saved BMW preference in a new session. Ranking relevance needs a separate evaluation set.


## Streamlit client verification (24 September 2026)

![Streamlit welcome view](docs/streamlit_welcome.png)

![Streamlit results view](docs/streamlit_results.png)

The UI ran locally at `http://127.0.0.1:8501` against FastAPI at `http://127.0.0.1:8000`; `/health` reported `ready` with 189 inventory rows and 189 vectors. The following are excerpts from live UI interactions using test user IDs:

```text
Session 1
User: Show me Toyota cars
Assistant: 1. CAR_0031; 2. CAR_0047; 3. CAR_0078; ...
User: Tell me more about the second one
Assistant: CAR_0047 ... A cash price is not listed; verified mileage is not listed.
User: Does it have a warranty?
Assistant: CAR_0047 ... warranty is not listed as a verified vehicle detail.

Separate returning-user check, session 1
User: I generally prefer BMW SUVs
Assistant: I've saved that vehicle preference.
User: I like that one
Assistant: I've saved CAR_0079 to your liked cars.

Same user ID, completely new session
User: What was I looking for before, and which car did I like?
Assistant: I remember your name is Live Demo; preferred makes: BMW; liked cars: CAR_0079; body type: SUV.
```

The live UI also returned supplied IDs for a fuzzy request ("sporty and comfortable") and a mixed Toyota/year/comfort request; returned no cars for an impossible AED 1 budget; declined a programming request; recorded a simulated Saturday 10:00 viewing request; and rejected Sunday and 21:00 requests. A browser run with **Test User** saved "I prefer Nissan SUVs," searched, liked the second result, started a new session, and recalled both the preference and liked listing. The session ID changed while `/users` returned the same UUID for a normalized name variant. Component tests cover missing images, missing price/mileage, unavailable API, timeout, and empty API replies. The local test suite passed 49 tests. Streamlit sends all chat turns to `POST /chat`; it contains no retrieval, memory, or booking validation logic. The "Nissan SUVs" live search also returned some Nissan sedans because body type is not a verified hard filter in the current inventory; body-style provenance needs review before it can be enforced as a factual constraint.
