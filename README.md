# Dubizzle Cars AI Assistant

A FastAPI car-search assistant with a Streamlit chat client. (https://app-dubizzle-case-study-48ew9fpqpk2dou4ybavz2g.streamlit.app/) (a cold start can take over a minute).
The frontend has been deployed on Streamlit, and the FastAPI backend has been deployed on Render.

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

I captured these screenshots from the [deployed Streamlit app](https://app-dubizzle-case-study-48ew9fpqpk2dou4ybavz2g.streamlit.app/)  using the name **Marvis**.

### Short-term memory: same session 

I searched for Toyota cars from 2020 under AED 150,000. The prompt and matching results are visible together:

![My search prompt and Toyota results in session](docs/streamlit_results.png)

I then asked for the second car's mileage and followed with "Does it have a warranty?" Both prompts and both replies refer to the same Toyota Prado:

![Both follow-up prompts and answers identify the same Toyota Prado in session](docs/streamlit_followup.png)

I liked that car before starting a new session:

![My like prompt and the saved Toyota Prado reply in session](docs/streamlit_like.png)

### Long-term memory: new session 

I selected **New Session** and asked what preferences I had given and which car I liked. The new session ID, prompt, and recalled Toyota, SUV, budget, and liked car are visible:

![My recall prompt and answer in new session](docs/streamlit_memory.png)

I also rejoined as Marvis in a fresh browser and asked what the assistant remembered. That created another session, with the same recall:

![My fresh-browser recall prompt and answer in session](docs/streamlit_rejoin.png)

The other liked cars in the memory screenshots were saved during earlier checks of the same demo profile.

## Deployed checks

On the deployed app, I received cars within the requested make, year, and price limits and no listings for an impossible Toyota price. A Saturday 10:00 viewing request was recorded; Sunday and 21:00 requests were rejected. A new user was asked about needs, budget, and contact details, and coding and competitor questions were declined. The public UI does not expose the backend CSV, so I confirmed its export path in `app/services/leads.py` rather than by opening the hosted file.
