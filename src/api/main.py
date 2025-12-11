"""FastAPI application entry point."""
from fastapi import FastAPI

from api.routers import bookmarks, health, users


app = FastAPI(
    title="Bookmarks API",
    description="A bookmark management system with tagging and search capabilities.",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(users.router)
app.include_router(bookmarks.router)
