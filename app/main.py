"""FastAPI entry point for the inventory and session foundation."""

from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(title="Dubizzle Cars Assistant API", version="0.1.0")
app.include_router(router)
