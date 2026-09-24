# Dubizzle Cars AI Assistant

A FastAPI car-search assistant with a Streamlit chat client. [Try the hosted demo](https://app-dubizzle-case-study-48ew9fpqpk2dou4ybavz2g.streamlit.app/) (a cold start can take over a minute).

## Quick start

You need Python 3.13, [uv](https://docs.astral.sh/uv/getting-started/installation/), the supplied `Cars_data.xlsx`, and credentials for PostgreSQL, Qdrant, and the NVIDIA embedding and chat APIs. Put `Cars_data.xlsx` in this folder. It is excluded from the repository because seller descriptions contain contact numbers.

Create a local `.env` file (gitignored). Use a full PostgreSQL URI for `Supabase_Link`:

```text
Supabase_Link=postgresql://USER:PASSWORD@HOST:5432/postgres
Vector_DB_Endpoint=https://YOUR-QDRANT-ENDPOINT
Vector_DB_Key=YOUR-QDRANT-KEY
nvidia_embed_model_key=YOUR-NVIDIA-KEY
nvidia_LLM_model_key=YOUR-NVIDIA-KEY
```

If `Supabase_Link` contains only a host, also set `Supabase_Pass`, `user`, `port`, and `database`. URL-encode reserved characters in passwords inside a full URI. Use your own keys; never commit `.env`.

Run these commands from the project folder:

```powershell
uv sync
uv run python -m scripts.prepare_inventory
uv run python -m scripts.ingest_inventory
uv run python -m unittest discover -s tests -q
```

Start the backend in one terminal:

```powershell
uv run uvicorn app.main:app --reload
```

Start the client in a second terminal:

```powershell
uv run streamlit run streamlit_app.py
```

Open `http://localhost:8501`, enter a name, and select **Start / switch user**. The API runs at `http://127.0.0.1:8000`; check `/health` for `ready` and `/docs` for the API. Set `FASTAPI_URL` in the Streamlit environment or `.env` if the backend uses another address. To demonstrate memory, state a preference, like a shown car, select **New Session**, and ask what the assistant remembers.

## Design and scope

I chose Streamlit for a lightweight reactive chat UI and kept search, memory, leads, and booking rules in FastAPI. There is no separate agent framework: a small Python controller uses NVIDIA Nemotron tool calls and validates them before acting. PostgreSQL applies exact filters and supplies the vehicle facts; Qdrant ranks eligible listing IDs for fuzzy queries. PostgreSQL stores recent conversation state and persistent user preferences, which lets a new session recall a returning user without trusting the browser as the source of truth.

The backend returns supplied listing IDs, marks missing prices or mileage as unknown, exports qualified leads to local `data/leads.csv`, and records only simulated viewing requests for Monday–Saturday, 08:00–20:00 Dubai time. The workbook has no managed-car flag, so this prototype treats every supplied listing as eligible. Future work would add authentication, real slot availability, durable hosted lead export, verified body-style attributes, and a labelled search-relevance evaluation set.

## Required conversation evidence

These screenshots use the name **Marvis** and were captured from the local client and backend against the same 189-car PostgreSQL and Qdrant inventory as the hosted demo.

![Marvis starts a session](docs/streamlit_welcome.png)

![Marvis saves a preference and explores Toyota listings](docs/streamlit_results.png)

![Marvis asks follow-up questions about the second car and likes it](docs/streamlit_followup.png)

![A completely new session recalls Marvis's preferences and liked cars](docs/streamlit_memory.png)

In session one, Marvis saved a Toyota SUV preference and AED 150,000 budget, searched the inventory, asked about the second result, asked whether it had a warranty, and liked it. In a **new session** with a different session ID, the assistant recalled the Toyota, SUV, and budget preferences along with liked cars. Another car in that screenshot was liked during an earlier check of the same demo profile.

## Verification and current limits

The local test suite passed **50 tests** on 24 September 2026. It covers retrieval, multi-turn references, returning-user memory, lead CSV writing, viewing hours, and out-of-scope requests. The API health check reported 189 cars and 189 vectors. On the deployed app, "I'm into SUVs" was saved and recalled in a new session and after rejoining the same profile in a fresh browser.

The assignment directs applicants to use a Google AI Studio API key; this implementation uses NVIDIA API keys instead, so that substitution needs to be accepted by the evaluator. Body style is not a verified hard filter, so an SUV request can include other vehicle types until the source data supports that filter. Name-only identity is suitable for a demo, not a real user account.
