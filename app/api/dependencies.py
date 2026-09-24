"""Shared service construction for API routes."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.engine import Engine

from app.core.config import Settings, load_settings
from app.core.database import ensure_identity_schema, make_engine
from app.services.agent import ChatAgent
from app.services.agent_tools import AgentTools
from app.services.booking import BookingService
from app.services.car_repository import CarRepository
from app.services.embedding_service import EmbeddingService
from app.services.leads import LeadService
from app.services.memory import MemoryService
from app.services.nvidia_chat import NvidiaChatClient
from app.services.retrieval import RetrievalService
from app.services.vector_store import VectorStore


@lru_cache
def get_settings() -> Settings:
    return load_settings()


@lru_cache
def get_engine() -> Engine:
    return make_engine(get_settings())


@lru_cache
def get_vector_store() -> VectorStore:
    return VectorStore(get_settings())


@lru_cache
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService(get_settings())


def get_car_repository() -> CarRepository:
    return CarRepository(get_engine())


def get_retrieval_service() -> RetrievalService:
    return RetrievalService(get_engine(), get_embedding_service(), get_vector_store())


@lru_cache
def get_memory_service() -> MemoryService:
    engine = get_engine()
    ensure_identity_schema(engine)
    return MemoryService(engine)


def get_booking_service() -> BookingService:
    return BookingService(get_engine())


@lru_cache
def get_nvidia_chat_client() -> NvidiaChatClient:
    return NvidiaChatClient(get_settings())


def get_agent_service() -> ChatAgent:
    tools = AgentTools(
        get_retrieval_service(),
        get_memory_service(),
        get_booking_service(),
        LeadService(get_engine()),
    )
    return ChatAgent(tools, get_nvidia_chat_client())
