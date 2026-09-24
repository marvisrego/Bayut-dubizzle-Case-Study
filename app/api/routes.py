"""Thin API routes: validation and dispatch only."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.api.dependencies import (
    get_agent_service,
    get_booking_service,
    get_car_repository,
    get_engine,
    get_memory_service,
    get_retrieval_service,
    get_vector_store,
)
from app.schemas.api import (
    BookingRequest,
    BookingResponse,
    ChatRequest,
    ChatResponse,
    CreateSessionRequest,
    HealthResponse,
    ResolveUserRequest,
    SessionResponse,
    UserResponse,
)
from app.schemas.cars import CarResponse, SearchRequest, SearchResponse
from app.services.agent import ChatAgent, SessionOwnershipError
from app.services.booking import BookingError, BookingService
from app.services.car_repository import CarRepository
from app.services.memory import MemoryService
from app.services.nvidia_chat import ChatModelError
from app.services.retrieval import RetrievalService
from app.services.vector_store import VectorStore

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
def health(
    engine: Annotated[Engine, Depends(get_engine)],
    store: Annotated[VectorStore, Depends(get_vector_store)],
) -> HealthResponse:
    postgres_ready = False
    qdrant_ready = False
    inventory_count = None
    vector_count = None
    try:
        with engine.connect() as connection:
            postgres_ready = connection.scalar(text("SELECT 1")) == 1
        inventory_count = CarRepository(engine).count()
    except Exception:  # noqa: BLE001 - health returns booleans without leaking service details
        logger.warning("PostgreSQL health check failed")
    try:
        qdrant_ready = store.client.collection_exists(store.collection)
        if qdrant_ready:
            vector_count = store.client.count(store.collection, exact=True).count
    except Exception:  # noqa: BLE001 - health returns booleans without leaking service details
        logger.warning("Qdrant health check failed")
    ready = postgres_ready and qdrant_ready and inventory_count == vector_count
    return HealthResponse(
        status="ready" if ready else "degraded",
        postgres_ready=postgres_ready,
        qdrant_ready=qdrant_ready,
        inventory_count=inventory_count,
        vector_count=vector_count,
    )


@router.post("/users", response_model=UserResponse)
def resolve_user(
    body: ResolveUserRequest,
    memory: Annotated[MemoryService, Depends(get_memory_service)],
) -> UserResponse:
    return memory.resolve_user(body.display_name)


@router.post(
    "/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED
)
def create_session(
    body: CreateSessionRequest,
    memory: Annotated[MemoryService, Depends(get_memory_service)],
) -> SessionResponse:
    return memory.create_session(body.user_id, body.display_name)


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: str,
    memory: Annotated[MemoryService, Depends(get_memory_service)],
) -> SessionResponse:
    result = memory.get_session(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    agent: Annotated[ChatAgent, Depends(get_agent_service)],
) -> ChatResponse:
    try:
        return agent.run(body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SessionOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ChatModelError as exc:
        logger.warning("NVIDIA chat failed: %s", exc)
        raise HTTPException(status_code=503, detail="Chat service unavailable") from exc
    except Exception as exc:
        logger.exception("Chat service failed")
        raise HTTPException(status_code=503, detail="Chat service unavailable") from exc


@router.get("/cars/{listing_id}", response_model=CarResponse)
def get_car(
    listing_id: str,
    cars: Annotated[CarRepository, Depends(get_car_repository)],
) -> CarResponse:
    car = cars.get(listing_id)
    if car is None:
        raise HTTPException(status_code=404, detail="Car not found")
    return CarResponse.model_validate(car)


@router.post("/cars/search", response_model=SearchResponse)
def search_cars(
    body: SearchRequest,
    retrieval: Annotated[RetrievalService, Depends(get_retrieval_service)],
) -> SearchResponse:
    try:
        if body.mode == "structured":
            found = retrieval.structured_search(body.filters)[: body.top_k]
        elif body.mode == "semantic":
            found = retrieval.semantic_search(
                body.semantic_query or "", body.filters, body.top_k
            )
        else:
            found = retrieval.hybrid_search(
                body.filters, body.semantic_query or "", body.top_k
            )
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Retrieval service unavailable"
        ) from exc
    results = [CarResponse.model_validate(car) for car in found]
    return SearchResponse(results=results, count=len(results))


@router.post(
    "/bookings", response_model=BookingResponse, status_code=status.HTTP_202_ACCEPTED
)
def create_booking(
    body: BookingRequest,
    booking: Annotated[BookingService, Depends(get_booking_service)],
) -> BookingResponse:
    try:
        return booking.create_request(body)
    except BookingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
