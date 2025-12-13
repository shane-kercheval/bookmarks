# Bookmark Management System - Implementation Plan

> **Reference**: See [2025-12-09-bookmarks-goal.md](./2025-12-09-bookmarks-goal.md) for the full vision and requirements.

This plan covers **Phase 1 (MVP)** implementation. Subsequent phases will be planned after Phase 1 is complete and reviewed.

---

## Overview

**Phase 1 MVP Scope**:
- Add/edit/delete bookmarks with auto-fetch metadata
- Manual tagging
- List view with sort/filter by tags/date
- Simple text search (title, tags, description)
- Auth0 authentication
- React frontend with basic UI

**Out of Scope for Phase 1** (deferred to later phases):
- AI-powered tagging
- Semantic search / embeddings
- Notes, Todos, Custom Views
- Recently accessed tracking, archive, reminders
- MCP integration

---

## Key Decisions

- **Tag format**: Lowercase only, hyphens (`-`) allowed (e.g., `machine-learning`, `how-to`). No underscores, spaces, or uppercase. Validate and normalize on input.
- **Tag filtering**: Support both AND (must have all tags) and OR (any tag matches) via query parameter.
- **Auth0**: Developer (you) creates Auth0 tenant and configures it. End users just see a login form - they don't know Auth0 exists. Agent should ask for domain/audience/client-id before implementing auth.
- **API Tokens**: Users can generate Personal Access Tokens (PATs) for CLI/MCP/scripts. PATs are separate from Auth0 - stored hashed in our database. API accepts both Auth0 JWTs (web UI) and PATs (programmatic access).

---

## Documentation to Read Before Implementing

The agent should read/reference these docs before starting each relevant milestone:

- **FastAPI**: https://fastapi.tiangolo.com/
- **SQLAlchemy 2.0** (async): https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- **Alembic**: https://alembic.sqlalchemy.org/en/latest/
- **Auth0 FastAPI Integration**: https://auth0.com/docs/quickstart/backend/python/interactive
- **pydantic v2**: https://docs.pydantic.dev/latest/
- **httpx** (for URL fetching): https://www.python-httpx.org/
- **BeautifulSoup4** (for HTML parsing): https://www.crummy.com/software/BeautifulSoup/bs4/doc/
- **React**: https://react.dev/
- **React Router**: https://reactrouter.com/
- **Auth0 React SDK**: https://auth0.com/docs/quickstart/spa/react/interactive

---

## Project Structure

Target project structure after Phase 1:

```
bookmarks/
|-- src/
|   |-- api/
|   |   |-- __init__.py
|   |   |-- main.py
|   |   |-- dependencies.py
|   |   |-- routers/
|   |       |-- __init__.py
|   |       |-- bookmarks.py
|   |       |-- tokens.py
|   |       |-- health.py
|   |-- models/
|   |   |-- __init__.py
|   |   |-- base.py
|   |   |-- user.py
|   |   |-- api_token.py
|   |   |-- bookmark.py
|   |-- schemas/
|   |   |-- __init__.py
|   |   |-- bookmark.py
|   |   |-- token.py
|   |   |-- user.py
|   |-- services/
|   |   |-- __init__.py
|   |   |-- bookmark_service.py
|   |   |-- url_fetcher.py
|   |-- db/
|   |   |-- __init__.py
|   |   |-- session.py
|   |   |-- migrations/
|   |-- core/
|       |-- __init__.py
|       |-- config.py
|       |-- auth.py
|-- frontend/
|   |-- src/
|   |   |-- components/
|   |   |-- pages/
|   |   |-- hooks/
|   |   |-- services/
|   |   |-- App.tsx
|   |-- package.json
|   |-- vite.config.ts
|-- tests/
|   |-- conftest.py
|   |-- api/
|   |   |-- test_bookmarks.py
|   |   |-- test_tokens.py
|   |-- services/
|   |   |-- test_bookmark_service.py
|   |   |-- test_url_fetcher.py
|   |-- integration/
|       |-- test_bookmark_flow.py
|-- alembic.ini
|-- docker-compose.yml
|-- pyproject.toml
```

---

## Milestones

### Milestone 1: Project Foundation & Database Setup

**Goal**: Set up FastAPI application structure, PostgreSQL connection, and Alembic migrations.

**Dependencies**: None (starting point)

**Success Criteria**:
- FastAPI app runs and responds to health check endpoint
- PostgreSQL connection works (via docker-compose)
- Alembic is configured and can run migrations
- Tests pass for database connection and health endpoint

**Key Changes**:

1. **Add dependencies** via uv:
   ```bash
   uv add fastapi "uvicorn[standard]" "sqlalchemy[asyncio]" asyncpg alembic pydantic pydantic-settings
   ```

2. **Create `.env.example`** (committed to repo) and `.env` (gitignored) for local dev:
   ```bash
   # .env.example
   POSTGRES_USER=bookmarks
   POSTGRES_PASSWORD=bookmarks
   POSTGRES_DB=bookmarks
   DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:5432/${POSTGRES_DB}
   DEV_MODE=true  # Set to true for local dev (bypasses auth). Omit in production.
   ```

3. **Update `docker-compose.yml`** - Add PostgreSQL service using env vars:
   ```yaml
   services:
     db:
       image: postgres:16
       environment:
         - POSTGRES_USER=${POSTGRES_USER}
         - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
         - POSTGRES_DB=${POSTGRES_DB}
       ports:
         - "5432:5432"
       volumes:
         - postgres_data:/var/lib/postgresql/data

   volumes:
     postgres_data:
   ```

   Note: docker-compose auto-loads `.env` for variable substitution. Railway/Render inject env vars at runtime via their dashboards.

4. **Create `src/core/config.py`** - Configuration using pydantic-settings:
   ```python
   class Settings(BaseSettings):
       database_url: str
       dev_mode: bool = False  # Auth bypass for local dev
       # ... other settings
   ```

5. **Create `src/db/session.py`** - Async SQLAlchemy session factory

6. **Create `src/models/base.py`** - SQLAlchemy declarative base with common mixins (id, created_at, updated_at)

7. **Create `src/api/main.py`** - FastAPI app with health endpoint

8. **Configure Alembic** - Initialize with async support

**Testing Strategy**:
- Test database connection with a simple query
- Test health endpoint returns 200
- Test Alembic can generate and run migrations

**Risk Factors**:
- Async SQLAlchemy setup can be tricky - ensure proper session lifecycle
- Alembic async configuration requires specific setup

---

### Milestone 2: User Model & Auth0 Integration

**Goal**: Implement Auth0 JWT validation and user model. Users are created/updated on first authenticated request.

**Dependencies**: Milestone 1

**Prerequisites - Auth0 Setup (User Must Complete First)**:

Before implementing this milestone, the user must set up Auth0 and provide configuration values.

#### Step 1: Create an Auth0 Account
1. Go to [auth0.com/signup](https://auth0.com/signup) and create a free account
2. A tenant will be created automatically (e.g., `your-name.auth0.com`)

#### Step 2: Create an API (for the FastAPI backend)
1. In Auth0 Dashboard, go to **Applications → APIs**
2. Click **+ Create API**
3. Fill in:
   - **Name**: `Bookmarks API`
   - **Identifier** (audience): `https://bookmarks-api` (can be any unique string)
   - **Signing Algorithm**: `RS256` (default)
4. Click **Create**

#### Step 3: Create a Single Page Application (for the React frontend)
1. Go to **Applications → Applications**
2. Click **+ Create Application**
3. Fill in:
   - **Name**: `Bookmarks Web`
   - **Application Type**: **Single Page Web Applications**
4. Click **Create**
5. Go to **Settings** tab and configure URLs (for local dev):

| Setting | Value |
|---------|-------|
| Allowed Callback URLs | `http://localhost:5173` |
| Allowed Logout URLs | `http://localhost:5173` |
| Allowed Web Origins | `http://localhost:5173` |

6. Under **Advanced Settings → OAuth**, verify:
   - JsonWebToken Signature Algorithm: `RS256`
   - OIDC Conformant: Enabled
7. Click **Save Changes**

#### Step 4: Provide These Values to the Agent

Once you have these values, share them so the agent can update `.env.example` and implement auth:

```
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_AUDIENCE=https://bookmarks-api
AUTH0_CLIENT_ID=<from SPA Settings tab>
```

The agent will add these to `.env.example` (and you'll copy to your `.env`):
```bash
# Auth0 Configuration
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_AUDIENCE=https://bookmarks-api
AUTH0_CLIENT_ID=your-client-id

# Development Mode
# DEV_MODE=true   → Bypasses auth, uses fake user (quick local dev)
# DEV_MODE=false  → Real Auth0 authentication (test actual login flow)
DEV_MODE=true
```

#### Best Practices (from Auth0 docs):
- Never commit secrets - `.env` is gitignored
- Use RS256 (default) - asymmetric signing is more secure
- Keep access token lifetime short - default 7200s (2 hours) is fine
- PKCE is automatic - React SDK uses Authorization Code Flow with PKCE

#### References:
- [Build and Secure FastAPI Server with Auth0](https://auth0.com/blog/build-and-secure-fastapi-server-with-auth0/)
- [Auth0 React SDK Quickstart](https://auth0.com/docs/quickstart/spa/react)
- [auth0-fastapi-api GitHub](https://github.com/auth0/auth0-fastapi-api)
- [Auth0 React SDK GitHub](https://github.com/auth0/auth0-react)

---

**Success Criteria**:
- Auth0 JWT tokens are validated on protected endpoints
- User record created/updated from Auth0 claims on authenticated requests
- Unauthenticated requests to protected endpoints return 401
- Tests cover auth flow with mocked JWTs

**Key Changes**:

1. **Create `src/models/user.py`**:
   ```python
   class User(Base):
       __tablename__ = "users"

       id: Mapped[int] = mapped_column(primary_key=True)
       auth0_id: Mapped[str] = mapped_column(unique=True, index=True)  # "sub" claim
       email: Mapped[str | None]
       created_at: Mapped[datetime]
       updated_at: Mapped[datetime]
   ```

2. **Create `src/core/auth.py`**:
   - JWT validation using Auth0's JWKS endpoint
   - `get_current_user` dependency that validates token and returns/creates User
   - Consider using `python-jose` or `authlib` for JWT handling
   - **Dev mode bypass**: When `DEV_MODE=true`, skip auth and return a test user:
     ```python
     async def get_current_user(...) -> User:
         if settings.dev_mode:
             return await get_or_create_dev_user(db)
         # Real auth validation...
     ```

3. **Create `src/api/dependencies.py`**:
   - `get_db` - yields database session
   - `get_current_user` - validates JWT and returns User model

4. **Add migration** for users table

**Testing Strategy**:
- Mock JWT validation for unit tests (don't hit Auth0 in tests)
- Test valid token returns user
- Test expired/invalid token returns 401
- Test user is created on first request, updated on subsequent
- Test missing Authorization header returns 401

**Implementation Notes**:
- Store only `auth0_id` (the "sub" claim) - don't duplicate Auth0's user management
- The User model is primarily for foreign key relationships and storing app-specific user data later (e.g., API keys, preferences)

**Risk Factors**:
- JWT validation setup varies by Auth0 configuration (RS256 vs HS256, audience, issuer)
- Agent should confirm Auth0 tenant details before implementing

---

### Milestone 2.5: Personal Access Tokens (PATs)

**Goal**: Allow users to create API tokens for programmatic access (CLI, MCP, scripts). API should accept both Auth0 JWTs and PATs.

**Dependencies**: Milestone 2

**Success Criteria**:
- User can create/list/revoke API tokens via authenticated endpoints
- API accepts both Auth0 JWTs and PATs in `Authorization: Bearer <token>` header
- PATs are stored hashed (never store plaintext)
- Token is shown only once at creation time
- Tests cover PAT creation, validation, and revocation

**Key Changes**:

1. **Create `src/models/api_token.py`**:
   ```python
   class ApiToken(Base):
       __tablename__ = "api_tokens"

       id: Mapped[int] = mapped_column(primary_key=True)
       user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
       name: Mapped[str]  # User-provided name, e.g., "CLI", "MCP"
       token_hash: Mapped[str]  # SHA-256 hash of the token
       token_prefix: Mapped[str]  # First 8 chars for identification, e.g., "bm_abc123"
       created_at: Mapped[datetime]
       last_used_at: Mapped[datetime | None]
       expires_at: Mapped[datetime | None]  # Optional expiration

       user: Mapped["User"] = relationship(back_populates="api_tokens")
   ```

2. **Update `src/core/auth.py`** to handle both token types:
   ```python
   async def get_current_user(token: str, db: AsyncSession) -> User:
       if token.startswith("bm_"):
           # Personal Access Token - validate against DB
           return await validate_pat(token, db)
       else:
           # JWT from Auth0
           return await validate_jwt(token, db)
   ```

3. **Create `src/api/routers/tokens.py`**:
   ```python
   @router.post("/", response_model=TokenCreateResponse)  # Returns plaintext token ONCE
   @router.get("/", response_model=list[TokenListResponse])  # List tokens (no secrets)
   @router.delete("/{token_id}", status_code=204)  # Revoke token
   ```

4. **Token generation**:
   ```python
   import secrets

   def generate_token() -> tuple[str, str]:
       """Returns (plaintext_token, hashed_token)"""
       raw = secrets.token_urlsafe(32)
       plaintext = f"bm_{raw}"  # Prefix for easy identification
       hashed = hashlib.sha256(plaintext.encode()).hexdigest()
       return plaintext, hashed
   ```

5. **Add migration** for api_tokens table

**Testing Strategy**:
- Test token creation returns plaintext token
- Test token validation with valid PAT returns user
- Test token validation with invalid/revoked PAT returns 401
- Test Auth0 JWT still works (regression)
- Test token hash is stored, not plaintext
- Test last_used_at is updated on use
- Test expired tokens are rejected

**Implementation Notes**:
- Token prefix `bm_` makes it easy to identify token type and helps users know which service the token belongs to
- Store only the hash - if DB is compromised, tokens can't be used
- Show plaintext only at creation - user must copy it then
- Consider rate limiting token creation

**Risk Factors**:
- Must ensure constant-time comparison for token validation to prevent timing attacks
- Token rotation/expiration policy TBD

---

### Milestone 3: Bookmark Model & CRUD API

**Goal**: Implement Bookmark model and REST API endpoints for create, read, update, delete operations.

**Dependencies**: Milestone 2

**Success Criteria**:
- All CRUD operations work via API
- Bookmarks are scoped to authenticated user (multi-tenant)
- Proper validation on inputs (URL format, tag format, etc.)
- Tests cover all endpoints and edge cases

**Key Changes**:

1. **Create `src/models/bookmark.py`**:
   ```python
   class Bookmark(Base):
       __tablename__ = "bookmarks"

       id: Mapped[int] = mapped_column(primary_key=True)
       user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
       url: Mapped[str]
       title: Mapped[str | None]
       description: Mapped[str | None]
       summary: Mapped[str | None]   # AI-generated summary (Phase 2)
       content: Mapped[str | None]   # Full page content (optional)
       tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
       created_at: Mapped[datetime]
       updated_at: Mapped[datetime]

       user: Mapped["User"] = relationship(back_populates="bookmarks")
   ```

2. **Create `src/schemas/bookmark.py`** - Pydantic models:
   ```python
   class BookmarkCreate(BaseModel):
       url: HttpUrl
       title: str | None = None
       description: str | None = None
       content: str | None = None      # User-provided content (e.g., paywalled)
       tags: list[str] = []
       store_content: bool = True      # Whether to persist scraped content

       @field_validator("tags", mode="before")
       @classmethod
       def normalize_tags(cls, v: list[str]) -> list[str]:
           """Normalize tags: lowercase, validate format (alphanumeric + hyphens only)."""
           normalized = []
           for tag in v:
               tag = tag.lower().strip()
               if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", tag):
                   raise ValueError(f"Invalid tag format: {tag}. Use lowercase letters, numbers, and hyphens only.")
               normalized.append(tag)
           return normalized

   class BookmarkUpdate(BaseModel):
       title: str | None = None
       description: str | None = None
       content: str | None = None
       tags: list[str] | None = None
       # Same tag validator as BookmarkCreate

   class BookmarkResponse(BaseModel):
       id: int
       url: str
       title: str | None
       description: str | None
       summary: str | None             # AI-generated (Phase 2)
       tags: list[str]
       created_at: datetime
       updated_at: datetime
   ```

3. **Create `src/services/bookmark_service.py`**:
   - `create_bookmark(user_id, data)`
   - `get_bookmark(user_id, bookmark_id)` - returns None if not found or wrong user
   - `get_bookmarks(user_id, ...)` - with pagination
   - `update_bookmark(user_id, bookmark_id, data)`
   - `delete_bookmark(user_id, bookmark_id)`

4. **Create `src/api/routers/bookmarks.py`**:
   ```python
   @router.post("/", response_model=BookmarkResponse, status_code=201)
   @router.get("/", response_model=list[BookmarkResponse])
   @router.get("/{bookmark_id}", response_model=BookmarkResponse)
   @router.patch("/{bookmark_id}", response_model=BookmarkResponse)
   @router.delete("/{bookmark_id}", status_code=204)
   ```

5. **Add migration** for bookmarks table

**Testing Strategy**:
- Test each CRUD operation independently
- Test user isolation (user A cannot see/modify user B's bookmarks)
- Test validation errors (invalid URL, empty required fields)
- Test tag validation:
  - Valid: `machine-learning`, `how-to`, `react`, `web-dev-2024`
  - Invalid: `Machine-Learning` (uppercase), `how_to` (underscore), `my tag` (space), `@special!` (special chars)
  - Auto-normalization: input `"React"` → stored as `"react"`
- Test 404 on non-existent bookmark
- Test pagination

**Risk Factors**:
- PostgreSQL ARRAY type for tags - ensure proper indexing for search later (GIN index added in Milestone 5)

---

### Milestone 4: URL Scraping & Metadata Extraction

**Goal**: Scrape URLs to extract title, description, and content when creating bookmarks. Also add `summary` field to model for future AI summaries.

**Dependencies**: Milestone 3

**Success Criteria**:
- When creating a bookmark, scrape URL unless content is user-provided
- Extract title and description from HTML (user values take precedence)
- Extract main page content using trafilatura
- Content storage is controlled by `store_content` flag (default: true)
- Fetching is best-effort - failures don't block bookmark creation
- Tests cover success, failure, and timeout scenarios

**Key Changes**:

1. **Add dependencies** via uv:
   ```bash
   uv add httpx beautifulsoup4 lxml trafilatura
   ```

2. **Add migration** for `summary` field on bookmarks table:
   ```python
   # Add summary column (nullable text) for AI-generated summaries (Phase 2)
   op.add_column('bookmarks', sa.Column('summary', sa.Text(), nullable=True))
   ```

3. **Update `src/models/bookmark.py`** - Add summary field:
   ```python
   summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # AI-generated (Phase 2)
   ```

4. **Update `src/schemas/bookmark.py`** - Add store_content and summary:
   ```python
   class BookmarkCreate(BaseModel):
       url: HttpUrl
       title: str | None = None
       description: str | None = None
       content: str | None = None      # User-provided content (e.g., paywalled)
       tags: list[str] = []
       store_content: bool = True      # Whether to persist scraped content

   class BookmarkResponse(BaseModel):
       # ... existing fields ...
       summary: str | None             # AI-generated (Phase 2)
   ```

5. **Create `src/services/url_scraper.py`** - Three-layer architecture:

   ```python
   @dataclass
   class FetchResult:
       html: str | None
       final_url: str          # After redirects
       status_code: int | None
       content_type: str | None
       error: str | None       # Error message if fetch failed

   @dataclass
   class ExtractedMetadata:
       title: str | None
       description: str | None

   async def fetch_url(url: str, timeout: float = 10.0) -> FetchResult:
       """
       Fetches raw HTML from URL. Best-effort - returns error info on failure.
       Uses httpx async client with reasonable User-Agent header.
       """

   def extract_metadata(html: str) -> ExtractedMetadata:
       """
       Extracts title and description from HTML using BeautifulSoup.
       Pure function, no I/O.

       Title extraction priority:
       1. <title> tag
       2. <meta property="og:title">
       3. <meta name="twitter:title">

       Description extraction priority:
       1. <meta name="description">
       2. <meta property="og:description">
       3. <meta name="twitter:description">
       """

   def extract_content(html: str) -> str | None:
       """
       Extracts main readable content from HTML using trafilatura.
       Pure function, no I/O. Returns plain text.
       """
   ```

6. **Update `src/services/bookmark_service.py`** - Integrate scraping:
   ```python
   async def create_bookmark(
       session: AsyncSession,
       user_id: int,
       data: BookmarkCreate,
   ) -> Bookmark:
       """
       Creates a bookmark with automatic URL scraping.

       Flow:
       1. If content not provided by user, fetch URL and extract content
       2. Extract metadata (title, description) from HTML
       3. Use user-provided values if given, else use extracted values
       4. Store content only if store_content=True
       5. Return the created bookmark
       """
   ```

**Bookmark Creation Flow**:
```
Input: url, optional title/description/content/tags, store_content flag

1. Determine if we need to fetch:
   - Skip fetch ONLY if user provided ALL of: title, description, AND content
   - Otherwise, fetch URL to get HTML for metadata and/or content extraction

2. If fetching:
   a. fetch_url(url) → get raw HTML
   b. extract_metadata(html) → get title, description
   c. If user did NOT provide content: extract_content(html) → get main text

3. Merge values (user takes precedence):
   - title = user_title or extracted_title
   - description = user_description or extracted_description
   - content = user_content or (extracted_content if store_content else None)

4. Create and return bookmark

Note: Fetch failures are non-blocking - bookmark is created with whatever values are available.
```

**Behavior Clarifications**:
- `store_content=False`: Still fetches and extracts title/description, just doesn't persist content
- User-provided content (e.g., paywalled copy/paste): Still fetch URL for metadata extraction, but use user's content
- Fetch timeout: 10 seconds, single attempt (no retries for MVP)
- User-Agent: Browser-like, e.g., `Mozilla/5.0 (compatible; Bookmarks/1.0)`

**Dependency Notes**:
- Move `httpx` from dev dependencies to main dependencies (URL scraping is a production feature)
- CORS configuration deferred to Milestone 6 (frontend setup)

**Testing Strategy**:
- Test with mock HTTP responses (don't hit real URLs in tests)
- Test `fetch_url`:
  - Successful fetch returns HTML
  - Timeout returns error
  - Non-HTML content type handled gracefully
  - Redirects followed, final URL captured
  - Connection errors return error info
- Test `extract_metadata`:
  - Extracts `<title>` tag
  - Falls back to og:title, twitter:title
  - Extracts meta description with fallbacks
  - Handles missing tags gracefully
  - Returns None for malformed HTML
- Test `extract_content`:
  - Returns readable text from article pages
  - Strips navigation, scripts, styles
  - Returns None for non-article content
- Test bookmark creation integration:
  - Auto-fetches when content not provided
  - User values override extracted values
  - store_content=false skips content storage
  - Fetch failures don't block creation
- Test encoding issues (UTF-8, ISO-8859-1, etc.)
- **Golden file / snapshot tests** for extraction regression detection:
  - Store realistic HTML pages in `tests/artifacts/html/` (e.g., `article_example.html`)
  - Run extraction and save output to `tests/artifacts/extracted/` (e.g., `article_example_metadata.json`, `article_example_content.txt`)
  - Test performs basic assertions but primary purpose is generating output files
  - Changes to extraction logic show up as git diffs in output files for review
  - Include 2-3 diverse page types: article/blog, documentation, product page

**Risk Factors**:
- Some sites block scrapers - use reasonable User-Agent header
- trafilatura may not extract well from all page types - acceptable for MVP
- Paywalled content will fail - user can paste content manually

**Deferred**:
- `POST /bookmarks/{id}/fetch-metadata` endpoint - will add when requirements for re-fetching are clearer (e.g., AI summary flow)

---

### Milestone 5: Search & Filtering

**Goal**: Implement text search across bookmarks and add tag filtering with sorting.

**Dependencies**: Milestone 4

**Success Criteria**:
- Search by query string matches title, description, url, summary, content
- Filter bookmarks by one or more tags (AND/OR modes)
- Sort by created_at, title (asc/desc)
- Pagination works with search/filter/sort
- Tests cover search relevance and edge cases

**Key Changes**:

1. **Update `src/services/bookmark_service.py`**:
   ```python
   async def search_bookmarks(
       db: AsyncSession,
       user_id: int,
       query: str | None = None,
       tags: list[str] | None = None,
       tag_match: Literal["all", "any"] = "all",  # AND vs OR
       sort_by: Literal["created_at", "title"] = "created_at",
       sort_order: Literal["asc", "desc"] = "desc",
       offset: int = 0,
       limit: int = 50,
   ) -> tuple[list[Bookmark], int]:  # Returns (bookmarks, total_count)
   ```

2. **Update `src/api/routers/bookmarks.py`**:
   ```python
   @router.get("/")
   async def list_bookmarks(
       q: str | None = None,
       tags: list[str] = Query(default=[]),
       tag_match: Literal["all", "any"] = "all",
       sort_by: Literal["created_at", "title"] = "created_at",
       sort_order: Literal["asc", "desc"] = "desc",
       offset: int = 0,
       limit: int = Query(default=50, le=100),
       ...
   )
   ```

3. **Add database indexes** (migration):
   - GIN index on tags array for fast containment queries (`@>` and `&&` operators)

**Implementation Notes**:

1. **Text search fields** (using ILIKE):
   - title, description, url, summary, content
   - Tags are NOT included in text search - use the dedicated `tags` filter parameter instead

2. **ILIKE special character escaping**:
   - User query may contain `%`, `_`, or `\` which have special meaning in ILIKE
   - Escape these before building the query:
     ```python
     def escape_ilike(value: str) -> str:
         """Escape special ILIKE characters."""
         return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
     ```

3. **Tag filtering**:
   - `tags=[]` or not provided → no tag filter, return all bookmarks
   - `tags=["python"]` → filter to bookmarks with "python" tag
   - `tag_match="all"` (AND): `WHERE tags @> ARRAY['tag1', 'tag2']` (must have all tags)
   - `tag_match="any"` (OR): `WHERE tags && ARRAY['tag1', 'tag2']` (has any of the tags)
   - **Normalize tag input**: Convert to lowercase before querying (reuse `validate_and_normalize_tags()` from schemas)

4. **Performance notes**:
   - ILIKE with leading wildcard (`%query%`) cannot use B-tree indexes
   - ILIKE on large content fields may be slow
   - Acceptable for MVP with small datasets (hundreds to low thousands of bookmarks)
   - Future optimization: PostgreSQL full-text search (tsvector) with GIN index

**Testing Strategy**:
- Test search finds bookmarks by title, description, url, summary, content
- Test search is case-insensitive
- Test search with special characters (`%`, `_`, `\`) is properly escaped
- Test tag filtering with `tag_match="all"` (AND behavior)
- Test tag filtering with `tag_match="any"` (OR behavior)
- Test tag filtering with empty tags returns all bookmarks
- Test tag filter input is normalized (case-insensitive)
- Test combining search + tag filter
- Test sorting by created_at and title (verify order)
- Test pagination with search results
- Test empty results
- Test total_count is accurate with filters applied

**Risk Factors**:
- Full-text search can get complex - ILIKE is fine for MVP, can upgrade to tsvector later
- Content search on large text may be slow - acceptable for personal use scale

---

### Milestone 6: React Frontend Setup

**Goal**: Set up React frontend with Vite, routing, and Auth0 integration.

**Dependencies**: Milestone 2 (Auth0 backend must be working)

**Success Criteria**:
- React app builds and runs
- Auth0 login/logout works
- Authenticated API calls work from frontend
- Protected routes redirect to login
- Basic layout/navigation in place

**Key Changes**:

1. **Initialize frontend** in `frontend/` directory:
   ```bash
   npm create vite@latest frontend -- --template react-ts
   ```

2. **Add dependencies**:
   ```json
   {
     "dependencies": {
       "@auth0/auth0-react": "^2.x",
       "react-router-dom": "^6.x",
       "axios": "^1.x"  // or use fetch
     }
   }
   ```

3. **Create `frontend/src/services/api.ts`**:
   - Axios instance with base URL
   - Interceptor to add Auth0 access token to requests
   ```typescript
   const api = axios.create({ baseURL: import.meta.env.VITE_API_URL });

   // Add auth token interceptor
   api.interceptors.request.use(async (config) => {
     const token = await getAccessTokenSilently();
     config.headers.Authorization = `Bearer ${token}`;
     return config;
   });
   ```

4. **Create routing structure**:
   - `/` - Home/dashboard (protected)
   - `/login` - Login page
   - `/callback` - Auth0 callback handler

5. **Create basic components**:
   - `Layout.tsx` - Header with nav and logout button
   - `ProtectedRoute.tsx` - Wrapper that redirects to login if not authenticated

6. **Update `docker-compose.yml`** or add dev script to run frontend

**Testing Strategy**:
- Manual testing for Auth0 flow (hard to automate OAuth)
- Verify access token is attached to API requests
- Verify protected routes redirect when not logged in
- Verify logout clears session

**Implementation Notes**:
- Use Tailwind CSS for styling - simple, minimal, clean, modern
- API URL should be configurable via environment variable

**Risk Factors**:
- Auth0 SPA configuration must match backend (audience, domain)
- CORS must be configured on backend to allow frontend origin

---

### Milestone 7: Bookmark UI

**Goal**: Implement the full bookmark management UI - list, add, edit, delete, search, filter.

**Dependencies**: Milestones 5 and 6

**Success Criteria**:
- User can view list of bookmarks
- User can add a bookmark (URL, optional title/description/tags)
- Auto-fetch populates title/description when URL is entered
- User can edit a bookmark
- User can delete a bookmark
- User can search bookmarks
- User can filter by tags
- User can sort bookmarks
- UI is clean and functional (doesn't need to be fancy)

**Key Changes**:

1. **Create `frontend/src/pages/BookmarkList.tsx`**:
   - Fetches and displays bookmarks
   - Search input
   - Tag filter (chips or multi-select)
   - Sort controls
   - Pagination or infinite scroll

2. **Create `frontend/src/components/BookmarkCard.tsx`**:
   - Displays single bookmark (title, URL, tags, description preview)
   - Edit and delete buttons
   - Click to open URL in new tab

3. **Create `frontend/src/components/BookmarkForm.tsx`**:
   - Form for adding/editing bookmark
   - URL input with auto-fetch trigger
   - Title, description, tags inputs
   - Tag input could be simple comma-separated or a tag picker

4. **Create `frontend/src/hooks/useBookmarks.ts`**:
   - Custom hook for bookmark CRUD operations
   - Handles loading states, errors
   - Caches/manages bookmark list state

5. **Create modal or separate page** for add/edit forms

**Testing Strategy**:
- Manual testing is primary for UI
- Consider adding a few React component tests for critical components
- Test form validation (URL format)
- Test error states (API failures)
- Test empty states (no bookmarks yet)

**UI/UX Notes**:
- Keep it simple and clean
- Show loading states
- Show error messages clearly
- Confirm before delete
- Tags should be easy to add (consider autocomplete from existing tags in future)

**Risk Factors**:
- Scope creep on UI polish - keep it minimal for MVP
- Tag input UX can get complex - start simple (comma-separated)

---

## Post-MVP: Phase 2+ Planning

After Phase 1 is complete and reviewed, create a new implementation plan for Phase 2:

- AI-powered auto-tagging (using sik-llms)
- Semantic search with embeddings (pgvector)
- Notes on bookmarks
- Recently accessed tracking

Each phase should follow the same milestone structure.

---

## General Guidelines for the Agent

1. **Read documentation first** - Before implementing each milestone, read the relevant documentation linked above.

2. **Ask questions** - If requirements are ambiguous, ask for clarification rather than assuming.

3. **Complete milestones fully** - Each milestone should include:
   - Implementation
   - Tests (unit + integration where appropriate)
   - Any necessary documentation updates

4. **Stop for review** - After each milestone, stop and wait for human review before proceeding.

5. **Test-driven where practical** - Write tests alongside implementation, especially for services and API endpoints.

6. **Keep it simple** - Don't over-engineer. MVP first, iterate later.

7. **Multi-tenant always** - Every query must filter by `user_id`. Never expose one user's data to another.

8. **Error handling** - Handle errors gracefully, return appropriate HTTP status codes, log errors for debugging.

9. **Type hints everywhere** - All functions should have type hints, including tests.

10. **No backwards compatibility** - This is a new project. Use best practices, don't worry about legacy patterns.
