"""FastAPI application entry point."""
from fastapi import FastAPI

from api.routers import health


app = FastAPI(
    title="Bookmarks API",
    description="A bookmark management system with tagging and search capabilities.",
    version="0.1.0",
)

app.include_router(health.router)
