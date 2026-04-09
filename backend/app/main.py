"""
FastAPI application entry-point.
"""
from __future__ import annotations
import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.database import init_db
from app.api.routes import router
from app.tasks.garbage_collector import run_gc_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(
    title="PDF → DXF Converter V001",
    description="Local, cost-free PDF to DXF conversion optimised for CNC.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
async def on_startup():
    init_db()
    asyncio.create_task(run_gc_loop())


@app.get("/health")
def health():
    return {"status": "ok"}
