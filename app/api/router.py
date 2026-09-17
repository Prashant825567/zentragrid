"""Aggregate v1 API router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import auth, files, keys, projects, usage

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(keys.router)
api_router.include_router(usage.router)
api_router.include_router(files.router)
