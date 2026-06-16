"""FastAPI backend for the Hybrid Data Lineage Engine.

Endpoints
---------
GET  /entities                       - catalogue for the UI picker
GET  /lineage/{entity_id}            - graph neighbourhood (table or column level)
GET  /provisional                    - AI-inferred edges awaiting review
POST /provisional/{edge_id}/review   - approve / reject a provisional edge
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from graph import LineageRepository

repo: LineageRepository | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global repo
    repo = LineageRepository()
    yield
    repo.close()


app = FastAPI(title="Hybrid Data Lineage Engine", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ReviewRequest(BaseModel):
    approve: bool


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/entities")
def entities() -> list[dict]:
    return repo.list_entities()


@app.get("/lineage/{entity_id}")
def lineage(
    entity_id: str,
    depth: int = Query(3, ge=1, le=8),
    level: str = Query("table", pattern="^(table|column)$"),
) -> dict:
    result = repo.lineage(entity_id, depth=depth, level=level)
    if not result["nodes"]:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")
    return result


@app.get("/provisional")
def provisional() -> list[dict]:
    return repo.provisional_edges()


@app.post("/provisional/{edge_id}/review")
def review(edge_id: str, body: ReviewRequest) -> dict:
    updated = repo.review_edge(edge_id, body.approve)
    if updated == 0:
        raise HTTPException(status_code=404, detail=f"Edge '{edge_id}' not found")
    return {"edge_id": edge_id,
            "status": "CONFIRMED" if body.approve else "REJECTED"}
