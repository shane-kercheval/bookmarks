"""FastAPI application entry point."""
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from api.routers import bookmarks, health, lists, settings, tags, tokens, users
from core.config import get_settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process request and add security headers to response."""
        response = await call_next(request)
        # HSTS: enforce HTTPS for 1 year, including subdomains
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Prevent clickjacking - API shouldn't be framed
        response.headers["X-Frame-Options"] = "DENY"
        return response


app_settings = get_settings()

app = FastAPI(
    title="Bookmarks API",
    description="A bookmark management system with tagging and search capabilities.",
    version="0.1.0",
)

# Security headers middleware (runs after CORS, adds headers to responses)
app.add_middleware(SecurityHeadersMiddleware)

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
