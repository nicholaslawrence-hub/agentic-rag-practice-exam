"""FastAPI application factory."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from apps.api.routes.chat import router as chat_router
from apps.api.routes.courses import router as courses_router
from apps.api.routes.upload import router as upload_router
from apps.api.settings import settings

# Wire provider keys read from env by sub-modules
for key, val in {
    "OPENAI_API_KEY": settings.openai_api_key,
    "ANTHROPIC_API_KEY": settings.anthropic_api_key,
    "PINECONE_API_KEY": settings.pinecone_api_key,
    "PINECONE_INDEX": settings.pinecone_index,
    "LANGCHAIN_API_KEY": settings.langchain_api_key,
    "LANGCHAIN_TRACING_V2": settings.langchain_tracing_v2,
    "LANGCHAIN_PROJECT": settings.langchain_project,
}.items():
    if val:
        os.environ.setdefault(key, val)


def create_app() -> FastAPI:
    app = FastAPI(title="MCB Tutor API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", settings.api_url.replace(":8000", ":3000")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(courses_router)
    app.include_router(chat_router)
    app.include_router(upload_router)

    # Serve slide images and generated exam PDFs from the local data/ directory.
    # In production, replace with S3/R2 and remove this mount.
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(data_dir)), name="static")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
