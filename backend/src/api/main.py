"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import bookmarks, health, lists, settings, tags, tokens, users
from core.config import get_settings


app_settings = get_settings()

app = FastAPI(
    title="Bookmarks API",
    description="A bookmark management system with tagging and search capabilities.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(users.router)
app.include_router(bookmarks.router)
app.include_router(tags.router)
app.include_router(tokens.router)
app.include_router(lists.router)
app.include_router(settings.router)
