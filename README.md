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

When FastAPI runs locally, saving a lead stores it in PostgreSQL and creates or updates `data/leads.csv` in this project folder. The CSV is generated on the first successful lead save, not during setup. If Streamlit connects to a remote FastAPI server, the CSV is created on that server instead.

## Design and scope

I chose Streamlit for a lightweight reactive chat UI and kept search, memory, leads, and booking rules in FastAPI. I used NVIDIA APIs for chat and embeddings. The agent is a small Python controller that validates model tool calls before acting; it needs no separate framework. PostgreSQL applies exact filters and supplies the vehicle facts; Qdrant ranks eligible listing IDs for fuzzy queries. PostgreSQL stores recent conversation state and persistent user preferences, which lets a new session recall a returning user without trusting the browser as the source of truth.

The backend keeps listing IDs for follow-up references while Streamlit shows car names. It stores qualified leads in PostgreSQL, exports them to `data/leads.csv`, marks missing prices or mileage as unknown, and records simulated viewing requests for Monday to Saturday, 08:00 to 20:00 Dubai time. The workbook has no managed-car flag, so every supplied listing is treated as eligible. Future work would add authentication, real slot availability, durable hosted lead export, verified body-style attributes, and a labelled search-relevance evaluation set.

## Deployed conversation evidence

I captured these screenshots from the [deployed Streamlit app](https://app-dubizzle-case-study-48ew9fpqpk2dou4ybavz2g.streamlit.app/) on 24 September 2026 using the name **Marvis**.

![I started a session as Marvis](docs/streamlit_welcome.png)

![I received Toyota listings with names, prices, and mileage but no internal listing IDs](docs/streamlit_results.png)

![I asked a follow-up warranty question about the second result, a Toyota Urban Cruiser](docs/streamlit_followup.png)

![A completely new session recalled my preferences and liked cars](docs/streamlit_memory.png)

![I rejoined as Marvis in a fresh browser and recalled the same profile](docs/streamlit_rejoin.png)

I saved a Toyota SUV preference and AED 150,000 budget, searched for Toyota cars from 2020 under that budget, asked for the second car's mileage and warranty, and liked it. A **new session** and a separate browser both recalled my preference and liked car. I had saved the other liked cars shown in the memory screenshots during earlier checks of the same demo profile.

## Deployed checks

On the deployed app, I received cars within the requested make, year, and price limits and no listings for an impossible Toyota price. A Saturday 10:00 viewing request was recorded; Sunday and 21:00 requests were rejected. A new user was asked about needs, budget, and contact details, and coding and competitor questions were declined. The public UI does not expose the backend CSV, so I confirmed its export path in `app/services/leads.py` rather than by opening the hosted file.
