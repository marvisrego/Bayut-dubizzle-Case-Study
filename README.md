# Dubizzle Cars AI Assistant

A FastAPI car-search assistant with a Streamlit chat client. [Try the hosted demo](https://app-dubizzle-case-study-48ew9fpqpk2dou4ybavz2g.streamlit.app/) (a cold start can take over a minute).

## Quick start

You need Python 3.11 or newer, [uv](https://docs.astral.sh/uv/getting-started/installation/), the supplied `Cars_data.xlsx`, and credentials for PostgreSQL, Qdrant, and the NVIDIA embedding and chat APIs. Put `Cars_data.xlsx` in this folder. It is excluded from the repository because seller descriptions contain contact numbers.

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

The backend keeps listing IDs for follow-up references while Streamlit shows car names. It marks missing prices or mileage as unknown, exports qualified leads to `data/leads.csv`, and records simulated viewing requests for Monday to Saturday, 08:00 to 20:00 Dubai time. The workbook has no managed-car flag, so every supplied listing is treated as eligible. Future work would add authentication, real slot availability, durable hosted lead export, verified body-style attributes, and a labelled search-relevance evaluation set.

## Deployed conversation evidence

These screenshots were captured from the [deployed Streamlit app](https://app-dubizzle-case-study-48ew9fpqpk2dou4ybavz2g.streamlit.app/) on 24 September 2026 using the name **Marvis**.

![Marvis starts a session](docs/streamlit_welcome.png)

![Marvis receives Toyota listings with names, prices, and mileage but no internal listing IDs](docs/streamlit_results.png)

![A follow-up warranty question stays on the Toyota Urban Cruiser selected as the second result](docs/streamlit_followup.png)

![A completely new session recalls Marvis's preferences and liked cars](docs/streamlit_memory.png)

![A fresh browser rejoins as Marvis and recalls the same profile](docs/streamlit_rejoin.png)

Marvis saved a Toyota SUV preference and AED 150,000 budget, searched for Toyota cars from 2020 under that budget, asked for the second car's mileage and warranty, and liked it. A **new session** and a separate browser both recalled the preference and liked car. Other liked cars in the memory screenshots were saved during earlier checks of the same demo profile.

## Verification and limits

The deployed app returned cars within the requested make, year, and price limits; returned no listings for an impossible Toyota price; accepted a Saturday 10:00 viewing request; rejected Sunday and 21:00 requests; asked a new user about needs, budget, and contact details; and declined coding and competitor questions. The public UI cannot expose the server-side lead CSV, so CSV export is verified from `app/services/leads.py` rather than from the hosted file.

The PDF instructs applicants to use a Google AI Studio API key; this project uses NVIDIA APIs, so that instruction is **not met**. Semantic results can include loose matches, an unfamiliar make may receive a generic scope reply, and body style is not a verified hard filter. Viewing requests are simulated, and name-only identity is for this demo.
